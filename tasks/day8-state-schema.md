# Day 8 state schema, version 1

This is an offline observation contract over frozen B0 events. It supplies no
demand, normalization, action, or training input. Frozen logs and models remain
unchanged. No raw CSV or official-test score is used to construct state.

## Clock and observation boundaries

Time is finite nonnegative seconds on B0's run-relative monotonic clock, not UTC.
`event_index` is a one-based JSONL line number; zero is start-up at 0.0 seconds.
Time cannot decrease. Equal times are ordered by event index. Every client has a
start-up snapshot and a snapshot after each consumed event, sorted by client ID.
The previous prefix snapshot is available before the next download. B0 did not
record the exact pre-selection instant, so these are event-boundary observations,
not measurements at exact live decision times.

Arrival availability uses the arrival record's `elapsed_seconds`, not the earlier
worker callback `arrival_elapsed_seconds`. Worker training duration has no absolute
clock timestamp. Replaying a prefix never reads a later event or backfills history.
Audit hashes of complete source files live in the manifest, not in feature rows:
changing a future suffix therefore cannot change earlier snapshot content.

## Snapshot JSONL

Each line is an object with exactly these keys:

| Key | Type / meaning |
|---|---|
| `schema_version` | integer, 1 |
| `run_id` | string, resolved source run directory; identity only |
| `client_id` | nonempty string from the pre-run partition |
| `through_event_index` | nonnegative integer, consumed prefix length |
| `observation_elapsed_seconds` | nonnegative finite number, current log time |
| `server_version` | nonnegative integer, accepted applies so far |
| `fields` | object containing exactly the six fields below |

Each field has exactly `value`, `unit`, `status`, `source`, `observed_at`, and
`available_at`. A time is null or an object with `event_index` (nonnegative integer)
and `elapsed_seconds` (finite nonnegative number). A present value must have both
times, each within the snapshot's consumed prefix and time boundary.

`source` is a list of objects with exactly `artifact` (one of `partition`,
`configuration`, `events`), `event_index` (nonnegative integer), `event` (string or
null), `job_id` (string or null), and `fields` (list of source-field names).
`artifact` resolves to a path and SHA256 in manifest `inputs`. Static sources have
index zero and null event/job. Unknown observations have no source. Derived age
cites its accepted apply and the current clock event; at start-up it is unknown.

| Field | Value type / unit | Source and update rule | Start-up |
|---|---|---|---|
| `num_samples` | positive integer / `samples` | Partition `clients.<id>.row_count`; static and available at zero. All logged job counts must agree. | Required; invalid/missing metadata fails. |
| `previous_local_train_seconds` | nullable finite nonnegative number / `seconds` | Latest consumed arrival's `local_train_seconds`; observed/available at its log boundary. | null, `not_yet_observed` |
| `rtt_seconds` | nullable finite nonnegative number / `seconds` | Configuration `byte_accounting.transfer_timing` documents unmeasured IPC. No RTT is inferred. | null, `unmeasured_process_pool_ipc` |
| `throughput_bytes_per_second` | nullable finite nonnegative number / `bytes/second` | Same contract. Bytes divided by serialization/training/turnaround time is not transfer throughput. | null, `unmeasured_process_pool_ipc` |
| `last_arrival_staleness` | nullable nonnegative integer / `server_versions` | Latest arrival's `server_version - model_start_version`, checked against `staleness`; available at arrival. Historical lag, not next-job lag. | null, `not_yet_observed` |
| `contribution_age_seconds` | nullable finite nonnegative number / `seconds` | Current log time minus last accepted apply time; derived/available at current boundary. | null, `never_contributed` |

Statuses: `static_metadata` for sample count, `observed` for valid arrival values,
`derived` for age, plus `not_yet_observed`, `never_contributed`,
`unmeasured_process_pool_ipc`, `missing_observation`, `invalid_observation`.
Never serialize NaN/infinity or impute zeros. Zero duration, age, and lag are valid.
Absent/null training duration becomes `missing_observation`; negative, nonfinite,
boolean, or nonnumeric duration becomes `invalid_observation`. Both replace any
prior value with null and retain the current arrival's source/time, distinguishing
an observed absence from no arrival yet. No-observation and unmeasured times are
null. Static sample count times are zero. No smoothing or expiry is applied.

Arrival observations remain valid records even if that job is later rejected.
Only accepted apply advances server version or resets contribution age. Age is
zero immediately after first apply; never-contributed clients retain null age.
Snapshots and input records cannot alias mutable reducer state.

## Validation and failures

Fail on invalid JSON, unknown event/client, invalid/decreasing log time, duplicate
job ID, multiple active jobs for one client, unmatched arrival/apply/reject,
identity/seed/count/version mismatch, future model version, or invalid artifact
hash/linkage. B0 arrival must be followed immediately by apply or reject; reject
must be followed by failure. Failure is terminal and does not imply acceptance.
Completed-run evidence requires all jobs drained and successful existing B0 replay.
The reducer supports failure prefixes, but the CLI only certifies completed schema-3
full-budget B0 runs with the unmeasured IPC timing contract.

## Hand-calculated example

Clients: fast=2, slow=5, idle=9 samples. Both jobs start at version zero.

| Prefix | Time (s) | Event | Version | fast T_prev / lag / age | slow T_prev / lag / age |
|---|---:|---|---:|---|---|
| 0 | 0 | start-up | 0 | null / null / null | null / null / null |
| 1 | 1 | fast download | 0 | null / null / null | null / null / null |
| 2 | 1 | slow download | 0 | null / null / null | null / null / null |
| 3 | 3 | fast arrival (duration 1.5s) | 0 | 1.5 / 0 / null | null / null / null |
| 4 | 3 | fast apply | 1 | 1.5 / 0 / 0 | null / null / null |
| 5 | 8 | slow arrival (duration 6s) | 1 | 1.5 / 0 / 5 | 6 / 1 / null |
| 6 | 9 | slow apply | 2 | 1.5 / 0 / 6 | 6 / 1 / 0 |

Even if fast callback time is 0.5s, its observations become available only at
prefix 3/time 3. Prefix 2 cannot contain fast duration. Idle keeps n=9 and null
duration/lag/age at every prefix. All clients keep null RTT/throughput. Equal-time
prefixes 3 and 4 differ: version/age becomes available only at apply.

## Evidence manifest

`manifest.json` has these keys (all required):

| Key | Type / meaning |
|---|---|
| `schema_version` | integer, 1 |
| `run_id` | string, resolved source run directory |
| `observation_scope` | string, `offline_event_prefix` |
| `clock` | string, `b0_log_elapsed_seconds_then_event_index` |
| `inputs` | object: `run_manifest`, `configuration`, `partition`, `partition_rows`, `events`; each `{path: string, sha256: string}` |
| `monitor_source` | `{path, sha256}` for `src/monitor.py` |
| `schema` | `{path, sha256}` for this document |
| `snapshots` | `{path, sha256}` for generated JSONL |
| `event_count` | nonnegative integer |
| `snapshot_count` | positive integer; client count times (event count + 1) |
| `client_ids` | sorted list of strings |
| `status_counts` | object: field name -> observed status -> nonnegative integer; counts across emitted rows, including repeated missing states |
| `observation_issues` | list of `{client_id, event_index, field, status}` for missing/invalid duration, once per source observation |
| `b0_replay` | unchanged receipt returned by existing `src.b0.replay` (accepted updates, model match, staleness summaries, byte totals, event/final-model hashes) |

The manifest links audit provenance; the reducer never uses manifest summaries,
final metrics, replay outcome, or complete-file hashes as state features.
Replay writes a fresh output directory outside its source run, never overwriting.
Verify checks references, regenerates every snapshot using the same reducer, and
compares exact bytes and report content. Source changes invalidate old evidence.
To reproduce: `python -m src.monitor replay --run-dir RUN --output-dir NEW_DIR`;
to verify: `python -m src.monitor verify --manifest NEW_DIR/manifest.json`.
