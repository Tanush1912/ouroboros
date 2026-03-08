#!/usr/bin/env bash
# Spin up an isolated per-worktree environment.
#
# Usage: scripts/worktree_up.sh <worktree-name> [port-offset]
# Example: scripts/worktree_up.sh feature-health-endpoint
# Example: scripts/worktree_up.sh feature-health-endpoint 200
#
# If port-offset is omitted, it is auto-computed from the worktree name hash.
#
# Creates a git worktree at ../project-ouroboros-<name>
# Starts the sandbox Docker stack with per-worktree observability.

set -euo pipefail

WORKTREE_NAME="${1:?Usage: worktree_up.sh <name> [port-offset]}"

# Auto-compute port offset from name hash if not provided (range 100-999)
if [ -z "${2:-}" ]; then
    HASH=$(echo -n "$WORKTREE_NAME" | sha256sum | cut -c1-4)
    PORT_OFFSET=$(( 16#$HASH % 900 + 100 ))
else
    PORT_OFFSET="$2"
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
WORKTREE_PATH="$(dirname "$REPO_ROOT")/project-ouroboros-${WORKTREE_NAME}"

APP_PORT=$((8000 + PORT_OFFSET))
VECTOR_PORT=$((9001 + PORT_OFFSET))
VICTORIA_LOGS_PORT=$((9428 + PORT_OFFSET))
VICTORIA_METRICS_PORT=$((8428 + PORT_OFFSET))

echo "=== Project Ouroboros: Worktree Up ==="
echo "Name:           $WORKTREE_NAME"
echo "Path:           $WORKTREE_PATH"
echo "Port offset:    $PORT_OFFSET"
echo "App port:       $APP_PORT"
echo "VictoriaLogs:   $VICTORIA_LOGS_PORT"
echo "VictoriaMetrics:$VICTORIA_METRICS_PORT"

# Create worktree (new branch from main)
if [ ! -d "$WORKTREE_PATH" ]; then
    echo "Creating worktree..."
    git worktree add "$WORKTREE_PATH" -b "$WORKTREE_NAME"
else
    echo "Worktree already exists at $WORKTREE_PATH"
fi

# Start Docker stack with per-worktree observability
echo "Starting sandbox + observability stack..."
cd "$WORKTREE_PATH"

COMPOSE_CMD="docker compose -f harness/sandbox/docker-compose.yml"
if [ -f "harness/sandbox/docker-compose.worktree.yml" ]; then
    COMPOSE_CMD="$COMPOSE_CMD -f harness/sandbox/docker-compose.worktree.yml"
fi

WORKTREE_NAME="$WORKTREE_NAME" \
APP_PORT="$APP_PORT" \
VECTOR_PORT="$VECTOR_PORT" \
VICTORIA_LOGS_PORT="$VICTORIA_LOGS_PORT" \
VICTORIA_METRICS_PORT="$VICTORIA_METRICS_PORT" \
    $COMPOSE_CMD up -d

echo ""
echo "=== Worktree ready ==="
echo "App:              http://localhost:${APP_PORT}"
echo "Vector:           http://localhost:${VECTOR_PORT}"
echo "VictoriaLogs:     http://localhost:${VICTORIA_LOGS_PORT}"
echo "VictoriaMetrics:  http://localhost:${VICTORIA_METRICS_PORT}"
echo ""
echo "Environment variables to set:"
echo "  export APP_URL=http://localhost:${APP_PORT}"
echo "  export VICTORIA_LOGS_URL=http://localhost:${VICTORIA_LOGS_PORT}"
echo "  export VICTORIA_METRICS_URL=http://localhost:${VICTORIA_METRICS_PORT}"
echo ""
echo "To tear down: scripts/worktree_down.sh ${WORKTREE_NAME}"
