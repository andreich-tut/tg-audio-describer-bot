#!/usr/bin/env bash
set -e

echo "=== Running project checks ==="
echo ""

# Single source of truth: .pre-commit-config.yaml
# All checks are defined there; this script just invokes pre-commit
# Excluding 'bump-version' since that's only for actual commits
pre-commit run --all-files --hook-stage manual

echo ""
echo "=== All checks passed! ==="
