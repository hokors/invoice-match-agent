#!/usr/bin/env bash
# Rebuilds the Odoo sandbox from scratch as Lakan Distribution Inc.
# DELETES the "lakan" database, then recreates it with PH accounting and seed data.
# Writes a new admin password and API key into .env.
#
#   bash scripts/reset_sandbox.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "Create .env from .env.example first"; exit 1; }

echo "== stopping Odoo and dropping database 'lakan'"
docker compose up -d db
docker compose stop odoo
docker compose exec -T db dropdb -U odoo --if-exists lakan

echo "== creating database with Purchase, Inventory, Invoicing and PH accounting (no demo data)"
docker compose run --rm -T odoo odoo -d lakan -i purchase,stock,account,l10n_ph --stop-after-init \
  2>&1 | grep -E "ERROR|CRITICAL|Modules loaded" || true

echo "== company setup"
out=$(docker compose run --rm -T odoo odoo shell -d lakan --no-http < scripts/odoo/setup_company.py 2>&1) || true
echo "$out" | grep -E "SETUP_OK|Error|Traceback" | grep -v "SETUP_ADMIN_PW\|SETUP_API_KEY" || true
pw=$(echo "$out" | grep -o 'SETUP_ADMIN_PW=[^ ]*' | cut -d= -f2-)
key=$(echo "$out" | grep -o 'SETUP_API_KEY=[^ ]*' | cut -d= -f2-)
[ -n "$pw" ] && [ -n "$key" ] || { echo "company setup failed"; echo "$out" | tail -20; exit 1; }

sed -i "s|^ODOO_API_KEY=.*|ODOO_API_KEY=$key|" .env
if grep -q '^ODOO_ADMIN_PASSWORD=' .env; then
  sed -i "s|^ODOO_ADMIN_PASSWORD=.*|ODOO_ADMIN_PASSWORD=$pw|" .env
else
  printf '\n# Odoo web login (local sandbox only)\nODOO_ADMIN_LOGIN=admin\nODOO_ADMIN_PASSWORD=%s\n' "$pw" >> .env
fi
echo "   saved new admin password and API key to .env"

echo "== seeding suppliers, products, purchase orders and receipts"
out=$(docker compose run --rm -T odoo odoo shell -d lakan --no-http < scripts/odoo/seed_lakan.py 2>&1) || true
echo "$out" | grep -E "SEED_OK" || { echo "seeding failed"; echo "$out" | grep -E -A3 "Error|Traceback" | tail -30; exit 1; }

echo "== starting Odoo"
docker compose up -d odoo
echo "Done: http://localhost:8069 (database lakan)"
