#!/usr/bin/env bash
# Setup script for GitHub Actions self-hosted runner (air-gapped)
# Run this on the runner host ONCE while internet is available.
set -euo pipefail

RUNNER_VERSION="2.317.0"
RUNNER_TOKEN="${GITHUB_RUNNER_TOKEN:?Set GITHUB_RUNNER_TOKEN}"
REPO_URL="${GITHUB_REPO_URL:?Set GITHUB_REPO_URL e.g. https://github.com/org/repo}"
RUNNER_NAME="${RUNNER_NAME:-safecontext-runner-01}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,linux,safecontext}"

echo "Installing GitHub Actions runner $RUNNER_VERSION"

# Download runner package (do this while internet is available)
mkdir -p /opt/actions-runner && cd /opt/actions-runner
curl -o actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz -L \
  "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
tar xzf actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

# Configure runner
./config.sh \
  --url "$REPO_URL" \
  --token "$RUNNER_TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS" \
  --unattended \
  --replace

# Install as service
sudo ./svc.sh install
sudo ./svc.sh start

echo "Runner configured and started: $RUNNER_NAME"
echo "Labels: $RUNNER_LABELS"
echo ""
echo "Pre-install these tools on the runner for air-gapped operation:"
echo "  - Docker (configured to use Harbor: $HARBOR_HOST)"
echo "  - OPA binary at /usr/local/bin/opa"
echo "  - Python 3.12 with packages at /opt/packages/"
echo "  - cosign binary at /usr/local/bin/cosign"
