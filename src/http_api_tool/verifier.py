# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""
Retry orchestration for HTTP API testing.

``HTTPAPITester`` drives the attempt loop: it validates the inputs, asks
:mod:`http_api_tool.curl_client` for each request, and reports the
outcome through an :class:`~http_api_tool.reporting.ActionReporter`.
"""

import base64
import os
import sys
import time
from typing import Any

from .curl_client import (
    check_regex_match,
    create_curl_handle,
    describe_curl_error,
    perform_request,
)
from .reporting import ActionReporter
from .sanitize import parse_url, sanitize_url_for_logging
from .validation import validate_inputs

RESPONSE_CODE_HINTS: dict[int, str] = {
    401: "Unauthorized; check/supply valid API/service credentials",
    404: "Not Found; verify the URL or endpoint",
}

SERVER_ERROR_HINT = "Server Error; the API might be down or overloaded"


def _format_target(url_parts: dict[str, Any]) -> str:
    """Render the credential-free target as ``protocol://host:port``."""
    return f"{url_parts['protocol']}://{url_parts['host']}:{url_parts['port']}"


def _initial_result() -> dict[str, Any]:
    """Return the output dictionary with its pre-request defaults."""
    return {
        "response_http_code": 0,
        "response_header_json": "{}",
        "response_header_size": 0,
        "response_body_size": 0,
        "total_time": 0,
        "connect_time": 0,
        "regex_match": False,
        "response_body_base64": "",
        "time_delay": 0,
        "response_time_exceeded": False,
    }


class HTTPAPITester:
    """Test an HTTP API endpoint, retrying until it answers or gives up."""

    def __init__(self, reporter: ActionReporter | None = None) -> None:
        self.reporter: ActionReporter = reporter or ActionReporter()

    def handle_curl_error(self, error_code: int) -> bool:
        """Report a cURL failure and say whether retrying is worthwhile."""
        self.reporter.log(f"cURL error code: {error_code}")
        message, fatal = describe_curl_error(error_code)
        self.reporter.log(message, "❌")
        if fatal:
            self.reporter.write_step_summary(f"{message} ❌")
            return False
        return True

    def _describe_target(
        self, config: dict[str, Any], url_parts: dict[str, Any]
    ) -> None:
        """Log the target of the run and open the step summary."""
        if os.environ.get("GITHUB_ACTIONS"):
            self.reporter.log(f"🎯 Starting test: {config['service_name']}")
            self.reporter.log(
                f"🌐 Target URL: {sanitize_url_for_logging(config['url'])}"
            )

        self.reporter.debug_log("URL Debug Info:")
        self.reporter.debug_log(
            f"  Original URL: '{sanitize_url_for_logging(config['url'])}'"
        )
        self.reporter.debug_log(f"  Protocol: '{url_parts['protocol']}'")
        self.reporter.debug_log(f"  Host: '{url_parts['host']}'")
        self.reporter.debug_log(f"  Port: '{url_parts['port']}'")
        self.reporter.debug_log(f"  Path: '{url_parts['path']}'")

        self.reporter.write_step_summary(f"# {config['service_name']}")
        self.reporter.write_step_summary("### Check API/Service Availability 🌍")

    def _run_attempt(self, config: dict[str, Any]) -> dict[str, Any]:
        """Perform one request, releasing the handle whatever happens."""
        curl = create_curl_handle(self.reporter, **config)
        try:
            return perform_request(curl)
        finally:
            curl.close()

    def _record_response(
        self, result: dict[str, Any], response: dict[str, Any], time_delay: int
    ) -> None:
        """Copy the response metrics of one attempt into the outputs."""
        result.update(
            {
                "response_http_code": response["http_code"],
                "response_header_json": response["header_json"],
                "response_header_size": response["header_size"],
                "response_body_size": response["body_size"],
                "total_time": response["total_time"],
                "connect_time": response["connect_time"],
                "time_delay": time_delay,
            }
        )
        self.reporter.debug_log(f"Response Code: {response['http_code']}")
        self.reporter.debug_log(f"Header Size: {response['header_size']} bytes")
        self.reporter.debug_log(f"Body Size: {response['body_size']} bytes")

    def _log_success(
        self,
        response: dict[str, Any],
        url_parts: dict[str, Any],
        counter: int,
        time_delay: int,
    ) -> None:
        """Announce that the service answered with the expected code."""
        target = _format_target(url_parts)
        self.reporter.log(target, "✅")
        self.reporter.write_step_summary(f"{target} ✅")
        self.reporter.log(f"Returned status code: {response['http_code']}")
        if counter > 1:
            self.reporter.log(
                f"Time taken for service availability: {time_delay}", "💬"
            )

    def _check_response_time(
        self, result: dict[str, Any], response: dict[str, Any], config: dict[str, Any]
    ) -> None:
        """Compare the response time against the configured ceiling."""
        max_time = config["max_response_time"]
        total_time = response["total_time"]
        if max_time <= 0 or not total_time:
            return

        if total_time <= max_time:
            self.reporter.log(
                f"Response time within acceptable limit "
                f"({total_time} <= {max_time} seconds)",
                "✅",
            )
            self.reporter.write_step_summary(f"Response Time: {total_time} seconds")
            return

        self.reporter.log(
            f"Warning: Response time exceeded maximum "
            f"({total_time} > {max_time} seconds)",
            "⚠️",
        )
        result["response_time_exceeded"] = True
        self.reporter.write_step_summary(
            f"Response Time: {total_time} seconds (exceeded limit of {max_time})"
        )
        if config["fail_on_timeout"]:
            self.reporter.log(
                "Error: Response time exceeded maximum allowed time", "❌"
            )
            self.reporter.write_step_summary(
                "Error: Response time exceeded maximum allowed time ❌"
            )
            sys.exit(1)

    def _check_regex(
        self, result: dict[str, Any], response: dict[str, Any], config: dict[str, Any]
    ) -> None:
        """Match the response body against the configured pattern."""
        pattern = config.get("regex")
        if not pattern:
            return

        self.reporter.log("Regular expression provided; validating response/reply")
        body = response["response_body"]
        if not body:
            self.reporter.log(
                "Error: regex validation requested, but response empty", "❌"
            )
            sys.exit(1)

        matched = check_regex_match(body, pattern)
        result["regex_match"] = matched
        if matched:
            self.reporter.log("RegEx matched server reply/body", "✅")
            self.reporter.write_step_summary("RegEx matched server reply/body ✅")
        else:
            self.reporter.log("Warning: RegEx NOT matched server reply/body", "⚠️")
            self.reporter.write_step_summary(
                "Warning: RegEx NOT matched server reply/body ⚠️"
            )

    def _report_exhausted(
        self, result: dict[str, Any], url_parts: dict[str, Any], time_delay: int
    ) -> None:
        """Report that every attempt failed, and hint at the likely cause."""
        target = _format_target(url_parts)
        self.reporter.write_step_summary(target)
        self.reporter.log(target)
        failure = f"Error: service marked failed at {time_delay} seconds"
        self.reporter.log(failure, "❌")
        self.reporter.write_step_summary(f"{failure} ❌")

        response_code = result["response_http_code"]
        if not isinstance(response_code, int):
            return
        hint = RESPONSE_CODE_HINTS.get(response_code)
        if hint is None and response_code >= 500:
            hint = SERVER_ERROR_HINT
        if hint:
            self.reporter.log(hint, "⚠️")

    def test_api(self, **config: Any) -> dict[str, Any]:
        """Test the configured endpoint, retrying until it answers.

        Returns the collected outputs once the service returns the
        expected status code. Exits the process when the retries run out
        or an unrecoverable error occurs.
        """
        config = validate_inputs(**config)
        self.reporter.debug = config["debug"]

        url_parts = parse_url(config["url"])
        self._describe_target(config, url_parts)

        result = _initial_result()
        counter = 0
        time_delay = 0
        sleep_time = config["initial_sleep_time"]

        while True:
            counter += 1
            self.reporter.debug_log(f"Attempt: {counter} / {config['retries']}")
            self.reporter.debug_log(f"Delay/Wait Interval: {sleep_time} seconds")
            self.reporter.debug_log(f"Delay/Wait Current Value: {time_delay} seconds")

            response = self._run_attempt(config)
            self._record_response(result, response, time_delay)
            if config["include_response_body"] and response["response_body"]:
                result["response_body_base64"] = base64.b64encode(
                    response["response_body"]
                ).decode("ascii")

            if not response["success"]:
                error_code, _ = response["curl_error"]
                if not self.handle_curl_error(error_code):
                    sys.exit(1)
            elif response["http_code"] == config["expected_http_code"]:
                self._log_success(response, url_parts, counter, time_delay)
                self._check_response_time(result, response, config)
                self._check_regex(result, response, config)
                return result

            if counter >= config["retries"]:
                self._report_exhausted(result, url_parts, time_delay)
                sys.exit(1)

            self.reporter.log(f"Waiting for {sleep_time} seconds before retrying...")
            time.sleep(sleep_time)
            time_delay += sleep_time
            sleep_time = min(sleep_time * (2 ** (counter - 1)), config["max_delay"])
            self.reporter.log(f"Sleep/wait time for next attempt: {sleep_time} seconds")
