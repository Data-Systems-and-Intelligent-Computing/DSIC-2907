# Day 8 implementation plan: Observational state monitoring

Status: COMPLETE — 2026-10-12. Plan approved by the user before implementation.
Evidence: [Day 8 gate receipt](../results/processed/day8_state_monitoring.json).
Day 7 records: [plan](day7-plan.md), [checklist](day7-todo.md).

## Objective and existing structure

Preserve the frozen B0 behavior while adding observations with defined units,
observation boundaries, provenance, availability times, and replayable snapshots.

- `src/b0.py::run_async` records downloads, arrivals, and applies in log order.
  It dispatches uniformly among idle clients and applies updates immediately in
  completion order, with at most one in-flight job per client.
- `src/client.py` returns local training duration. B0 records it on arrival;
  process-pool transfer timing is explicitly unmeasured.
- `src/async_server.py::apply_update` uses the frozen weighted dense delta,
  fixed multiplier, full budget, and one version increment per accepted update.
- `src/b0.py::replay` reconstructs model tensors, versions, staleness, and bytes
  from saved messages. `src/backbone_freeze.py` checks source/configuration hashes,
  event schema, and both Day 7 repeat runs.
- `src/monitor.py` is an unused stub, outside the pinned B0 source list. Implement
  there and reuse replay, artifact hashing, and JSON utilities without editing them.
- The verified partition manifest supplies all client IDs and their `row_count`
  before dispatch, including clients that never contribute.
- Existing tests cover fast/slow completion, rejected updates, worker failure,
  process execution, exact replay, and operation without the official-test CSV.

## Architecture and scope

1. Implement a deterministic event-prefix reducer and an offline replay CLI.
   Read frozen B0 artifacts and write separate monitoring artifacts. This avoids
   inserting work into the live asynchronous loop or changing completion order.
2. Preserve frozen source, configuration, logs, models, payloads, receipts, and
   the Week 1 manifest. Do not regenerate the freeze or extend B0 event fields.
3. Consume JSONL records in their original line order. Use recorded
   `elapsed_seconds` as the conservative server observation/availability time.
   Worker callback `arrival_elapsed_seconds` can precede intervening log records;
   it must not reorder observations or backdate their availability.
4. Emit start-up and post-event snapshots for every client. The prior prefix
   snapshot supplies state before the next download. Frozen logs lack an exact
   pre-selection timestamp: describe this as an event-boundary reconstruction,
   not a measured live decision-time observation.
5. Exclude demand, action selection, normalization, calibration, network simulation,
   and live policy integration. Do not use raw labels or validation/test scores.
   B0 cannot supply measured RTT or throughput; keep these explicitly missing.
6. Use the existing dependencies. No new packages, live hooks, or general-purpose
   monitoring framework. Work sequentially; subagents are not authorized.

## Implemented schema and temporal contract

Schema version 1 uses seconds on the run-relative monotonic B0 clock, not UTC.
Event ordinal is the one-based JSONL line number. Prefix zero is start-up at
zero seconds. Equal timestamps are ordered by event ordinal.

A snapshot contains `schema_version`, source-run identity, `client_id`,
`through_event_index`, `observation_elapsed_seconds`, `server_version`, and the
six fields below. Each field has `value`, `unit`, `status`, `source`,
`observed_at`, and `available_at`. Source references identify artifact path/hash,
event ordinal/type, job ID, and source field as applicable. Time references contain
seconds and event ordinal; static metadata uses boundary zero. The implementation
schema must enumerate every envelope/provenance field, type, and nullability.

| Field | Type and unit | Source and availability | Start-up / missing rule |
|---|---|---|---|
| `num_samples` (`n_i`) | Positive integer, samples | Verified partition `clients[id].row_count`, available at prefix zero; later counts must agree. | Required for all clients; missing/conflicting metadata is an input error. |
| `previous_local_train_seconds` (`T_prev`) | Nonnegative finite number, seconds | Latest valid consumed arrival's `local_train_seconds`; observed/available at that arrival's log boundary. | Null, `not_yet_observed`, before any arrival. Missing/invalid duration replaces the current value with null and an explicit status, never disguised stale data. |
| `rtt_seconds` (`RTT_i`) | Nullable nonnegative finite number, seconds | Frozen IPC timing contract states RTT was not measured. | Always null, `unmeasured_process_pool_ipc`; observation and availability timestamps null. |
| `throughput_bytes_per_second` (`BW_i`) | Nullable nonnegative finite number, bytes/second | No B0 transfer duration exists. Serialization time or training turnaround cannot substitute. | Always null, `unmeasured_process_pool_ipc`; observation and availability timestamps null. |
| `last_arrival_staleness` | Nonnegative integer, server versions | Latest consumed arrival's `server_version - model_start_version`, checked against its logged staleness; available at that arrival. | Null, `not_yet_observed`, before first arrival. This is historical lag, not a prediction for the next job. |
| `contribution_age_seconds` (`age_i`) | Nonnegative finite number, seconds | Snapshot time minus the last accepted apply's log time; cite the apply and current boundary. Derived/available at the snapshot boundary. | Null, `never_contributed`, until first apply; zero immediately after apply. Rejection never resets age. |

Available values use `static_metadata`, `observed`, or `derived` status. Missing
statuses are `not_yet_observed`, `never_contributed`, `unmeasured_process_pool_ipc`,
`missing_observation`, and `invalid_observation`. Missing values are JSON null,
never NaN, infinity, or an imputed zero. Observed zero duration/staleness is valid.

Every present value's source availability must be within the consumed prefix and
no later than the snapshot boundary. Derived values cite every input. A worker's
training duration is not an absolute worker timestamp. The network capability
contract is known at start-up but does not establish a measurement timestamp.

Arrival measurements can describe a job subsequently rejected at apply. Keep
arrival observations distinct from accepted contributions; only apply updates
age/version. Hold prior observations without smoothing or expiry in Day 8 and
retain their original timestamps. Emitted snapshots must be detached from mutable
reducer/input state. Never backfill earlier snapshots from later events.

Structural errors fail replay: invalid JSON, nonfinite/decreasing log times,
unknown clients, duplicate/unmatched job lifecycle, future/inconsistent versions,
count mismatches, and artifact hash mismatches. Missing/invalid optional duration
is reported explicitly. Valid reject/failure records can be consumed without an
accepted update, but a failed run cannot receive a completed B0 replay receipt.

## Dependency order

Schema/examples -> reducer -> replay adapter -> temporal/regression proof ->
frozen-run evidence -> documented acceptance gate.

### Task 1: Specify the state schema

**Description:** Write the complete contract and hand-calculated examples for
start-up, overlapping fast/slow jobs, first arrival/apply, and an idle client.

**Acceptance criteria:**
- [x] Every serialized field has type, units, provenance, observation/availability
  rules, allowed statuses, and missing/invalid behavior.
- [x] Examples distinguish pre-download prefix, post-arrival, and post-apply state,
  including equal timestamps and earlier callback times.
- [x] Schema defines the snapshot file and evidence manifest, including input/output
  hashes, monitor-source identity, observation scope, and missing/invalid counts.

**Verification:** Compare examples with exact B0 log fields and partition metadata;
hand-calculate values at each event prefix and review for future dependencies.

**Dependencies:** None.
**Files likely touched:** `tasks/day8-state-schema.md` (new).
**Estimated scope:** Small, 1 file.

### Task 2: Implement the event-prefix reducer

**Description:** Replace the existing monitor stub with a small incremental
reducer taking pre-run metadata and one event at a time. It holds no live model,
server, RNG, scheduler, or future-event collection.

**Acceptance criteria:**
- [x] All clients receive snapshots matching Task 1 examples, with updates at the
  specified arrival/apply boundaries and explicit missing network values.
- [x] Tests cover unequal sample counts, never-selected clients, start-up, valid
  zero values, invalid/missing durations, job lifecycle, rejects, and failures.
- [x] Inputs/history stay unchanged, serialization is deterministic, and outputs
  contain no demand/action fields.

**Verification:** `rtk pytest -q tests/test_monitor.py`;
`rtk proxy python -m ruff check src/monitor.py tests/test_monitor.py`.

**Dependencies:** Task 1.
**Files likely touched:** `src/monitor.py`, `tests/test_monitor.py` (new).
**Estimated scope:** Small, 2 files.

### Checkpoint after Tasks 1–2

- [x] Hand-worked schema examples agree with reducer tests.
- [x] Week 1 freeze verification still passes; no frozen files changed.

### Task 3: Add replayable monitoring artifacts

**Description:** Add `python -m src.monitor replay --run-dir PATH --output-dir PATH`
and `verify --manifest PATH`. Verify configuration/partition linkage, reuse B0
replay, and feed source events to the same reducer without raw CSV access.

**Acceptance criteria:**
- [x] Replay writes `snapshots.jsonl` and `manifest.json`; the manifest includes
  missing/invalid counts, hashes, schema/source versions, observation semantics,
  row counts, and the existing B0 replay receipt.
- [x] Verify recomputes snapshots and compares content/hashes; tampered events,
  metadata, monitor source, and snapshot files fail. Duplicate replay outputs have
  identical snapshot bytes and normalized report content.
- [x] Existing destinations and destinations inside the input run are rejected;
  input artifacts are read-only and output creation never changes B0 evidence.

**Verification:** `rtk pytest -q tests/test_monitor_replay.py`; exercise replay
and verify on a completed fixture with training/test CSVs unavailable.

**Dependencies:** Task 2.
**Files likely touched:** `src/monitor.py`, `tests/test_monitor_replay.py` (new).
**Estimated scope:** Small, 2 files.

### Task 4: Prove temporal consistency and B0 non-interference

**Description:** Add adversarial temporal tests and regression tests against the
same captured B0 trace before/after observational replay.

**Acceptance criteria:**
- [x] Prefix invariance: truncating, appending, or altering future observations
  cannot change earlier snapshots. Include ties, overlapping jobs, callback/log
  time differences, invalid time/order, and startup/pre-download boundaries.
- [x] Every present value satisfies provenance/availability bounds. Mutating input
  records or returned snapshots cannot corrupt previously emitted state.
- [x] Before/after monitoring, identical captured B0 inputs yield identical replay
  receipts and tensors, apply order/weights, versions, staleness, byte counts, and
  artifact hashes; existing fast/slow and rejection tests continue to pass.

**Verification:**
```bash
rtk pytest -q tests/test_monitor.py tests/test_monitor_replay.py tests/test_b0.py tests/test_async_apply.py tests/test_staleness.py tests/test_byte_accounting.py tests/test_backbone_freeze.py
rtk proxy python -m src.backbone_freeze verify --manifest results/processed/week1_backbone_freeze.json
```
Do not require independent asynchronous runs to have identical completion order.

**Dependencies:** Task 3.
**Files likely touched:** `tests/test_monitor.py`, `tests/test_monitor_replay.py`.
**Estimated scope:** Small, 2 files.

### Checkpoint after Tasks 3–4

- [x] Temporal adversarial tests and baseline regression tests pass.
- [x] Freeze and monitoring verification pass; tampering is detected.

### Task 5: Capture the Day 8 evidence

**Description:** Replay both frozen Day 7 runs to independent output directories,
verify each bundle, and save a gate receipt with commands, results, and limitations.

**Acceptance criteria:**
- [x] Each 30-update run has verified snapshots covering all clients, with schema
  links, actual counts, source hashes, and missing/invalid reports.
- [x] Missing RTT/throughput and start-up observations remain explicit; the gate
  receipt links the temporal and regression test results without overstating them.
- [x] Full tests, lint/format, package build, and freeze verification pass; any
  failed or unavailable check leaves the acceptance gate open.

**Verification:**
```bash
rtk proxy python -m src.monitor replay --run-dir results/raw/b0_day7_a_seed42 --output-dir results/processed/day8_monitor_a
rtk proxy python -m src.monitor replay --run-dir results/raw/b0_day7_b_seed42 --output-dir results/processed/day8_monitor_b
rtk proxy python -m src.monitor verify --manifest results/processed/day8_monitor_a/manifest.json
rtk proxy python -m src.monitor verify --manifest results/processed/day8_monitor_b/manifest.json
rtk pytest -q
rtk proxy python -m ruff check .
rtk proxy python -m ruff format --check src/monitor.py tests/test_monitor.py tests/test_monitor_replay.py
rtk proxy python -m build --outdir /tmp/dsic2907-day8-build
rtk proxy python -m src.backbone_freeze verify --manifest results/processed/week1_backbone_freeze.json
rtk git diff --check
```

**Dependencies:** Task 4 and a compatible existing development environment.
**Files likely touched:** `snapshots.jsonl` and `manifest.json` in each of the two
new output directories; `results/processed/day8_state_monitoring.json` gate receipt.
**Estimated scope:** Medium, 5 generated artifact files; no source changes.

### Task 6: Document the verified gate

**Description:** Update project status after evidence exists, linking the schema,
snapshots, replay commands, actual test results, and limitations.

**Acceptance criteria:**
- [x] README and technical Day 8 status explain offline event-boundary observations,
  missing network measurements, and preserved B0 behavior.
- [x] Plan/checklist link real verification evidence and mark only completed work;
  calibration and policy integration remain pending their later gates.
- [x] Unrelated user edits, including the removed Week 1 journal, are preserved.

**Verification:** Check links against generated artifacts; `rtk git diff --check`.

**Dependencies:** Task 5.
**Files likely touched:** `README.md`, `teknis-lab/README.md`, `tasks/plan.md`,
`tasks/todo.md`.
**Estimated scope:** Medium, 4 files.

## Completion checkpoint

| User acceptance gate | Evidence / tasks |
|---|---|
| Complete documented schema, provenance, availability time | Schema document and schema tests, Tasks 1–2 |
| Replayable state snapshots from B0 | Two verified monitoring bundles, Tasks 3 and 5 |
| Explicit start-up and missing-value rules | Schema, boundary tests, missing reports, Tasks 1–2 and 5 |
| Temporal consistency and no future-information leakage | Prefix-invariance and availability tests, Task 4 |
| Passing regression tests preserving B0 model-update semantics | Same-trace before/after replay, full tests, unchanged freeze, Tasks 4–5 |

- [x] All five acceptance gates have linked passing evidence.
- [x] Documentation reflects measured results and limitations (Task 6).

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Monitoring changes completion order or pinned hashes | High | Offline reducer, no frozen source/log edits. |
| Future values backfilled into old snapshots | High | Pre-run metadata, incremental prefixes, adversarial tests. |
| Callback time confused with server availability | High | Log-boundary time and ordinal ordering. |
| Training/serialization time used as network measurement | High | Explicit unmeasured RTT/BW nulls. |
| Returned snapshots alias mutable state | High | Detached snapshots and mutation tests. |
| Independent B0 runs differ naturally | Medium | Compare identical captured traces; verify A and B independently. |
| Test environment cannot execute regression suite | High | Resolve tooling before implementation verification; no silent installs. |

## Planning verification and open constraints

- On 2026-10-11, `rtk proxy python -m src.backbone_freeze verify --manifest
  results/processed/week1_backbone_freeze.json` passed for both saved runs.
- Targeted baseline tests could not start: active Python lacks pytest; system
  pytest cannot import pandas (system Python also lacks torch). No packages were
  installed. Select a compatible existing environment, or obtain approval for
  installing the already-declared development tools if necessary.
- Codebase-memory bootstrap failed with a contained indexing-worker crash; status
  confirmed no index. Relevant exact source/configuration/tests were read directly.
- The invoked skill's optional `references/definition-of-done.md` was absent at its
  supplied location. The user's five explicit acceptance gates govern completion.
- The user reviewed and approved the plan on 2026-10-12. Day 8 implements offline
  event-boundary monitoring; live integration and controlled network measurements
  remain later work.


## Execution record — 2026-10-12

- [Schema](day8-state-schema.md), `src/monitor.py`, and the two monitor test modules
  implement Tasks 1–4. The first tests failed on the missing reducer/CLI, then
  passed after implementation. The old unused `log_event` stub was replaced;
  artifact hashing, JSON I/O, B0 replay, and the B0 fixture were reused.
- 48 new monitor tests plus existing regressions: targeted suite **79 passed**;
  full suite **184 passed**. Prefix/adversarial tests cover equal times, delayed
  availability, missing values, history mutation, rejection, and malformed input.
  Replay tests delete both raw CSVs, compare before/after receipts and tensors,
  preserve input file hashes and RNG state, and detect content/reference tampering.
- [A manifest](../results/processed/day8_monitor_a/manifest.json) and
  [B manifest](../results/processed/day8_monitor_b/manifest.json) each certify
  **910 snapshots**, **90 events**, **10 clients**, and **30 accepted updates**.
  Each retains **8,094,060** serialized B0 bytes and has zero invalid/missing
  duration observations. Missing start-up/network states are counted separately.
- Source hashes, update semantics, event schema, and artifacts of frozen B0 remain
  unchanged. The Week 1 freeze verifier passes for both runs.
- Code review checked temporal boundaries, read-only input behavior, artifact
  linkage, deterministic output, and dependency scope. No unresolved findings.
- README/technical status now link the schema, bundles, commands, and gate receipt.
  Unrelated user changes were preserved.

### Actual verification environment

The initial tooling blocker was resolved without changing project dependencies:
existing system pytest works with the existing ML environment when invoked as:

```bash
rtk proxy env PYTHONPATH=/home/fadil/.local/share/venvs/deep-learning/lib/python3.14/site-packages:/usr/lib/python3/dist-packages python -m pytest -q
```

Ruff 0.17.0 (already declared in the dev extra) was installed with permission in
`/tmp/dsic-day8-tools`; full lint and format checks passed using its executable.
The `build` frontend is unavailable, so source/wheel builds used the existing
configured setuptools backend directly, with output under `/tmp/dsic2907-day8-build`.
The [gate receipt](../results/processed/day8_state_monitoring.json) records actual
commands, environment, output, test/source hashes, and package artifact hashes.
No live policy integration, network measurement, or calibration is claimed.
