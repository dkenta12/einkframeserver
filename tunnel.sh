#!/usr/bin/env bash
# Expose the local SMS server to the internet via Cloudflare Tunnel.
#
# Quick tunnel (no Cloudflare account): random *.trycloudflare.com URL each run.
#   ./tunnel.sh
#
# Named tunnel (stable URL): copy cloudflared-config.example.yml, set it up once,
# then run: cloudflared tunnel run camera-screen

set -euo pipefail

PORT="${PORT:-5000}"
ORIGIN="http://localhost:${PORT}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found. Install with: brew install cloudflared"
  exit 1
fi

echo "Starting Cloudflare quick tunnel -> ${ORIGIN}"
echo "Copy the https://....trycloudflare.com URL into Twilio as: <that-url>/sms"
echo ""

# --protocol http2 forces TCP instead of QUIC (UDP) — needed on networks that
# silently drop outbound UDP (common on corporate/VPN networks), which shows up
# as "failed to dial to edge with quic: timeout: no recent network activity".
exec cloudflared tunnel --protocol http2 --url "${ORIGIN}"
