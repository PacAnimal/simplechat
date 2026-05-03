#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "=== lint ==="
.venv/bin/ruff check backend/ tests/

echo ""
echo "=== frontend build ==="
cd frontend && npm run build
cd ..

echo ""
echo "=== backend tests ==="
.venv/bin/pytest tests/backend/

echo ""
echo "=== e2e tests (stub providers) ==="
rm -f data/e2e_test.db
# clear any server left over from a previous run
{ lsof -ti :8084; lsof -ti :5181; } 2>/dev/null | xargs kill -9 2>/dev/null || true
cd tests/e2e && npx playwright test
cd ../..

echo ""
echo "=== all tests passed ==="
