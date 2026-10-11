# Day 5 implementation plan: communication byte accounting

## Scope and current state

Make B0's message accounting complete and auditable at its actual application
message boundary. Record upload, download, combined, and cumulative serialized
bytes; separate serialization and local-training duration from the run clock;
and verify the counts from saved messages during replay. Preserve the Day 3/4
pilot artifacts and their schema-1 replay. Do not add compression, an adaptive
policy, a network simulator, dependencies, or an official-test evaluation.

`src/client.py` serializes messages with `torch.save` into bytes. `src/b0.py`
passes those bytes through a local `ProcessPoolExecutor`, saves each payload,
logs `len(payload)` separately for downloads and uploads, and checks those
lengths during replay. The current summary has separate serialized totals but
no combined/cumulative total or serialization duration. `local_train_seconds`
and run wall-clock duration already exist. `tests/test_byte_accounting.py` is a
placeholder. `src/monitor.py` is also a placeholder; keep the accounting next to
the current serializer and B0 event/replay path instead of creating a second
event writer.

The Day 4 approved plan/checklist are retained as `tasks/day4-plan.md` and
`tasks/day4-todo.md`. This document and `tasks/todo.md` are the active Day 5
files.

## Measurement contract

- Count the exact byte string passed as each B0 application message. It already
  includes PyTorch's serialized tensor values, container headers, and message
  metadata. There is currently **no B0 application protocol frame**, so its
  measured frame length is 0. If an explicit frame is added, count its actual
  serialized bytes before transport with the same rule for every policy.
- For the dense B0 message, report tensor-value bytes separately from the
  remaining serialization overhead. The authoritative communication count is
  the complete serialized message length, not parameter count or tensor density.
  Define `total_bytes = upload_bytes + download_bytes` for each run and as a
  cumulative event total. Do not count model checkpoints or event logs as
  client communication.
- The CPU executor's private IPC envelope is opaque to this application. Mark
  it unmeasured in the manifest and never call the application-message count
  physical-network bytes. Record download preparation/serialization duration
  around model-state retrieval and `serialize_message`; time upload
  `serialize_message` in the worker. Keep `local_train_seconds` separate. Expose
  `transfer_seconds: null` with an explicit `unmeasured_process_pool_ipc` reason;
  do not infer transfer time by subtracting concurrent training from wall clock.
- Put cumulative counted bytes on each validation observation. A frozen
  Macro-F1 target is still pending; do not invent one for Day 5. The saved
  cumulative curve supports later bytes-to-target calculation at the first
  qualifying observed validation point.
- New runs use summary schema 3. Replay must keep accepting immutable schema-1
  Day 3 evidence and schema-2 Day 4 test runs, checking only fields those
  schemas actually contain.

Dependency flow: message boundary and validation -> per-transfer logging and
timing -> aggregation and replay -> fresh Day 5 pilot -> documented gate.

## Task 1: Validate and measure one serialized message

**Description:** Reuse the existing serializer to establish exact payload,
framing, dense tensor-value, and serialization-overhead counts. Replace the
byte-accounting placeholder test with real payload checks.

**Acceptance criteria:**
- [x] A dense model download and dense delta upload report their own exact
  `len(serialized_message)`; tensor-value plus serialized overhead equals that
  length, including metadata and container headers.
- [x] The B0 application-frame count is explicitly 0; an empty, non-byte, or
  unreadable payload fails clearly before it can be counted as a transfer.
- [x] Upload and download identities cannot be exchanged without a test failure.

**Verification:** `pytest -q tests/test_byte_accounting.py tests/test_client.py`;
Ruff check/format for touched Python files.

**Dependencies:** None.

**Files likely touched:** `src/client.py`, `tests/test_byte_accounting.py`,
`tests/test_client.py`.

**Estimated scope:** Medium, 2-3 files.

## Task 2: Record per-transfer bytes and timing boundaries

**Description:** Extend B0's existing download/arrival events with the Task 1
breakdown and serialization timing. The worker reports upload serialization
duration as executor-result metadata alongside the serialized upload bytes; it
cannot accurately time serialization by embedding its own duration in that same
payload. The server records download serialization duration. Preserve the
existing local-training and elapsed wall-clock fields.

**Acceptance criteria:**
- [x] Every completed upload/download event identifies direction, payload
  bytes, frame bytes, counted bytes, tensor-value bytes, serialization overhead,
  and nonnegative serialization duration.
- [x] `local_train_seconds`, run wall-clock time, and the unavailable transfer
  time are separate fields with unambiguous definitions; no value is labeled
  network transfer time under the process-pool pilot.
- [x] Rejected or malformed uploads do not silently enter accepted-update
  counts, while bytes already dispatched/received remain auditable.

**Verification:** `pytest -q tests/test_byte_accounting.py tests/test_b0.py`;
inspect a controlled run's saved payload lengths against its event log.

**Dependencies:** Task 1.

**Files likely touched:** `src/b0.py`, `src/client.py`,
`tests/test_byte_accounting.py`, `tests/test_b0.py`.

**Estimated scope:** Medium, 4 files.

### Checkpoint after Tasks 1-2

- [x] Exact download/upload lengths and overhead decomposition pass on dense
  messages, including a malformed-payload case.
- [x] Timing labels cannot be mistaken for measured network transfer time.

## Task 3: Reconcile totals, validation bytes, and replay

**Description:** Build summary totals from transfer events, attach the running
total to validation observations, and verify every new field from saved
messages on replay. Keep legacy replay read-only.

**Acceptance criteria:**
- [x] New completed summaries report upload, download, and total counted
  bytes; `total = upload + download`, and each equals the event/payload sum.
- [x] Cumulative total bytes never decreases and each validation observation
  records the total reached by that server version; no unfrozen target is used.
- [x] Schema-3 replay reproduces per-direction and combined totals and rejects
  tampered byte/overhead records even if artifact hashes are refreshed; schema-1
  and schema-2 replay remain valid.

**Verification:** `pytest -q tests/test_byte_accounting.py tests/test_b0.py`;
read-only replay of `results/raw/b0_day3_seed42`.

**Dependencies:** Tasks 1-2.

**Files likely touched:** `src/b0.py`, `tests/test_b0.py`,
`tests/test_byte_accounting.py`.

**Estimated scope:** Medium, 3 files.

## Task 4: Capture a fresh measured B0 pilot

**Description:** Copy the Day 3 B0 configuration to fresh Day 5 run/summary
paths, run one CPU pilot with the same fixed training and policy settings, and
save a separate replay receipt. Keep the old pilot untouched. Live arrival
ordering can vary, so this is accounting evidence rather than a paired policy
comparison.

**Acceptance criteria:**
- [x] The new configuration changes only artifact paths and its descriptive
  label; it does not change model, training, partition, policy, or stop settings.
- [x] A completed schema-3 run and replay receipt agree on upload, download,
  total, and cumulative validation bytes; every saved message hash resolves.
- [x] The official test CSV is not opened; old Day 3/4 artifact hashes are
  unchanged and existing outputs are never overwritten.

**Verification:** `python -m src.b0 train --config configs/day5_b0.yaml`, then
`python -m src.b0 replay --run-dir results/raw/b0_day5_seed42 --output
results/processed/b0_day5_seed42_replay.json`; compare manifests and hashes.

**Dependencies:** Task 3.

**Files likely touched:** `configs/day5_b0.yaml`,
`results/processed/b0_day5_seed42.json`,
`results/processed/b0_day5_seed42_replay.json` (raw run under ignored
`results/raw/b0_day5_seed42/`).

**Estimated scope:** Medium, 3 tracked files plus raw evidence.

### Checkpoint after Tasks 3-4

- [x] New and legacy replays pass; the new receipt reconciles with its log and
  message files.
- [x] The scope of every measured and unmeasured byte/time field is explicit.

## Task 5: Record the Day 5 gate

**Description:** Document the accounting equation, measured boundary, timing
limits, fresh run results, and exact verification commands. Update status only
after the test/build/replay gates pass.

**Acceptance criteria:**
- [x] A Day 5 journal links the new configuration, run, and replay receipt and
  reports exact upload/download/total bytes and overhead scope.
- [x] README and technical status identify Day 5 as complete only for the
  application-message boundary, with the executor envelope and transfer time
  explicitly unmeasured and no compression-saving claim.
- [x] Full pytest, Ruff lint/format, package build, read-only legacy replay,
  new replay, and `git diff --check` pass.

**Verification:** Run the full commands above and compare old artifact hashes
again after documentation. Review all links and the active checklist.

**Dependencies:** Task 4.

**Files likely touched:** `paper/docs/Jurnal/Day-5-Byte-Accounting.md`,
`README.md`, `teknis-lab/README.md`, `tasks/todo.md`.

**Estimated scope:** Medium, 4 files.

### Completion checkpoint

- [x] Every counted byte comes from an exact saved serialized transfer;
  upload, download, combined, and cumulative totals reconcile on run and replay.
- [x] Serialization, local training, wall-clock, and unmeasured transfer timing
  are distinguishable; no physical-network claim is made from the CPU executor.
- [x] The Day 5 pilot is reproducible from its immutable configuration and
  artifacts, and no previous pilot artifact was changed.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Payload length is mislabeled as physical network traffic | Name the application-message boundary, record frame length 0 and opaque IPC envelope as unmeasured. |
| Metadata or future sparse indices disappear from the estimate | Treat full serialized length as authoritative and report tensor-value bytes only as a decomposition. |
| Concurrent durations are subtracted into a fictitious transfer time | Record serialization and local training at their own boundaries; keep transfer time null under the opaque executor. |
| New accounting breaks old evidence | Bump new runs to schema 3, gate new replay checks by schema, and leave Day 3/4 artifacts untouched. |
| Arrival order changes live byte totals | Treat the new pilot as one measured trace, not a paired policy comparison; replay its exact recorded order. |

## Open question for protocol freeze

A future real network transport must define and measure its own framing and
one-way transfer timing before network-byte or transfer-latency claims. This
does not block the Day 5 application-message accounting gate.
