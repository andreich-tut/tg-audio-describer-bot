#!/usr/bin/env bash
set -e

echo "=== Running project checks ==="
echo ""

# Single source of truth: .pre-commit-config.yaml
# All checks are defined there; this script just invokes pre-commit
# Excluding 'bump-version' since that's only for actual commits
./.venv/bin/pre-commit run --all-files --hook-stage manual

echo ""
echo "=== Alembic migrations check ==="
echo ""
# Test migrations: upgrade -> downgrade -> upgrade (idempotency check)
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python -m alembic downgrade base
./.venv/bin/python -m alembic upgrade head

echo ""
echo "=== All checks passed! ==="
