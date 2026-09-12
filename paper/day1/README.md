# Demand-aware asynchronous FL NIDS — Day 1

Research topic: *Demand-Aware Adaptive Participation and Update Budgeting for
Communication-Efficient Asynchronous Federated Network Intrusion Detection under
Non-IID Data.*

This repository currently implements **only** UNSW-NB15 binary preprocessing and
one centralized MLP sanity baseline. Federated Learning, asynchronous execution,
demand estimation, scheduling, compression and network emulation are not implemented.

## Dataset and frozen protocol

Use the **official training/testing CSV pair**, available from the
[UNSW dataset page](https://research.unsw.edu.au/projects/unsw-nb15-dataset).
Follow the dataset authors' citation requirements on that page. Do not substitute
the four full-dataset CSVs or combine/resplit the official train/test pair.

| File | Rows | Normal (0) | Attack (1) |
| --- | ---: | ---: | ---: |
| UNSW_NB15_training-set.csv | 175341 | 56000 | 119341 |
| UNSW_NB15_testing-set.csv | 82332 | 37000 | 45332 |

The target is exactly `y = label`: 0 = Normal, 1 = Attack. `attack_cat` never
determines the target. Input excludes `id`, `attack_cat`, and `label`; using
`attack_cat` as a feature would leak attack-category information.

The source schema has 45 ordered columns (42 usable features), categorical
`proto`, `service`, `state`, and 39 numerical features. The supplied CSVs have a
UTF-8 BOM, handled with `utf-8-sig`. Unexpected names/order, duplicate headers,
invalid labels, missing values and nonfinite numeric values are rejected. The
observed schema and parsing dtypes are recorded in the dataset manifest; no
unknown distribution is silently interpreted.

The initial `freeze` command audits both files for identity/schema, counts and
SHA256 only. After that, `prepare` and `train` open **only official training**.
An 80/20 stratified split with seed 42 yields 140272 train-fit and 35069 validation
rows. StandardScaler and OneHotEncoder fit exclusively on train-fit rows.
Validation is transformed without fitting. Unknown categories use
`handle_unknown="ignore"` (all-zero indicators for that categorical field).
No imputer, feature selection, class rebalancing or learned threshold is used.

The official test is next opened only by the separate `evaluate` command after
training. It never selects preprocessing, epochs, architecture, learning rate,
checkpoint, or threshold, and must not inform later demand logic. Day 1 has no
hyperparameter search or early stopping. Validation metrics are a final sanity
report, not a selection mechanism for this run.

## Reproduction commands

Run from this project directory. Python 3.11+ is required. The commands below are
the initial-run workflow; it has already been executed in the supplied workspace.
Existing manifests, preprocessing outputs, run directories and final results are
protected from overwrite. To inspect the completed run, use the inspection
commands below rather than reevaluating the test set.

Install in an isolated environment (CPU PyTorch first avoids CUDA downloads):

```bash
cd /home/fadil/DSIC-2907/DSIC-2907
python3 -m venv .venv
.venv/bin/python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -e '.[dev]'
```

The official files already present in this workspace can be used in place,
without copying large data into the project:

```bash
.venv/bin/python -m src.preprocess freeze \
  --train 'data/raw/UNSW-NB15/OneDrive_3_9-7-2026/CSV Files/Training and Testing Sets/UNSW_NB15_training-set.csv' \
  --test 'data/raw/UNSW-NB15/OneDrive_3_9-7-2026/CSV Files/Training and Testing Sets/UNSW_NB15_testing-set.csv' \
  --output data/manifests/dataset.json
```

On another machine, download the pair from UNSW and place them in `data/raw/`.
That directory is ignored by Git. Use this alternative freeze command:

```bash
.venv/bin/python -m src.preprocess freeze \
  --train data/raw/UNSW_NB15_training-set.csv \
  --test data/raw/UNSW_NB15_testing-set.csv \
  --output data/manifests/dataset.json
```

Then preprocess, train/validate, and perform the explicit final evaluation:

```bash
.venv/bin/python -m src.preprocess prepare --config configs/day1_experiments.yaml
.venv/bin/python -m src.centralized train \
  --config configs/day1_experiments.yaml --model-config configs/day1_model.yaml
.venv/bin/python -m src.centralized evaluate \
  --checkpoint results/raw/centralized_seed42/model.pt \
  --output results/processed/centralized_seed42_test.json
```

For an independent reproduction, reserve fresh output paths in a copied
experiment configuration and pass that configuration explicitly. Never overwrite
the archived run or compare test scores to choose settings. Archived absolute paths retain their original provenance. The migration map in
`data/manifests/relocation.json` resolves them relative to this repository; loaders
still verify every SHA256. Do not edit archived manifests or repeat evaluation.

Inspect the saved reports without loading or reevaluating test data:

```bash
.venv/bin/python -m json.tool data/manifests/dataset.json
.venv/bin/python -m json.tool data/manifests/preprocessing.json
.venv/bin/python -m json.tool results/raw/centralized_seed42/training.json
.venv/bin/python -m json.tool results/processed/centralized_seed42_test.json
```

## Model and metric definitions

`input -> Linear(128) -> ReLU -> Dropout(0.1) -> Linear(64) -> ReLU -> Linear(1)`.
Train logits using BCEWithLogitsLoss; sigmoid produces Attack probabilities.
The default configuration uses seed 42, ten epochs, batch size 512, Adam with
learning rate 0.001, CPU and one CPU thread. Save the final epoch checkpoint.
The MLP is a sanity baseline, not the research contribution.

| JSON metric | Definition |
| --- | --- |
| `macro_f1` | Unweighted mean of Normal and Attack F1 |
| `attack_recall` | Recall with positive class Attack = 1 |
| `auprc_average_precision` | sklearn `average_precision_score`, Average Precision |
| `accuracy` | Correct predictions / samples |
| `auroc` | ROC area from Attack probabilities |
| `balanced_accuracy` | Mean of Normal and Attack recall |
| `confusion_matrix` | Rows true, columns predicted; [Normal, Attack]; [[TN, FP], [FN, TP]] |

The first three metrics are primary. Predictions are Attack if probability
**>= 0.5**. Average Precision and AUROC use probabilities, not thresholded labels.
Average Precision is the non-interpolated PR summary documented by
[scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html);
it is not trapezoidal interpolation of a PR curve. Metric inputs must contain
both classes; malformed inputs and undefined single-class evaluations fail clearly.

## Artifacts and provenance

| Location | Contents |
| --- | --- |
| `data/manifests/dataset.json` | Dataset identity, source hashes, schema/dtypes, labels, counts |
| `data/manifests/preprocessing.json` | Dataset manifest hash, artifact hashes, fit scope, split counts, versions |
| `data/processed/pipeline.joblib` | Fitted train-fit-only ColumnTransformer |
| `data/processed/split_indices.npz` | Original zero-based official-training row positions for each subset |
| `data/processed/feature_names.json` | Ordered final transformed features |
| `data/processed/preprocessing_config.json` | Configuration snapshot |
| `results/raw/centralized_seed42/configuration.json` | Saved model and experiment configuration |
| `results/raw/centralized_seed42/model.pt` | Final weights and run metadata |
| `results/raw/centralized_seed42/training.json` | Checkpoint SHA256, training metadata, final validation metrics |
| `results/processed/centralized_seed42_test.json` | Final test metrics and complete provenance |

Trace `metrics -> checkpoint SHA256 -> preprocessing manifest SHA256 -> dataset
manifest SHA256 -> source CSV SHA256`. The preprocessing manifest also hashes
the pipeline, indices, feature names and configuration. Artifact loaders reject
changed hashes. Training verifies only training source bytes; final evaluation
verifies test source bytes. Test counts in training reports come from the frozen
identity manifest, not from reopening test data.

The final report includes seeds, model configuration, actual Adam defaults,
package versions for training/evaluation, device/thread count, trainable parameter
and input counts, per-split sample/class counts and positive prevalence, training
duration (training loop only), per-epoch training loss and final validation metrics.
Git metadata is null when no valid repository exists; no Git metadata is created.

The fitted pipeline and split indices are authoritative. No transformed arrays
are persisted. The real one-hot feature matrix remains sparse in memory; only a
minibatch is densified for PyTorch. sklearn can return dense output for a completely
dense tiny fixture, which is also supported. Large artifacts and raw data are
ignored by Git; retain them externally alongside the small manifests/results.
Use only trusted local joblib/checkpoint artifacts; fingerprints detect accidental
mixing or changes, not malicious replacement of an entire provenance chain.

Python, NumPy and PyTorch are seeded, and DataLoader uses a fixed shuffle generator
with no worker subprocesses. Reproducibility is expected within the recorded
environment/configuration; it is not a bit-for-bit guarantee across different
PyTorch/compiler/platform versions. Install ranges in pyproject are convenience
bounds; consult recorded package versions when reconstructing this environment.

## Verification

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m build
```

Tests use synthetic CSV fixtures and do not read the real official test split.
They cover schema/label failures, manifest hashes, split coverage and ordering,
train-fit-only statistics/categories, non-refitting transforms and unknown
categories, saved pipeline reload, deterministic features, controlled metrics,
seeded weights/shuffles, a training I/O guard, explicit checkpoint requirements,
fixed evaluation threshold, provenance fields, tampering and overwrite rejection.

The ordered implementation/acceptance record is in `paper/day1/tasks/plan.md` and
`paper/day1/tasks/todo.md`. Stop at Day 1.

## Recorded sanity run

The local official pair produced 192 transformed input features and a 33025
parameter MLP. Training took 5.60 seconds for the training loop on CPU.

| Metric | Final validation | Frozen official test |
| --- | ---: | ---: |
| Macro-F1 | 0.935908 | 0.834634 |
| Attack Recall | 0.978885 | 0.981007 |
| Average Precision (AUPRC) | 0.995007 | 0.980808 |
| Accuracy | 0.945507 | 0.843876 |
| AUROC | 0.989537 | 0.973654 |
| Balanced Accuracy | 0.926630 | 0.828436 |

Test confusion matrix: `[[25007, 11993], [861, 44471]]`, in the order defined
above. This is one fixed sanity run; no settings were changed based on these
results. The JSON report retains full precision and the environment versions.
