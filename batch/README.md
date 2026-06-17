# Batch Experiments

This directory is reserved for dataset-scale experiments.

Planned layout:

```text
batch/
  datasets/   input JSONL or other datasets
  configs/    experiment configuration files
  results/    structured batch outputs
  logs/       run logs
```

Batch execution code is intentionally not implemented yet. When added, it should reuse the shared translation engine in `src/nl2stl_app/` and write artifacts under:

```text
tmp/batch/<run_id>/<case_id>/ast.json
```
