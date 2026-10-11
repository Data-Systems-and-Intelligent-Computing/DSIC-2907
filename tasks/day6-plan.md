# Day 6 implementation plan: 25/50/100% update budgets

## Scope and current state

Implement a fixed grid of `0.25`, `0.50`, and `1.00` update budgets with
magnitude top-k on each delta tensor. Keep local training fixed. Encode the
selected values, indices, and reconstruction metadata into actual upload
bytes; decode and apply them; measure all three actions against the same saved
Day 5 delta. This is an operator and controlled application probe, not the
later demand-to-budget policy or a new asynchronous policy run. Do not read
the official test CSV, add dependencies, or change the frozen B0 policy.

`FLClient.train` currently returns a dense delta. `src/client.py` uses
`torch.save`/`torch.load` for application messages, and Day 5 counts their
exact serialized bytes. `AsyncServer.apply_update` accepts only budget `1.0`
and applies a validated dense tensor map. `src/compressor.py` and
`tests/test_budget_operator.py` are placeholders. The completed Day 5 pilot
has saved matching upload/download bytes under
`results/raw/b0_day5_seed42/messages/`. The previous plan and checklist
are preserved as `tasks/day5-plan.md` and `tasks/day5-todo.md`.

## Frozen operator and payload contract

- Accept exactly the three actions. For each nonempty tensor with `N`
  entries, retain `k = ceil(qN)` independently. Rank by descending absolute
  magnitude, then ascending row-major flat index for ties. Emit chosen entries
  in ascending flat-index order for canonical serialization. Report actual
  retained counts because rounding can exceed the nominal share.
- Sparse actions carry selected values and `int32` flat indices plus format
  version, operator, budget, tensor names, shapes, dtypes, and counts. Reject
  tensors too large for this index format and unsupported/nonfinite tensors.
  Omitted positions reconstruct as zero. The wire message must not contain a
  second dense delta copy.
- Budget `1.00` retains every entry and uses the current dense upload form
  without redundant indices. This preserves Day 5's B0 baseline. Direct
  operator inspection still obeys the same full-retention rule.
- Reuse `serialize_message`/`deserialize_message`. Before server mutation,
  validate format/version, tensor names/counts, shapes/dtypes, selected counts,
  index type/uniqueness/range, finite values, and model compatibility. Reject
  malformed payloads without changing model/version.
- Keep `AsyncServer`'s default permitted budget at `1.0`; enable the grid only
  by explicit construction for this probe. Feed reconstructed dense deltas to
  its existing weighted apply logic. B0 configuration/replay still reject
  sparse budgets until a later integration stage.
- Compare exact serialized upload lengths using one saved Day 5 full delta.
  Count selected value bytes, index bytes, and all remaining metadata and
  serialization overhead. Include the unchanged matching download in total
  per-contribution bytes. Report signed absolute and percentage differences
  from `1.00`, even if an action costs more. These are application-message
  bytes, not physical-network bytes. Measure compression/serialization time
  separately from the already completed local training.

Dependency flow: selection -> wire round-trip -> server application -> real
delta byte probe -> documentation and gate.

## Task 1: Implement deterministic per-tensor selection

**Description:** Replace the compressor placeholder with the frozen magnitude
top-k rule, independent of local training and server state.

**Acceptance criteria:**
- [x] Each tensor retains exactly `ceil(qN)` entries for all three actions;
  values and flat indices match the source tensor.
- [x] Equal magnitudes resolve by ascending flat index, including boundary
  ties; repeated calls produce the same selection and output order.
- [x] Invalid action, empty/nonfinite or unsupported tensor, and index-range
  overflow fail clearly without a partial result.

**Verification:** `pytest -q tests/test_budget_operator.py`; Ruff check/format
for touched Python files.

**Dependencies:** None.

**Files likely touched:** `src/compressor.py`, `tests/test_budget_operator.py`.

**Estimated scope:** Small, 2 files.

## Task 2: Round-trip the versioned sparse upload

**Description:** Encode a complete update for sparse actions, serialize it
with existing client functions, deserialize it, and reconstruct the delta.
Preserve the exact dense form for action `1.00`.

**Acceptance criteria:**
- [x] Sparse actions round-trip every tensor to its original shape/dtype,
  preserve selected values at their indices, and zero omitted entries.
- [x] Sparse wire messages contain only selected values/indices and metadata;
  the dense `1.00` message remains compatible with the B0 form.
- [x] Bad format/version, count/name mismatch, invalid metadata, duplicate or
  out-of-range indices, and nonfinite values are rejected before apply.

**Verification:** `pytest -q tests/test_budget_operator.py tests/test_client.py`;
Ruff check/format for touched Python files.

**Dependencies:** Task 1.

**Files likely touched:** `src/compressor.py`, `src/client.py`,
`tests/test_budget_operator.py`, `tests/test_client.py`.

**Estimated scope:** Medium, 4 files.

### Checkpoint after Tasks 1-2

- [x] Selection and sparse/dense round-trips pass, including malformed
  metadata and tie cases.
- [x] Sparse bytes contain no full delta copy; local training is unchanged.

## Task 3: Apply reconstructed updates under explicit opt-in

**Description:** Permit the Day 6 grid in a controlled `AsyncServer` instance
and pass decoded dense deltas through its existing sample-weighted apply path.
Retain the default B0 full-budget guard.

**Acceptance criteria:**
- [x] Reconstructed `0.25`, `0.50`, and `1.00` updates produce the expected
  weighted model change and exactly one version increment each.
- [x] A default server still rejects sparse budgets, and B0 configuration
  still rejects a non-full budget.
- [x] Corrupt/incompatible sparse updates and illegal labels leave model
  parameters and server version unchanged.

**Verification:** `pytest -q tests/test_async_apply.py tests/test_budget_operator.py tests/test_b0.py`;
Ruff check/format for touched Python files.

**Dependencies:** Task 2.

**Files likely touched:** `src/async_server.py`, `src/compressor.py`,
`tests/test_async_apply.py`, `tests/test_budget_operator.py`.

**Estimated scope:** Medium, 4 files.

## Task 4: Measure three actions on one saved real delta

**Description:** Add a repeatable controlled probe using one Day 5 saved
upload and its matching download. Produce a new processed report; never
overwrite Day 5 run or replay artifacts.

**Acceptance criteria:**
- [x] Report source paths/hashes, operator and format versions, actual retained
  counts, exact upload value/index/other bytes, unchanged download bytes, total
  bytes, and signed savings against `1.00` for every action.
- [x] The same original delta feeds every action without retraining; each
  payload decodes and applies to an independent server initialized from the
  matching download, with the expected model effect.
- [x] Tests recompute counts from emitted bytes, include index/metadata cost,
  and permit negative savings.

**Verification:** Run the probe on a fixed Day 5 job; run
`pytest -q tests/test_budget_operator.py tests/test_byte_accounting.py tests/test_async_apply.py`;
compare source hashes and report byte equations.

**Dependencies:** Task 3.

**Files likely touched:** `src/compressor.py`, `tests/test_budget_operator.py`,
`tests/test_byte_accounting.py`,
`results/processed/b0_day6_budget_probe_seed42.json`.

**Estimated scope:** Medium, 4 files.

### Checkpoint after Tasks 3-4

- [x] All real-delta payloads decode and apply under opt-in; default B0 and
  replay remain valid.
- [x] Actual differences come from serialized bytes including indices and
  metadata, not from parameter-retention percentages.

## Task 5: Record and verify the Day 6 gate

**Description:** Document the contract, probe results, provenance, and B0
boundary. Update status only after verification passes.

**Acceptance criteria:**
- [x] A Day 6 journal links the report and records exact results, tie rule,
  reconstruction checks, byte equation, and limits.
- [x] README and technical status mark Day 6 complete only for the operator
  and controlled probe, without implying an adaptive policy or network count.
- [x] Full pytest, Ruff lint/format, package build, read-only legacy and Day 5
  B0 replays, and `git diff --check` pass; old artifact hashes stay unchanged.

**Verification:** Run the commands above, inspect the report against saved
messages, and review the checklist.

**Dependencies:** Task 4.

**Files likely touched:** `paper/docs/Jurnal/Day-6-Update-Budgets.md`,
`README.md`, `teknis-lab/README.md`, `tasks/todo.md`.

**Estimated scope:** Medium, 4 files.

### Completion checkpoint

- [x] Three actions select, reconstruct, and apply correctly.
- [x] Exact serialized costs and signed savings are reproducible from one
  saved delta and include values, indices, and metadata.
- [x] Fixed compute and dense B0 remain intact; no official-test or physical
  network-saving claim is made.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `ceil(qN)` retains more than the nominal share for small tensors | Medium | Report actual per-tensor and total counts. |
| Indices/metadata erase savings, especially at `0.50` | High | Count exact bytes and permit signed negative savings. |
| Ties change selection across runs | High | Freeze rank/order and test boundary ties. |
| Malformed payload mutates a model | High | Validate fully before apply; test state/version unchanged. |
| Sparse opt-in changes B0 evidence | High | Keep default guard and B0 config rejection; use a new report path and read-only replay. |
| IPC counts mistaken for network cost | Medium | Label the application boundary; leave private IPC unmeasured. |

## Human review gate

- [x] Review and approve this plan and `tasks/todo.md` before Day 6 code
  implementation, as required by the planning-and-task-breakdown skill.
