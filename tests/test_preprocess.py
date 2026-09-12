import csv

import pytest

from src import preprocess as pp


def make_csv(path, labels=(0, 1), columns=None):
    columns = pp.SOURCE_COLUMNS if columns is None else columns
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        for i, label in enumerate(labels):
            row = {c: i + 1 for c in columns}
            row.update(proto="tcp", service="-", state="FIN", attack_cat="Normal", label=label)
            writer.writerow([row[c] for c in columns])
    return path


def test_dataset_schema_labels_and_hash(tmp_path):
    path = make_csv(tmp_path / "train.csv")
    audit = pp.audit_csv(path)
    assert audit["sha256"] == pp.sha256(path)
    assert audit["row_count"] == 2
    assert audit["class_counts"] == {"0": 1, "1": 1}
    assert audit["dtypes"]["proto"] == "string"
    assert audit["ordered_source_columns"] == pp.SOURCE_COLUMNS


@pytest.mark.parametrize(
    "columns",
    [
        pp.SOURCE_COLUMNS[:-1],
        pp.SOURCE_COLUMNS + ["extra"],
        pp.SOURCE_COLUMNS[:-1] + ["attack_cat"],
        list(reversed(pp.SOURCE_COLUMNS)),
    ],
)
def test_dataset_unexpected_schema(tmp_path, columns):
    with pytest.raises(ValueError, match="schema"):
        pp.audit_csv(make_csv(tmp_path / "bad.csv", columns=columns))


@pytest.mark.parametrize("label", [2, "Attack", "", "nan", 0.5])
def test_dataset_invalid_label(tmp_path, label):
    with pytest.raises(ValueError):
        pp.audit_csv(make_csv(tmp_path / "bad.csv", labels=(0, label)))


def test_dataset_manifest_and_official_count_guard(tmp_path, monkeypatch):
    train = make_csv(tmp_path / "UNSW_NB15_training-set.csv")
    test = make_csv(tmp_path / "UNSW_NB15_testing-set.csv")
    output = tmp_path / "dataset.json"
    with pytest.raises(ValueError, match="counts"):
        pp.freeze_dataset(train, test, output)
    monkeypatch.setattr(pp, "OFFICIAL_COUNTS", {s: {"0": 1, "1": 1} for s in ("train", "test")})
    pp.freeze_dataset(train, test, output)
    manifest = pp.read_json(output)
    assert manifest["target_column"] == "label"
    assert manifest["label_mapping"] == {"Normal": 0, "Attack": 1}
    assert manifest["sources"]["test"]["sha256"] == pp.sha256(test)
    with pytest.raises(FileExistsError):
        pp.freeze_dataset(train, test, output)


def test_split_deterministic_disjoint_and_exhaustive():
    import numpy as np

    labels = np.array([0, 1] * 50)
    first = pp.split_indices(labels, 42, 0.2)
    second = pp.split_indices(labels, 42, 0.2)
    for name in first:
        np.testing.assert_array_equal(first[name], second[name])
        assert labels[first[name]].mean() == 0.5
    assert len(first["train_fit"]) == 80
    assert not set(first["train_fit"]) & set(first["validation"])
    assert set(first["train_fit"]) | set(first["validation"]) == set(range(100))


def test_dataset_target_is_label_and_features_exclude_labels(tmp_path):
    import pandas as pd

    # attack_cat is deliberately Normal even where label is 1.
    frame = pd.read_csv(make_csv(tmp_path / "train.csv"), encoding="utf-8-sig")
    features, labels = pp.features_target(frame)
    assert labels.tolist() == [0, 1]
    assert not set(pp.EXCLUDED) & set(features.columns)
    assert features.shape[1] == 42


def test_fit_uses_only_train_fit_after_split(tmp_path):
    import numpy as np
    import pandas as pd

    frame = pd.read_csv(make_csv(tmp_path / "train.csv", labels=[0, 1] * 20))
    indices = pp.split_indices(frame.label.to_numpy(), 42, 0.2)
    frame.loc[indices["validation"], "dur"] = 1000000
    frame.loc[indices["validation"], "proto"] = "validation_only"
    features, _ = pp.features_target(frame)
    pipeline = pp.fit_preprocessor(features, indices)
    scaler = pipeline.named_transformers_["numeric"]
    encoder = pipeline.named_transformers_["categorical"]
    np.testing.assert_allclose(
        scaler.mean_, features.iloc[indices["train_fit"]][pp.NUMERICAL].mean().to_numpy()
    )
    assert int(scaler.n_samples_seen_) == len(indices["train_fit"])
    assert "validation_only" not in encoder.categories_[0]


def test_transform_no_refit_unknowns_order_and_reload(tmp_path, monkeypatch):
    import joblib
    import numpy as np
    import pandas as pd

    frame = pd.read_csv(make_csv(tmp_path / "train.csv", labels=[0, 1] * 20))
    frame["proto"] = ["tcp", "udp"] * 20
    features, labels = pp.features_target(frame)
    indices = pp.split_indices(labels, 42, 0.2)
    pipeline = pp.fit_preprocessor(features, indices)
    repeated = pp.fit_preprocessor(features, indices)
    names = pipeline.get_feature_names_out().tolist()
    assert names == repeated.get_feature_names_out().tolist()
    assert not any(name.split("__", 1)[-1] in pp.EXCLUDED for name in names)
    path = tmp_path / "pipeline.joblib"
    joblib.dump(pipeline, path)
    pipeline = joblib.load(path)
    before = joblib.hash(pipeline)

    def forbidden(*args, **kwargs):
        pytest.fail("Transformation attempted to refit")

    for estimator in [pipeline, *pipeline.named_transformers_.values()]:
        if hasattr(estimator, "fit"):
            monkeypatch.setattr(type(estimator), "fit", forbidden)
        if hasattr(estimator, "fit_transform"):
            monkeypatch.setattr(type(estimator), "fit_transform", forbidden)
    heldout = features.iloc[indices["validation"]].copy()
    heldout["proto"] = "unknown_test_category"
    heldout["dur"] = 99999999.0
    fit_values = pp.transform(pipeline, features.iloc[indices["train_fit"]])
    validation = pp.transform(pipeline, features.iloc[indices["validation"]])
    test = pp.transform(pipeline, heldout)
    assert fit_values.shape[1] == validation.shape[1] == test.shape[1] == len(names)
    assert test.format == "csr"
    assert joblib.hash(pipeline) == before
    np.testing.assert_array_equal(test.toarray(), pp.transform(pipeline, heldout).toarray())


def test_preprocessing_artifacts_and_no_test_access(experiment, monkeypatch):
    import numpy as np

    config_path, config, paths = experiment
    # A missing official test CSV cannot prevent preparation or artifact loading.
    paths["test"].unlink()
    original_fit = pp.fit_preprocessor
    seen = []

    def fit_spy(features, indices):
        seen.append(indices)
        assert len(indices["train_fit"]) == 80
        assert len(indices["validation"]) == 20
        return original_fit(features, indices)

    monkeypatch.setattr(pp, "fit_preprocessor", fit_spy)
    manifest = pp.preprocess(config_path)
    saved, dataset, pipeline, indices = pp.load_preprocessing(config["preprocessing_manifest"])
    assert seen and manifest == saved
    assert manifest["fit_scope"] == "train_fit_only"
    assert manifest["representation"] == "sparse"
    assert manifest["dataset_manifest"]["sha256"] == pp.sha256(config["dataset_manifest"])
    assert dataset["sources"]["test"]["row_count"] == 40
    assert int(pipeline.named_transformers_["numeric"].n_samples_seen_) == 80
    np.testing.assert_array_equal(indices["train_fit"], seen[0]["train_fit"])
    with pytest.raises(FileExistsError):
        pp.preprocess(config_path)


@pytest.mark.parametrize(
    "artifact", ["pipeline", "split_indices", "feature_names", "configuration"]
)
def test_preprocessing_rejects_modified_artifacts(experiment, artifact):
    from pathlib import Path

    config_path, config, _ = experiment
    manifest = pp.preprocess(config_path)
    with Path(manifest["artifacts"][artifact]["path"]).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        pp.load_preprocessing(config["preprocessing_manifest"])


def test_dataset_changed_source_rejected(experiment):
    config_path, _, paths = experiment
    with paths["train"].open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        pp.preprocess(config_path)
