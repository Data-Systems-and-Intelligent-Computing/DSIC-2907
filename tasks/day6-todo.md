# Day 6 checklist: 25/50/100% update budgets

- [x] Review and approve `tasks/plan.md` before implementation.
- [x] Task 1: Implement deterministic per-tensor magnitude top-k selection for
  `0.25`, `0.50`, and `1.00`, including tie and invalid-input tests.
- [x] Task 2: Encode, serialize, decode, and reconstruct versioned sparse
  uploads; preserve the dense `1.00` wire form.

## Checkpoint after Tasks 1-2

- [x] Selection and round-trip tests pass; sparse bytes exclude a dense delta
  copy and fixed local training is unchanged.

## Remaining tasks

- [x] Task 3: Apply reconstructed deltas under explicit server opt-in while
  keeping the default B0 full-budget guard.
- [x] Task 4: Probe one saved Day 5 delta at all three actions, record source
  hashes and actual value/index/metadata/upload/download bytes, and verify
  each model effect.

## Checkpoint after Tasks 3-4

- [x] All actions reconstruct/apply correctly; signed savings use serialized
  bytes including metadata.

## Final task and completion gate

- [x] Task 5: Write the Day 6 journal and update README/technical status with
  the contract, report, measured boundary, and limitations.
- [x] Full pytest, Ruff lint/format, build, read-only B0 replays, and
  `git diff --check` pass; existing artifact hashes remain unchanged.
- [x] No adaptive-policy, physical-network, or official-test result is
  inferred from this controlled operator probe.
