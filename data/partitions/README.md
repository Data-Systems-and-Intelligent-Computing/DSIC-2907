# Day 2 — Ten-client Dirichlet partition

Status: **COMPLETE**, 6 October 2026. Day 1's saved pipeline, split, model,
metrics, and eight artifact fingerprints were checked before proceeding.

The frozen condition is 10 clients, binary label skew, alpha 0.5, partition
seeds 42, 123, and 2026 from `configs/experiments.yaml`. All three partitions
reuse Day 1's seed-42 train-fit/validation split; changing the partition seed
does not change the held-out validation rows.

For each seed, this directory contains:

- `partition_alpha0.5_seed<seed>.json`: client IDs `client_0` through `client_9`
  mapped to **zero-based row positions in the official training CSV**, not CSV
  `id` values or positions in a transformed train-fit matrix.
- `partition_alpha0.5_seed<seed>_clients.csv`: sample counts, Normal/Attack counts,
  and attack prevalence for every client.
- `partition_alpha0.5_seed<seed>_manifest.json`: parameters, algorithm version,
  class-seed rule, NumPy version, client summaries, verified invariants, source
  links, and SHA256 fingerprints of the partition and CSV.

Only the 140,272 frozen train-fit rows are allocated: 44,800 Normal and 95,472
Attack. The 35,069 validation rows are excluded. The official test CSV is not
opened. Preprocessing is loaded and verified without fitting or transforming it.

Each binary class uses `PCG64(SeedSequence([partition_seed, class_label]))`.
Its train-fit positions are shuffled, then a symmetric Dirichlet draw provides
ten proportions. Floor cumulative cut points allocate the rows, with the
remainder going to the last client. Each client's Normal allocation is followed
by its Attack allocation. Local training must shuffle batches independently.
Empty clients are retained without resampling or rebalancing; none occur in
these three frozen partitions. This is simulated label skew, not evidence of
real-world client distributions.

| Partition seed | Total rows | Smallest client | Largest client |
|---|---:|---:|---:|
| 42 | 140,272 | 2,864 | 60,183 |
| 123 | 140,272 | 2,008 | 32,829 |
| 2026 | 140,272 | 959 | 56,959 |

Partition SHA256 fingerprints:

```text
42    d918af9ad5fb0dcd2e19b3fb38e3052c740d3e0e29aa5b871a6fa3e3aef80407
123   d4adee77a1e682ed989ffc908dc0e59e470ac1f7e4ca095c7f78996bf8650dd6
2026  0a2099014fe7a988eb485d1aac507efa40fff6dc7eea67897954f1449bb9b0ca
```

Generate into a **fresh directory** from the repository root:

```bash
rtk proxy python -m src.partition --output-dir /tmp/day2-partitions
```

The default output is `data/partitions`; generation refuses to overwrite any
existing artifact for that seed. Use the existing Python environment or an
environment with the project's declared dependencies. No dependencies were added.
Manifests follow the existing artifact-reference convention: output references
contain absolute paths. Repeating at the same paths produces identical manifest
bytes; a fresh output directory changes those paths only. Partition/CSV bytes
and their hashes remain identical with the recorded inputs and NumPy version.
Historical source references resolve through `data/manifests/relocation.json`.
When moving these new artifacts, retain their hashes and update their location
mapping rather than changing the frozen partition.

Verification on 6 October 2026, using the pre-existing TA Python environment:

- Exact train-fit coverage, unique row positions, validation exclusion, class
  totals, nonempty clients, and all source/artifact fingerprints passed for
  every frozen seed.
- A fresh-directory replay produced identical partition and CSV bytes for all
  three seeds; manifests matched after accounting for output-directory paths.
- `python -m pytest -q -p no:cacheprovider`: **75 passed**. The 21 new partition
  tests include test-CSV absence, no preprocessing refit, tampered-split rejection,
  overwrite refusal, identical replay bytes, and the multi-seed CLI.
- `python -m ruff check src/partition.py tests/test_partition.py` and the matching
  format check passed.
- `python -m build --no-isolation --outdir /tmp/dsic2907-day2-build`: wheel and
  source distribution built successfully.
- Full `ruff check src tests` still reports the pre-existing F841 in
  `src/async_server.py:9`.

Day 3 (B0 asynchronous training) is next. B0--B3 must reuse the corresponding
frozen partition hash; no FL training or policy comparison was run for Day 2.
