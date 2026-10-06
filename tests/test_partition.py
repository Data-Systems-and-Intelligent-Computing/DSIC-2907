import csv
import subprocess
import sys

import numpy as np
import pytest

from src import partition as part
from src import preprocess as pp
from src.partition import make_dirichlet_partitions


def test_partition_exact_coverage_and_reproducibility():
    labels = np.array([0] * 4480 + [1] * 9547)
    original = labels.copy()
    first = make_dirichlet_partitions(labels, 10, 0.5, 42)
    repeated = make_dirichlet_partitions(labels, 10, 0.5, 42)
    assert list(first) == [f"client_{i}" for i in range(10)]
    np.testing.assert_array_equal(
        np.sort(np.concatenate(list(first.values()))), np.arange(len(labels))
    )
    np.testing.assert_array_equal(labels, original)
    for client, rows in first.items():
        np.testing.assert_array_equal(rows, repeated[client])
        assert rows.dtype == np.int64
        assert len(rows) > 0
    prevalence = [labels[rows].mean() for rows in first.values()]
    assert max(prevalence) - min(prevalence) > 0.5
    changed = make_dirichlet_partitions(labels, 10, 0.5, 123)
    assert any(not np.array_equal(first[c], changed[c]) for c in first)


def test_partition_preserves_global_rng_and_single_class_coverage():
    np.random.seed(7)
    before = np.random.get_state()
    partitions = make_dirichlet_partitions([1, 1, 1], 10, 0.5, 0)
    after = np.random.get_state()
    np.testing.assert_array_equal(before[1], after[1])
    assert before[2:] == after[2:]
    assert len(partitions) == 10  # No hidden resampling or minimum-size rebalancing.
    np.testing.assert_array_equal(np.sort(np.concatenate(list(partitions.values()))), [0, 1, 2])


@pytest.mark.parametrize("labels", [[], [[0, 1]], [0, 2], [0, np.nan], ["0", "1"]])
def test_partition_rejects_invalid_labels(labels):
    with pytest.raises(ValueError):
        make_dirichlet_partitions(labels, 10, 0.5, 42)


@pytest.mark.parametrize("clients", [0, -1, 1.5, True])
def test_partition_rejects_invalid_client_count(clients):
    with pytest.raises(ValueError):
        make_dirichlet_partitions([0, 1], clients, 0.5, 42)


@pytest.mark.parametrize("alpha", [0, -0.5, np.inf, np.nan])
def test_partition_rejects_invalid_alpha(alpha):
    with pytest.raises(ValueError):
        make_dirichlet_partitions([0, 1], 10, alpha, 42)


@pytest.mark.parametrize("seed", [-1, 1.5, True])
def test_partition_rejects_invalid_seed(seed):
    with pytest.raises(ValueError):
        make_dirichlet_partitions([0, 1], 10, 0.5, seed)


def test_frozen_partition_uses_only_train_fit_and_repeats_bytes(experiment, tmp_path, monkeypatch):
    config_path, config, sources = experiment
    pp.preprocess(config_path)
    _, dataset, _, indices = pp.load_preprocessing(config["preprocessing_manifest"])
    labels = pp.load_source(dataset, "train").label.to_numpy()
    sources["test"].unlink()  # Generation must work without the official test CSV.
    from sklearn.compose import ColumnTransformer

    def forbidden(*args, **kwargs):
        pytest.fail("Partitioning attempted to refit preprocessing")

    monkeypatch.setattr(ColumnTransformer, "fit", forbidden)
    output = tmp_path / "partitions"
    manifest = part.freeze_partitions(config["preprocessing_manifest"], output, 10, 0.5, 42)
    assert manifest["partition_scope"] == "train_fit_only"
    assert manifest["index_space"] == "zero_based_official_training_row_position"
    for reference in [manifest["preprocessing_manifest"], manifest["dataset_manifest"]]:
        pp.verify_ref(reference)
    partition_path = pp.verify_ref(manifest["artifacts"]["partition"])
    clients = pp.read_json(partition_path)
    combined = [row for rows in clients.values() for row in rows]
    assert sorted(combined) == sorted(indices["train_fit"].tolist())
    assert not set(combined) & set(indices["validation"])
    assert all(type(row) is int for row in combined)
    summary_path = pp.verify_ref(manifest["artifacts"]["client_distribution"])
    with summary_path.open(newline="") as stream:
        summaries = list(csv.DictReader(stream))
    assert len(summaries) == 10
    for summary in summaries:
        rows = clients[summary["client_id"]]
        assert int(summary["row_count"]) == len(rows)
        assert int(summary["normal_count"]) == int(np.sum(labels[rows] == 0))
        assert int(summary["attack_count"]) == int(np.sum(labels[rows] == 1))
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(FileExistsError):
        part.freeze_partitions(config["preprocessing_manifest"], output, 10, 0.5, 42)
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}
    for path in output.iterdir():
        path.unlink()
    repeated = part.freeze_partitions(config["preprocessing_manifest"], output, 10, 0.5, 42)
    assert repeated == manifest
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}


def test_frozen_partition_rejects_changed_split_before_writing(experiment, tmp_path):
    config_path, config, _ = experiment
    pp.preprocess(config_path)
    split_path = tmp_path / "processed/split_indices.npz"
    split_path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        part.freeze_partitions(config["preprocessing_manifest"], tmp_path / "out", 10, 0.5, 42)
    assert not (tmp_path / "out").exists()


def test_partition_cli_generates_all_configured_seeds(experiment, tmp_path):
    config_path, config, _ = experiment
    pp.preprocess(config_path)
    experiments = tmp_path / "main.yaml"
    experiments.write_text("main:\n  seeds: [42, 123, 2026]\n  alpha: 0.5\n")
    fl = tmp_path / "fl.yaml"
    fl.write_text("fl:\n  num_clients: 10\n")
    output = tmp_path / "partitions"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.partition",
            "--config",
            str(experiments),
            "--fl-config",
            str(fl),
            "--preprocessing-manifest",
            config["preprocessing_manifest"],
            "--output-dir",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert len(result.stdout.splitlines()) == 3
    for seed in (42, 123, 2026):
        manifest = pp.read_json(output / f"partition_alpha0.5_seed{seed}_manifest.json")
        assert manifest["seed"] == seed
        assert manifest["num_clients"] == 10
        assert manifest["alpha"] == 0.5
        for reference in manifest["artifacts"].values():
            pp.verify_ref(reference)
