"""Tests for the local dataset store."""
# ruff: noqa: TC002,TC003

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from code2workspace_cli.dataset_store import DatasetSearchFilter, DatasetStore


def test_dataset_store_writes_record_and_queries_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE2WORKSPACE_OPERATOR_STORE_EMBEDDINGS_ENABLED", "0")
    store = DatasetStore(tmp_path / "dataset_store")

    record_path = store.write_dataset(
        {
            "dataset_id": "immune-escape-sequence-bundle",
            "name": "Immune escape sequence bundle",
            "version": "v1",
            "domain": "immune_escape",
            "source": "local benchmark fixture",
            "license": "unknown",
            "summary": (
                "Protein FASTA and antibody CSV inputs for immune escape scoring."
            ),
            "files": [
                {
                    "name": "few_proteins",
                    "role": "input_fasta",
                    "media_type": "fasta",
                    "uri": "datasets/few_proteins.fasta",
                },
                {
                    "name": "antibody_data",
                    "role": "metadata",
                    "media_type": "csv",
                    "uri": "datasets/antibody_data.csv",
                },
            ],
            "tags": ["benchmark", "immune-escape"],
            "compatible_operator_ids": ["benchmark:esm"],
        }
    )

    rows = store.search_datasets(
        DatasetSearchFilter(
            query="protein fasta immune escape",
            media_type="fasta",
            tag="immune-escape",
        )
    )

    assert record_path == (
        tmp_path
        / "dataset_store"
        / "datasets"
        / "immune-escape-sequence-bundle"
        / "dataset.json"
    )
    assert rows
    assert rows[0]["dataset_id"] == "immune-escape-sequence-bundle"
    assert rows[0]["record_path"] == str(record_path)


def test_dataset_store_rebuilds_index_from_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE2WORKSPACE_OPERATOR_STORE_EMBEDDINGS_ENABLED", "0")
    store = DatasetStore(tmp_path / "dataset_store")
    store.write_dataset(
        {
            "dataset_id": "long-read-pacbio",
            "name": "Long read PacBio toy reads",
            "domain": "genome_assembly",
            "summary": "PacBio reads for long-read assembly smoke tests.",
            "files": [{"media_type": "fastq", "uri": "reads.fastq"}],
            "tags": ["assembly"],
        }
    )
    store.db_path.unlink()

    rebuilt = DatasetStore(store.root)
    count = rebuilt.rebuild()
    rows = rebuilt.search_datasets(DatasetSearchFilter(domain="genome_assembly"))

    assert count == 1
    assert rows[0]["dataset_id"] == "long-read-pacbio"


def test_dataset_store_search_supports_semantic_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE2WORKSPACE_OPERATOR_STORE_EMBEDDINGS_ENABLED", "0")
    store = DatasetStore(tmp_path / "dataset_store")
    with patch(
        "code2workspace_cli.dataset_store._embed_documents",
        return_value=([[1.0, 0.0]], "test-embedding-model"),
    ), patch(
        "code2workspace_cli.dataset_store._embed_query",
        return_value=([1.0, 0.0], "test-embedding-model"),
    ):
        store.write_dataset(
            {
                "dataset_id": "respiratory-weekly-signals",
                "name": "Respiratory weekly signals",
                "domain": "respiratory_surveillance",
                "summary": (
                    "Weekly COVID and flu time series used for peak forecasting."
                ),
                "files": [{"media_type": "csv", "uri": "weekly_signals.csv"}],
                "tags": ["forecast"],
            }
        )
        rows = store.search_datasets(
            DatasetSearchFilter(query="latent semantic probe", media_type="csv")
        )

    assert (
        store.root / "datasets" / "respiratory-weekly-signals" / "embedding.json"
    ).exists()
    assert rows
    assert rows[0]["dataset_id"] == "respiratory-weekly-signals"
