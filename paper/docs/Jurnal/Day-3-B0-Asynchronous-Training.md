# Day 3 — B0 asynchronous training

Completed 6 October 2026. This is a CPU backbone pilot, before the main-experiment
protocol freeze. Days 1 and 2 artifacts were reused; no dependencies were added.

## What now runs

`src/b0.py` dispatches logical clients to separate spawned CPU worker processes.
Each worker receives the current model, records its starting version, trains on
its own frozen train-fit rows, and returns a serialized full model delta. The
server applies completed updates in receipt order and redispatches an idle
client without waiting for the other clients. There is at most one in-flight
job per client. All admitted jobs are drained before the pilot ends.

`src/client.py` reuses Day 1's `train_model` with the downloaded initial state;
the existing centralized behavior remains the default. Each local contribution
starts a fresh Adam optimizer. `src/async_server.py` validates all delta tensors
before changing the model and increments its version only after a valid apply.

## Recorded pilot choices

| Setting | Value |
|---|---|
| Policy | B0 Async-Uniform; both demand flags false; budget 1.0 |
| Data | UNSW-NB15 official training source; train-fit only |
| Partition | Seed 42, alpha 0.5, ten clients, 140,272 rows |
| Partition SHA256 | `d918af9ad5fb0dcd2e19b3fb38e3052c740d3e0e29aa5b871a6fa3e3aef80407` |
| Model | 192 → 128 → 64 → 1, dropout 0.2, fp32 |
| Local training | Adam, learning rate 0.001, batch 64, one epoch |
| Optimizer state | Reset on each dispatch |
| CPU threads | One per worker; one for the server/evaluator |
| Maximum concurrency | Three; separate CPU processes |
| Initialization seed | 42, from pilot config (overrides the model YAML seed) |
| Dispatch | PCG64 seed 42; uniform random choice among currently idle clients |
| Local RNG seed | `SeedSequence([run_seed, sorted_client_index, global_dispatch_index]).generate_state(1)[0]` |
| Server step | `global += server_lr * (client_samples / total_train_fit) * fixed_multiplier * delta` |
| Server learning rate | 1.0 |
| Fixed staleness multiplier | 1.0; independent of measured staleness |
| Stop | Thirty admitted jobs, all thirty accepted; any worker/update failure aborts and retains evidence |
| Validation | Version 0, every ten accepted updates, and final version |
| Checkpoints | Every 25 accepted updates plus initial and final model |
| Classification threshold | Fixed 0.5, reusing existing binary metrics |

These explicit choices resolve the Day 3 pilot implementation. They remain
subject to backbone/pilot review and the Day 14 main-experiment freeze.
Uniform eligibility does not imply equal completion counts: busy clients are
ineligible until their current job finishes. This pilot added no demand policy
or adaptive local computation.

## Observed evidence

The event log contains 90 records: 30 downloads, 30 arrivals, and 30 applies.
Server versions progress from 0 to 30. Peak in-flight concurrency is three,
and every client contributed at least once.

The large `client_0` downloaded version 0 and applied at version 14. Thirteen
other updates were accepted before it finished. This is direct runtime evidence
that the server does not wait for the slowest client. Maximum observed
staleness was 13; it is calculated from versions, not timestamps.

| Accepted updates / server version | Validation Macro-F1 |
|---:|---:|
| 0 | 0.242906 |
| 10 | 0.736445 |
| 20 | 0.920266 |
| 30 | 0.924870 |

Final validation Attack Recall was 0.994135. This uses the existing 35,069-row
global validation set. The official test CSV was not opened, and the archived
centralized official-test result was not changed. These pilot metrics are not
B0–B3 comparisons or communication-efficiency results.

The recorded pilot loop took 7.68 seconds, including initial/final validation,
process startup, training, event recording, and checkpoint/curve writing. It
excludes source loading, preprocessing transformation, configuration snapshot,
and initial-checkpoint creation. It is not a runtime forecast for main runs.

Canonical serialized uploads total 4,046,070 bytes and downloads total 4,047,990
bytes. These are the saved messages actually passed to/from the process-pool
jobs, including tensor serialization and message metadata. They exclude the
process-pool's own envelope, raw-data bootstrap IPC, and network/framing overhead.
Full communication accounting and timing separation remain Day 5 work.

## Artifacts

- `configs/day3_b0.yaml`: pilot launcher settings; existing FL/model/policy
  configurations supply the shared training and backbone values.
- `results/raw/b0_day3_seed42/configuration.json`: resolved settings, seed rules,
  source/config/data hashes, environment, Git status, and measurement scope.
- `results/raw/b0_day3_seed42/events.jsonl`: client downloads/arrivals and server
  applies, payload locations/hashes, versions, sample counts, loss, and timing.
- `results/raw/b0_day3_seed42/messages/`: every downloaded model and uploaded
  delta, with client/job/seed/version metadata.
- `results/raw/b0_day3_seed42/initial.pt`, `checkpoint_v25.pt`, `model.pt`.
- `results/raw/b0_day3_seed42/version_history.json`, `validation.json`,
  `manifest.json`: version transitions, global validation curve, run receipt.
- `results/processed/b0_day3_seed42.json`: completed pilot summary and artifact
  fingerprints.
- `results/processed/b0_day3_seed42_replay.json`: successful replay receipt.

Final model SHA256:

```text
531ec95f359d4567d9df47f856e6d9f371c9e5346c1d095ae8193f5866ebe8f3
```

Raw artifacts are Git ignored, following the existing repository convention.
Retain them together with the immutable dataset/preprocessing artifacts. A Git
clone alone does not contain the recorded pilot or the original raw dataset.
References use the existing absolute-path/hash convention and relocation resolver.

## Commands and verification

The pre-existing Python environment was used; no packages were installed:

```bash
rtk proxy /home/fadil/TA/Code/demand-aware-async-fl-nids/.venv/bin/python \
  -m pytest -q -p no:cacheprovider
rtk proxy /home/fadil/TA/Code/demand-aware-async-fl-nids/.venv/bin/python \
  -m ruff check src tests
rtk proxy /home/fadil/TA/Code/demand-aware-async-fl-nids/.venv/bin/python \
  -m ruff format --check src/centralized.py src/client.py src/async_server.py \
  src/b0.py tests/test_async_apply.py tests/test_client.py tests/test_b0.py
rtk proxy /home/fadil/TA/Code/demand-aware-async-fl-nids/.venv/bin/python \
  -m build --no-isolation --outdir /tmp/dsic2907-day3-build
rtk proxy /home/fadil/TA/Code/demand-aware-async-fl-nids/.venv/bin/python \
  -m src.b0 train --config configs/day3_b0.yaml
rtk proxy /home/fadil/TA/Code/demand-aware-async-fl-nids/.venv/bin/python \
  -m src.b0 replay --run-dir results/raw/b0_day3_seed42 \
  --output results/processed/b0_day3_seed42_replay.json
```

Results: **93 tests passed**, full Ruff lint and Day 3 format checks passed,
wheel and source distribution built successfully, and pilot/replay completed.
The previous unused `staleness` lint error disappeared when the server began
using the value in its actual apply receipt.

The controlled fast/slow test holds the slow worker until the fast client has
applied twice, proving both immediate apply and redispatch. Additional tests
cover exact sample weighting, valid stale updates, atomic rejection of invalid
tensors, repeatable local training, full budget, invalid/adaptive config guards,
partition tampering, worker failure logging, absent official test CSV, overwrite
refusal, and replay with both raw CSVs removed.

Live OS completion order can differ when the same seed is rerun. Local training
is deterministic for the same downloaded weights, rows, configuration, and local
seed. **Arrival replay** verifies payload hashes, downloaded states, weighted
apply receipts, serialized totals, and tensor-identical final weights using the
recorded event order. It does not retrain the clients or claim identical live
wall-clock timings. Keep paired-run arrival/dispatch controls explicit before
main-experiment freeze.

Existing runs and summaries cannot be overwritten. To start another pilot, copy
the pilot YAML and choose fresh `run_dir` and `summary_output` paths. To repeat
the recorded replay without writing a new receipt, omit `--output`.

Day 3's gate is satisfied. Next: **Day 4 — controlled versioning and staleness
verification**. Days 5–6 transport accounting and update compression remain planned.
