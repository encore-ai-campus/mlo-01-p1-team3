from __future__ import annotations

import socket
from collections.abc import Callable
from typing import Any

import pytest


@pytest.mark.parametrize(
    "attempt",
    [
        lambda: socket.create_connection(("example.test", 443)),
        lambda: socket.getaddrinfo("example.test", 443),
        lambda: socket.gethostbyname("example.test"),
        lambda: socket.gethostbyname_ex("example.test"),
        lambda: socket.getnameinfo(("127.0.0.1", 443), 0),
    ],
    ids=(
        "create-connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname-ex",
        "getnameinfo",
    ),
)
def test_mock_network_guard_blocks_connection_and_dns(
    attempt: Callable[[], Any],
) -> None:
    with pytest.raises(
        pytest.fail.Exception, match="Mock test attempted a real network connection"
    ):
        attempt()


@pytest.mark.parametrize("method_name", ["connect", "connect_ex"])
def test_mock_network_guard_blocks_socket_methods(method_name: str) -> None:
    with socket.socket() as candidate:
        with pytest.raises(
            pytest.fail.Exception,
            match="Mock test attempted a real network connection",
        ):
            getattr(candidate, method_name)(("127.0.0.1", 443))
