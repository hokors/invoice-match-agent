# Run inside `odoo shell -d lakan` after setup_company.py (see scripts/reset_sandbox.sh).
# Creates Lakan Distribution's fictional suppliers, products, purchase orders and goods receipts.
# All names are fictional. Deterministic: the same seed gives the same data.
#
# Each product has two names on purpose:
#   - Lakan's own name and SKU (what the PO shows)
#   - the supplier's name and code for it (what supplier invoices usually print)
# so the agent has to match "PBT-CL15-12" / "Cola Litro 1.5L x12" to Lakan's "Cola 1.5L (case of 12)".

import random
from datetime import datetime, timedelta

rng = random.Random(20261115)
company = env.company
assert company.name == "Lakan Distribution Inc.", "run setup_company.py first"
vat12 = company.account_purchase_tax_id

SUPPLIERS = [
    # name, TIN (fictional), city, code prefix
    ("Pampanga Beverage Trading Corp.", "201-334-118-00000", "Angeles City", "PBT"),
    ("Gitnang Luzon Noodle Supply Inc.", "215-907-442-00000", "Tarlac City", "GLN"),
    ("Bulacan Canned Goods Distributors", "228-510-976-00000", "Malolos City", "BCG"),
    ("Malolos Rice & Grains Co.", "233-128-604-00000", "Malolos City", "MRG"),
    ("Tarlac Household Care Supply", "240-662-381-00000", "Tarlac City", "THC"),
    ("Batangas Coffee & Creamer Trading", "252-019-737-00000", "Lipa City", "BCC"),
    ("Pangasinan Snacks Corp.", "266-845-210-00000", "Dagupan City", "PSC"),
    ("Laguna Dairy & Bakery Supply", "271-390-558-00000", "Calamba City", "LDB"),
]

# supplier index, Lakan name, Lakan SKU, supplier's name for it, supplier code suffix, unit price (PHP, VAT-exclusive)
PRODUCTS = [
    (0, "Cola 1.5L (case of 12)", "BEV-001", "Cola Litro 1.5L x12", "CL15-12", 780.00),
    (0, "Orange Soda 1.5L (case of 12)", "BEV-002", "Orange Sparkling 1.5L x12", "OR15-12", 760.00),
    (0, "Bottled Water 500ml (case of 24)", "BEV-003", "Purified Water 500ml x24", "PW500-24", 210.00),
    (0, "Iced Tea Lemon 1L (case of 12)", "BEV-004", "Lemon Iced Tea 1L x12", "LIT1-12", 540.00),
    (1, "Pancit Canton Kalamansi 60g (box of 72)", "NDL-001", "Canton Kalamansi 60g x72", "CK60-72", 1080.00),
    (1, "Pancit Canton Chilimansi 60g (box of 72)", "NDL-002", "Canton Chilimansi 60g x72", "CC60-72", 1080.00),
    (1, "Instant Mami Chicken 55g (box of 72)", "NDL-003", "Chicken Mami Noodles 55g x72", "MC55-72", 864.00),
    (1, "Sotanghon Vermicelli 100g (pack of 50)", "NDL-004", "Sotanghon 100g x50", "ST100-50", 1250.00),
    (2, "Sardines in Tomato Sauce 155g (case of 100)", "CAN-001", "Sardinas Tomato 155g x100", "SR155-100", 2150.00),
    (2, "Corned Beef 150g (case of 48)", "CAN-002", "Corned Beef 150g x48", "CB150-48", 1920.00),
    (2, "Meat Loaf 150g (case of 48)", "CAN-003", "Meatloaf 150g x48", "ML150-48", 1392.00),
    (2, "Tuna Flakes in Oil 180g (case of 48)", "CAN-004", "Tuna Flakes Oil 180g x48", "TF180-48", 1680.00),
    (3, "Well-milled Rice 25kg (sack)", "GRN-001", "WMR Rice 25kg sack", "WMR25", 1225.00),
    (3, "Premium Jasmine Rice 25kg (sack)", "GRN-002", "Jasmine Rice Premium 25kg", "JAS25", 1550.00),
    (3, "Refined Sugar 1kg (bale of 20)", "GRN-003", "Sugar Refined 1kg x20", "SGR1-20", 1500.00),
    (3, "Brown Sugar 1kg (bale of 20)", "GRN-004", "Sugar Brown 1kg x20", "SGB1-20", 1300.00),
    (4, "Powder Detergent 66g (pack of 72)", "HHC-001", "Detergent Powder 66g x72", "DP66-72", 648.00),
    (4, "Fabric Conditioner 22ml (pack of 72)", "HHC-002", "Fab Con 22ml x72", "FC22-72", 432.00),
    (4, "Dishwashing Liquid 250ml (case of 24)", "HHC-003", "Dishwash Liquid 250ml x24", "DW250-24", 912.00),
    (4, "Bath Soap 90g (box of 72)", "HHC-004", "Beauty Soap 90g x72", "BS90-72", 1872.00),
    (5, "3-in-1 Coffee Original 20g (pack of 30)", "COF-001", "Coffee Mix Original 20g x30", "CM20-30", 165.00),
    (5, "Instant Coffee Classic 50g (case of 24)", "COF-002", "Classic Instant Coffee 50g x24", "IC50-24", 1440.00),
    (5, "Powdered Creamer 170g (case of 24)", "COF-003", "Creamer Powder 170g x24", "CR170-24", 1104.00),
    (5, "Chocolate Drink 30g (pack of 30)", "COF-004", "Choco Drink Mix 30g x30", "CD30-30", 240.00),
    (6, "Potato Chips Original 60g (case of 24)", "SNK-001", "Potato Crisps Orig 60g x24", "PC60-24", 696.00),
    (6, "Corn Chips Barbecue 100g (case of 24)", "SNK-002", "Corn Snack BBQ 100g x24", "CS100-24", 840.00),
    (6, "Cheese Crackers 30g (pack of 50)", "SNK-003", "Cheese Crackers 30g x50", "CC30-50", 350.00),
    (6, "Chicharon Spicy 50g (case of 24)", "SNK-004", "Chicharon Hot & Spicy 50g x24", "CH50-24", 600.00),
    (7, "Evaporated Milk 370ml (case of 48)", "DRY-001", "Evap Milk 370ml x48", "EM370-48", 1728.00),
    (7, "Condensed Milk 300ml (case of 48)", "DRY-002", "Sweetened Condensed 300ml x48", "SC300-48", 2304.00),
    (7, "Powdered Milk 33g (pack of 72)", "DRY-003", "Milk Powder Sachet 33g x72", "MP33-72", 1080.00),
    (7, "Loaf Bread 450g (tray of 20)", "DRY-004", "White Loaf 450g x20", "WL450-20", 1100.00),
]

# --- Suppliers ---------------------------------------------------------------
partners = []
for name, tin, city, prefix in SUPPLIERS:
    partners.append(env["res.partner"].create({
        "name": name,
        "is_company": True,
        "vat": tin,
        "city": city,
        "country_id": company.country_id.id,
        "supplier_rank": 1,
        "email": f"billing@{prefix.lower()}.example",
        "ref": prefix,
    }))

# --- Products ----------------------------------------------------------------
products = []
for sup_i, name, sku, sup_name, sup_code, price in PRODUCTS:
    prefix = SUPPLIERS[sup_i][3]
    tmpl = env["product.template"].create({
        "name": name,
        "default_code": sku,
        "type": "consu",
        "is_storable": True,
        "purchase_ok": True,
        "sale_ok": True,
        "purchase_method": "receive",  # bill on received quantities (needed for 3-way matching)
        "standard_price": price,
        "list_price": round(price * 1.18, 2),
        "supplier_taxes_id": [(6, 0, vat12.ids)],
        "seller_ids": [(0, 0, {
            "partner_id": partners[sup_i].id,
            "product_name": sup_name,
            "product_code": f"{prefix}-{sup_code}",
            "price": price,
            "min_qty": 1,
        })],
    })
    products.append((sup_i, tmpl.product_variant_id, price))

# --- Purchase orders + goods receipts ----------------------------------------
# 120 POs over the last ~90 days, so test sets can invoice each PO at most once. Receipt outcome per PO:
#   full (60%), partial with backorder (25%), not yet received (15%)
today = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
outcomes = {"full": 0, "partial": 0, "not_received": 0}

for n in range(120):
    sup_i = rng.randrange(len(SUPPLIERS))
    sup_products = [p for p in products if p[0] == sup_i]
    picked = rng.sample(sup_products, k=rng.randint(2, len(sup_products)))
    order_date = today - timedelta(days=rng.randint(5, 90))

    po = env["purchase.order"].create({
        "partner_id": partners[sup_i].id,
        "date_order": order_date,
        "partner_ref": f"QUOTE-{rng.randint(1000, 9999)}",
        "order_line": [(0, 0, {
            "product_id": prod.id,
            "product_qty": rng.choice([5, 10, 10, 15, 20, 25, 30, 40, 50]),
            "price_unit": price,
            "tax_ids": [(6, 0, vat12.ids)],
        }) for _, prod, price in picked],
    })
    po.button_confirm()

    r = rng.random()
    outcome = "full" if r < 0.60 else "partial" if r < 0.85 else "not_received"
    outcomes[outcome] += 1
    if outcome == "not_received":
        continue

    picking = po.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))[:1]
    for move in picking.move_ids:
        qty = move.product_uom_qty
        if outcome == "partial" and rng.random() < 0.7:
            qty = max(1, int(qty * rng.choice([0.5, 0.6, 0.75, 0.8, 0.9])))
        move.quantity = qty
        move.picked = True
    picking.with_context(cancel_backorder=False)._action_done()
    picking.date_done = order_date + timedelta(days=rng.randint(2, 6))

env.cr.commit()

pos = env["purchase.order"].search([])
print(f"SEED_OK suppliers={len(partners)} products={len(products)} pos={len(pos)} outcomes={outcomes}")
print("SEED_OK backorders_open=%d" % env["stock.picking"].search_count([
    ("picking_type_code", "=", "incoming"), ("state", "not in", ("done", "cancel"))]))
