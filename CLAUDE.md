# Racing Dashboard – notes for Claude

Start with [docs/HANDOVER.md](docs/HANDOVER.md): current state, what was verified in the game and what is still open, what a cloud session can and cannot do, and the owner's design decisions. Then [README.md](README.md) and [docs/SPEC.md](docs/SPEC.md).

- Run: `python core\server.py` (or `start_dashboard.bat`); check: `python core\server.py --check`; tests: `python -m unittest discover tests`; ACE live values: `py tools\ace_probe.py` (analysis values and car slots: `--analysis`); recorded analysis data: `python tools\analysis_check.py`.
- Log: `logs\racing-dashboard.log`; live frame: `http://localhost:8080/state`; served dash map: `http://localhost:8080/api/info`.
- Python standard library only; one folder per game in `games/`; the UI in `ui/` is plain HTML / CSS / JS.
- Commit directly to `main`. Only one other branch: one work-in-progress branch for prototypes waiting for the owner's OK; merge it into `main` once approved (no branch per feature). Keep docs and tests in step with every change. No personal data in commits.
- For visual changes, show PNG mockups first and ask for feedback before building.
