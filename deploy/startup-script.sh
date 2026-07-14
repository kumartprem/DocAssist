#!/bin/bash
###############################################################################
# DocAssist — Compute Engine startup script
#
# Runs automatically as root when the VM boots (passed via the
# `startup-script` metadata key). It is idempotent and safe to re-run:
#   • installs Python + git
#   • clones (or updates) the app from GitHub
#   • creates a virtualenv and installs dependencies
#   • installs & starts a systemd service that serves the app on port 80
#
# Logs: view with `sudo journalctl -u google-startup-scripts.service` and
#       `sudo journalctl -u docassist.service` on the VM.
###############################################################################
set -euo pipefail

REPO_URL="https://github.com/Bisht9887/DocAssist.git"
APP_DIR="/opt/docassist"
BRANCH="main"

echo ">>> [DocAssist] Installing system packages…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git

echo ">>> [DocAssist] Fetching application source…"
if [ -d "${APP_DIR}/.git" ]; then
  git -C "${APP_DIR}" fetch --all --quiet
  git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
else
  git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

echo ">>> [DocAssist] Setting up virtual environment…"
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo ">>> [DocAssist] Writing systemd service…"
cat >/etc/systemd/system/docassist.service <<'UNIT'
[Unit]
Description=DocAssist FastAPI application
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/docassist
ExecStart=/opt/docassist/venv/bin/uvicorn main:app --host 0.0.0.0 --port 80
Restart=always
RestartSec=3
# Runs as root so it can bind to the privileged port 80 (fine for a demo VM).

[Install]
WantedBy=multi-user.target
UNIT

echo ">>> [DocAssist] Starting service…"
systemctl daemon-reload
systemctl enable docassist.service
systemctl restart docassist.service

echo ">>> [DocAssist] Done. App is serving on port 80."
