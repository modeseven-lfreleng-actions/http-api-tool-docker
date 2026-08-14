# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""
pycurl handle construction and request execution.

The functions here own everything that touches libcurl, so the retry and
reporting logic in :mod:`http_api_tool.verifier` stays free of transport
detail.
"""

import json
import os
import re
from io import BytesIO
from typing import Any

import pycurl

from .reporting import ActionReporter
from .sanitize import extract_url_credentials, sanitize_headers_for_logging

# cURL exit code mapped to its message and whether retrying is pointless.
CURL_ERRORS: dict[int, tuple[str, bool]] = {
    1: ("Error: Unsupported protocol", False),
    3: ("Error: URL malformed", False),
    5: ("Error: Couldn't resolve proxy", False),
    6: ("Error: Couldn't resolve host", False),
    7: ("Error: Failed to connect to host", False),
    28: ("Error: Request timeout", False),
    35: ("Error: SSL connect error", True),
    51: ("Error: The peer's SSL certificate is not OK", True),
    52: ("Error: Nothing was returned from the server", False),
    60: ("Error: SSL self-signed certificate", True),
}


def describe_curl_error(error_code: int) -> tuple[str, bool]:
    """Return the message for a cURL exit code, and whether it is fatal."""
    return CURL_ERRORS.get(
        error_code,
        (f"Error: cURL encountered an error (code {error_code})", False),
    )


def _configure_tls(
    curl: pycurl.Curl, reporter: ActionReporter, config: dict[str, Any]
) -> None:
    """Apply certificate verification and CA bundle settings."""
    if not config["verify_ssl"]:
        curl.setopt(pycurl.SSL_VERIFYPEER, 0)
        curl.setopt(pycurl.SSL_VERIFYHOST, 0)
        reporter.log("Warning: SSL certificate verification disabled", "⚠️")
        return

    ca_bundle_path = config.get("ca_bundle_path")
    if not ca_bundle_path:
        return
    if os.path.isfile(ca_bundle_path):
        curl.setopt(pycurl.CAINFO, ca_bundle_path)
        reporter.debug_log(f"Using custom CA bundle: {ca_bundle_path}")
    else:
        reporter.log(f"Warning: CA bundle file not found: {ca_bundle_path}", "⚠️")


def _configure_auth(
    curl: pycurl.Curl, reporter: ActionReporter, config: dict[str, Any]
) -> None:
    """Apply credentials taken from the config or embedded in the URL."""
    auth_string = config.get("auth_string")
    if not auth_string:
        username, password = extract_url_credentials(config["url"])
        if username is not None:
            auth_string = f"{username}:{password}"

    if not auth_string:
        return
    reporter.mask_credentials_from_auth_string(auth_string)
    reporter.log("Authentication credentials provided", "💬")
    curl.setopt(pycurl.USERPWD, auth_string)


def _build_headers(reporter: ActionReporter, config: dict[str, Any]) -> list[str]:
    """Assemble the request header lines from the config."""
    headers = []
    if config.get("request_body"):
        headers.append(f"Content-Type: {config['content_type']}")

    if not config.get("request_headers"):
        return headers

    try:
        custom_headers = json.loads(config["request_headers"])
    except json.JSONDecodeError:
        raise ValueError("Error: Invalid JSON in request_headers ❌") from None

    headers.extend(f"{key}: {value}" for key, value in custom_headers.items())
    sanitized = sanitize_headers_for_logging(config["request_headers"])
    reporter.debug_log(f"Added custom headers: {sanitized}")
    return headers


def _warn_about_verbose_credentials(
    reporter: ActionReporter, config: dict[str, Any]
) -> None:
    """Warn that pycurl's verbose mode prints credentials in clear text."""
    username, _ = extract_url_credentials(config["url"])
    if username is None and not config.get("auth_string"):
        return
    reporter.log("⚠️  Warning: Debug mode enabled with authentication credentials.", "⚠️")
    reporter.log("⚠️  pycurl verbose output may expose credentials in logs.", "⚠️")
    reporter.log("⚠️  Disable debug mode for production use.", "⚠️")


def create_curl_handle(reporter: ActionReporter, **config: Any) -> pycurl.Curl:
    """Build a configured pycurl handle for a single request."""
    curl = pycurl.Curl()

    curl.setopt(pycurl.URL, config["url"])
    curl.setopt(pycurl.TIMEOUT, config["curl_timeout"])
    curl.setopt(pycurl.CUSTOMREQUEST, config["http_method"])
    curl.setopt(pycurl.VERBOSE, config["debug"])
    if config["debug"]:
        _warn_about_verbose_credentials(reporter, config)

    _configure_tls(curl, reporter, config)

    if not config["connection_reuse"]:
        curl.setopt(pycurl.FRESH_CONNECT, 1)
        curl.setopt(pycurl.FORBID_REUSE, 1)

    if config["follow_redirects"]:
        curl.setopt(pycurl.FOLLOWLOCATION, 1)
    else:
        curl.setopt(pycurl.MAXREDIRS, 0)

    _configure_auth(curl, reporter, config)

    headers = _build_headers(reporter, config)
    if headers:
        curl.setopt(pycurl.HTTPHEADER, headers)

    if config.get("request_body"):
        body_data = config["request_body"].encode("utf-8")
        curl.setopt(pycurl.POSTFIELDS, body_data)
        curl.setopt(pycurl.POSTFIELDSIZE, len(body_data))

    # Nothing downstream reads the body in this combination, so ask for
    # headers alone.
    if (
        not config.get("regex")
        and not config.get("include_response_body", True)
        and not config["debug"]
    ):
        curl.setopt(pycurl.NOBODY, 1)

    return curl


def perform_request(curl: pycurl.Curl) -> dict[str, Any]:
    """Run a prepared request and return its response and metrics."""
    response_buffer = BytesIO()
    header_buffer = BytesIO()

    curl.setopt(pycurl.WRITEDATA, response_buffer)
    curl.setopt(pycurl.HEADERFUNCTION, header_buffer.write)

    try:
        curl.perform()
    except pycurl.error as error:
        error_code = error.args[0] if len(error.args) > 0 else 0
        error_msg = error.args[1] if len(error.args) > 1 else str(error)
        return {
            "success": False,
            "http_code": 0,
            "total_time": 0,
            "connect_time": 0,
            "body_size": 0,
            "header_size": 0,
            "response_body": b"",
            "response_headers": "",
            "header_json": "{}",
            "curl_error": (error_code, error_msg),
        }

    response_headers = header_buffer.getvalue().decode("utf-8", errors="ignore")
    return {
        "success": True,
        "http_code": int(curl.getinfo(pycurl.RESPONSE_CODE)),
        "total_time": curl.getinfo(pycurl.TOTAL_TIME),
        "connect_time": curl.getinfo(pycurl.CONNECT_TIME),
        "body_size": int(curl.getinfo(pycurl.SIZE_DOWNLOAD)),
        "header_size": int(curl.getinfo(pycurl.HEADER_SIZE)),
        "response_body": response_buffer.getvalue(),
        "response_headers": response_headers,
        "header_json": parse_headers_to_json(response_headers),
        "curl_error": None,
    }


def parse_headers_to_json(headers_text: str) -> str:
    """Render raw HTTP response headers as a compact JSON object."""
    if not headers_text.strip():
        return "{}"

    headers_dict = {}
    for raw_line in headers_text.strip().split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("HTTP/"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            headers_dict[key.strip()] = value.strip()

    try:
        return json.dumps(headers_dict, separators=(",", ":"))
    except (TypeError, ValueError):
        return "{}"


def check_regex_match(response_body: bytes, regex_pattern: str) -> bool:
    """Report whether the response body matches the given pattern."""
    if not regex_pattern:
        return True

    try:
        body_text = response_body.decode("utf-8", errors="ignore")
        return bool(re.search(regex_pattern, body_text))
    except (re.error, UnicodeDecodeError, AttributeError):
        return False
