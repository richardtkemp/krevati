"""Tests for the one-shot 'upsearch' plumbing: collection-name derivation and
sync_update's walk/skip logic. These avoid Chroma and the embedding model by
driving sync_update with a fake Indexer, so they run fast and offline."""
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from config import Config
from filesystem import sync_update
from misc import upsearch_collection_name


# ── collection name ───────────────────────────────────────────────────

def test_collection_name_is_deterministic() -> None:
    d = Path("/home/foci/coach/memory")
    assert upsearch_collection_name(d) == upsearch_collection_name(d)


def test_collection_name_differs_per_dir() -> None:
    assert upsearch_collection_name(Path("/a")) != upsearch_collection_name(Path("/b"))


def test_collection_name_is_chroma_valid() -> None:
    name = upsearch_collection_name(Path("/some/dir with spaces/x"))
    assert 3 <= len(name) <= 63
    assert name[0].isalnum() and name[-1].isalnum()
    assert all(c.isalnum() or c in "._-" for c in name)


# ── sync_update ───────────────────────────────────────────────────────

class FakeIndexer:
    def __init__(self, stale: bool = True) -> None:
        self._stale = stale
        self.upserted: list[Path] = []

    def needs_indexing(self, file: Path) -> bool:
        return self._stale

    def upsert_file(self, vault_path: Path, relative_path: Path) -> None:
        self.upserted.append(relative_path)

    def delete_file(self, file: Path) -> None: ...
    def dangerously_wipe_db(self) -> None: ...


def _cfg(tmp_path: Path, exclude: list[str] | None = None) -> Config:
    # sync_update only touches vault_path / file_match_glob / exclude_dirs, so a
    # lightweight stand-in is enough; cast to satisfy the type checker.
    return cast(Config, SimpleNamespace(
        vault_path=tmp_path,
        file_match_glob="*.md",
        exclude_dirs=exclude or [],
    ))


def test_indexes_matching_files_recursively(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("alpha")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_text("bravo")
    (tmp_path / "note.txt").write_text("not markdown")

    idx = FakeIndexer(stale=True)
    n = sync_update(_cfg(tmp_path), idx)

    assert n == 2
    assert set(idx.upserted) == {Path("a.md"), Path("sub/b.md")}


def test_skips_unchanged_files(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("alpha")
    idx = FakeIndexer(stale=False)
    n = sync_update(_cfg(tmp_path), idx)
    assert n == 0
    assert idx.upserted == []


def test_hidden_files_are_excluded(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("alpha")
    (tmp_path / ".secret.md").write_text("hidden")
    idx = FakeIndexer()
    sync_update(_cfg(tmp_path), idx)
    assert idx.upserted == [Path("a.md")]


def test_excluded_dir_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("alpha")
    (tmp_path / "junk").mkdir()
    (tmp_path / "junk" / "c.md").write_text("charlie")
    idx = FakeIndexer()
    sync_update(_cfg(tmp_path, exclude=["junk"]), idx)
    assert idx.upserted == [Path("a.md")]
