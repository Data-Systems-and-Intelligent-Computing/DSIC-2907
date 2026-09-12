# Day 1 implementation plan

## Scope and current state

Implement only UNSW-NB15 binary preprocessing and one centralized MLP sanity
baseline. No Federated Learning, asynchronous execution, demand estimation,
scheduling, compression, or network emulation. The model is a sanity baseline,
not the research contribution.

Project root: `Code/demand-aware-async-fl-nids/`. The existing official CSV pair
is under `../Data/UNSW-NB15/OneDrive_3_9-7-2026/CSV Files/Training and Testing Sets/`
relative to that root. No Python implementation or usable Git repository exists.
The approved Day 1 implementation is complete. Dataset identity is frozen in
`data/manifests/dataset.json`; execution evidence is recorded below and in
`tasks/todo.md`. The original implementation sequence is retained for audit.

## Dataset contract: freeze before preprocessing

Dataset name: `UNSW-NB15`. Variant: `official training/testing CSV pair`.
Use the files already present; do not substitute the four full-dataset CSVs,
resplit a combined dataset, download a different variant, or infer split roles.

| Split | Filename | Rows | Normal (0) | Attack (1) |
| --- | --- | ---: | ---: | ---: |
| Official training | UNSW_NB15_training-set.csv | 175341 | 56000 | 119341 |
| Official test | UNSW_NB15_testing-set.csv | 82332 | 37000 | 45332 |

These counts were observed locally and must be verified again when freezing.
Read UTF-8-sig to handle the observed BOM. The expected ordered source columns
after BOM decoding are:

```text
id, dur, proto, service, state, spkts, dpkts, sbytes, dbytes, rate,
sttl, dttl, sload, dload, sloss, dloss, sinpkt, dinpkt, sjit, djit,
swin, stcpb, dtcpb, dwin, tcprtt, synack, ackdat, smean, dmean,
trans_depth, response_body_len, ct_srv_src, ct_state_ttl, ct_dst_ltm,
ct_src_dport_ltm, ct_dst_sport_ltm, ct_dst_src_ltm, is_ftp_login,
ct_ftp_cmd, ct_flw_http_mthd, ct_src_ltm, ct_srv_dst, is_sm_ips_ports,
attack_cat, label
```

Reject missing, extra, duplicate, ambiguous, or unexpectedly ordered headers and
invalid dtypes/values with actionable errors. Do not silently alias unknown
columns or infer label semantics. Only the observed BOM variation is accepted;
other variants require explicit inspection and a documented schema change.
Inspect and record each split's observed dtypes and the explicit parsing schema.
CSV dtypes are a parsing contract, not intrinsic file metadata.

The target is exactly `y = label`, restricted to 0 = Normal and 1 = Attack.
Never derive it from `attack_cat`. Exclude `id`, `attack_cat`, and `label` from
model input. `attack_cat` leaks attack-category information. The remaining
42 source features comprise categorical `proto`, `service`, `state` and
39 numerical columns, with their ordered lists recorded explicitly.

Create `data/manifests/dataset.json` containing dataset name/variant, source
paths and filenames, per-file SHA256, train/test row counts and observed class
counts, target column, label semantics, ordered source columns, observed dtypes,
and parsing schema. Hash the saved manifest's exact bytes; keep its SHA256 in
downstream artifacts rather than placing a self-referential hash inside it.
Source hashes identify the local files; they do not establish upstream
authenticity independently. Later source hash mismatches must fail.

## Leakage controls and artifact design

Required order:

```text
official training -> stratified train-fit + validation
                  -> fit preprocessing on train-fit only
                  -> transform validation with saved fitted preprocessing
                  -> final evaluation transforms frozen official test
```

Use a configured validation fraction of 0.20 and seed 42; this is a fixed Day 1
default, not a tuned choice. Persist original zero-based row indices with source
hash linkage. Indices must be disjoint, exhaustive over official training, and
reproducible. All learned preprocessing (scaler, encoder, any future imputer)
must fit on train-fit rows only, never validation, test, or combined splits.
For Day 1, fail clearly on missing/nonfinite values rather than learn imputation
statistics unless inspection demonstrates a need within this scope.

Use a sklearn ColumnTransformer with StandardScaler for numerical columns and
OneHotEncoder(handle_unknown="ignore") for categoricals. Preserve sparse output;
do not make full dense transformed arrays authoritative. For the small PyTorch
MLP, densify only the current batch if needed. Persist the fitted preprocessing
pipeline, split indices, dataset and preprocessing manifests, ordered transformed
feature names, configuration snapshots and hashes. Optional transformed caches
must be sparse where appropriate, regenerable, and linked to these artifacts.

The initial dataset audit may read both CSVs solely for identity/schema/value
validation and required counts/dtypes/hashes. Thereafter training, preprocessing
fit, and validation commands must not open official test data or test arrays,
including for hash verification. They may read frozen manifest metadata.
Task 5 implements the test transformation path and verifies it using synthetic
fixtures; the real official test is next opened only by task 10's explicit final
evaluation command. This reconciles early transformation tests with test isolation.

The separate final evaluation command requires an existing saved checkpoint,
loads the saved preprocessing artifacts, verifies the linked dataset identity
and test file hash, transforms the official test without fitting, applies fixed
threshold 0.5, and writes final metrics JSON. No test score can choose epochs,
learning rate, architecture, preprocessing, threshold, or checkpoint. No tuning,
calibration, hyperparameter search, or early stopping is part of Day 1.

## Model, metrics, and practical reproducibility

Fixed model: input -> Linear(128) -> ReLU -> Dropout(0.1) -> Linear(64) -> ReLU
-> Linear(1). Train logits using binary cross-entropy with logits; apply sigmoid
for Attack probabilities at evaluation. Use CPU, seed 42, 10 epochs, batch size
512, Adam, learning rate 0.001. Save the final epoch checkpoint, not one selected
by test results. Record final validation metrics without adjusting these choices.

Seed Python, NumPy, and PyTorch. Use a fixed DataLoader shuffle generator and
deterministic stratified splitting. Record dependency versions and configuration;
expect reproducibility within that environment, not universal bit-for-bit
equivalence across PyTorch/compiler/platform versions. Avoid additional machinery
for cross-platform determinism.

Primary metrics: Macro-F1, Attack-class Recall, AUPRC implemented as sklearn
`average_precision_score` and explicitly named Average Precision in documentation.
Secondary: Accuracy, AUROC, Balanced Accuracy, Confusion Matrix. Positive class
is Attack = 1. Predictions use probability >= 0.5. Confusion matrix label order
is [Normal, Attack], rows true and columns predicted: [[TN, FP], [FN, TP]].
Use probabilities for Average Precision and AUROC. Validate binary labels,
shapes, lengths, finite probabilities and [0, 1] bounds; undefined metrics on
single-class inputs must fail clearly rather than produce misleading numbers.

## Provenance contract

```text
final metrics JSON -> model checkpoint SHA256 -> preprocessing manifest SHA256
                   -> dataset manifest SHA256 -> source CSV SHA256 values
```

The checkpoint records the dataset/preprocessing manifest hashes and model
configuration. The preprocessing manifest references the dataset manifest hash,
pipeline hash, split-index hash, feature-name hash, and config fingerprints.
Saved configuration snapshots and package versions make these links interpretable.
Verify links on artifact loading; reject mismatched or stale artifacts.

Final results record run seed, complete model/optimizer configuration,
preprocessing and dataset manifest paths/IDs/SHA256, checkpoint path/SHA256,
package versions, device, trainable parameter count, final input feature count,
training duration, final validation metrics, fixed threshold, and all test metrics.
Include official-training, train-fit, validation and test sample counts, class
counts and positive-class prevalence for each. Store timing/validation details
with the training run so final evaluation can include them without retraining.
Use Git commit metadata only if a valid repository exists; otherwise record its
absence. Never initialize or alter protected Git metadata. Refuse accidental
overwrite of existing final results.

## Ordered implementation tasks

Each task is a verified increment. Source file counts below exclude generated
artifacts. Persist artifacts when first needed; task 11 audits/finalizes the
complete chain, rather than delaying checkpoint creation until after evaluation.

### 1. Dataset identity/schema verification and dataset manifest

- Acceptance: recognize the exact schema, validate label values directly, and
  verify the official pair's counts; reject unexpected/ambiguous schemas.
- Acceptance: persist dataset identity, ordered columns, dtypes, semantics,
  source SHA256 values and observed counts before preprocessing begins.
- Verification: `python -m pytest tests/test_preprocess.py -k dataset` after
  task 2 enables the test environment; run the identity audit on the local pair
  and inspect its manifest immediately using standard-library checks.
- Dependencies: none. Files: `src/preprocess.py`, `tests/test_preprocess.py`,
  generated `data/manifests/dataset.json`. Scope: small; standard-library-first
  audit avoids needing dependency installation before task 2.

### 2. Foundation/configuration

- Acceptance: installable project and explicit YAML settings for the fixed
  model, seed, split, paths, epochs, batches, optimizer and learning rate.
- Acceptance: ignore raw data, large generated artifacts and the virtualenv.
- Verification: config parsing, approved dependency installation, and task 1's
  dataset tests. Dependencies: 1 and dependency approval.
- Files: `pyproject.toml`, `.gitignore`, `configs/model.yaml`,
  `configs/experiments.yaml`. Scope: medium.

### 3. Deterministic train/validation split

- Acceptance: stratify official-training row indices before fitting anything;
  persist split indices and their source/config linkage.
- Acceptance: prove disjointness, coverage, deterministic membership/order, and
  that the splitting path never loads official test data.
- Verification: `python -m pytest tests/test_preprocess.py -k split`.
- Dependencies: 2. Files: `src/preprocess.py`, `tests/test_preprocess.py`.
  Scope: small.

### 4. Train-fit-only preprocessing

- Acceptance: y comes only from label; exclude id, attack_cat, label and keep
  numerical/categorical feature lists explicit.
- Acceptance: fit scaler/encoder exclusively on train-fit rows; extreme values
  and categories confined to validation/test cannot influence fitted statistics.
- Verification: `python -m pytest tests/test_preprocess.py -k fit` with spies
  and controlled fixtures that expose leakage.
- Dependencies: 3. Files: `src/preprocess.py`, `tests/test_preprocess.py`.
  Scope: small.

### 5. Validation/test transformation

- Acceptance: transforms never call fit or mutate fitted scaler/encoder state;
  unknown categories are safe and feature names/order/dimensions deterministic.
- Acceptance: preserve sparse representations and reload the saved pipeline;
  use synthetic test fixtures here, deferring real test transformation to task 10.
- Verification: `python -m pytest tests/test_preprocess.py -k transform`.
- Dependencies: 4. Files: `src/preprocess.py`, `tests/test_preprocess.py`.
  Scope: small.

### 6. Preprocessing tests and real-data artifact generation

- Acceptance: all dataset/split/fit/transform tests pass, including invalid
  labels, missing/ambiguous headers, feature exclusion, and train-fit isolation.
- Acceptance: generate the fitted pipeline, split indices, ordered feature
  names, config snapshot and preprocessing manifest from official training only;
  verify hashes and reject changed source/artifact content.
- Verification: `python -m pytest tests/test_preprocess.py`; real-data
  preprocessing CLI run and artifact inspection, without loading official test.
- Dependencies: 5. Files: `src/preprocess.py`, `tests/test_preprocess.py`;
  generated files in `data/processed/` and `data/manifests/`. Scope: small.

### 7. Binary metrics and controlled tests

- Acceptance: all seven metrics match controlled examples; positive class is
  Attack, matrix ordering is fixed, and AUPRC is Average Precision.
- Acceptance: malformed inputs fail clearly; tests exercise threshold 0.5.
- Verification: `python -m pytest tests/test_metrics.py`.
- Dependencies: 6. Files: `src/metrics.py`, `tests/test_metrics.py`. Scope: small.

### 8. Centralized MLP training

- Acceptance: fixed CPU MLP trains for ten epochs from train-fit data with all
  seeds set and a fixed shuffle generator; test data is never opened.
- Acceptance: save final checkpoint and training metadata, including config,
  manifest hashes, versions, device, parameter count, counts and duration.
- Verification: `python -m pytest tests/test_centralized.py -k train`; controlled
  same-environment split/shuffle/training reproducibility checks and an I/O guard
  that fails any official-test access; then run official-training CLI once.
- Dependencies: 7. Files: `src/centralized.py`, `tests/test_centralized.py`.
  Scope: small.

### 9. Validation sanity check

- Acceptance: evaluate the final saved model on validation with the fitted
  pipeline and threshold 0.5; save final validation metrics and prevalence.
- Acceptance: do not refit preprocessing or change epochs, checkpoint, model
  configuration or threshold in response to validation results for this run.
- Verification: `python -m pytest tests/test_centralized.py -k validation`;
  inspect real validation metrics and training metadata without test access.
- Dependencies: 8. Files: `src/centralized.py`, `tests/test_centralized.py`.
  Scope: small. This stage may run at the end of the training command.

### 10. One explicit frozen-test evaluation

- Acceptance: a separate evaluation command requires an existing checkpoint and
  saved preprocessing, verifies provenance/test hash, and transforms without fit.
- Acceptance: fixed threshold 0.5 produces all required metrics in final JSON;
  do not select a checkpoint or tune anything using test performance.
- Verification: `python -m pytest tests/test_centralized.py -k evaluation` with
  missing-checkpoint, threshold and isolation cases; after synthetic checks pass,
  run exactly one final evaluation on the frozen official test.
- Dependencies: 9. Files: `src/centralized.py`, `tests/test_centralized.py`.
  Scope: small.

### 11. Persist checkpoint/manifests/results/provenance

- Acceptance: audit saved artifacts and complete all required result fields,
  including per-split class counts/prevalence and final validation metrics.
- Acceptance: resolve and verify every hash in the metrics-to-source chain;
  preserve existing final results, and do not modify protected Git metadata.
- Verification: `python -m pytest tests/test_centralized.py -k provenance`;
  inspect the actual artifact chain without another test evaluation.
- Dependencies: 10. Files: `src/centralized.py`, `tests/test_centralized.py`
  as needed; previously generated manifests/checkpoint/results. Scope: small.
  Required writers and provenance tests must already pass before the task 10 run.

### 12. Full pytest, Ruff, build, README, and artifact inspection

- Acceptance: exact install, dataset-freeze, preprocess, train and explicit
  evaluate commands; artifact locations, assumptions and metric definitions
  documented, including same-environment reproducibility limits.
- Acceptance: full tests/lint/build pass and all Day 1 criteria below are checked;
  raw data remain external/ignored, with documented placement under `data/raw/`.
- Verification: `python -m pytest`, `python -m ruff check .`,
  `python -m ruff format --check .`, `python -m build`; inspect JSON/provenance
  without rerunning test evaluation. Repeat passed checks only after relevant edits.
- Dependencies: 11. Files: `README.md`, `tasks/plan.md`, `tasks/todo.md` and
  directory placeholders. Scope: documentation; split placeholders into a small
  separate increment if necessary. Retain the requested repository layout.

Checkpoints: verify identity/config after tasks 1–2; split and fit after 3–4;
preprocessing artifacts after 5–6; metrics before training; training/validation
before the sole real test evaluation; provenance and full checks at completion.
Do not rerun official-test evaluation as routine verification.

## Day 1 acceptance criteria

- Official local UNSW-NB15 train/test CSV identity, schema and SHA256 are frozen.
- y is label (0 Normal, 1 Attack); id, attack_cat and label are excluded from X.
- Validation is split before fitting; every learned preprocessor fits train-fit only.
- After the initial identity audit, official test is isolated until explicit
  final evaluation; training/validation never load its data or arrays.
- The fixed CPU MLP trains successfully; all required metrics are generated
  with Average Precision, positive class 1, and threshold 0.5 as specified.
- Pipeline, splits, configuration, checkpoint, manifests and results are saved
  and traceable by hashes; dense arrays are not authoritative artifacts.
- Automated tests, Ruff and build pass; README has exact reproduction commands
  and practical environment-specific reproducibility expectations.
- No Day 2 or FL work has started.

## Approval and execution record

The user approved the revised plan and dependencies before implementation.
NumPy, pandas, scikit-learn, PyYAML, CPU PyTorch, joblib, pytest, Ruff and build
are installed in `.venv/`; exact versions are saved in manifests/run metadata.
No subagents, external messages, merge, deployment, Git initialization or changes
to protected Git metadata were used. Commits are unavailable in this workspace.

Dataset freezing verified the previously observed official counts and schema.
Source SHA256 values:

- Train: `bec7dd5ec88dc2a0ccc7a07879d338395ed7421750f675fd0339e07dfe0648fa`
- Test: `734fe6642edf758f7c94d7d9149426b49d202fe8e7bf0bef47392489c3c0a559`

The 80/20 training split yields 140272 train-fit / 35069 validation rows.
Preprocessing uses 192 final features with sparse real-data transforms.
The MLP has 33025 trainable parameters and completed ten epochs on CPU in
5.599518 seconds (training loop only). Final validation Macro-F1 is 0.935908.

One explicit real-test evaluation produced Macro-F1 0.834634, Attack Recall
0.981007, Average Precision 0.980808, Accuracy 0.843876, AUROC 0.973654 and
Balanced Accuracy 0.828436. Matrix: [[25007, 11993], [861, 44471]]. Full-precision
results and provenance are in `results/processed/centralized_seed42_test.json`.
The artifact audit verified the saved hash chain without reopening test data.

Verification commands: `.venv/bin/python -m pytest -q` (46 passed),
`.venv/bin/python -m ruff check .`, `.venv/bin/python -m ruff format --check .`,
and `.venv/bin/python -m build`. Build network access required sandbox escalation.
`MANIFEST.in` includes configuration files and shared test fixtures in the source
distribution. Reproduction commands and limitations are in README.md.

No Day 2 work started. Practical limits: hashes identify the supplied files but
are not independently certified upstream checksums; absolute artifact paths need
regeneration after relocation; numerical reproducibility is environment-specific.
