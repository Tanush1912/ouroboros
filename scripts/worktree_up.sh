#!/usr/bin/env bash
# Spin up an isolated per-worktree environment.
#
# Usage: scripts/worktree_up.sh <worktree-name> [port-offset]
# Example: scripts/worktree_up.sh feature-health-endpoint 100
#
# Creates a git worktree at ../project-ouroboros-<name>
# Starts the sandbox Docker stack with unique port allocation.

set -euo pipefail

WORKTREE_NAME="${1:?Usage: worktree_up.sh <name> [port-offset]}"
PORT_OFFSET="${2:-0}"
REPO_ROOT="$(git rev-parse --show-toplevel)"
WORKTREE_PATH="$(dirname "$REPO_ROOT")/project-ouroboros-${WORKTREE_NAME}"

APP_PORT=$((8000 + PORT_OFFSET))
VECTOR_PORT=$((9001 + PORT_OFFSET))

echo "=== Project Ouroboros: Worktree Up ==="
echo "Name:     $WORKTREE_NAME"
echo "Path:     $WORKTREE_PATH"
echo "App port: $APP_PORT"

# Create worktree (new branch from main)
if [ ! -d "$WORKTREE_PATH" ]; then
    echo "Creating worktree..."
    git worktree add "$WORKTREE_PATH" -b "$WORKTREE_NAME"
else
    echo "Worktree already exists at $WORKTREE_PATH"
fi

# Start Docker stack
echo "Starting sandbox stack..."
cd "$WORKTREE_PATH"
WORKTREE_NAME="$WORKTREE_NAME" \
APP_PORT="$APP_PORT" \
VECTOR_PORT="$VECTOR_PORT" \
    docker compose -f harness/sandbox/docker-compose.yml up -d

echo ""
echo "=== Worktree ready ==="
echo "App:    http://localhost:${APP_PORT}"
echo "Vector: http://localhost:${VECTOR_PORT}"
echo ""
echo "To tear down: scripts/worktree_down.sh ${WORKTREE_NAME}"
