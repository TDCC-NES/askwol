# Contributing

Thanks for considering a contribution!

## Quick setup

```bash
git clone https://github.com/TDCC-NES/askwol.git 
cd askwol
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Pull requests

- One focused change per PR.
- Add or update tests for behaviour changes - `pytest` must pass.
- Keep public API and CLI output stable where possible; mention breaking changes in the PR description.
- Match the existing style (no formatter enforced yet; just keep diffs minimal).
- If you touch `report_html.py` or `templates.py`, keep the `CHECKS` registry and `GUIDE_SECTIONS` listing the same anchors, in the same order - `report_html.py` asserts this at import time and the test suite catches it.

## Bug reports

Open a [GitHub issue](https://github.com/TDCC-NES/askwol/issues) with:
- The ontology (or a minimal snippet) that triggers the problem.
- The command you ran or the URL you submitted.
- Expected vs. actual output.
