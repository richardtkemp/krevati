"""Tests for the HTTP and socket servers (server.py).

Uses Flask's in-process test client with an injected FakeSearcher, so no real
server, model, DB, or network is involved.
"""
import json
from types import SimpleNamespace
from typing import cast

from flask.testing import FlaskClient

from config import Config
from db import SearchResult
from server import Webserver, Socketserver


class FakeSearcher:
    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results or []
        self.last_query = None
        self.last_limit = None

    def search(self, term: str, n_results: int = 5) -> list[SearchResult]:
        self.last_query = term
        self.last_limit = n_results
        return self.results


def make_client(searcher: FakeSearcher, api_key: str = 'testkey') -> FlaskClient:
    cfg = cast(Config, SimpleNamespace(API_KEY=api_key, host='127.0.0.1', port=5000))
    return Webserver(cfg, searcher).app.test_client()


LOCAL = {'REMOTE_ADDR': '127.0.0.1'}   # auth skipped for localhost
REMOTE = {'REMOTE_ADDR': '8.8.8.8'}    # auth required


# ── query handling ──────────────────────────────────────────────────────────

def test_query_is_read_from_the_request_body() -> None:
    fake = FakeSearcher([SearchResult('notes/rosie.md', 0.9, '', 'hi')])
    client = make_client(fake)
    resp = client.post('/search', json={'query': 'rosie', 'limit': 5}, environ_base=LOCAL)
    assert resp.status_code == 200
    assert fake.last_query == 'rosie'
    assert fake.last_limit == 5


def test_response_is_a_json_list_of_results() -> None:
    fake = FakeSearcher([SearchResult('notes/rosie.md', 0.91, '', 'hi rosie')])
    client = make_client(fake)
    resp = client.post('/search', json={'query': 'rosie', 'limit': 5}, environ_base=LOCAL)
    assert json.loads(resp.data) == [
        {'path': 'notes/rosie.md', 'score': 0.91, 'header': '', 'snippet': 'hi rosie'}
    ]


def test_missing_query_returns_400_and_does_not_call_searcher() -> None:
    fake = FakeSearcher()
    client = make_client(fake)
    resp = client.post('/search', json={'limit': 5}, environ_base=LOCAL)
    assert resp.status_code == 400
    assert fake.last_query is None


# ── limit validation ────────────────────────────────────────────────────────

def test_omitted_limit_uses_a_default_and_succeeds() -> None:
    fake = FakeSearcher()
    client = make_client(fake)
    resp = client.post('/search', json={'query': 'rosie'}, environ_base=LOCAL)
    assert resp.status_code == 200


def test_non_int_limit_returns_400() -> None:
    fake = FakeSearcher()
    client = make_client(fake)
    resp = client.post('/search', json={'query': 'rosie', 'limit': 'abc'}, environ_base=LOCAL)
    assert resp.status_code == 400


# ── auth ────────────────────────────────────────────────────────────────────

def test_localhost_is_allowed_without_a_token() -> None:
    client = make_client(FakeSearcher())
    resp = client.post('/search', json={'query': 'x', 'limit': 5}, environ_base=LOCAL)
    assert resp.status_code == 200


def test_remote_without_token_is_rejected() -> None:
    client = make_client(FakeSearcher())
    resp = client.post('/search', json={'query': 'x', 'limit': 5}, environ_base=REMOTE)
    assert resp.status_code == 401


def test_remote_with_wrong_token_is_rejected() -> None:
    client = make_client(FakeSearcher(), api_key='secret')
    resp = client.post('/search', json={'query': 'x', 'limit': 5},
                       headers={'Authorization': 'Bearer wrong'}, environ_base=REMOTE)
    assert resp.status_code == 401


def test_remote_with_correct_token_is_allowed() -> None:
    client = make_client(FakeSearcher(), api_key='secret')
    resp = client.post('/search', json={'query': 'x', 'limit': 5},
                       headers={'Authorization': 'Bearer secret'}, environ_base=REMOTE)
    assert resp.status_code == 200


# ── socket server's pretty_print ────────────────────────────────────────────

def make_socketserver() -> Socketserver:
    cfg = cast(Config, SimpleNamespace(socket_path='/tmp/unused-in-test.sock'))
    return Socketserver(cfg, FakeSearcher())


def test_pretty_print_of_no_results_is_empty_string() -> None:
    assert make_socketserver().pretty_print([]) == ''


def test_pretty_print_includes_score_path_header_and_snippet() -> None:
    out = make_socketserver().pretty_print(
        [SearchResult('notes/x.md', 0.876, 'Heading', 'the snippet')])
    assert 'SCORE 0.876' in out
    assert 'PATH notes/x.md' in out
    assert 'HEADER Heading' in out
    assert 'the snippet' in out


def test_pretty_print_truncates_snippet_to_200_chars() -> None:
    out = make_socketserver().pretty_print([SearchResult('x', 0.5, '', 'a' * 500)])
    assert 'a' * 200 in out
    assert 'a' * 201 not in out
