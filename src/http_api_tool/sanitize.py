# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""
Redaction helpers for values that reach logs or the job summary.

Every function here returns a value that is safe to display. Credential
extraction lives in ``extract_url_credentials``, whose result must never
reach a logging call.
"""

import json
from typing import Any
from urllib.parse import urlparse, urlunparse

SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "auth",
        "x-api-key",
        "x-auth-token",
        "x-access-token",
        "cookie",
        "set-cookie",
        "x-csrf-token",
        "x-session-token",
        "bearer",
        "api-key",
        "access-token",
    }
)

SENSITIVE_BODY_PATTERNS = (
    "password",
    "secret",
    "token",
    "key",
    "auth",
    "credential",
)


def sanitize_url_for_logging(url: str) -> str:
    """Remove credentials from a URL so it is safe to display."""
    if not url:
        return url

    try:
        parsed = urlparse(url)
        if not (parsed.username or parsed.password):
            return url
        sanitized_netloc = parsed.hostname or ""
        if parsed.port:
            sanitized_netloc += f":{parsed.port}"
        return urlunparse(parsed._replace(netloc=sanitized_netloc))
    except ValueError:
        return "[URL parsing failed - credentials may be present]"


def sanitize_headers_for_logging(headers_json: str) -> str:
    """Redact the values of headers that commonly carry secrets."""
    if not headers_json:
        return headers_json

    try:
        headers: dict[str, str] = json.loads(headers_json)
        sanitized = {
            key: "*** (redacted)" if key.lower() in SENSITIVE_HEADERS else value
            for key, value in headers.items()
        }
        return json.dumps(sanitized)
    except (json.JSONDecodeError, TypeError, AttributeError):
        return "*** (invalid JSON - potentially sensitive)"


def sanitize_request_body_for_logging(body: str, max_length: int = 100) -> str:
    """Truncate a request body, or withhold it when it looks sensitive."""
    if not body:
        return body

    body_lower = body.lower()
    if any(pattern in body_lower for pattern in SENSITIVE_BODY_PATTERNS):
        return "*** (request body contains potentially sensitive data)"

    if len(body) > max_length:
        return body[:max_length] + "... (truncated)"
    return body


def parse_url(url: str) -> dict[str, Any]:
    """Split a URL into display components, dropping any credentials.

    The ``clean_url`` entry and every other value returned here are safe
    to log. Use ``extract_url_credentials`` when the credentials
    themselves are needed.
    """
    parsed = urlparse(url)

    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    hostname = parsed.hostname or ""
    # urlparse strips the brackets that delimit an IPv6 literal, so a
    # round trip through urlunparse must put them back.
    if ":" in hostname:
        hostname = f"[{hostname}]"
    sanitized_netloc = hostname
    if parsed.port is not None:
        sanitized_netloc += f":{parsed.port}"
    clean_url = urlunparse(parsed._replace(netloc=sanitized_netloc))

    return {
        "protocol": parsed.scheme,
        "host": parsed.hostname,
        "port": port,
        "path": parsed.path or "/",
        "query": parsed.query,
        "fragment": parsed.fragment,
        "clean_url": clean_url,
    }


def extract_url_credentials(url: str) -> tuple[str | None, str]:
    """Return the ``(username, password)`` embedded in a URL.

    The return value feeds authentication setup only, and must never be
    passed to a logging function.

    Args:
        url: The URL that may carry embedded credentials.

    Returns:
        A tuple of ``(username, password)``. *username* is ``None`` when
        the URL carries no credentials; *password* defaults to an empty
        string.
    """
    parsed = urlparse(url)
    if parsed.username is not None or parsed.password is not None:
        return (parsed.username, parsed.password or "")
    return (None, "")
