import json
import socket
from types import SimpleNamespace

from codex_view import network


def test_all_assigned_ipv4_addresses_with_actual_port(monkeypatch):
    interfaces = [
        {"ifname": "lo", "addr_info": [{"local": "127.0.0.1"}, {"local": "::1"}]},
        {
            "ifname": "eth0",
            "addr_info": [
                {"local": "192.0.2.10"},
                {"local": "192.0.2.11"},
                {"local": "fe80::1"},
            ],
        },
        {"ifname": "vpn0", "addr_info": [{"local": "10.0.0.2"}, {"local": "192.0.2.10"}]},
    ]
    monkeypatch.setattr(
        network.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=json.dumps(interfaces))
    )
    assert network.listening_urls("0.0.0.0", 43210) == [
        "http://127.0.0.1:43210",
        "http://192.0.2.10:43210",
        "http://192.0.2.11:43210",
        "http://10.0.0.2:43210",
    ]


def test_restricted_bind_does_not_advertise_other_interfaces(monkeypatch):
    def unexpected():
        raise AssertionError("No discovery needed for a specific bind")

    monkeypatch.setattr(network, "interface_addresses", unexpected)
    assert network.listening_urls("127.0.0.1", 1234) == ["http://127.0.0.1:1234"]
    assert network.listening_urls("::1", 1234) == ["http://[::1]:1234"]


def test_ipv6_scope_invalid_addresses_and_dual_stack(monkeypatch):
    monkeypatch.setattr(
        network,
        "interface_addresses",
        lambda: [
            "127.0.0.1",
            "::1",
            "fe80::1%eth0",
            "2001:db8::1",
            "::",
            "ff02::1",
            "invalid",
        ],
    )
    expected = [
        "http://[::1]:8080",
        "http://[fe80::1%25eth0]:8080",
        "http://[2001:db8::1]:8080",
    ]
    assert network.listening_urls("::", 8080) == expected
    assert network.listening_urls("::", 8080, dual_stack=True) == [
        "http://127.0.0.1:8080",
        *expected,
    ]


def test_missing_ip_command_falls_back_to_hostname(monkeypatch):
    def unavailable(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(network.subprocess, "run", unavailable)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.10", 0)),
        ],
    )
    assert network.listening_urls("0.0.0.0", 8765) == [
        "http://127.0.0.1:8765",
        "http://192.0.2.10:8765",
    ]


def test_tentative_addresses_are_skipped(monkeypatch):
    monkeypatch.setattr(
        network.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            stdout=json.dumps(
                [
                    {
                        "ifname": "eth0",
                        "addr_info": [
                            {"local": "2001:db8::1", "tentative": True},
                            {"local": "2001:db8::2"},
                        ],
                    }
                ]
            )
        ),
    )
    assert network.listening_urls("::", 8765) == [
        "http://[::1]:8765",
        "http://[2001:db8::2]:8765",
    ]
