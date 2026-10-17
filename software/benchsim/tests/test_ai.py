import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchsim.ai import llm as L
from benchsim.ai import pipeline
from benchsim.ai.__main__ import main as ai_main
from benchsim.process import steps as S

EXAMPLE = Path(pipeline.__file__).parent / 'examples' / 'elephant_toothpaste.txt'
TEXT = EXAMPLE.read_text()


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    """the real API is never called from tests"""
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False); monkeypatch.delenv('ANTHROPIC_AUTH_TOKEN', raising=False)
    monkeypatch.delenv('BENCHSIM_LLM_MODEL', raising=False)


class FakeLLM:
    model = 'fake-model'

    def __init__(self, reply=None, error=None):
        self.reply = reply; self.error = error; self.calls = []

    def complete_json(self, system, user, schema):
        self.calls.append(dict(system=system, user=user, schema=schema))
        if self.error: raise self.error
        return self.reply


def demo_reply(mutate=None):
    d = dict(steps=[s.to_dict() for s in pipeline.preset_steps()], notes='as written')
    if mutate: mutate(d)
    return json.dumps(d)


def closed_objects(schema):
    """every object node in the schema has additionalProperties false"""
    if isinstance(schema, dict):
        if schema.get('type') == 'object' and schema.get('additionalProperties') is not False: return False
        return all(closed_objects(v) for v in schema.values())
    if isinstance(schema, list): return all(closed_objects(v) for v in schema)
    return True


def test_vocabulary_matches_the_steps_module():
    assert set(pipeline.PARAMS) == set(S.STEP_TYPES)
    for st in S.demo_protocol():
        assert set(st.params) <= set(pipeline.PARAMS[st.type])
        assert all(pipeline._json_type_ok(v, pipeline.PARAMS[st.type][k]) for k, v in st.params.items())
    sch = pipeline.step_schema()
    assert closed_objects(sch)
    assert {b['properties']['type']['enum'][0] for b in sch['properties']['steps']['items']['anyOf']} == set(S.STEP_TYPES)


def test_good_proposal_validates_and_is_approved():
    fake = FakeLLM(demo_reply())
    res = pipeline.run(TEXT, llm=fake, approver=pipeline.AutoApprover())
    steps, validation, approval = res
    assert res.proposal.source == 'llm' and res.proposal.model == 'fake-model' and res.proposal.fallback_reason is None
    assert validation == dict(ok=True, problems=[])
    assert approval['approved'] and approval['approved_by'] == 'test' and approval['plan_sha256'] == pipeline.plan_sha256(steps)
    assert [s.to_dict() for s in steps] == [s.to_dict() for s in pipeline.preset_steps()]
    call = fake.calls[0]
    assert TEXT.strip() in call['user'] and call['schema'] == pipeline.step_schema() and 'POUR_TO_SCALE' in call['system']
    args = res.runlog_args()
    assert args['source'] == 'llm' and args['approved_by'] == 'test' and args['text'] == TEXT


def test_changed_amount_is_kept():
    def less_developer(d): d['steps'][1]['params']['target_g'] = 35.0
    res = pipeline.run(TEXT, llm=FakeLLM(demo_reply(less_developer)), approver=pipeline.AutoApprover())
    assert res.proposal.source == 'llm' and res.validation['ok'] and res.approved
    assert res.steps[1].params['target_g'] == 35.0


def test_malformed_reply_falls_back_to_preset():
    res = pipeline.run(TEXT, llm=FakeLLM('Sure! Here is the plan: {"steps": ['), approver=pipeline.AutoApprover())
    assert res.proposal.source == 'preset' and 'did not parse' in res.proposal.fallback_reason
    assert res.proposal.raw.startswith('Sure!') and res.proposal.rejected
    assert res.validation['ok'] and res.approved
    assert [s.to_dict() for s in res.steps] == [s.to_dict() for s in pipeline.preset_steps()]
    # without the fallback nothing is left to run, and nothing can be approved
    res = pipeline.run(TEXT, llm=FakeLLM('not json'), approver=pipeline.AutoApprover(), fallback=None)
    assert res.proposal.source == 'none' and res.steps == [] and not res.validation['ok'] and not res.approved


def test_out_of_range_target_is_never_approvable():
    def too_much(d): d['steps'][1]['params']['target_g'] = 500.0
    reply = demo_reply(too_much)
    res = pipeline.run(TEXT, llm=FakeLLM(reply), approver=pipeline.AutoApprover())
    assert res.proposal.source == 'llm'                                 # a valid-shaped proposal is shown, not replaced
    assert not res.validation['ok'] and any('outside 1..60' in p for p in res.validation['problems'])
    assert not res.approved and res.approval['approved_by'] is None
    # the interactive approver does not even ask
    asked = []
    res = pipeline.run(TEXT, llm=FakeLLM(reply), approver=pipeline.InteractiveApprover(input_fn=lambda q: asked.append(q) or 'approve',
                                                                                      print_fn=lambda *a: None))
    assert not res.approved and asked == [] and res.approval['reason'] == 'validation failed'

    class Rogue(pipeline.Approver):
        name = 'rogue'
        def review(self, rv): return dict(approved=True, approved_by='mallory', operator='mallory', reason='rubber stamp')
    res = pipeline.run(TEXT, llm=FakeLLM(reply), approver=Rogue())
    assert not res.approved and res.approval['approved_by'] is None and 'refused by the pipeline' in res.approval['reason']
    assert res.runlog_args()['approved_by'] is None


@pytest.mark.parametrize('mutate, needle', [
    (lambda d: d['steps'][1]['params'].update(joint_deg=[0, 45, -90, 30, 0]), 'joint_deg'),
    (lambda d: d['steps'][0].update(servo_cmd={'id': 3, 'goal': 2048}), 'servo_cmd'),
    (lambda d: d.update(actuator_commands=['TT 180']), 'actuator_commands'),
    (lambda d: d['steps'][1]['params'].update(target_g='39'), 'target_g must be a number'),
    (lambda d: d['steps'].insert(0, dict(type='MOVE_JOINTS', params=dict(q=[0, 0, 0, 0, 0]), label='x')), "unknown step type 'MOVE_JOINTS'"),
])
def test_fields_outside_the_vocabulary_are_rejected(mutate, needle):
    reply = demo_reply(mutate)
    res = pipeline.run(TEXT, llm=FakeLLM(reply), approver=pipeline.AutoApprover())
    assert res.proposal.source == 'preset' and res.proposal.raw == reply
    assert any(needle in p for p in res.proposal.rejected), res.proposal.rejected
    assert 'reply rejected' in res.proposal.fallback_reason
    assert all(set(s.params) <= set(pipeline.PARAMS[s.type]) for s in res.steps)
    res = pipeline.run(TEXT, llm=FakeLLM(reply), approver=pipeline.AutoApprover(), fallback=None)
    assert res.steps == [] and not res.approved


def test_unavailable_model_falls_back_to_preset():
    res = pipeline.run(TEXT, llm=FakeLLM(error=L.LLMUnavailable('network unavailable')), approver=pipeline.AutoApprover())
    assert res.proposal.source == 'preset' and 'network unavailable' in res.proposal.fallback_reason and res.approved
    res = pipeline.run(TEXT, llm=None, approver=pipeline.AutoApprover())
    assert res.proposal.source == 'preset' and 'preset requested' in res.proposal.fallback_reason and res.approved
    # with no credentials the SDK wrapper refuses before any request
    assert not L.available()[0]
    res = pipeline.run(TEXT, llm=L.AnthropicLLM(), approver=pipeline.AutoApprover())
    assert res.proposal.source == 'preset' and 'unavailable' in res.proposal.fallback_reason


def test_interactive_approver_requires_typing_approve():
    def approve_with(*answers):
        it = iter(answers); shown = []
        def inp(q):
            try: return next(it)
            except StopIteration: raise EOFError
        res = pipeline.run(TEXT, llm=None, approver=pipeline.InteractiveApprover(input_fn=inp, print_fn=lambda *a: shown.append(' '.join(map(str, a)))))
        return res, shown
    res, shown = approve_with('Nick', 'yes')
    assert not res.approved and res.approval['operator'] == 'Nick'
    assert any(ln.startswith('  1. TRANSFER') for ln in shown) and 'VALIDATION: PASSED' in shown
    res, _ = approve_with('Nick', 'approve')
    assert res.approved and res.approval['approved_by'] == 'Nick' and res.approval['approver'] == 'interactive'
    res, _ = approve_with('', 'approve')
    assert not res.approved
    res, _ = approve_with()
    assert not res.approved and res.approval['reason'] == 'no input'


def fake_sdk(reply_text, stop_reason='end_turn', calls=None):
    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(model=kw['model'], stop_reason=stop_reason, stop_details=SimpleNamespace(category='cyber'),
                               content=[SimpleNamespace(type='text', text=reply_text)], usage=SimpleNamespace(input_tokens=10, output_tokens=20),
                               _request_id='req_test')
    ns = SimpleNamespace(create=create)
    return SimpleNamespace(messages=ns, beta=SimpleNamespace(messages=ns))


def test_anthropic_wrapper_request(monkeypatch):
    calls = []
    m = L.AnthropicLLM(client=fake_sdk(demo_reply(), calls=calls))
    assert m.model == 'claude-opus-5-5'
    res = pipeline.run(TEXT, llm=m, approver=pipeline.AutoApprover())
    assert res.proposal.source == 'llm' and res.approved and m.last['request_id'] == 'req_test'
    kw = calls[0]
    assert kw['model'] == 'claude-opus-5-5' and kw['output_config']['format'] == dict(type='json_schema', schema=pipeline.step_schema())
    assert 'tool_choice' not in kw and 'thinking' not in kw and kw['fallbacks'] == 'default' and kw['betas'] == [L.FALLBACK_BETA]
    assert kw['messages'][0]['role'] == 'user' and TEXT.strip() in kw['messages'][0]['content']
    monkeypatch.setenv('BENCHSIM_LLM_MODEL', 'claude-haiku-5-5')
    calls.clear(); m = L.AnthropicLLM(client=fake_sdk('{}', calls=calls))
    m.complete_json('s', 'u', {})
    assert calls[0]['model'] == 'claude-haiku-5-5' and 'fallbacks' not in calls[0]
    with pytest.raises(L.LLMUnavailable, match='declined'):
        L.AnthropicLLM(client=fake_sdk('', stop_reason='refusal', calls=[])).complete_json('s', 'u', {})
    with pytest.raises(L.LLMUnavailable, match='truncated'):
        L.AnthropicLLM(client=fake_sdk('{"steps": [', stop_reason='max_tokens', calls=[])).complete_json('s', 'u', {})


def test_cli_writes_report(tmp_path, capsys):
    out = tmp_path / 'ai.json'
    assert ai_main(['--text', str(EXAMPLE), '--preset', '--approve', '--out', str(out)]) == 0
    r = json.loads(out.read_text())
    assert r['approved'] and r['proposal']['source'] == 'preset' and r['validation']['ok'] and len(r['steps']) == 12
    assert r['approval']['approver'] == 'command line --approve' and r['llm']['status'] == 'not used (--preset)'
    assert 'VALIDATION: PASSED' in capsys.readouterr().out
