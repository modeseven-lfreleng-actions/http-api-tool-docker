#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""
Security linter for pip install commands in GitHub workflows.

This script enforces that all pip install commands in GitHub workflows
use SHA256 hash pinning for security compliance.
"""

import argparse
import re
import sys
from pathlib import Path


def main() -> int:
    """Main function to check pip install security."""
    parser = argparse.ArgumentParser(
        description="Check GitHub workflows for pip install commands without SHA hashes"
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Files to check (if empty, checks all workflow files)"
    )

    args = parser.parse_args()

    # Determine files to check
    if args.files:
        files_to_check = [Path(f) for f in args.files]
    else:
        # Default to checking all workflow files
        workflow_dir = Path('.github/workflows')
        if workflow_dir.exists():
            files_to_check = list(workflow_dir.glob('*.yml')) + list(workflow_dir.glob('*.yaml'))
        else:
            print("No .github/workflows directory found", file=sys.stderr)
            return 1

    violation_count = 0

    for file_path in files_to_check:
        if not file_path.exists() or file_path.suffix not in ['.yml', '.yaml']:
            continue

        violations = check_file_for_violations(file_path)
        violation_count += violations

    if violation_count > 0:
        print_security_guidance()
        return 1

    print("✅ All pip install commands use proper SHA hash pinning")
    return 0


def check_file_for_violations(file_path: Path) -> int:
    """Check a single file for pip install violations."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"Warning: Could not read {file_path}: {e}", file=sys.stderr)
        return 0

    violations = 0
    lines = content.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Check for pip install commands
        if re.search(r'\bpip\s+.*install\b', line):
            # Collect full command (may span multiple lines)
            command_lines = [line]
            while line.endswith('\\') and i + 1 < len(lines):
                i += 1
                line = lines[i].strip()
                command_lines.append(line)

            full_command = ' '.join(command_lines)

            if is_violation(full_command):
                violations += 1
                print(f"❌ Violation in {file_path}:{i + 1}")
                print(f"   Command: {full_command}")
                print()

        i += 1

    return violations


def is_violation(command: str) -> bool:
    """Check if a pip install command violates security requirements."""
    # Skip safe patterns
    safe_patterns = [
        r'pip\s+.*install\s+--upgrade\s+pip\s*$',  # pip upgrade itself
        r'pip\s+.*install\s+-r\s+',  # requirements file
        r'pip\s+.*install\s+-e\s+',  # editable installs
        r'pip\s+.*install\s+\.\s*$',  # current directory
    ]

    for pattern in safe_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return False

    # Check for package with version constraints
    has_version = re.search(r'\b[a-zA-Z0-9_-]+\s*[><=!~]+\s*[0-9.]+', command)
    has_hash = '--hash=' in command or '--hash ' in command

    return bool(has_version and not has_hash)


def print_security_guidance() -> None:
    """Print security guidance for fixing violations."""
    print()
    print("🔒 Security Requirement:")
    print("All pip install commands with version constraints must use SHA256 hash pinning")
    print("to prevent supply chain attacks and ensure deterministic builds.")
    print()
    print("Recommended approach:")
    print("  Use the provided script to generate requirements with complete dependency tree:")
    print("  python3 scripts/generate_requirements.py \\")
    print("    --platform linux_x86_64 \\")
    print("    --python-version 311 \\")
    print("    --output /tmp/requirements.txt \\")
    print("    package==1.0.0")
    print("  pip install --require-hashes -r /tmp/requirements.txt")
    print()
    print("Manual approach (not recommended for complex dependencies):")
    print("  cat > requirements.txt << 'EOF'")
    print("  package==1.0.0 \\")
    print("    --hash=sha256:abcd1234...")
    print("  EOF")
    print("  pip install --require-hashes -r requirements.txt")
    print()
    print("Note: --hash is a per-requirement option for requirements files only,")
    print("      not a command-line option for 'pip install'. When using --require-hashes,")
    print("      ALL dependencies (including transitive ones) must have hashes.")
    print()
    print("For more information, see:")
    print("https://pip.pypa.io/en/stable/topics/secure-installs/")


if __name__ == "__main__":
    sys.exit(main())
