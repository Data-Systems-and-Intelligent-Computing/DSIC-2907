# Day 5 checklist: communication byte accounting

- [x] Review and approve `tasks/plan.md` before implementation.
- [x] Task 1: Validate one serialized message and measure exact payload,
  zero application framing, tensor-value bytes, and serialization overhead.
- [x] Task 2: Add per-transfer byte/timing fields to B0 events without calling
  process-pool turnaround a network transfer time.

## Checkpoint after Tasks 1-2

- [x] Dense and malformed payload tests pass; upload/download fields remain
  distinct and all counted bytes are exact serialized lengths.

## Remaining tasks

- [x] Task 3: Reconcile run totals and validation cumulative bytes; verify
  schema-3 replay while preserving schema-1/2 replay.
- [x] Task 4: Run a fresh Day 5 seed-42 B0 pilot at new paths and save a replay
  receipt without touching the frozen Day 3/4 evidence.

## Checkpoint after Tasks 3-4

- [x] New run and replay totals match event/payload sums; legacy replay passes.

## Final task and completion gate

- [x] Task 5: Write the Day 5 journal and update README/technical status with
  measurement scope, exact totals, verification commands, and limits.
- [x] Full pytest, Ruff lint/format, build, both replays, and `git diff --check`
  pass; old artifact hashes remain unchanged.
- [x] No physical-network, transfer-latency, compression-saving, or
  bytes-to-target claim is inferred from the CPU process-pool pilot.
