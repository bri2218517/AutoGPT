import json
from pathlib import Path

import pytest

from backend.data import block_preflight_estimates as bpe


@pytest.fixture(autouse=True)
def reset_cache():
    bpe.reset_cache()
    yield
    bpe.reset_cache()


def test_missing_file_returns_zero(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bpe, "_ESTIMATES_PATH", tmp_path / "missing.json")
    assert bpe.get_preflight_estimate("any-id") == 0


def test_malformed_json_falls_back_to_zero(monkeypatch, tmp_path: Path):
    bad = tmp_path / "estimates.json"
    bad.write_text("{ not valid json")
    monkeypatch.setattr(bpe, "_ESTIMATES_PATH", bad)
    assert bpe.get_preflight_estimate("any-id") == 0


def test_returns_estimate_for_known_block(monkeypatch, tmp_path: Path):
    f = tmp_path / "estimates.json"
    f.write_text(
        json.dumps(
            {
                "version": 1,
                "estimates": {
                    "block-1": {
                        "block_name": "FooBlock",
                        "cost_type": "SECOND",
                        "samples": 50,
                        "mean_credits": 7,
                    }
                },
            }
        )
    )
    monkeypatch.setattr(bpe, "_ESTIMATES_PATH", f)
    assert bpe.get_preflight_estimate("block-1") == 7
    assert bpe.get_preflight_estimate("block-2") == 0


def test_cache_does_not_re_read_file(monkeypatch, tmp_path: Path):
    f = tmp_path / "estimates.json"
    f.write_text(
        json.dumps(
            {
                "version": 1,
                "estimates": {
                    "block-1": {
                        "block_name": "FooBlock",
                        "cost_type": "SECOND",
                        "samples": 50,
                        "mean_credits": 7,
                    }
                },
            }
        )
    )
    monkeypatch.setattr(bpe, "_ESTIMATES_PATH", f)
    assert bpe.get_preflight_estimate("block-1") == 7
    # Mutate the file; cached value should win until reset.
    f.write_text(
        json.dumps(
            {
                "version": 1,
                "estimates": {
                    "block-1": {
                        "block_name": "FooBlock",
                        "cost_type": "SECOND",
                        "samples": 50,
                        "mean_credits": 999,
                    }
                },
            }
        )
    )
    assert bpe.get_preflight_estimate("block-1") == 7
    bpe.reset_cache()
    assert bpe.get_preflight_estimate("block-1") == 999
