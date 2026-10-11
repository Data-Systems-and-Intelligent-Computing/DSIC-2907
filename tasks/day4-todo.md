# Day 4 checklist: versioning and staleness

- [x] Review and approve `tasks/plan.md` before implementation.
- [x] Task 1: Log arrival staleness and rejected arrivals; prove the controlled
  fast/fast/slow sequence and unchanged state after rejection.
- [x] Task 2: Add schema-2 accepted-update staleness summaries for the run and
  every client, including zero-update clients.

## Checkpoint after Tasks 1-2

- [x] Focused server/B0 tests pass; immediate apply and Day 3 aggregation stay intact.

## Remaining tasks

- [x] Task 3: Replay checks arrival and apply versions/staleness; schema-1 Day 3
  trace remains replayable without modification and reports audited staleness.
- [x] Task 4: Save new verification receipt; document controlled fixture and
  frozen-trace results; update status only after the gate passes.

## Completion checkpoint

- [x] All Day 4 minimum tests in `teknis-lab/README.md` pass.
- [x] Full pytest, Ruff lint/format, package build, and `git diff --check` pass.
- [x] Frozen Day 3 artifact hashes are unchanged; official test data was not opened.
