"""Tests for Config validation (config.py).

API_KEY is bound at import time, so these patch the class attribute directly.
"""
import pytest
from config import Config


def test_raises_when_api_key_is_left_as_default(monkeypatch):
    monkeypatch.setattr(Config, 'API_KEY', 'default')
    with pytest.raises(ValueError):
        Config()


def test_constructs_when_api_key_is_set(monkeypatch):
    monkeypatch.setattr(Config, 'API_KEY', 'a-real-key')
    Config()
