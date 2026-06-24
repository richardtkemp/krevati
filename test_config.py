"""Tests for Config (config.py): TOML loading, coercion and API-key resolution.

Every test passes an explicit `path` so it reads a temp file rather than the
real ~/.config/krevati/config.toml.
"""
from pathlib import Path

import pytest

from config import Config, ConfigCreated, _EXAMPLE_PATH

# A complete, valid config body. Individual tests mutate/extend it.
FULL = """\
vault_name = "vault"
vault_path = "/data/notes"
cache_dir = "/data/cache"
file_match_glob = "*.md"
exclude_dirs = []
socket_path = "/tmp/krevati.sock"
server_enabled = true
socket_enabled = true
host = "0.0.0.0"
port = 5000
model_string = "BAAI/bge-small-en-v1.5"
model_context = 512
overlap = 150
"""


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(body)
    return p


def test_loads_values_from_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KREVATI_API_KEY", "k")
    cfg = Config(path=_write(tmp_path, FULL))
    assert cfg.port == 5000
    assert cfg.server_enabled is True
    # path-typed fields are coerced from the TOML string to a Path
    assert cfg.vault_path == Path("/data/notes")
    assert isinstance(cfg.vault_path, Path)


def test_copies_example_config_and_signals_when_file_missing(tmp_path: Path) -> None:
    # Parent dir also absent, to confirm it gets created.
    path = tmp_path / "krevati" / "config.toml"
    with pytest.raises(ConfigCreated):
        Config(path=path)

    # The shipped example is copied verbatim for the user to edit.
    assert path.exists()
    assert path.read_text() == _EXAMPLE_PATH.read_text()


def test_shipped_example_satisfies_the_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The example must define every required key, or the copy-on-first-run
    # flow would hand the user a config that fails to load.
    monkeypatch.setenv("KREVATI_API_KEY", "k")
    Config(path=_EXAMPLE_PATH)


def test_raises_when_a_required_key_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KREVATI_API_KEY", "k")
    body = FULL.replace("port = 5000\n", "")
    with pytest.raises(ValueError, match="port"):
        Config(path=_write(tmp_path, body))


def test_raises_when_api_key_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KREVATI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="KREVATI_API_KEY"):
        Config(path=_write(tmp_path, FULL))


def test_api_key_read_from_file_when_env_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KREVATI_API_KEY", raising=False)
    cfg = Config(path=_write(tmp_path, FULL + 'api_key = "from-file"\n'))
    assert cfg.API_KEY == "from-file"


def test_env_api_key_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KREVATI_API_KEY", "from-env")
    cfg = Config(path=_write(tmp_path, FULL + 'api_key = "from-file"\n'))
    assert cfg.API_KEY == "from-env"
