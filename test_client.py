"""Tests for the CLI socket client (client.py)."""
import os
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from config import Config
from client import search_daemon_send


def test_returns_empty_when_socket_does_not_exist(tmp_path: Path) -> None:
    cfg = cast(Config, SimpleNamespace(socket_path=str(tmp_path / 'nope.sock')))
    assert search_daemon_send(cfg, 'rosie') == ''


@pytest.mark.timeout(5)
def test_sends_query_and_returns_the_reply(tmp_path: Path) -> None:
    sock_path = str(tmp_path / 'krevati.sock')
    received = {}

    def fake_daemon() -> None:
        with socket.socket(socket.AF_UNIX) as s:
            s.bind(sock_path)
            s.listen()
            conn, _ = s.accept()
            data = b''
            while chunk := conn.recv(1024):
                data += chunk
            received['query'] = data.decode()
            conn.sendall(b'RESULT-FOR-ROSIE')
            conn.close()

    t = threading.Thread(target=fake_daemon, daemon=True)
    t.start()

    for _ in range(100):   # wait for the server to bind before connecting
        if os.path.exists(sock_path):
            break
        time.sleep(0.02)

    cfg = cast(Config, SimpleNamespace(socket_path=sock_path))
    result = search_daemon_send(cfg, 'rosie')
    t.join(timeout=2)

    assert received['query'] == 'rosie'
    assert result == 'RESULT-FOR-ROSIE'
