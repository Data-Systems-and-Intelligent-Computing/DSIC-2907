# Day 4 implementation plan: versioning and staleness

## Scope and current state

Verify the B0 server's version transitions and staleness under controlled fast
and slow arrivals, then make those transitions auditable in event logs, summaries,
and replay. This is a Day 4 evidence pass on the existing CPU pilot. Keep the
Day 3 aggregation equation, fixed multiplier, dispatch rule, local training,
full update budget, and official-test isolation unchanged. Do not add packages
or introduce a new policy.

Day 3 already increments `AsyncServer.version` after each valid apply, computes
`version_before - model_start_version`, and rejects invalid updates without
mutating the model. `run_async` logs the downloaded start version and the server
version at arrival. Its controlled test already holds a slow client while a fast
client applies twice. The missing Day 4 evidence is explicit arrival staleness,
a versioned rejection record, per-run/per-client staleness summaries, and replay
checks against the arrival record itself.

The frozen Day 3 raw trace and processed summary are immutable evidence. The new
event/summary schema must preserve replay of that schema-1 trace.

## Contract and implementation order

For each arrival, `v_arrival` is the server version immediately before its
apply decision, and `staleness = v_arrival - model_start_version`. Accepted
updates advance the version exactly once; rejected updates do not. Elapsed time
is recorded separately and never used to calculate staleness. Keep Day 3's
fail-fast behavior on an invalid update while recording a rejection with its
job/client identity, start version, arrival version, staleness, and reason.

New completed runs use summary `schema_version: 2`. Their arrival records have
`server_version`, `model_start_version`, and `staleness`. Existing schema-1
records have no arrival staleness; replay derives it from their two version
fields and checks it against the subsequent apply. New run summaries report
accepted-update staleness by run and client: count, minimum, mean, median, p95,
and maximum. Clients with no accepted update have count zero and null statistics.
Rejected arrivals remain in the event log of a failed run, not in the completed
run's accepted-update summary.

Dependency flow: arrival/rejection record and controlled tests -> summary
contract -> replay audit of both schemas -> saved verification receipt and Day 4
documentation. Each task leaves the existing B0 pilot and replay usable.

## Task 1: Record and test arrival decisions

**Description:** Add explicit staleness to the arrival record and log a rejected
arrival if server validation fails. Extend the existing controlled fixture and
server tests; reuse the current `AsyncServer` calculation and event writer.

**Acceptance criteria:**
- [x] Controlled fast/slow arrivals start at versions 0, 1, and 0; arrive at
  versions 0, 1, and 2; have staleness 0, 0, and 2; and accepted transitions are
  0->1->2->3 without waiting for the slow worker.
- [x] An invalid update records a rejected arrival with nonnegative staleness,
  leaves model/version unchanged, and retains the existing failed-run behavior.
- [x] A future/invalid start version cannot produce a negative accepted or
  rejected staleness value.

**Verification:** `pytest -q tests/test_async_apply.py tests/test_b0.py`.

**Dependencies:** None.

**Files likely touched:** `src/b0.py`, `tests/test_b0.py`,
`tests/test_async_apply.py` (only if the server validation needs more coverage).

**Estimated scope:** Medium, 2-3 files.

## Task 2: Summarize accepted-update staleness

**Description:** Build run and client statistics from recorded applies in the
existing pilot result path. Keep the summary independent of wall-clock duration
and preserve zero-update clients explicitly.

**Acceptance criteria:**
- [x] Completed run summary contains count, minimum, mean, median, p95, and
  maximum staleness for the run and each client; counts sum to accepted updates.
- [x] All summary values are reconstructed from apply records; empty clients
  have count zero and null statistics; output is valid JSON without NaN.
- [x] New completed summaries use schema 2 and preserve all Day 3 result fields.

**Verification:** `pytest -q tests/test_b0.py` with a small controlled run and
the existing process-pilot fixture.

**Dependencies:** Task 1.

**Files likely touched:** `src/b0.py`, `tests/test_b0.py`.

**Estimated scope:** Small, 2 files.

### Checkpoint after Tasks 1-2

- [x] Controlled version transitions and rejected-arrival behavior pass.
- [x] The normal B0 run still applies updates immediately and reports the same
  aggregation weights as Day 3.

## Task 3: Audit version history during replay

**Description:** Extend `replay` to verify the recorded arrival version and
staleness before applying each update, in addition to its existing apply-receipt
and final-model checks. Retain read-only replay of the frozen Day 3 schema-1 run.

**Acceptance criteria:**
- [x] Replay checks `server_version == current version` at every arrival and
  checks `staleness == server_version - model_start_version` for schema 2.
- [x] Replay checks matching arrival/apply job identity, start version,
  `version_before`, `version_after`, and staleness; a modified version field is
  rejected even when the event artifact hash is updated accordingly.
- [x] The replay receipt reports staleness statistics from the audited applies,
  using the same summary definition as a completed run.
- [x] The saved Day 3 schema-1 trace still replays to the identical final model
  and accepted-update count without rewriting its artifacts.

**Verification:** `pytest -q tests/test_b0.py`; run `python -m src.b0 replay
--run-dir results/raw/b0_day3_seed42` without `--output`.

**Dependencies:** Tasks 1-2.

**Files likely touched:** `src/b0.py`, `tests/test_b0.py`.

**Estimated scope:** Small, 2 files.

## Task 4: Save the Day 4 evidence

**Description:** Run the focused and full checks, record the controlled
fast/slow sequence and rejection result, and save a new receipt from the frozen
Day 3 trace. Document exactly which checks use the old trace and which use the
new event schema.

**Acceptance criteria:**
- [x] A Day 4 journal records the controlled fixture's download, arrival,
  staleness, and version sequence plus the completed-run summary definition.
- [x] A new processed replay receipt and journal record the schema-1 trace's
  30 accepted transitions, final-model match, and observed staleness range.
- [x] README/technical status indicates Day 4 complete only after all gates
  pass; the original Day 3 artifacts remain unchanged.

**Verification:** Full pytest, Ruff check, Ruff format check for changed Python
files, package build, read-only replay, and `git diff --check`. Compare the
frozen Day 3 artifact hashes before and after.

**Dependencies:** Task 3.

**Files likely touched:** `paper/docs/Jurnal/Day-4-Versioning-and-Staleness.md`,
`README.md`, `teknis-lab/README.md`, plus one new `results/processed/` receipt.

**Estimated scope:** Medium, 3-4 files.

### Completion checkpoint

- [x] Every accepted/rejected arrival has nonnegative version-based staleness.
- [x] Controlled fast/slow behavior, monotonic accepted versions, and no
  rejected-version increment are demonstrated.
- [x] New summaries and both replay schemas pass their checks.
- [x] Tests, lint, format, build, and artifact-integrity checks pass.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Changing log fields breaks the Day 3 trace | Version new summaries as schema 2 and replay schema 1 explicitly; never rewrite Day 3 artifacts. |
| A timestamp is mistaken for staleness | Assert the 0, 0, 2 controlled sequence from model versions and keep elapsed time separate. |
| A rejected update silently changes state | Assert model and server version before/after the invalid apply, then inspect the reject event. |
| Replay trusts a self-consistent but false log | Recompute arrival versions from replay state and test semantic tampering after refreshing artifact hashes. |

## Open questions

None blocking. The plan keeps invalid-update handling fail-fast because Day 3
already uses that behavior and Day 4 does not define a retry or skip policy.
