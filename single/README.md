# Single-Case Runs

This directory is for interactive, one-requirement-at-a-time testing.

Use either entry point:

```bash
.venv/bin/python src/main.py "For the next few seconds, the ego vehicle speed shall remain low speed"
.venv/bin/python single/run_single.py "For the next few seconds, the ego vehicle speed shall remain low speed"
```

Single-case AST artifacts are written under:

```text
tmp/single/<session_id>/ast.json
```

The translation engine remains shared in `src/nl2stl_app/`.
