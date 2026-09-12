# TA migration — 2026-09-12

Destination Git root: `/home/fadil/DSIC-2907/DSIC-2907`.
The outer directory is a container, not a Git repository.

| Original location in TA | Destination relative to Git root |
| --- | --- |
| Code/demand-aware-async-fl-nids/src, tests, data, results | src, tests, data, results |
| Code/demand-aware-async-fl-nids/configs/*.yaml | configs/day1_*.yaml |
| Code/demand-aware-async-fl-nids/README.md, tasks | paper/day1/README.md, paper/day1/tasks |
| Code/Data/* | data/raw/* (local, Git ignored) |
| Docs/* | paper/docs/* |
| Root README, LICENSE, package.json, package-lock.json | paper/day1/ta-workspace/* (historical workspace metadata) |

The supervisor's README, research configs, manuscript and FL scaffold are retained.
Only the preprocessing placeholder is replaced. Packaging combines the existing
Day 1 dependency requirements with the supervisor's package identity and dependencies.
The original Day 1 model settings are preserved separately from future FL settings.
Historical task records describe the original run and its original verification.

All frozen manifests, pipeline, split indices, checkpoint and result bytes are
preserved. `data/manifests/relocation.json` maps their original absolute paths to
repository-relative copies, including source CSVs. The loader uses the mapped
copy even when TA still exists and checks its original SHA256. A missing or
modified mapped copy fails instead of silently reading TA. Checkpoint receipt
validation compares the resolved path and verifies the original checksum.
No real-data training or official-test evaluation is repeated during migration.

TA remains an untouched backup. Its Git history is not merged into the supervisor's
repository. Virtual environments, node_modules, caches and build outputs are not
research artifacts and are not transferred. The root Node manifests are archived
only because they recorded the local Codex tool, not a research dependency.
Create a new `.venv` using the Day 1 installation commands. Large datasets and
model/preprocessing artifacts are copied locally but remain Git ignored; a Git
clone alone will not contain them. Keep those artifacts in external storage too.

## Migration verification

Using the existing TA Python environment from the staged destination:

- `python -m pytest -q`: 54 passed (46 imported, 2 relocation, 6 existing scaffold tests).
- Ruff lint and format checks pass for all imported/modified Python files.
- `python -m build --no-isolation`: source distribution and wheel built successfully.
- Raw files and archived artifacts compared byte-for-byte; saved preprocessing and checkpoint loaded without running inference.

Full-repository Ruff reports an existing unused `staleness` variable in
`src/async_server.py:9`. The scaffold is preserved unchanged. Packaging uses
Day 1's setuptools-only build requirement; no dependency installation was needed
for migration verification. A fresh environment should follow the installation
commands in the Day 1 README.
