"""Tests for full_update (filesystem.py)."""
from types import SimpleNamespace
from typing import cast

import pytest

import filesystem
from config import Config
from filesystem import full_update, Watcher


class FakeIndexer:
    def __init__(self):
        self.checked = []
        self.upserted = []

    def needs_indexing(self, file):
        self.checked.append(file)
        return True

    def upsert_file(self, vault_path, file):
        self.upserted.append(file)

    def delete_file(self, file): ...
    def dangerously_wipe_db(self): ...


@pytest.fixture
def no_ionice(monkeypatch):
    # full_update sets I/O priority via psutil; stub it out for hermeticity.
    class DummyProc:
        def ionice(self, *a, **k): pass
    monkeypatch.setattr(filesystem.psutil, 'Process', lambda: DummyProc())


def cfg_for(tmp_path):
    return cast(Config, SimpleNamespace(vault_path=tmp_path, file_match_glob='*.md'))


def test_indexes_matching_files_recursively(tmp_path, no_ionice):
    (tmp_path / 'a.md').write_text('x')
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'b.md').write_text('x')
    (tmp_path / 'note.txt').write_text('x')

    idx = FakeIndexer()
    full_update(cfg_for(tmp_path), idx)

    assert sorted(f.name for f in idx.upserted) == ['a.md', 'b.md']


def test_skips_hidden_files_and_hidden_directories(tmp_path, no_ionice):
    (tmp_path / 'visible.md').write_text('x')
    (tmp_path / '.secret.md').write_text('x')
    (tmp_path / '.hidden').mkdir()
    (tmp_path / '.hidden' / 'c.md').write_text('x')

    idx = FakeIndexer()
    full_update(cfg_for(tmp_path), idx)

    assert sorted(f.name for f in idx.upserted) == ['visible.md']


def test_only_upserts_files_that_need_indexing(tmp_path, no_ionice):
    (tmp_path / 'stale.md').write_text('x')
    (tmp_path / 'fresh.md').write_text('x')

    class PickyIndexer(FakeIndexer):
        def needs_indexing(self, file):
            return file.name == 'stale.md'

    idx = PickyIndexer()
    full_update(cfg_for(tmp_path), idx)

    assert [f.name for f in idx.upserted] == ['stale.md']


def test_one_failing_file_does_not_abort_the_whole_scan(tmp_path, no_ionice):
    (tmp_path / 'a.md').write_text('x')
    (tmp_path / 'b.md').write_text('x')

    class BoomIndexer(FakeIndexer):
        def upsert_file(self, vault_path, file):
            if file.name == 'a.md':
                raise RuntimeError('boom')
            self.upserted.append(file)

    idx = BoomIndexer()
    full_update(cfg_for(tmp_path), idx)

    assert [f.name for f in idx.upserted] == ['b.md']


def make_watcher(tmp_path, should_update=lambda p: True):
    cfg = cast(Config, SimpleNamespace(vault_path=tmp_path, file_match_glob='*.md'))
    calls = {'upsert': [], 'delete': []}
    w = Watcher(
        cfg,
        should_update=should_update,
        upsert=lambda vp, p: calls['upsert'].append(p),
        delete=lambda p: calls['delete'].append(p),
    )
    return w, calls


def test_handle_change_upserts_a_modified_md_file(tmp_path):
    f = tmp_path / 'note.md'
    f.write_text('x')
    w, calls = make_watcher(tmp_path, should_update=lambda p: True)
    w._handle_change(str(f))
    assert calls['upsert'] == [f]
    assert calls['delete'] == []


def test_handle_change_does_not_upsert_when_should_update_is_false(tmp_path):
    f = tmp_path / 'note.md'
    f.write_text('x')
    w, calls = make_watcher(tmp_path, should_update=lambda p: False)
    w._handle_change(str(f))
    assert calls['upsert'] == []


def test_handle_change_ignores_non_md_files(tmp_path):
    f = tmp_path / 'note.txt'
    f.write_text('x')
    w, calls = make_watcher(tmp_path)
    w._handle_change(str(f))
    assert calls['upsert'] == []
    assert calls['delete'] == []


def test_handle_change_deletes_a_missing_md_file(tmp_path):
    gone = tmp_path / 'gone.md'   # never created on disk
    w, calls = make_watcher(tmp_path)
    w._handle_change(str(gone))
    assert calls['delete'] == [gone]
    assert calls['upsert'] == []
