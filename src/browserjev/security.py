from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit


class UnsafeURLError(ValueError):
    """Raised when a crawl target is malformed or not safe to fetch."""


Resolver = Callable[[str, int], Awaitable[list[str]]]
_INVALID_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
_VALID_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def normalize_start_url(value: str) -> str:
    """Return a strict normalized HTTP(S) URL while preserving path and query."""
    candidate = value.strip()
    if not candidate:
        raise UnsafeURLError("target URL cannot be empty")
    if any(ord(character) <= 32 or ord(character) == 127 for character in candidate):
        raise UnsafeURLError("target URL cannot contain whitespace or control characters")
    if _INVALID_PERCENT.search(candidate):
        raise UnsafeURLError("target URL contains an invalid percent escape")
    if "://" not in candidate:
        candidate = "https://" + candidate

    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise UnsafeURLError("target URL is malformed") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeURLError("target URL must use http or https")
    if not parsed.hostname:
        raise UnsafeURLError("target URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURLError("credentials in target URLs are not allowed")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURLError("target URL contains an invalid port") from exc

    raw_hostname = parsed.hostname
    try:
        literal = ipaddress.ip_address(raw_hostname)
    except ValueError:
        literal = None

    if literal is not None:
        host = str(literal)
        netloc_host = f"[{host}]" if literal.version == 6 else host
    else:
        try:
            host = raw_hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise UnsafeURLError("target URL contains an invalid hostname") from exc
        labels = host.rstrip(".").split(".")
        if (
            not host
            or len(host) > 253
            or any(not label or not _VALID_HOST_LABEL.fullmatch(label) for label in labels)
        ):
            raise UnsafeURLError("target URL contains an invalid hostname")
        host = host.rstrip(".")
        netloc_host = host

    netloc = netloc_host if port is None else f"{netloc_host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


def _is_public(address: str) -> bool:
    parsed = ipaddress.ip_address(address)
    return parsed.is_global and not (
        parsed.is_loopback
        or parsed.is_private
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    )


async def default_resolver(hostname: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        records = await loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"could not resolve target hostname: {hostname}") from exc
    addresses = {str(record[4][0]) for record in records}
    return sorted(addresses, key=lambda address: ipaddress.ip_address(address).version)


async def resolve_url(
    url: str,
    *,
    allow_private_networks: bool = False,
    resolver: Resolver = default_resolver,
) -> tuple[str, list[str]]:
    """Normalize a URL and resolve the exact addresses eligible for connection."""
    normalized = normalize_start_url(url)
    parsed = urlsplit(normalized)
    hostname = parsed.hostname
    assert hostname is not None
    if (hostname == "localhost" or hostname.endswith(".localhost")) and not (
        allow_private_networks
    ):
        raise UnsafeURLError("private or local network targets are blocked")

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None

    if literal is not None:
        addresses = [str(literal)]
    else:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = await resolver(hostname, port)

    if not addresses:
        raise UnsafeURLError(f"could not resolve target hostname: {hostname}")
    try:
        parsed_addresses = [str(ipaddress.ip_address(address)) for address in addresses]
    except ValueError as exc:
        raise UnsafeURLError("resolver returned an invalid IP address") from exc
    if not allow_private_networks and any(not _is_public(address) for address in parsed_addresses):
        raise UnsafeURLError("private or local network targets are blocked")
    return normalized, parsed_addresses


async def validate_public_url(
    url: str,
    *,
    allow_private_networks: bool = False,
    resolver: Resolver = default_resolver,
) -> str:
    """Validate a URL and reject targets resolving to non-public networks by default."""
    normalized, _addresses = await resolve_url(
        url,
        allow_private_networks=allow_private_networks,
        resolver=resolver,
    )
    return normalized
