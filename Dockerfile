# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

# Multi-stage build for optimized caching and smaller final image
FROM python:3.11-slim@sha256:7a3ed1226224bcc1fe5443262363d42f48cf832a540c1836ba8ccbeaadf8637c AS base

# Install system dependencies and create app user in a single layer
RUN apt-get update && apt-get install -y \
    build-essential \
    ca-certificates \
    curl \
    docker.io \
    iproute2 \
    libcurl4-openssl-dev \
    libssl-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && groupadd -r appuser \
    && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Build stage for dependencies
FROM base AS deps

# Copy the requirements generation script
COPY scripts/generate_requirements.py ./scripts/

# Generate requirements file dynamically for the current platform during build
# This ensures correct hashes for the actual build environment
# Note: Script will fallback to current platform if specific platform downloads fail
RUN python3 scripts/generate_requirements.py \
    --platform linux_x86_64 \
    --python-version 311 \
    --output requirements-docker.txt \
    --comment "PDM and all its dependencies generated for Docker build environment" \
    pdm==2.24.2 && \
    echo "Generated requirements-docker.txt successfully" && \
    head -10 requirements-docker.txt

# Upgrade pip and install PDM with hash verification using pip cache
# The --require-hashes mode is automatically enabled when hashes are present
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements-docker.txt

# Copy project files and lock file for dependency resolution
COPY pyproject.toml pdm.lock ./

# Install dependencies only (without the package itself) using PDM cache
RUN --mount=type=cache,target=/root/.cache/pdm \
    pdm install --prod --no-isolation --no-self

# Production stage
FROM base AS production

# Copy the virtual environment from deps stage
COPY --from=deps /app/.venv /app/.venv

# Copy source code and project configuration
COPY src/ src/
COPY pyproject.toml ./

# Fix the python symlinks (PDM creates circular symlinks) and install the package
RUN rm -f /app/.venv/bin/python /app/.venv/bin/python3 /app/.venv/bin/python3.11 && \
    ln -sf /usr/local/bin/python3.11 /app/.venv/bin/python && \
    ln -sf /app/.venv/bin/python /app/.venv/bin/python3 && \
    ln -sf /app/.venv/bin/python /app/.venv/bin/python3.11 && \
    VENV_SITE_PACKAGES=$(/app/.venv/bin/python -c "import site; print(site.getsitepackages()[0])") && \
    cp -r /app/src/http_api_tool "$VENV_SITE_PACKAGES/"

# Note: For GitHub Actions Docker containers that need to write to environment files,
# running as root is necessary due to file permission requirements.
# This is a common pattern in GitHub Actions Docker containers.

# Activate the virtual environment permanently for the container
ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# Set entrypoint to use the installed package from site-packages
ENTRYPOINT ["/app/.venv/bin/python", "-m", "http_api_tool"]
