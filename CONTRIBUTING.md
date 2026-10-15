# Contributing

Thanks for considering a contribution!

## Quick setup

```bash
git clone https://github.com/TDCC-NES/askwol.git
cd askwol
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

## Pull requests

- One focused change per PR.
- Add or update tests for behaviour changes - `pytest` must pass.
- Keep public API and CLI output stable where possible; mention breaking changes in the PR description.
- Match the existing style (no formatter enforced yet; just keep diffs minimal).
- `CHECKS` in `src/askwol/checks.py` supplies shared anchors, titles, descriptions, categories, and numbering. `templates.py` checks that guide sections use the same anchors, order, and categories; tests verify the catalogue and numbering.

## Bug reports

Open a [GitHub issue](https://github.com/TDCC-NES/askwol/issues) with:
- The ontology (or a minimal snippet) that triggers the problem.
- The command you ran or the URL you submitted.
- Expected vs. actual output.
