"""Tests for filesystem.py: full_update (discovery + enqueue) and Watcher routing.

Both full_update and Watcher now hand work to a Feeder, whose worker thread does
the real indexing. These tests replace the Feeder with a recording stub (see the
autouse `enqueued` fixture) so they assert *what gets enqueued* deterministically,
without spawning the worker thread or touching the class-global queue.
"""
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import filesystem
from config import Config
from db import WorkItem
from filesystem import full_update, Watcher


class FakeIndexer:
    def __init__(self, needs: bool = True) -> None:
        self._needs = needs
        self.checked = []
        self.deleted = []

    def needs_indexing(self, file: Path) -> bool:
        self.checked.append(file)
        return self._needs

    def upsert_file(self, vault_path: Path, relative_path: Path) -> None: ...

    def delete_file(self, file: Path) -> None:
        self.deleted.append(file)

    def dangerously_wipe_db(self) -> None: ...


@pytest.fixture(autouse=True)
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[WorkItem]:
    # Replace Feeder everywhere in filesystem.py with a stub that just records
    # the WorkItems handed to it — no worker thread, no shared queue. Autouse so
    # no test can accidentally start the real daemon worker. Returns the list of
    # recorded items for tests that want to assert on it.
    items = []

    class FakeFeeder:
        def __init__(self, idx: object = None) -> None: pass
        def enqueue(self, item: WorkItem) -> None: items.append(item)

    monkeypatch.setattr(filesystem, 'Feeder', FakeFeeder)
    return items


def cfg_for(tmp_path: Path, exclude_dirs: list[str] | None = None) -> Config:
    return cast(Config, SimpleNamespace(
        vault_path=tmp_path,
        file_match_glob='*.md',
        exclude_dirs=exclude_dirs or [],
    ))


# ── full_update: discovers matching files and enqueues one WorkItem each ──────

def test_enqueues_matching_files_recursively(tmp_path: Path, enqueued: list[WorkItem]) -> None:
    (tmp_path / 'a.md').write_text('x')
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'b.md').write_text('x')
    (tmp_path / 'note.txt').write_text('x')   # non-match, ignored

    full_update(cfg_for(tmp_path), FakeIndexer())

    # .txt excluded; vault-relative paths carried on each WorkItem
    assert {str(i.relative_path) for i in enqueued} == {'a.md', 'sub/b.md'}
    assert all(i.vault_path == tmp_path for i in enqueued)


def test_skips_hidden_files_and_hidden_directories(tmp_path: Path, enqueued: list[WorkItem]) -> None:
    (tmp_path / 'visible.md').write_text('x')
    (tmp_path / '.secret.md').write_text('x')
    (tmp_path / '.hidden').mkdir()
    (tmp_path / '.hidden' / 'c.md').write_text('x')

    full_update(cfg_for(tmp_path), FakeIndexer())

    assert sorted(i.relative_path.name for i in enqueued) == ['visible.md']


def test_excludes_directories_by_bare_name(tmp_path: Path, enqueued: list[WorkItem]) -> None:
    (tmp_path / 'keep.md').write_text('x')
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules' / 'dep.md').write_text('x')

    full_update(cfg_for(tmp_path, exclude_dirs=['node_modules']), FakeIndexer())

    assert sorted(i.relative_path.name for i in enqueued) == ['keep.md']


def test_excludes_an_absolute_subtree(tmp_path: Path, enqueued: list[WorkItem]) -> None:
    (tmp_path / 'keep.md').write_text('x')
    (tmp_path / 'archive').mkdir()
    (tmp_path / 'archive' / 'old.md').write_text('x')

    excluded = str(tmp_path / 'archive')   # an absolute path, not a bare name
    full_update(cfg_for(tmp_path, exclude_dirs=[excluded]), FakeIndexer())

    assert sorted(i.relative_path.name for i in enqueued) == ['keep.md']


def test_absolute_exclude_matches_through_a_symlinked_vault(
        tmp_path: Path, enqueued: list[WorkItem]) -> None:
    # vault is reached via a symlink, but the exclude is given as the real path.
    # Without resolving, the prefixes wouldn't match; the .resolve() makes it work.
    real = tmp_path / 'real'
    (real / 'archive').mkdir(parents=True)
    (real / 'keep.md').write_text('x')
    (real / 'archive' / 'old.md').write_text('x')
    vault = tmp_path / 'vault'
    vault.symlink_to(real)

    full_update(cfg_for(vault, exclude_dirs=[str(real / 'archive')]), FakeIndexer())

    assert sorted(i.relative_path.name for i in enqueued) == ['keep.md']


# ── Watcher._handle_change: routes a single filesystem event ──────────────────

def test_handle_change_enqueues_a_modified_md_file(tmp_path: Path, enqueued: list[WorkItem]) -> None:
    f = tmp_path / 'note.md'
    f.write_text('x')
    idx = FakeIndexer(needs=True)
    w = Watcher(cfg_for(tmp_path), idx)

    w._handle_change(str(f))

    assert len(enqueued) == 1
    assert enqueued[0].vault_path == tmp_path
    assert enqueued[0].relative_path == Path('note.md')
    assert idx.deleted == []


def test_handle_change_does_not_enqueue_when_should_update_is_false(tmp_path: Path, enqueued: list[WorkItem]) -> None:
    f = tmp_path / 'note.md'
    f.write_text('x')
    w = Watcher(cfg_for(tmp_path), FakeIndexer(needs=False))

    w._handle_change(str(f))

    assert enqueued == []


def test_handle_change_ignores_non_md_files(tmp_path: Path, enqueued: list[WorkItem]) -> None:
    f = tmp_path / 'note.txt'
    f.write_text('x')
    idx = FakeIndexer()
    w = Watcher(cfg_for(tmp_path), idx)

    w._handle_change(str(f))

    assert enqueued == []
    assert idx.deleted == []


def test_handle_change_ignores_files_in_excluded_dirs(tmp_path: Path, enqueued: list[WorkItem]) -> None:
    d = tmp_path / 'node_modules'
    d.mkdir()
    f = d / 'dep.md'
    f.write_text('x')
    w = Watcher(cfg_for(tmp_path, exclude_dirs=['node_modules']), FakeIndexer())

    w._handle_change(str(f))

    assert enqueued == []


def test_handle_change_deletes_a_missing_md_file(tmp_path: Path, enqueued: list[WorkItem]) -> None:
    gone = tmp_path / 'gone.md'   # never created on disk
    idx = FakeIndexer()
    w = Watcher(cfg_for(tmp_path), idx)

    w._handle_change(str(gone))

    assert idx.deleted == [gone]
    assert enqueued == []
