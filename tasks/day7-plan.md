# Day 7 implementation record: Week 1 backbone freeze

## Scope

Freeze the verified Week 1 CPU B0 backbone from Days 1–6. This records the
pilot's data, model, training, async aggregation, serialization, update
operator, and evaluation identity. The Day 14 main protocol remains open.
The completed Day 6 plan/checklist are archived as `tasks/day6-plan.md` and
`tasks/day6-todo.md`.

## Dependency order

Fresh identical-input B0 repeats -> independent replays -> configuration and
event-schema comparison -> hash-pinned freeze manifest -> documentation gate.

## Task 1: Capture two fresh B0 repeats

**Acceptance:**
- [x] Configurations differ only by artifact destinations.
- [x] Both runs complete 30 accepted updates with the same initial tensors;
  neither overwrites Day 3/5 evidence or reads official test data.

**Verification:** Run `src.b0 train` with `configs/day7_b0_a.yaml` and
`configs/day7_b0_b.yaml`, then read-only replay each run.

**Files:** Two new configs, two raw run directories, summaries and replay
receipts under `results/processed/`.

## Task 2: Pin and verify the shared backbone

**Acceptance:**
- [x] A write-once manifest contains the normalized configuration snapshot,
  source and operator hashes, feature order, event schema, and pending choices.
- [x] Verification recomputes replay, byte counts, initial tensor equality,
  configuration/source equality, and Day 6 payload integrity.
- [x] An incompatible event field/type or changed training setting fails a
  focused test.

**Verification:** `pytest -q tests/test_backbone_freeze.py`; run
`src.backbone_freeze create` and `verify` against both saved runs.

**Files:** `src/backbone_freeze.py`, `tests/test_backbone_freeze.py`,
`results/processed/week1_backbone_freeze.json`.

### Checkpoint after Tasks 1–2

- [x] Both replay receipts match their saved models, staleness, and bytes;
  the freeze verifier accepts the manifest and current source hashes.

## Task 3: Record the Day 7 gate

**Acceptance:**
- [x] A Week 1 journal distinguishes the CPU B0 backbone freeze from Day 14
  protocol decisions and documents known limitations.
- [x] README, technical status, and active checklist reflect the completed
  gate and link the manifest and evidence.
- [x] Full pytest, Ruff lint/format, source/wheel build, freeze verification,
  and `git diff --check` pass.

**Verification:** Review journal, manifest, links, and final commands.

**Files:** `paper/docs/Jurnal/Minggu 1/Progres-Minggu-1.md`, `README.md`,
`teknis-lab/README.md`, `tasks/plan.md`, `tasks/todo.md`.

### Completion checkpoint

- [x] Week 1 data/partition, async/staleness, byte accounting, and budget
  reconstruction evidence is pinned and verifiable.
- [x] Main-run resource, network, adaptive-policy, target, and analysis
  decisions remain explicitly pending their later gates.
