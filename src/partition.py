"""Reproducible binary Dirichlet label skew over frozen train-fit rows only."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from src.preprocess import (
    artifact_ref,
    class_summary,
    features_target,
    load_preprocessing,
    load_source,
    read_config,
    write_json,
)


def make_dirichlet_partitions(labels, num_clients: int, alpha: float, seed: int):
    """Return client -> positions in labels; callers map positions to source rows.

    Each class uses PCG64(SeedSequence([seed, class_label])). Class rows are
    shuffled before drawing proportions. Floor cumulative cut points allocate
    every row exactly once. Empty clients are retained, without resampling.
    """
    labels = np.asarray(labels)
    if labels.ndim != 1 or not len(labels) or not np.isin(labels, [0, 1]).all():
        raise ValueError("labels must be a nonempty 1-D array of Normal=0 / Attack=1")
    if isinstance(num_clients, bool) or not isinstance(num_clients, (int, np.integer)):
        raise ValueError("num_clients must be a positive integer")
    if num_clients <= 0:
        raise ValueError("num_clients must be a positive integer")
    if not np.isfinite(alpha) or alpha <= 0:
        raise ValueError("alpha must be finite and positive")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    clients = [[] for _ in range(num_clients)]
    for label in (0, 1):
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([int(seed), label])))
        rows = np.flatnonzero(labels == label).astype(np.int64)
        rng.shuffle(rows)
        proportions = rng.dirichlet(np.full(num_clients, alpha))
        if not np.isfinite(proportions).all():
            raise ValueError("Nonfinite Dirichlet draw; choose a numerically supported alpha")
        cuts = np.minimum((np.cumsum(proportions)[:-1] * len(rows)).astype(np.int64), len(rows))
        for client, allocated in zip(clients, np.split(rows, cuts)):
            client.append(allocated)
    return {f"client_{i}": np.concatenate(rows) for i, rows in enumerate(clients)}


def freeze_partitions(preprocessing_path, output_dir, num_clients, alpha, seed):
    """Save source-row partitions, a CSV distribution, and a linked manifest."""
    directory = Path(output_dir)
    stem = f"partition_alpha{float(alpha):g}_seed{seed}"
    paths = {
        "partition": directory / f"{stem}.json",
        "client_distribution": directory / f"{stem}_clients.csv",
        "manifest": directory / f"{stem}_manifest.json",
    }
    if any(path.exists() for path in paths.values()):
        raise FileExistsError(f"Partition artifacts already exist: {stem}")
    preprocessing, dataset, _, indices = load_preprocessing(preprocessing_path)
    if preprocessing["fit_scope"] != "train_fit_only":
        raise ValueError("Preprocessing must be fitted on train-fit only")
    _, labels = features_target(load_source(dataset, "train"))
    fit = indices["train_fit"]
    local = make_dirichlet_partitions(labels[fit], num_clients, alpha, seed)
    clients = {client: fit[rows] for client, rows in local.items()}
    combined = np.concatenate(list(clients.values()))
    if not np.array_equal(np.sort(combined), np.sort(fit)):
        raise ValueError("Partition must cover train-fit exactly once")
    if np.intersect1d(combined, indices["validation"]).size:
        raise ValueError("Partition contains held-out validation rows")
    summaries = {
        client: class_summary(labels[rows])
        if len(rows)
        else {"row_count": 0, "class_counts": {"0": 0, "1": 0}, "positive_prevalence": None}
        for client, rows in clients.items()
    }
    write_json(paths["partition"], {client: rows.tolist() for client, rows in clients.items()})
    with paths["client_distribution"].open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["client_id", "row_count", "normal_count", "attack_count", "positive_prevalence"]
        )
        for client, summary in summaries.items():
            writer.writerow(
                [
                    client,
                    summary["row_count"],
                    summary["class_counts"]["0"],
                    summary["class_counts"]["1"],
                    summary["positive_prevalence"],
                ]
            )
    manifest = {
        "schema_version": 1,
        "algorithm_version": "binary_dirichlet_cumulative_floor_v1",
        "seed_rule": "PCG64(SeedSequence([partition_seed, class_label])); shuffle then draw",
        "allocation_rule": "floor cumulative cuts; remainder to last client; concatenate 0 then 1",
        "empty_client_rule": "retain; no resampling or rebalancing",
        "numpy_version": np.__version__,
        "partition_scope": "train_fit_only",
        "index_space": "zero_based_official_training_row_position",
        "num_clients": int(num_clients),
        "alpha": float(alpha),
        "seed": int(seed),
        "split_seed": preprocessing["seed"],
        "client_ids": list(clients),
        "train_fit": class_summary(labels[fit]),
        "clients": summaries,
        "preprocessing_manifest": artifact_ref(preprocessing_path),
        "dataset_manifest": preprocessing["dataset_manifest"],
        "split_indices": preprocessing["artifacts"]["split_indices"],
        "training_source": dataset["sources"]["train"],
        "artifacts": {
            name: artifact_ref(paths[name]) for name in ("partition", "client_distribution")
        },
        "checks": {
            "exact_train_fit_coverage": True,
            "no_overlap": True,
            "no_validation_rows": True,
        },
    }
    write_json(paths["manifest"], manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/experiments.yaml")
    parser.add_argument("--fl-config", default="configs/async_fl.yaml")
    parser.add_argument("--preprocessing-manifest", default="data/manifests/preprocessing.json")
    parser.add_argument("--output-dir", default="data/partitions")
    args = parser.parse_args()
    experiment = read_config(args.config)["main"]
    num_clients = read_config(args.fl_config)["fl"]["num_clients"]
    for seed in experiment["seeds"]:
        manifest = freeze_partitions(
            args.preprocessing_manifest, args.output_dir, num_clients, experiment["alpha"], seed
        )
        print(
            json.dumps(
                {"seed": seed, "train_fit": manifest["train_fit"], "checks": manifest["checks"]}
            )
        )


if __name__ == "__main__":
    main()
