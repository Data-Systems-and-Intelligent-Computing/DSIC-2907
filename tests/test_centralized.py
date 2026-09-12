import numpy as np
import pytest
import torch

from src import centralized as central
from src import preprocess as pp


def small_model_config():
    return {
        "hidden_dimensions": [128, 64],
        "dropout": 0.1,
        "epochs": 2,
        "batch_size": 8,
        "optimizer": "Adam",
        "learning_rate": 0.001,
    }


def test_training_reproducible_weights_and_shuffle(monkeypatch):
    values = np.arange(80, dtype=np.float32).reshape(40, 2) / 80
    labels = np.array([0, 1] * 20)
    orders = []
    original = central.dense_batch

    def capture(values, indices):
        orders.append(np.asarray(indices).tolist())
        return original(values, indices)

    monkeypatch.setattr(central, "dense_batch", capture)
    first, losses, _, defaults = central.train_model(values, labels, small_model_config(), 42)
    first_order = orders.copy()
    orders.clear()
    second, repeated_losses, _, _ = central.train_model(values, labels, small_model_config(), 42)
    assert defaults["lr"] == 0.001
    assert orders == first_order
    assert losses == repeated_losses
    for key, tensor in first.state_dict().items():
        assert torch.equal(tensor, second.state_dict()[key])
    assert first_order[:5] != first_order[5:]  # deterministic new shuffle per epoch


def test_validation_probabilities_and_fixed_architecture():
    model = central.build_model(3, small_model_config())
    assert [m.out_features for m in model if isinstance(m, torch.nn.Linear)] == [128, 64, 1]
    assert sum(p.numel() for p in model.parameters()) == 8833
    result = central.predict(model, np.zeros((5, 3), dtype=np.float32), 2)
    assert result.shape == (5,)
    assert np.all((result >= 0) & (result <= 1))


def test_training_rejects_invalid_configuration():
    config = small_model_config()
    config["epochs"] = 0
    with pytest.raises(ValueError, match="epochs"):
        central.train_model(np.zeros((4, 3)), np.array([0, 1, 0, 1]), config, 42)


@pytest.fixture
def trained(experiment, tmp_path):
    import yaml

    config_path, config, paths = experiment
    pp.preprocess(config_path)
    model_path = tmp_path / "model.yaml"
    model_path.write_text(yaml.safe_dump(small_model_config()))
    checkpoint = central.train(config_path, model_path)
    return checkpoint, config, paths


def test_training_command_never_opens_test(experiment, tmp_path, monkeypatch):
    import builtins
    import io
    import sys
    from pathlib import Path

    import yaml

    config_path, config, paths = experiment
    pp.preprocess(config_path)
    model_path = tmp_path / "model.yaml"
    model_path.write_text(yaml.safe_dump(small_model_config()))
    opened = []

    def guarded(original):
        def open_file(file, *args, **kwargs):
            if isinstance(file, (str, Path)):
                path = Path(file).resolve()
                assert path != paths["test"].resolve(), "Training opened official test data"
                opened.append(path)
            return original(file, *args, **kwargs)

        return open_file

    monkeypatch.setattr(builtins, "open", guarded(builtins.open))
    monkeypatch.setattr(io, "open", guarded(io.open))
    monkeypatch.setattr(
        sys,
        "argv",
        ["centralized", "train", "--config", str(config_path), "--model-config", str(model_path)],
    )
    central.main()
    assert paths["train"].resolve() in opened
    metadata = pp.read_json(Path(config["run_dir"]) / "training.json")
    assert metadata["checkpoint_selection"] == "final_epoch"
    assert metadata["final_validation_metrics"]["attack_recall"] >= 0
    assert metadata["splits"]["validation"]["row_count"] == 20


def test_evaluation_requires_checkpoint(tmp_path):
    with pytest.raises(FileNotFoundError, match="Saved checkpoint required"):
        central.evaluate(tmp_path / "missing.pt", tmp_path / "out.json")


def test_evaluation_threshold_provenance_and_no_refit(trained, monkeypatch):
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    checkpoint, config, paths = trained
    paths["train"].unlink()  # Final evaluation does not need to reopen training.

    def forbidden(*args, **kwargs):
        pytest.fail("Final evaluation attempted preprocessing fit")

    for cls in (ColumnTransformer, StandardScaler, OneHotEncoder):
        monkeypatch.setattr(cls, "fit", forbidden)
        monkeypatch.setattr(cls, "fit_transform", forbidden)
    monkeypatch.setattr(
        central, "predict", lambda model, values, batch_size: np.full(values.shape[0], 0.5)
    )
    result = central.evaluate(checkpoint, config["evaluation_output"])
    assert result["threshold"] == 0.5
    assert result["test_metrics"]["confusion_matrix"] == [[0, 20], [0, 20]]
    assert result["test_metrics"]["attack_recall"] == 1.0
    required = {
        "seed",
        "model_config",
        "preprocessing_manifest",
        "dataset_manifest",
        "checkpoint",
        "package_versions",
        "evaluation_package_versions",
        "device",
        "trainable_parameters",
        "splits",
        "training_duration_seconds",
        "final_validation_metrics",
        "n_features",
        "source_csv_sha256",
    }
    assert required <= result.keys()
    assert pp.read_json(config["evaluation_output"]) == result
    for name in ("checkpoint", "preprocessing_manifest", "dataset_manifest", "configuration"):
        assert result[name]["sha256"] == pp.sha256(result[name]["path"])
    pre = pp.read_json(result["preprocessing_manifest"]["path"])
    assert pre["dataset_manifest"] == result["dataset_manifest"]
    for split in ("official_training", "train_fit", "validation", "test"):
        assert {"row_count", "class_counts", "positive_prevalence"} <= result["splits"][
            split
        ].keys()
    with pytest.raises(FileExistsError):
        central.evaluate(checkpoint, config["evaluation_output"])


@pytest.mark.parametrize(
    "target", ["checkpoint", "test", "dataset_manifest", "preprocessing_manifest"]
)
def test_evaluation_provenance_rejects_tampering(trained, target):
    from pathlib import Path

    checkpoint, config, paths = trained
    path = (
        checkpoint
        if target == "checkpoint"
        else paths["test"]
        if target == "test"
        else Path(config[target])
    )
    with path.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="SHA256"):
        central.evaluate(checkpoint, config["evaluation_output"])


def test_evaluation_real_model_smoke(trained):
    checkpoint, config, _ = trained
    result = central.evaluate(checkpoint, config["evaluation_output"])
    assert all(
        0 <= value <= 1
        for key, value in result["test_metrics"].items()
        if key != "confusion_matrix"
    )


@pytest.mark.parametrize("tamper", [False, True])
def test_relocated_provenance_without_original_workspace(trained, tmp_path, monkeypatch, tamper):
    import shutil

    checkpoint, config, _ = trained
    files = list(tmp_path.rglob("*"))
    root = tmp_path / "relocated"
    locations = {}
    for source in files:
        if source.is_file():
            relative = source.relative_to(tmp_path)
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            locations[str(source)] = str(relative)
            source.unlink()
    pp.write_json(root / "data/manifests/relocation.json", locations)
    monkeypatch.setattr(pp, "__file__", str(root / "src/preprocess.py"))
    moved_checkpoint = root / checkpoint.relative_to(tmp_path)
    if tamper:
        with moved_checkpoint.open("ab") as stream:
            stream.write(b"changed")
        with pytest.raises(ValueError, match="SHA256"):
            central.evaluate(moved_checkpoint, root / "evaluation.json")
    else:
        result = central.evaluate(moved_checkpoint, root / "evaluation.json")
        assert result["checkpoint"]["path"] == str(moved_checkpoint)
        assert result["splits"]["validation"]["row_count"] == 20
