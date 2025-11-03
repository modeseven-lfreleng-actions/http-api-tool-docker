<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# Security Scripts

This directory contains security-related scripts and tools for the project.

## check-pip-security.py

A security linter that enforces SHA256 hash pinning for all pip install
commands in GitHub workflows.

### Purpose

This script prevents supply chain attacks by ensuring that all pip install
commands with version constraints also include SHA256 hash verification.
This provides protection against:

- Package substitution attacks
- Repository compromise
- Dependency confusion attacks
- Ensures deterministic builds

### Usage

```bash
# Check all workflow files
python3 scripts/check-pip-security.py

# Check specific files
python3 scripts/check-pip-security.py .github/workflows/build-test.yaml

# Via make target
make security-check
```

### Integration

The project's security infrastructure integrates this script:

1. **Pre-commit Hook**: Automatically runs on workflow file changes
2. **GitHub Actions**: Runs as part of the security-scan job in CI
3. **Make Target**: Available via `make security-check` for local development

### Example Violations and Fixes

**Violation:**

```yaml
- name: Install package
  run: pip install requests==2.31.0
```

**Fixed:**

```yaml
- name: Install package
  run: pip install requests==2.31.0 \
    --hash=sha256:58cd2187c01e70e6e26505bca751777aa9f2ee0b7f4300988b709f44e013003f
```

### Safe Patterns (Not Flagged)

These patterns are safe and won't trigger violations:

- `pip install --upgrade pip` (pip upgrading itself)
- `pip install -r requirements.txt` (requirements files - checked separately)
- `pip install -e .` (editable installs for development)
- `pip install .` (current directory installation)

### Getting SHA Hashes

To get SHA256 hashes for packages:

```bash
# Download and get hash
pip download --no-deps package==version
sha256sum package-version-py3-none-any.whl
```

### Configuration

Configure the script via:

- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `Makefile` - Make target definition
- `.github/workflows/build-test.yaml` - CI integration

## generate_requirements.py

A universal utility script that generates complete requirements files with all
dependencies and their SHA256 hashes for any specified packages and platform.
This ensures reproducible builds and protects against supply chain attacks.

### Requirements Generation Purpose

This script solves the hash verification challenge by:

- Capturing all transitive dependencies for any package installation
- Downloading packages for any specified platform and Python version
- Generating SHA256 hashes for all dependencies
- Creating requirements files compatible with pip's `--require-hashes` mode

### Requirements Generation Usage

```bash
# Generate requirements for security tools (e.g., for CI workflows)
python3 scripts/generate_requirements.py \
  --platform linux_x86_64 \
  --python-version 310 \
  --output /tmp/security-requirements.txt \
  --comment "Security scanning tools" \
  safety==3.6.0 bandit==1.8.3 pip-audit==2.7.3

# Note: This project now uses UV for dependency management
# The Dockerfile uses UV directly, so requirements-docker.txt is no longer
# needed for package management
# UV lock file (uv.lock) is automatically generated and used during Docker
# builds
```

### When to Use

Run this script when:

- Setting up CI workflows that need hash-verified package installations for
  security tools
- Creating requirements files for specific tools with hash verification
- Updating package versions in any environment
- Ensuring supply chain security compliance

**Note:** Docker builds now use UV with `uv.lock` for dependency management.
This script is primarily used for generating requirements files for security
scanning tools and other CI utilities.

### Output

The script generates `requirements-docker.txt` containing:

```text
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

# Security scanning tools with SHA256 hash verification
# This ensures reproducible builds and protection against supply chain attacks
# Generated for Linux x86_64 platform

safety==3.6.0 \
    --hash=sha256:example_hash_here
bandit==1.8.3 \
    --hash=sha256:example_hash_here
# ... all other dependencies with hashes
```

### Integration with UV

The project now uses UV for dependency management. The Dockerfile uses UV directly:

```dockerfile
# Install dependencies using uv with lock file
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
```

This ensures that UV's lock file verification works and UV verifies all
dependencies using `uv.lock`.
