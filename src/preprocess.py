"""Frozen UNSW-NB15 identity and train-fit-only preprocessing."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

SOURCE_COLUMNS = (
    "id dur proto service state spkts dpkts sbytes dbytes rate sttl dttl sload "
    "dload sloss dloss sinpkt dinpkt sjit djit swin stcpb dtcpb dwin tcprtt "
    "synack ackdat smean dmean trans_depth response_body_len ct_srv_src "
    "ct_state_ttl ct_dst_ltm ct_src_dport_ltm ct_dst_sport_ltm ct_dst_src_ltm "
    "is_ftp_login ct_ftp_cmd ct_flw_http_mthd ct_src_ltm ct_srv_dst "
    "is_sm_ips_ports attack_cat label"
).split()
CATEGORICAL = ["proto", "service", "state"]
EXCLUDED = ["id", "attack_cat", "label"]
NUMERICAL = [c for c in SOURCE_COLUMNS if c not in CATEGORICAL + EXCLUDED]
LABEL_MAPPING = {"Normal": 0, "Attack": 1}
OFFICIAL_COUNTS = {"train": {"0": 56000, "1": 119341}, "test": {"0": 37000, "1": 45332}}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_header(columns):
    if list(columns) != SOURCE_COLUMNS:
        raise ValueError(f"Unexpected/ambiguous UNSW-NB15 schema: {list(columns)}")


def audit_csv(path):
    """Inspect identity/schema only; learn no feature-processing statistics."""
    path = Path(path).resolve()
    digest = sha256(path)
    strings = CATEGORICAL + ["attack_cat"]
    dtypes = {c: "string" if c in strings else "int64" for c in SOURCE_COLUMNS}
    counts = {"0": 0, "1": 0}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.reader(stream)
        check_header(next(rows, []))
        for line, row in enumerate(rows, start=2):
            if len(row) != len(SOURCE_COLUMNS):
                raise ValueError(f"Invalid row width at {path}:{line}")
            for column, value in zip(SOURCE_COLUMNS, row):
                if not value.strip():
                    raise ValueError(f"Missing {column} at {path}:{line}")
                if column not in strings:
                    try:
                        number = float(value)
                    except ValueError as exc:
                        raise ValueError(f"Invalid numeric {column} at line {line}") from exc
                    if not math.isfinite(number):
                        raise ValueError(f"Nonfinite {column} at line {line}")
                    if column == "label" and value not in ("0", "1"):
                        raise ValueError(f"label must be 0 or 1 at line {line}")
                    if column == "id" and not number.is_integer():
                        raise ValueError(f"id must be integer at line {line}")
                    if any(char in value.lower() for char in (".", "e")):
                        dtypes[column] = "float64"
            counts[row[-1]] += 1
    if not all(counts.values()):
        raise ValueError("Dataset must contain both Normal=0 and Attack=1")
    if sha256(path) != digest:
        raise ValueError("Source changed during dataset audit")
    return {
        "path": str(path),
        "filename": path.name,
        "sha256": digest,
        "row_count": sum(counts.values()),
        "class_counts": counts,
        "positive_prevalence": counts["1"] / sum(counts.values()),
        "ordered_source_columns": SOURCE_COLUMNS,
        "dtypes": dtypes,
    }


def freeze_dataset(train_path, test_path, output):
    if Path(output).exists():
        raise FileExistsError(f"Dataset identity already frozen: {output}")
    sources = {}
    for split, path in (("train", train_path), ("test", test_path)):
        expected = f"UNSW_NB15_{'training' if split == 'train' else 'testing'}-set.csv"
        if Path(path).name != expected:
            raise ValueError(f"Expected official filename {expected}")
        sources[split] = audit_csv(path)
        if sources[split]["class_counts"] != OFFICIAL_COUNTS[split]:
            raise ValueError(f"Unexpected official {split} counts")
    manifest = {
        "dataset_name": "UNSW-NB15",
        "schema_version": 1,
        "dataset_variant": "official training/testing CSV pair",
        "target_column": "label",
        "label_mapping": LABEL_MAPPING,
        "ordered_source_columns": SOURCE_COLUMNS,
        "excluded_features": EXCLUDED,
        "categorical_features": CATEGORICAL,
        "numerical_features": NUMERICAL,
        "parsing_schema": {
            c: "string"
            if c in CATEGORICAL + ["attack_cat"]
            else "binary_int"
            if c == "label"
            else "integer"
            if c == "id"
            else "finite_numeric"
            for c in SOURCE_COLUMNS
        },
        "sources": sources,
    }
    write_json(output, manifest)
    return manifest


def artifact_ref(path):
    return {"path": str(Path(path).resolve()), "sha256": sha256(path)}


def verify_ref(reference):
    # Archived manifests retain their original bytes and hashes after relocation.
    root = Path(__file__).resolve().parents[1]
    relocation = root / "data/manifests/relocation.json"
    locations = read_json(relocation) if relocation.is_file() else {}
    path = (
        root / locations[reference["path"]]
        if reference["path"] in locations
        else Path(reference["path"])
    )
    if sha256(path) != reference["sha256"]:
        raise ValueError(f"SHA256 mismatch: {path}")
    return path


def load_source(dataset, split):
    """Open only the explicitly requested source; train never verifies test bytes."""
    import pandas as pd

    source = dataset["sources"][split]
    path = verify_ref(source)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        check_header(next(csv.reader(stream), []))
    frame = pd.read_csv(path, encoding="utf-8-sig", dtype=source["dtypes"], keep_default_na=False)
    if len(frame) != source["row_count"]:
        raise ValueError("Source row count mismatch")
    return frame


def features_target(frame):
    import numpy as np
    from pandas.api.types import is_numeric_dtype

    check_header(frame.columns)
    if frame.isna().any().any():
        raise ValueError("Missing values are not supported")
    labels = frame["label"].to_numpy()
    if not np.isin(labels, [0, 1]).all():
        raise ValueError("label must contain only 0=Normal and 1=Attack")
    for name in NUMERICAL:
        if not is_numeric_dtype(frame[name]) or not np.isfinite(frame[name]).all():
            raise ValueError(f"Expected finite numeric feature: {name}")
    for name in CATEGORICAL:
        if not frame[name].map(lambda value: isinstance(value, str) and bool(value.strip())).all():
            raise ValueError(f"Expected nonempty categorical feature: {name}")
    return frame.drop(columns=EXCLUDED), labels.astype(np.int64)


def split_indices(labels, seed, validation_fraction):
    import numpy as np
    from sklearn.model_selection import train_test_split

    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    fit, validation = train_test_split(
        np.arange(len(labels)), test_size=validation_fraction, stratify=labels, random_state=seed
    )
    return {"train_fit": fit, "validation": validation}


def fit_preprocessor(features, indices):
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    pipeline = ColumnTransformer(
        [
            ("numeric", StandardScaler(), NUMERICAL),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=True),
                CATEGORICAL,
            ),
        ],
        sparse_threshold=1.0,
    )
    pipeline.fit(features.iloc[indices["train_fit"]])
    return pipeline


def transform(pipeline, features):
    import numpy as np

    values = pipeline.transform(features).astype(np.float32)
    # ColumnTransformer keeps the combined matrix sparse when density < 1.
    if not np.isfinite(values.data if hasattr(values, "tocsr") else values).all():
        raise ValueError("Nonfinite transformed features")
    return values


def read_config(path):
    import yaml

    with Path(path).open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a mapping")
    return config


def package_versions():
    import platform
    from importlib.metadata import distributions

    return {
        "python": platform.python_version(),
        **{d.metadata["Name"]: d.version for d in distributions()},
    }


def class_summary(labels):
    import numpy as np

    return {
        "row_count": len(labels),
        "class_counts": {str(c): int(np.sum(labels == c)) for c in (0, 1)},
        "positive_prevalence": float(np.mean(labels == 1)),
    }


def preprocess(config_path):
    import joblib
    import numpy as np

    config = read_config(config_path)
    output = Path(config["preprocessing_manifest"])
    if output.exists():
        raise FileExistsError(f"Preprocessing already exists: {output}")
    dataset_path = Path(config["dataset_manifest"])
    dataset = read_json(dataset_path)
    features, labels = features_target(load_source(dataset, "train"))
    indices = split_indices(labels, config["seed"], config["validation_fraction"])
    pipeline = fit_preprocessor(features, indices)
    validation = transform(pipeline, features.iloc[indices["validation"]])
    directory = Path(config["processed_dir"])
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "pipeline": directory / "pipeline.joblib",
        "split_indices": directory / "split_indices.npz",
        "feature_names": directory / "feature_names.json",
        "configuration": directory / "preprocessing_config.json",
    }
    if any(path.exists() for path in paths.values()):
        raise FileExistsError("Preprocessing output artifacts already exist")
    with paths["pipeline"].open("xb") as stream:
        joblib.dump(pipeline, stream)
    with paths["split_indices"].open("xb") as stream:
        np.savez_compressed(stream, **indices)
    write_json(paths["feature_names"], pipeline.get_feature_names_out().tolist())
    write_json(paths["configuration"], config)
    summaries = {
        "official_training": class_summary(labels),
        **{s: class_summary(labels[i]) for s, i in indices.items()},
        "test": {
            k: dataset["sources"]["test"][k]
            for k in ("row_count", "class_counts", "positive_prevalence")
        },
    }
    manifest = {
        "schema_version": 1,
        "dataset_manifest": artifact_ref(dataset_path),
        "artifacts": {name: artifact_ref(path) for name, path in paths.items()},
        "seed": config["seed"],
        "validation_fraction": config["validation_fraction"],
        "fit_scope": "train_fit_only",
        "excluded_features": EXCLUDED,
        "categorical_features": CATEGORICAL,
        "numerical_features": NUMERICAL,
        "scaler": "StandardScaler",
        "encoder": "OneHotEncoder(handle_unknown=ignore)",
        "missing_values": "reject",
        "n_features": validation.shape[1],
        "representation": "sparse" if hasattr(validation, "tocsr") else "dense",
        "splits": summaries,
        "package_versions": package_versions(),
    }
    write_json(output, manifest)
    return manifest


def load_preprocessing(path):
    """Verify artifact links, without accessing either raw source CSV."""
    import joblib
    import numpy as np

    manifest = read_json(path)
    dataset = read_json(verify_ref(manifest["dataset_manifest"]))
    paths = {key: verify_ref(ref) for key, ref in manifest["artifacts"].items()}
    pipeline = joblib.load(paths["pipeline"])
    with np.load(paths["split_indices"], allow_pickle=False) as archive:
        indices = {name: archive[name] for name in ("train_fit", "validation")}
    names = read_json(paths["feature_names"])
    if names != pipeline.get_feature_names_out().tolist() or len(names) != manifest["n_features"]:
        raise ValueError("Transformed feature ordering mismatch")
    all_indices = np.concatenate(list(indices.values()))
    if not np.array_equal(
        np.sort(all_indices), np.arange(dataset["sources"]["train"]["row_count"])
    ):
        raise ValueError("Split indices are not a disjoint exhaustive partition")
    return manifest, dataset, pipeline, indices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze", help="Audit and freeze the official CSV pair")
    freeze.add_argument("--train", required=True)
    freeze.add_argument("--test", required=True)
    freeze.add_argument("--output", default="data/manifests/dataset.json")
    prepare = commands.add_parser("prepare", help="Fit on train-fit; transform validation only")
    prepare.add_argument("--config", default="configs/day1_experiments.yaml")
    args = parser.parse_args()
    if args.command == "freeze":
        freeze_dataset(args.train, args.test, args.output)
        print(f"Frozen dataset manifest: {args.output} ({sha256(args.output)})")
    else:
        manifest = preprocess(args.config)
        print(json.dumps({"n_features": manifest["n_features"], "splits": manifest["splits"]}))


if __name__ == "__main__":
    main()
