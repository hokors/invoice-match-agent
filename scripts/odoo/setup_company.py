# Run inside `odoo shell -d lakan` (see scripts/reset_sandbox.sh).
# Turns the fresh database into the fictional Lakan Distribution Inc.:
# Philippine chart of accounts, PHP currency, 12% VAT, and bills based on received quantities.
# Prints a new admin password and an API key for the agent (the reset script saves them to .env).

import secrets

company = env.company
ph = env.ref("base.ph")

company.write({
    "name": "Lakan Distribution Inc.",
    "country_id": ph.id,
    "street": "123 MacArthur Highway",
    "city": "San Fernando",
    "zip": "2000",
    "vat": "000-123-456-00000",  # fictional TIN
    "email": "ap@lakan.example",
    "phone": "+63 45 000 0000",
})

# Philippine chart of accounts + taxes; also sets the company currency to PHP.
env["account.chart.template"].try_loading("ph", company=company, install_demo=False)

php = env.ref("base.PHP")
php.active = True
assert company.currency_id == php, f"company currency is {company.currency_id.name}, expected PHP"

# Default 12% VAT on purchases, so PO lines get it automatically.
vat12 = env["account.tax"].search([
    ("company_id", "=", company.id),
    ("type_tax_use", "=", "purchase"),
    ("amount", "=", 12),
    ("amount_type", "=", "percent"),
], limit=1)
assert vat12, "no 12% purchase tax found in the PH chart"
company.account_purchase_tax_id = vat12

# Fresh admin password + API key for the agent.
admin = env.ref("base.user_admin")
admin.write({"name": "Lakan AP Admin", "tz": "Asia/Manila"})
password = secrets.token_urlsafe(16)
admin.password = password
api_key = env["res.users.apikeys"].with_user(admin)._generate("rpc", "invoice-match-agent", None)

env.cr.commit()
print(f"SETUP_OK company={company.name} currency={company.currency_id.name} purchase_vat={vat12.name}")
print("SETUP_ADMIN_PW=" + password)
print("SETUP_API_KEY=" + api_key)
