"""Describe the concrete URLs served by a bound listening address."""

import ipaddress
import json
import socket
import subprocess


def interface_addresses() -> list[str]:
    addresses = ["127.0.0.1", "::1"]
    try:
        result = subprocess.run(
            ["ip", "-j", "address", "show", "up"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        interfaces = json.loads(result.stdout)
        if not isinstance(interfaces, list):
            raise ValueError("unexpected interface listing")
        for interface in interfaces:
            if not isinstance(interface, dict):
                continue
            for entry in interface.get("addr_info", []):
                if not isinstance(entry, dict) or entry.get("tentative") or entry.get("dadfailed"):
                    continue
                value = entry.get("local")
                if not isinstance(value, str):
                    continue
                try:
                    address = ipaddress.ip_address(value)
                except ValueError:
                    continue
                if address.version == 6 and address.is_link_local:
                    name = interface.get("ifname")
                    if not isinstance(name, str) or not name:
                        continue
                    value = f"{address}%{name}"
                addresses.append(value)
    except (OSError, subprocess.SubprocessError, ValueError):
        # Some minimal/non-Linux hosts have no iproute2. Hostname resolution
        # provides a useful fallback but cannot guarantee every interface.
        try:
            addresses.extend(
                item[4][0]
                for item in socket.getaddrinfo(socket.gethostname(), None, type=socket.SOCK_STREAM)
            )
        except OSError:
            pass
    return addresses


def listening_urls(host: str, port: int, *, dual_stack: bool = False) -> list[str]:
    bound = ipaddress.ip_address(host)
    if not bound.is_unspecified:
        addresses = [host]
    else:
        addresses = interface_addresses()
    urls = []
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if address.is_unspecified or address.is_multicast:
            continue
        if address.version != bound.version and not (bound.version == 6 and dual_stack):
            continue
        value = str(address)
        authority = f"[{value.replace('%', '%25')}]" if address.version == 6 else value
        url = f"http://{authority}:{port}"
        if url not in urls:
            urls.append(url)
    return urls
