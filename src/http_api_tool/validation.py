# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""
Input normalisation and validation.

GitHub Actions delivers every input as a string, so the values arrive
here untyped and leave as the booleans, integers, and floats the rest of
the package expects.
"""

import json
import os
import re
from typing import Any

BOOL_FIELDS = (
    "verify_ssl",
    "include_response_body",
    "follow_redirects",
    "connection_reuse",
    "debug",
    "fail_on_timeout",
    "show_header_json",
)

INT_FIELDS = (
    "initial_sleep_time",
    "max_delay",
    "retries",
    "curl_timeout",
    "expected_http_code",
)

TRUTHY_VALUES = frozenset({"true", "1", "yes", "on"})


def _coerce_booleans(values: dict[str, Any]) -> None:
    """Turn the string form of each boolean input into a ``bool``."""
    for field in BOOL_FIELDS:
        if field in values and isinstance(values[field], str):
            values[field] = values[field].lower() in TRUTHY_VALUES


def _coerce_integers(values: dict[str, Any]) -> None:
    """Turn each integer input into a non-negative ``int``."""
    for field in INT_FIELDS:
        if field not in values:
            continue
        error_msg = f"Error: {field} must be a positive integer ❌"
        try:
            parsed = int(values[field])
        except (ValueError, TypeError):
            raise ValueError(error_msg) from None
        if parsed < 0:
            raise ValueError(error_msg)
        values[field] = parsed


def _coerce_floats(values: dict[str, Any]) -> None:
    """Turn each floating-point input into a ``float``."""
    if "max_response_time" not in values:
        return
    try:
        values["max_response_time"] = float(values["max_response_time"])
    except (ValueError, TypeError):
        raise ValueError("Error: max_response_time must be a number ❌") from None


def _check_patterns(values: dict[str, Any]) -> None:
    """Reject an unusable regular expression or header JSON document."""
    if values.get("regex"):
        try:
            _ = re.compile(values["regex"])
        except re.error:
            raise ValueError(
                "Error: Invalid regular expression syntax ❌\n"
                + f"Regex: {values['regex']}"
            ) from None

    if values.get("request_headers"):
        try:
            _ = json.loads(values["request_headers"])
        except json.JSONDecodeError:
            raise ValueError("Error: request_headers must be valid JSON ❌") from None


def _resolve_url(values: dict[str, Any]) -> None:
    """Apply the URL fallback, and require a URL under GitHub Actions.

    Typer enforces the URL for CLI use, so only the GitHub Actions entry
    point needs this guard.
    """
    fallback = os.environ.get("HTTP_API_URL")
    if os.environ.get("GITHUB_ACTIONS") and not values.get("url") and not fallback:
        raise ValueError("Error: a URL must be provided as input ❌")

    if not values.get("url"):
        values["url"] = fallback


def validate_inputs(**kwargs: Any) -> dict[str, Any]:
    """Normalise and validate the raw inputs, returning usable values."""
    _coerce_booleans(kwargs)
    _resolve_url(kwargs)
    _coerce_integers(kwargs)
    _coerce_floats(kwargs)
    _check_patterns(kwargs)
    return kwargs
