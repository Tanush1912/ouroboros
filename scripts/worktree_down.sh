#!/usr/bin/env bash
# Tear down an isolated per-worktree environment.
#
# Usage: scripts/worktree_down.sh <worktree-name>
# Example: scripts/worktree_down.sh feature-health-endpoint
#
# Stops Docker stack, removes volumes, removes git worktree.

set -euo pipefail

WORKTREE_NAME="${1:?Usage: worktree_down.sh <name>}"
REPO_ROOT="$(git rev-parse --show-toplevel)"
WORKTREE_PATH="$(dirname "$REPO_ROOT")/project-ouroboros-${WORKTREE_NAME}"

echo "=== Project Ouroboros: Worktree Down ==="
echo "Name: $WORKTREE_NAME"
echo "Path: $WORKTREE_PATH"

if [ -d "$WORKTREE_PATH" ]; then
    echo "Stopping Docker stack..."
    cd "$WORKTREE_PATH"
    WORKTREE_NAME="$WORKTREE_NAME" \
        docker compose -f harness/sandbox/docker-compose.yml down -v 2>/dev/null || true

    echo "Removing worktree..."
    cd "$REPO_ROOT"
    git worktree remove "$WORKTREE_PATH" --force

    echo "Removing branch..."
    git branch -D "$WORKTREE_NAME" 2>/dev/null || echo "Branch not found (may have been merged)"
else
    echo "Worktree not found at $WORKTREE_PATH"
fi

echo ""
echo "=== Worktree removed ==="
