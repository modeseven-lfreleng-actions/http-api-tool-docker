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

# Generate requirements-docker.txt for PDM (Docker builds)
python3 scripts/generate_requirements.py \
  --platform linux_aarch64 \
  --python-version 311 \
  --output requirements-docker.txt \
  --comment "PDM and all its dependencies for Linux ARM64 platform" \
  pdm==2.24.2

# Generate for different PDM version
python3 scripts/generate_requirements.py \
  --platform linux_aarch64 \
  --python-version 311 \
  --output requirements-docker.txt \
  --comment "PDM and all its dependencies for Linux ARM64 platform" \
  pdm==2.26.0
```

### When to Use

Run this script when:

- Setting up CI workflows that need hash-verified package installations
- Creating Docker images that require reproducible builds
- **Docker builds automatically use this script during the build process**
- Updating package versions in any environment
- Ensuring supply chain security compliance

- Updating PDM version in the Docker container
- Docker build fails with hash verification errors
- Setting up the project for the first time
- Dependencies change in `pyproject.toml`

### Output

The script generates `requirements-docker.txt` containing:

```text
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

# PDM and all its dependencies with SHA256 hash verification
# This ensures reproducible builds and protection against supply chain attacks
# Generated for Linux ARM64 platform

pdm==2.25.4 \
    --hash=sha256:3efab7367cb5d9d6e4ef9db6130e4f5620c247343c8e95e18bd0d76b201ff7da
# ... all other dependencies with hashes
```

### Integration with Docker

The Dockerfile uses the generated file:

```dockerfile
# Copy requirements file with hashes
COPY requirements-docker.txt ./

# Install PDM with hash verification
RUN pip install -r requirements-docker.txt
```

This ensures that pip's `--require-hashes` mode works and verifies all dependencies.
