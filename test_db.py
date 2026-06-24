"""Tests for db.py: the SearchResult dataclass and the pure is_stale decision."""
from dataclasses import asdict
from pathlib import Path
from db import SearchResult, is_stale


def test_equal_results_compare_equal() -> None:
    a = SearchResult('notes/p.md', 0.9, 'Heading', 'snippet')
    b = SearchResult('notes/p.md', 0.9, 'Heading', 'snippet')
    assert a == b


def test_results_differing_in_one_field_are_not_equal() -> None:
    a = SearchResult('notes/p.md', 0.9, 'Heading', 'snippet')
    b = SearchResult('notes/q.md', 0.9, 'Heading', 'snippet')
    assert a != b


def test_asdict_produces_the_json_shape() -> None:
    a = SearchResult('notes/p.md', 0.91, '', 'hi rosie')
    assert asdict(a) == {
        'path': 'notes/p.md',
        'score': 0.91,
        'header': '',
        'snippet': 'hi rosie',
    }


# ── is_stale (pure decision: no I/O, no Chroma) ───────────────────────
#
# Signature: is_stale(file, size, stored_ver, ver,
#                           stored_chunking, chunking, stored_mtime, mtime)

FILE = Path('notes/x.md')          # unused by the function; passed for realism
CHUNK = '(1536, 150)'              # a "current" chunking string


def test_empty_file_is_never_indexed() -> None:
    # size 0 short-circuits even when every other input would trigger a reindex
    assert is_stale(FILE, 0, 0, 2, 'old', CHUNK, 0, 999) is False


def test_unindexed_signals_via_caller_not_here() -> None:
    # An up-to-date, indexed, non-empty file is left alone.
    assert is_stale(FILE, 10, 2, 2, CHUNK, CHUNK, 100, 100) is False


def test_schema_version_bump_triggers_reindex() -> None:
    assert is_stale(FILE, 10, stored_ver=1, ver=2,
                          stored_chunking=CHUNK, chunking=CHUNK,
                          stored_mtime=100, mtime=100) is True


def test_chunking_change_triggers_reindex() -> None:
    assert is_stale(FILE, 10, 2, 2, 'old-chunking', CHUNK, 100, 100) is True


def test_newer_file_mtime_triggers_reindex() -> None:
    assert is_stale(FILE, 10, 2, 2, CHUNK, CHUNK, stored_mtime=100, mtime=101) is True


def test_equal_mtime_is_not_reindexed() -> None:
    assert is_stale(FILE, 10, 2, 2, CHUNK, CHUNK, stored_mtime=100, mtime=100) is False


def test_older_file_mtime_is_not_reindexed() -> None:
    assert is_stale(FILE, 10, 2, 2, CHUNK, CHUNK, stored_mtime=100, mtime=50) is False


def test_empty_takes_precedence_over_a_schema_bump() -> None:
    assert is_stale(FILE, 0, stored_ver=1, ver=2,
                          stored_chunking=CHUNK, chunking=CHUNK,
                          stored_mtime=100, mtime=100) is False
