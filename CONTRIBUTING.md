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
- `CHECKS` (defined once in `templates.py`) is the single source for every check's anchors, category, title, and one-line `description`. It feeds `report_html.py` (re-exported from there), the landing page's "What do you get?" list, and the `/api/validate` OpenAPI description - don't hand-edit those separately. `templates.py` asserts at import time that `CHECKS` and `GUIDE_SECTIONS` agree on anchors and categories, and that every `description` is non-empty; the test suite catches any drift immediately. README.md deliberately keeps no copy of this list - it just links to the live app and the publishing guide.

## Bug reports

Open a [GitHub issue](https://github.com/TDCC-NES/askwol/issues) with:
- The ontology (or a minimal snippet) that triggers the problem.
- The command you ran or the URL you submitted.
- Expected vs. actual output.
