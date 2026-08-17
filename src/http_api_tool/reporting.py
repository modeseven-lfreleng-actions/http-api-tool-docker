# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""
Console, step-summary, and workflow-command output.

``ActionReporter`` owns every channel the tool writes to: stdout for the
operator, ``GITHUB_STEP_SUMMARY`` for the job summary, ``GITHUB_OUTPUT``
for downstream steps, and stdout again for runner workflow commands.
"""

import os
import sys

import typer


class ActionReporter:
    """Write operator output and GitHub Actions side channels."""

    def __init__(self, debug: bool = False) -> None:
        self.debug: bool = debug
        self.step_summary_file: str | None = os.environ.get("GITHUB_STEP_SUMMARY")
        self.github_output_file: str | None = os.environ.get("GITHUB_OUTPUT")

    def log(self, message: str, emoji: str = "") -> None:
        """Write a message to stdout with an optional trailing emoji."""
        if emoji:
            message = f"{message} {emoji}"
        typer.echo(message)

    def debug_log(self, message: str) -> None:
        """Write a message to stdout when debug mode is active."""
        if self.debug:
            typer.echo(f"🐞 {message}")

    def write_step_summary(self, message: str) -> None:
        """Append a line to the GitHub Actions step summary."""
        if not self.step_summary_file:
            return
        try:
            with open(self.step_summary_file, "a", encoding="utf-8") as summary:
                _ = summary.write(f"{message}\n")
        except OSError as error:
            # Writing can fail because a container runs as a different
            # user than the one that created the summary file.
            self.debug_log(f"Unable to write to step summary file: {error}")

    def write_github_output(self, key: str, value: str) -> None:
        """Append a key/value pair to the GitHub Actions output file."""
        if not self.github_output_file:
            return
        try:
            with open(self.github_output_file, "a", encoding="utf-8") as output:
                if "\n" in str(value):
                    _ = output.write(f"{key}<<EOF\n{value}\nEOF\n")
                else:
                    _ = output.write(f"{key}={value}\n")
        except OSError as error:
            self.debug_log(f"Unable to write to GitHub output file: {error}")
            self.log(f"Output: {key}={value}")

    @staticmethod
    def escape_workflow_value(value: str) -> str:
        """Percent-encode the control characters of a workflow command.

        GitHub Actions treats ``%``, ``\\r``, and ``\\n`` as workflow
        command control characters, so encoding them prevents command
        injection through an attacker-supplied value.

        Args:
            value: The raw string to escape.

        Returns:
            The escaped string, safe for workflow command output.
        """
        value = value.replace("%", "%25")
        value = value.replace("\r", "%0D")
        value = value.replace("\n", "%0A")
        return value

    def emit_workflow_command(self, command: str) -> None:
        """Write a GitHub Actions workflow command to stdout.

        The runner strips these commands before it displays the log, so
        writing them through the binary buffer keeps static analysis from
        mistaking a runner directive for a clear-text log message. The
        text layer flushes first to stop the two interleaving.

        Args:
            command: The complete workflow command string.
        """
        sys.stdout.flush()
        sys.stdout.buffer.write(f"{command}\n".encode("utf-8"))
        sys.stdout.buffer.flush()

    def mask_credentials(self, username: str | None, password: str) -> None:
        """Register credential values with the GitHub Actions log masker.

        Emits ``::add-mask::`` workflow commands so the runner redacts
        the values from all later log output. Outside GitHub Actions this
        is a no-op.

        Args:
            username: The username to mask, or ``None``.
            password: The password to mask.
        """
        if not os.environ.get("GITHUB_ACTIONS"):
            return
        if username:
            self.emit_workflow_command(
                f"::add-mask::{self.escape_workflow_value(username)}"
            )
        if password:
            self.emit_workflow_command(
                f"::add-mask::{self.escape_workflow_value(password)}"
            )

    def mask_credentials_from_auth_string(self, auth_string: str) -> None:
        """Mask both halves of a ``user:password`` authentication string.

        Args:
            auth_string: Credentials in ``user:password`` format.
        """
        if ":" in auth_string:
            username, password = auth_string.split(":", 1)
        else:
            username = auth_string
            password = ""
        self.mask_credentials(username, password)
