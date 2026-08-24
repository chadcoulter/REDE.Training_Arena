#!/bin/sh
set -eu

TAG="${1:-rede-training-arena-cloudflare:latest}"
WRANGLER_VERSION="${WRANGLER_VERSION:-4.68.0}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker is installed but the engine is not running" >&2
  exit 1
fi

echo "Building and pushing ${TAG} to the Cloudflare managed registry..."
echo "Wrangler will use the currently authenticated Cloudflare account."
npx --yes "wrangler@${WRANGLER_VERSION}" containers build -p -t "$TAG" .

echo "Use the registry.cloudflare.com URI printed above as the image value in 100Monkeys.Arena/deployment/cloudflare/wrangler.jsonc."
