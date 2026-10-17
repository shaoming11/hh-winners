"""python -m benchsim.ai --text FILE [--preset] [--approve] [--operator NAME] [--out PATH]

Prints the plan, the validation result and the approval record, and writes them as JSON (default
reports/ai_pipeline_example.json). Without --preset the language model is tried when the SDK and a key are available;
otherwise, or when its reply is unusable, the preset demo protocol is used and the reason recorded. Without --approve the
operator approves interactively (types 'approve'); --approve pre-approves on the command line, which still applies only
to a plan that passed validation. Exit status 0 if approved, 1 if not. Nothing is executed.
"""
import argparse
import json
import sys
from pathlib import Path

from .. import paths, runlog
from . import llm as L
from . import pipeline


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m benchsim.ai', description='protocol text -> validated, operator-approved step plan')
    ap.add_argument('--text', required=True, help='protocol text file')
    ap.add_argument('--preset', action='store_true', help='skip the language model; use the preset demo protocol')
    ap.add_argument('--approve', action='store_true', help='pre-approve on the command line (only applies if validation passes)')
    ap.add_argument('--operator', default=None, help='operator name for the approval record')
    ap.add_argument('--out', default=str(paths.SIM_ROOT / 'reports' / 'ai_pipeline_example.json'))
    a = ap.parse_args(argv)
    text_path = Path(a.text); text = text_path.read_text()
    ok, why = L.available()
    model = None if a.preset else L.AnthropicLLM()          # raises LLMUnavailable before any request when not available
    llm_note = 'not used (--preset)' if a.preset else ('request sent' if ok else 'not called: %s' % why)
    approver = (pipeline.CommandLineApprover(a.operator or 'operator (--approve)') if a.approve
                else pipeline.InteractiveApprover(a.operator))
    res = pipeline.run(text, llm=model, approver=approver)
    if a.approve:                                     # the interactive approver prints the review itself
        for ln in pipeline.review_lines(res.review): print(ln)
    print('APPROVAL: %s' % json.dumps(res.approval))
    try: rel = text_path.resolve().relative_to(paths.SIM_ROOT).as_posix()
    except ValueError: rel = str(text_path)
    report = dict(schema='benchsim.ai_pipeline/1', generated_utc=runlog.utc(), text_file=rel,
                  llm=dict(model=L.model_id(), status=llm_note, last_reply=getattr(model, 'last', None)),
                  approved=res.approved, **res.to_dict())
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(report, indent=1) + '\n')
    print('wrote %s' % out)
    return 0 if res.approved else 1


if __name__ == '__main__':
    sys.exit(main())
