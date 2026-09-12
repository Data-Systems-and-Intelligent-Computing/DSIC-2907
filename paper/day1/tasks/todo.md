# Day 1 checklist

- [x] Inspect workspace and supplied official dataset schema/counts.
- [x] Revise plan with the requested 12-task order, acceptance and verification.
- [x] User approved the revised plan and dependencies before implementation.

## Ordered execution

- [x] 1. Verify/freeze dataset identity and schema in `data/manifests/dataset.json`:
  name/variant, filenames, row/class counts, label semantics, ordered columns,
  per-split dtypes, parsing schema and source SHA256 values; reject surprises.
- [x] 2. Add foundation/configuration and approved dependencies; preserve the
  fixed model/run settings and ignore raw data/large generated artifacts.
- [x] 3. Persist deterministic stratified train-fit/validation indices before
  any preprocessing fit; verify disjointness, coverage and source linkage.
- [x] 4. Fit preprocessing exclusively on train-fit; y = label; exclude id,
  attack_cat and label from X; no validation/test learning or target inference.
- [x] 5. Implement validation/test transforms with no refit, unknown-category
  safety, sparse output and deterministic features; use synthetic test data here.
- [x] 6. Pass preprocessing tests and generate real-data fitted pipeline,
  indices, feature names, configuration and manifest from training only.
- [x] 7. Implement/test all binary metrics with Attack positive, Average
  Precision for AUPRC, threshold 0.5, and matrix [[TN, FP], [FN, TP]].
- [x] 8. Train the fixed 128/64 CPU MLP for 10 epochs with seed 42, dropout 0.1,
  batch 512, Adam and learning rate 0.001; save final checkpoint and metadata.
- [x] 9. Record final validation sanity metrics at threshold 0.5 without
  refitting, tuning or accessing official test data.
- [x] 10. Run one explicit frozen-test evaluation using saved checkpoint and
  preprocessing; verify test identity, apply threshold 0.5, write metrics JSON.
- [x] 11. Audit persisted checkpoint/manifests/results and all provenance links,
  counts, prevalence, versions, CPU device, parameter count and duration.
- [x] 12. Pass full pytest, Ruff and build; finish README reproduction commands
  and inspect artifacts without rerunning official-test evaluation.

## Required automated evidence

- [x] Dataset: exact official schema recognized; unexpected/ambiguous schemas
  fail; labels valid; manifest contains both source hashes and observed counts.
- [x] Split: stratified validation created before fit; same seed reproduces
  membership/order; train-fit/validation indices disjoint and exhaustive.
- [x] Fit: train-fit rows alone determine scaler statistics and encoder
  categories; validation and test cannot influence learned preprocessing.
- [x] Transform: validation and test transformation never refit or mutate
  learned state; unseen categories safe; sparse output and stable order/dimensions.
- [x] Features/target: label supplies 0 Normal / 1 Attack directly; id,
  attack_cat and label excluded; attack_cat never supplies the binary target.
- [x] Metrics: expected controlled values, Attack positive, matrix ordering,
  threshold 0.5, and clear failures for malformed/undefined inputs.
- [x] Training: seeded Python/NumPy/PyTorch and fixed shuffle generator reproduce
  split/order within the environment; I/O guard proves no official-test access.
- [x] Evaluation: existing checkpoint required; saved pipeline used without
  refit; fixed 0.5 threshold; all metrics and required provenance in JSON.
- [x] Provenance: hash chain resolves; modified/mismatched sources or artifacts
  rejected; final results cannot be accidentally overwritten.

## Completion gate

- [x] Official dataset identity, schema, hashes and counts persisted.
- [x] y = label; id, attack_cat, label absent from model inputs.
- [x] Validation split precedes all learned preprocessing; fit uses train-fit only.
- [x] Official test isolated after identity audit until explicit final evaluation.
- [x] Fixed CPU MLP trained and final validation/test metrics persisted.
- [x] Checkpoint -> preprocessing manifest -> dataset manifest -> source hashes
  verifiable from final result JSON; authoritative artifacts do not require dense arrays.
- [x] Seeds, model config, versions, device, parameter/input counts, split/class
  counts, positive prevalence, duration and final validation metrics recorded.
- [x] All automated tests, lint/format checks and package build pass.
- [x] README has exact commands, dataset placement, metric definitions,
  artifact paths and environment-specific reproducibility limits.
- [x] No protected Git metadata altered; no Day 2 or FL work started.

Status: Day 1 complete. All 46 tests pass; Ruff lint/format checks and source/wheel
build pass. Real data preprocessing and ten-epoch CPU training completed, followed
by exactly one explicit frozen-test evaluation. Artifact hashes were verified
without reopening test data. See README.md and results/processed/centralized_seed42_test.json.
