"""Tests for get_mtime (misc.py). chunk_text is covered in test_chunk.py."""
import os
from misc import get_mtime


def test_get_mtime_returns_an_int(tmp_path):
    f = tmp_path / 'x.md'
    f.write_text('hi')
    os.utime(f, (1000, 1000))
    assert get_mtime(f) == 1000
    assert isinstance(get_mtime(f), int)


def test_get_mtime_truncates_subsecond_precision(tmp_path):
    f = tmp_path / 'x.md'
    f.write_text('hi')
    os.utime(f, (1000.9, 1000.9))
    assert get_mtime(f) == 1000   # truncated, not rounded
