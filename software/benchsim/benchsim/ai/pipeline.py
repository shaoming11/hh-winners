"""Protocol text -> proposed steps -> deterministic validation -> operator approval.

The language model only proposes. Its reply must be one JSON object ``{"steps": [...], "notes": "..."}`` whose steps use
the fixed vocabulary of benchsim.process.steps (type, params, label). A reply with any other field, step type or parameter
name, or a parameter of the wrong JSON type, is rejected whole: nothing from it is kept. A proposal that is kept goes
through ``steps.validate``, the only gate, which is imported and not re-implemented here. Only a plan that passes it can be
approved, and only an Approver approves. Nothing here emits actuator commands or joint values or runs anything; the
caller hands ``result.steps`` to the sequencer.

Preset fallback: ``steps.demo_protocol`` with the bench_params.toml [recipe] targets. It is used when no model is
configured, when the SDK, credentials or network are unavailable, when the reply does not parse, or when it is rejected
for leaving the vocabulary. The result records the source and the reason. A proposal that parses but fails validation is
NOT replaced by the preset: the operator sees it with its problems, and it cannot be approved.

    result = run(text, llm=AnthropicLLM(), approver=InteractiveApprover())
    steps, validation, approval = result            # also result.proposal, result.text, result.to_dict()
    runlog.set_protocol(**result.runlog_args())
"""
import hashlib
import json
import math
from dataclasses import dataclass, field

from .. import layout, runlog
from ..process import steps as S
from .llm import LLMUnavailable

# step type -> {param: JSON type}. Mirrors the vocabulary table in benchsim.process.steps (tests check the two agree).
PARAMS = {
    'TRANSFER': dict(beaker='string', src='string', dst='string'),
    'POUR_TO_SCALE': dict(reagent='string', beaker='string', target_g='number', tol_g='number', relative='boolean'),
    'POUR_TO_FUNNEL': dict(beaker='string'),
    'CAROUSEL': dict(beaker='string', station='string'),
    'DOSE_YEAST': dict(beaker='string', target_g='number', tol_g='number', max_topups='integer'),
    'VERIFY_MASS': dict(beaker='string', target_g='number', tol_g='number'),
    'WAIT': dict(seconds='number', reason='string'),
    'STAGE': dict(position='string'),
}
# allowed values offered to the model in the schema; out-of-domain values are still reported by steps.validate
ENUMS = dict(beaker=list(S.CAROUSEL_BEAKERS), reagent=list(S.REAGENTS), src=list(S.STATIONS), dst=list(S.STATIONS),
             station=['pick', 'auger'], position=['WORK', 'ERUPT'])
STEP_FIELDS = ('type', 'params', 'label')
REPLY_FIELDS = ('steps', 'notes')


# ======================================================================= schema and prompt
def step_schema():
    """JSON schema of a model reply (structured outputs): one anyOf branch per step type, every object closed"""
    branches = []
    for t, ps in PARAMS.items():
        props = {k: dict(type=v, **({'enum': ENUMS[k]} if k in ENUMS else {})) for k, v in ps.items()}
        branches.append(dict(type='object', additionalProperties=False, required=list(STEP_FIELDS), properties=dict(
            type=dict(type='string', enum=[t]), label=dict(type='string'),
            params=dict(type='object', additionalProperties=False, required=list(ps), properties=props))))
    return dict(type='object', additionalProperties=False, required=list(REPLY_FIELDS),
                properties=dict(steps=dict(type='array', items=dict(anyOf=branches)), notes=dict(type='string')))


def system_prompt(params=None):
    """bench description, vocabulary, limits and the standard demo as an example; built from the shared constants"""
    demo = [s.to_dict() for s in preset_steps(params)]
    lim = S.LIMITS
    return '\n'.join([
        'You turn a lab protocol written by the operator of the Wet Lab Bench into a plan made only of the bench\'s step vocabulary.',
        'You only propose. A deterministic validator checks the plan and a human operator must approve it before anything moves.',
        '',
        'The bench: two SO-101 arms, a load-cell scale, a 4-pocket carousel, a yeast auger and a slider-crank stage that carries the flask.',
        'Beakers: P1 starts in the carousel pick pocket (empty); P2 starts in another carousel pocket (empty).',
        'Reagent beakers sit in the rack: %s. Pour from them by reagent name.' % ', '.join('%s (rack beaker %s)' % kv for kv in S.REAGENTS.items()),
        'The developer is 12 % hydrogen peroxide (40-volume). The flask is pre-loaded by hand with dish soap and colouring.',
        '',
        'Step vocabulary (type: params):',
        '  TRANSFER: beaker, src, dst - transfer arm moves P1/P2 between carousel_pick and scale_pan',
        '  POUR_TO_SCALE: reagent, beaker, target_g, tol_g, relative - pourer pours a reagent onto the beaker on the scale, closed loop; '
        'relative=true adds target_g on top of the current reading (use it for water onto yeast)',
        '  POUR_TO_FUNNEL: beaker - pourer empties the beaker on the scale into the flask through the funnel',
        '  CAROUSEL: beaker, station - turn the carousel so the beaker\'s pocket is at pick or auger',
        '  DOSE_YEAST: beaker, target_g, tol_g, max_topups - auger doses yeast into a carousel beaker',
        '  VERIFY_MASS: beaker, target_g, tol_g - check the mass of the beaker on the scale',
        '  WAIT: seconds, reason',
        '  STAGE: position - WORK or ERUPT; ERUPT is last and starts the show',
        '',
        'Limits: pours 1-%g g, tolerance at least %g g, a beaker holds at most %g g, yeast 0.5-%g g with at most %d top-ups, waits 0-%g s, '
        'the flask holds at most %g mL.' % (lim['max_pour_g'], lim['min_tol_g'], lim['max_beaker_ml'], lim['max_yeast_g'], lim['max_topups'],
                                            lim['max_wait_s'], lim['max_flask_ml']),
        'Use only these step types and parameters. Never output joint angles, motor or servo commands, coordinates, speeds or any other field.',
        'If the protocol asks for something the vocabulary cannot do, or exceeds a limit, do not invent a step: keep the numbers the operator gave, '
        'and say so in notes. Give each step a short label starting with its demo step number.',
        '',
        'The standard elephant-toothpaste demo, as a plan:',
        json.dumps(dict(steps=demo, notes='standard demo'), indent=None),
    ])


def user_prompt(text):
    return 'Protocol from the operator:\n<protocol>\n%s\n</protocol>\nReturn the plan.' % text.strip()


# ======================================================================= proposal
def preset_steps(params=None):
    return S.demo_protocol(dict(layout.load_params()['recipe'] if params is None else params['recipe']))


def _json_type_ok(v, t):
    if t == 'string': return isinstance(v, str)
    if t == 'boolean': return isinstance(v, bool)
    if t == 'integer': return isinstance(v, int) and not isinstance(v, bool)
    if t == 'number': return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    return False


def check_reply(obj):
    """vocabulary check of a parsed reply -> (steps, problems). Field names, step types and JSON types only; values are
    for steps.validate. Missing parameters are left to steps.validate too (it reports them)."""
    problems = []
    if not isinstance(obj, dict): return [], ['reply is %s, not an object' % type(obj).__name__]
    extra = sorted(set(obj) - set(REPLY_FIELDS))
    if extra: problems.append('reply has fields outside the vocabulary: %s' % ', '.join(extra))
    if not isinstance(obj.get('steps'), list): return [], problems + ['reply has no steps list']
    if not obj['steps']: problems.append('reply proposes no steps')
    if 'notes' in obj and not isinstance(obj['notes'], str): problems.append('notes is not a string')
    out = []
    for i, st in enumerate(obj['steps']):
        tag = 'step %d' % (i + 1)
        if not isinstance(st, dict): problems.append('%s is not an object' % tag); continue
        extra = sorted(set(st) - set(STEP_FIELDS))
        if extra: problems.append('%s has fields outside the vocabulary: %s' % (tag, ', '.join(extra)))
        t = st.get('type')
        if t not in PARAMS: problems.append('%s: unknown step type %r' % (tag, t)); continue
        p = st.get('params', {})
        if not isinstance(p, dict): problems.append('%s: params is not an object' % tag); continue
        extra = sorted(set(p) - set(PARAMS[t]))
        if extra: problems.append('%s (%s): parameters outside the vocabulary: %s' % (tag, t, ', '.join(extra)))
        for k, v in p.items():
            if k in PARAMS[t] and not _json_type_ok(v, PARAMS[t][k]): problems.append('%s (%s): %s must be a %s' % (tag, t, k, PARAMS[t][k]))
        if not isinstance(st.get('label', ''), str): problems.append('%s: label is not a string' % tag)
        out.append(S.Step(t, dict(p), st.get('label', '')))
    return ([] if problems else out), problems


@dataclass
class Proposal:
    source: str                         # 'llm' | 'preset' | 'none'
    steps: list
    notes: str = ''
    model: str = None
    raw: str = None                     # the model's reply text, kept for the record even when rejected
    rejected: list = field(default_factory=list)    # why the model's reply was rejected
    fallback_reason: str = None         # why the preset was used

    def to_dict(self):
        return dict(source=self.source, steps=[s.to_dict() for s in self.steps], notes=self.notes, model=self.model, raw=self.raw,
                    rejected=self.rejected, fallback_reason=self.fallback_reason)


def propose(text, llm=None, fallback='preset', params=None):
    """-> Proposal. ``llm``: an object with ``complete_json(system, user, schema) -> str`` and ``model`` (AnthropicLLM or a
    fake), or None for no model. ``fallback``: 'preset' or None (then an unusable reply leaves the plan empty)."""
    def fall(reason, **kw):
        if fallback == 'preset':
            return Proposal('preset', preset_steps(params), notes='preset demo protocol', fallback_reason=reason, **kw)
        return Proposal('none', [], fallback_reason=reason, **kw)
    if llm is None: return fall('no language model used (preset requested)')
    model = getattr(llm, 'model', None)
    try:
        raw = llm.complete_json(system_prompt(params), user_prompt(text), step_schema())
    except LLMUnavailable as e:
        return fall('language model unavailable: %s' % e, model=model)
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError) as e:
        return fall('reply did not parse as JSON', model=model, raw=raw if isinstance(raw, str) else repr(raw), rejected=['not JSON: %s' % e])
    steps, problems = check_reply(obj)
    if problems: return fall('reply rejected: %s' % '; '.join(problems), model=model, raw=raw, rejected=problems)
    return Proposal('llm', steps, notes=obj.get('notes', ''), model=model, raw=raw)


# ======================================================================= validation and approval
def validation_of(steps, initial=None):
    """steps.validate, the deterministic gate -> dict(ok, problems). An empty plan is not valid."""
    if not steps: return dict(ok=False, problems=['no steps to run'])
    ok, problems = S.validate(steps, initial)
    return dict(ok=bool(ok), problems=list(problems))


def plan_sha256(steps):
    return hashlib.sha256(json.dumps([s.to_dict() for s in steps], sort_keys=True).encode()).hexdigest()


def plan_lines(steps):
    return ['%3d. %-15s %-72s %s' % (i + 1, s.type, ', '.join('%s=%s' % kv for kv in s.params.items()), s.label) for i, s in enumerate(steps)]


def review_lines(rv):
    """what the operator sees: source, numbered plan, validation result"""
    o = ['PROTOCOL SOURCE: %s' % rv['source'] + (' (%s)' % rv['model'] if rv.get('model') and rv['source'] == 'llm' else '')]
    if rv.get('fallback_reason'): o.append('  preset used because: %s' % rv['fallback_reason'])
    if rv.get('notes'): o.append('  notes: %s' % rv['notes'])
    o.append('PLAN (%d steps, sha256 %s):' % (len(rv['steps']), rv['plan_sha256'][:12]))
    o += plan_lines(rv['steps'])
    o.append('VALIDATION: %s' % ('PASSED' if rv['validation']['ok'] else 'FAILED'))
    o += ['  - %s' % p for p in rv['validation']['problems']]
    return o


class Approver:
    """``review(review: dict) -> dict(approved, approved_by, operator, reason)``. ``review`` holds text, source, model,
    fallback_reason, notes, steps (Step list), validation and plan_sha256. The pipeline refuses approval of a plan that
    failed validation whatever an approver returns."""
    name = 'approver'

    def review(self, review):
        raise NotImplementedError


class InteractiveApprover(Approver):
    """shows the numbered plan and the validation result; the operator must type ``approve``. A plan that failed
    validation is shown with its problems and rejected without asking."""
    name = 'interactive'

    def __init__(self, operator=None, input_fn=input, print_fn=print):
        self.operator = operator; self.input = input_fn; self.print = print_fn

    def review(self, rv):
        pr = self.print
        for ln in review_lines(rv): pr(ln)
        if not rv['validation']['ok']:
            pr('This plan failed validation and cannot be approved.')
            return dict(approved=False, approved_by=None, operator=self.operator, reason='validation failed')
        try:
            op = self.operator or self.input('Operator name: ').strip()
            if not op: return dict(approved=False, approved_by=None, operator=None, reason='no operator name given')
            ans = self.input("Type 'approve' to approve this plan (anything else rejects): ").strip()
        except EOFError:
            return dict(approved=False, approved_by=None, operator=self.operator, reason='no input')
        if ans != 'approve': return dict(approved=False, approved_by=None, operator=op, reason='operator did not type approve (%r)' % ans)
        return dict(approved=True, approved_by=op, operator=op, reason='operator typed approve')


class AutoApprover(Approver):
    """for tests only: approves exactly when validation passed"""
    name = 'auto (tests only)'

    def __init__(self, operator='test'):
        self.operator = operator

    def review(self, rv):
        ok = rv['validation']['ok']
        return dict(approved=ok, approved_by=self.operator if ok else None, operator=self.operator,
                    reason='validation passed' if ok else 'validation failed')


class CommandLineApprover(AutoApprover):
    """the operator approved in advance on the command line (``python -m benchsim.ai --approve``); still only for a plan
    that passed validation"""
    name = 'command line --approve'

    def review(self, rv):
        rec = super().review(rv)
        if rec['approved']: rec['reason'] = 'pre-approved with --approve; validation passed'
        return rec


@dataclass
class PipelineResult:
    text: str
    proposal: Proposal
    steps: list
    validation: dict
    approval: dict
    review: dict = None                 # what the approver was shown

    def __iter__(self):
        return iter((self.steps, self.validation, self.approval))

    @property
    def approved(self): return bool(self.approval.get('approved'))

    def runlog_args(self):
        """keyword arguments for RunLog.set_protocol"""
        return dict(source=self.proposal.source, steps=self.steps, validation=self.validation, text=self.text,
                    approved_by=self.approval.get('approved_by') if self.approved else None)

    def to_dict(self):
        return dict(text=self.text, proposal=self.proposal.to_dict(), steps=[s.to_dict() for s in self.steps], validation=self.validation,
                    approval=self.approval)


def run(text, llm=None, approver=None, fallback='preset', initial=None, params=None):
    """propose -> validate -> approve. ``approver`` None means no approval is sought (record says so)."""
    prop = propose(text, llm, fallback, params)
    steps = prop.steps; V = validation_of(steps, initial); sha = plan_sha256(steps)
    rv = dict(text=text, source=prop.source, model=prop.model, fallback_reason=prop.fallback_reason, notes=prop.notes, steps=steps,
              validation=V, plan_sha256=sha)
    rec = dict(approver.review(rv)) if approver is not None else dict(approved=False, approved_by=None, operator=None, reason='no approver')
    if rec.get('approved') and not V['ok']:
        rec.update(approved=False, approved_by=None, reason='refused by the pipeline: validation failed')
    rec.update(approved=bool(rec.get('approved')), approver=getattr(approver, 'name', None), plan_sha256=sha,
               utc=runlog.utc(), validation_ok=V['ok'])
    if not rec['approved']: rec['approved_by'] = None
    return PipelineResult(text, prop, steps, V, rec, rv)
