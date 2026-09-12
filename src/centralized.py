"""CPU sanity MLP training; frozen-test evaluation is a separate explicit command."""

import argparse
import json
import random
import subprocess
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from src.metrics import THRESHOLD, binary_metrics
from src.preprocess import (
    artifact_ref,
    features_target,
    load_preprocessing,
    load_source,
    package_versions,
    read_config,
    read_json,
    transform,
    verify_ref,
    write_json,
)


def build_model(n_features, config):
    dimensions = config["hidden_dimensions"]
    if len(dimensions) != 2 or any(type(n) is not int or n <= 0 for n in dimensions):
        raise ValueError("hidden_dimensions must contain two positive integers")
    if not 0 <= config["dropout"] < 1:
        raise ValueError("dropout must be in [0, 1)")
    return nn.Sequential(
        nn.Linear(n_features, dimensions[0]),
        nn.ReLU(),
        nn.Dropout(config["dropout"]),
        nn.Linear(dimensions[0], dimensions[1]),
        nn.ReLU(),
        nn.Linear(dimensions[1], 1),
    )


def dense_batch(values, indices):
    batch = values[indices]
    if hasattr(batch, "toarray"):
        batch = batch.toarray()
    return torch.from_numpy(np.asarray(batch, dtype=np.float32))


def train_model(values, labels, config, seed, cpu_threads=1):
    if config["optimizer"] != "Adam":
        raise ValueError("Day 1 supports Adam only")
    for key in ("epochs", "batch_size"):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    if not np.isfinite(config["learning_rate"]) or config["learning_rate"] <= 0:
        raise ValueError("learning_rate must be finite and positive")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(cpu_threads)
    model = build_model(values.shape[1], config).cpu()
    optimizer = torch.optim.Adam(model.parameters(), lr=config["learning_rate"])
    loss_function = nn.BCEWithLogitsLoss()
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(
        range(len(labels)),
        batch_size=config["batch_size"],
        shuffle=True,
        generator=generator,
        num_workers=0,
    )
    targets = torch.from_numpy(labels.astype(np.float32))
    history = []
    started = time.perf_counter()
    model.train()
    for epoch in range(config["epochs"]):
        total_loss = 0.0
        for indices in loader:
            optimizer.zero_grad(set_to_none=True)
            logits = model(dense_batch(values, indices.numpy())).squeeze(1)
            loss = loss_function(logits, targets[indices])
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
        history.append(total_loss / len(labels))
        print(f"Epoch {epoch + 1}/{config['epochs']}: train BCE={history[-1]:.6f}", flush=True)
    return model, history, time.perf_counter() - started, optimizer.defaults


def predict(model, values, batch_size):
    model.eval()
    probabilities = []
    with torch.inference_mode():
        for start in range(0, values.shape[0], batch_size):
            logits = model(dense_batch(values, slice(start, start + batch_size))).squeeze(1)
            probabilities.append(torch.sigmoid(logits).numpy())
    return np.concatenate(probabilities)


def git_metadata():
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return None


def train(config_path, model_config_path):
    config, model_config = read_config(config_path), read_config(model_config_path)
    if config["device"] != "cpu":
        raise ValueError("Day 1 runs on CPU only")
    pre_path = Path(config["preprocessing_manifest"])
    pre, dataset, pipeline, indices = load_preprocessing(pre_path)
    if config["seed"] != pre["seed"] or config["validation_fraction"] != pre["validation_fraction"]:
        raise ValueError("Run seed/split settings differ from saved preprocessing")
    if artifact_ref(config["dataset_manifest"])["sha256"] != pre["dataset_manifest"]["sha256"]:
        raise ValueError("Run dataset differs from saved preprocessing")
    run_dir = Path(config["run_dir"])
    if run_dir.exists():
        raise FileExistsError(f"Run already exists: {run_dir}")
    features, labels = features_target(load_source(dataset, "train"))
    fit_values = transform(pipeline, features.iloc[indices["train_fit"]])
    validation_values = transform(pipeline, features.iloc[indices["validation"]])
    model, losses, duration, optimizer_defaults = train_model(
        fit_values,
        labels[indices["train_fit"]],
        model_config,
        config["seed"],
        config["cpu_threads"],
    )
    validation_metrics = binary_metrics(
        labels[indices["validation"]], predict(model, validation_values, model_config["batch_size"])
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    snapshot = run_dir / "configuration.json"
    write_json(snapshot, {"experiment": config, "model": model_config})
    metadata = {
        "seed": config["seed"],
        "model_config": model_config,
        "optimizer_defaults": json.loads(json.dumps(optimizer_defaults)),
        "configuration": artifact_ref(snapshot),
        "preprocessing_manifest": artifact_ref(pre_path),
        "dataset_manifest": pre["dataset_manifest"],
        "package_versions": package_versions(),
        "device": "cpu",
        "cpu_threads": config["cpu_threads"],
        "git": git_metadata(),
        "trainable_parameters": sum(p.numel() for p in model.parameters() if p.requires_grad),
        "n_features": pre["n_features"],
        "splits": pre["splits"],
        "training_duration_seconds": duration,
        "training_bce_by_epoch": losses,
        "checkpoint_selection": "final_epoch",
        "completed_epochs": model_config["epochs"],
        "final_validation_metrics": validation_metrics,
        "threshold": THRESHOLD,
        "positive_class": {"name": "Attack", "label": 1},
        "confusion_matrix_order": ["Normal", "Attack"],
        "auprc_implementation": "sklearn.metrics.average_precision_score",
    }
    checkpoint = run_dir / "model.pt"
    torch.save({"model_state": model.state_dict(), "metadata": metadata}, checkpoint)
    write_json(run_dir / "training.json", {**metadata, "checkpoint": artifact_ref(checkpoint)})
    print(f"Saved final checkpoint: {checkpoint}", flush=True)
    print(json.dumps({"final_validation_metrics": validation_metrics}), flush=True)
    return checkpoint


def evaluate(checkpoint_path, output):
    """The only post-audit command permitted to open the frozen official test CSV."""
    checkpoint_path, output = Path(checkpoint_path), Path(output)
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"Saved checkpoint required: {checkpoint_path}")
    if output.exists():
        raise FileExistsError(f"Final evaluation already exists: {output}")
    receipt = read_json(checkpoint_path.parent / "training.json")
    checkpoint_ref = artifact_ref(checkpoint_path)
    if checkpoint_path.resolve() != verify_ref(receipt["checkpoint"]).resolve():
        raise ValueError("Checkpoint SHA256/path differs from training receipt")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    metadata = checkpoint["metadata"]
    if metadata["threshold"] != THRESHOLD or metadata["device"] != "cpu":
        raise ValueError("Checkpoint violates Day 1 threshold/device protocol")
    verify_ref(metadata["configuration"])
    pre_path = verify_ref(metadata["preprocessing_manifest"])
    pre, dataset, pipeline, _ = load_preprocessing(pre_path)
    if metadata["dataset_manifest"] != pre["dataset_manifest"]:
        raise ValueError("Checkpoint and preprocessing dataset identity differ")
    torch.set_num_threads(metadata["cpu_threads"])
    model = build_model(metadata["n_features"], metadata["model_config"]).cpu()
    model.load_state_dict(checkpoint["model_state"], strict=True)
    # Test data is opened only after checkpoint and preprocessing provenance pass.
    features, labels = features_target(load_source(dataset, "test"))
    values = transform(pipeline, features)
    probabilities = predict(model, values, metadata["model_config"]["batch_size"])
    metrics = binary_metrics(labels, probabilities)
    result = {
        **metadata,
        "checkpoint": checkpoint_ref,
        "test_metrics": metrics,
        "evaluation_package_versions": package_versions(),
        "source_csv_sha256": {s: source["sha256"] for s, source in dataset["sources"].items()},
    }
    write_json(output, result)
    print(json.dumps({"test_metrics": metrics, "output": str(output)}), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    training = commands.add_parser("train", help="Train and validate without opening test data")
    training.add_argument("--config", default="configs/day1_experiments.yaml")
    training.add_argument("--model-config", default="configs/day1_model.yaml")
    evaluation = commands.add_parser("evaluate", help="Explicit final frozen-test evaluation")
    evaluation.add_argument("--checkpoint", required=True)
    evaluation.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "train":
        train(args.config, args.model_config)
    else:
        evaluate(args.checkpoint, args.output)


if __name__ == "__main__":
    main()
