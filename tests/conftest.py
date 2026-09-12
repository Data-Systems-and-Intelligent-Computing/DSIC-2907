import numpy as np
import pandas as pd
import pytest
import yaml

from src import preprocess as pp


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    paths = {}
    counts = {}
    for split, rows, filename in [
        ("train", 100, "UNSW_NB15_training-set.csv"),
        ("test", 40, "UNSW_NB15_testing-set.csv"),
    ]:
        labels = np.arange(rows) % 2
        frame = pd.DataFrame({c: np.arange(rows) + 1 for c in pp.SOURCE_COLUMNS})
        frame["label"] = labels
        frame["proto"] = np.where(labels, "udp", "tcp")
        frame["service"] = "-"
        frame["state"] = "FIN"
        frame["attack_cat"] = "Normal"  # Must never determine y.
        paths[split] = tmp_path / filename
        frame.to_csv(paths[split], index=False, encoding="utf-8-sig")
        counts[split] = {"0": rows // 2, "1": rows // 2}
    monkeypatch.setattr(pp, "OFFICIAL_COUNTS", counts)
    dataset_path = tmp_path / "dataset.json"
    pp.freeze_dataset(paths["train"], paths["test"], dataset_path)
    config = {
        "seed": 42,
        "validation_fraction": 0.2,
        "device": "cpu",
        "cpu_threads": 1,
        "dataset_manifest": str(dataset_path),
        "preprocessing_manifest": str(tmp_path / "preprocessing.json"),
        "processed_dir": str(tmp_path / "processed"),
        "run_dir": str(tmp_path / "run"),
        "evaluation_output": str(tmp_path / "metrics.json"),
    }
    config_path = tmp_path / "experiments.yaml"
    config_path.write_text(yaml.safe_dump(config))
    return config_path, config, paths
