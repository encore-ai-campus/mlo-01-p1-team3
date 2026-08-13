from __future__ import annotations

import socket
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every Mock test fail immediately if it reaches a real socket."""

    def blocked(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("Mock test attempted a real network connection")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "gethostbyname", blocked)
    monkeypatch.setattr(socket, "gethostbyname_ex", blocked)
    monkeypatch.setattr(socket, "getnameinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
