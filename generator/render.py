"""Draws an invoice in one of three supplier layouts, as a PDF or as an image.

Layouts are written once against a tiny canvas interface (points, origin top-left, A4),
with two backends: reportlab for PDFs and Pillow for images (later degraded into scans/photos).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from .scenarios import Invoice

PAGE_W, PAGE_H = A4  # 595 x 842 points
FONT_DIR = Path("C:/Windows/Fonts")
REGULAR, BOLD = FONT_DIR / "arial.ttf", FONT_DIR / "arialbd.ttf"

BUYER = [
    "Lakan Distribution Inc.",
    "123 MacArthur Highway, San Fernando, Pampanga 2000",
    "TIN: 000-123-456-00000",
]


# --- backends ---------------------------------------------------------------
class PdfCanvas:
    def __init__(self, path: Path):
        self.c = rl_canvas.Canvas(str(path), pagesize=A4)
        self.regular, self.bold = "Helvetica", "Helvetica-Bold"
        if REGULAR.exists() and BOLD.exists():
            if "Arial" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("Arial", str(REGULAR)))
                pdfmetrics.registerFont(TTFont("Arial-Bold", str(BOLD)))
            self.regular, self.bold = "Arial", "Arial-Bold"

    def text(self, x, y, s, size=9, bold=False, align="left", gray=0.0):
        self.c.setFont(self.bold if bold else self.regular, size)
        self.c.setFillGray(gray)
        y = PAGE_H - y
        {"left": self.c.drawString, "right": self.c.drawRightString, "center": self.c.drawCentredString}[align](x, y, str(s))

    def line(self, x1, y1, x2, y2, width=0.6, gray=0.0):
        self.c.setLineWidth(width)
        self.c.setStrokeGray(gray)
        self.c.line(x1, PAGE_H - y1, x2, PAGE_H - y2)

    def rect(self, x, y, w, h, fill=None, width=0.6):
        self.c.setLineWidth(width)
        if fill is not None:
            self.c.setFillGray(fill)
        self.c.rect(x, PAGE_H - y - h, w, h, stroke=1, fill=1 if fill is not None else 0)
        self.c.setFillGray(0)

    def save(self):
        self.c.showPage()
        self.c.save()


class ImageCanvas:
    def __init__(self, scale: float = 2.2):
        self.s = scale
        self.img = Image.new("RGB", (int(PAGE_W * scale), int(PAGE_H * scale)), "white")
        self.d = ImageDraw.Draw(self.img)
        self._fonts: dict = {}

    def _font(self, size, bold):
        key = (size, bold)
        if key not in self._fonts:
            path = BOLD if bold else REGULAR
            self._fonts[key] = ImageFont.truetype(str(path), int(size * self.s)) if path.exists() else ImageFont.load_default()
        return self._fonts[key]

    def text(self, x, y, s, size=9, bold=False, align="left", gray=0.0):
        anchor = {"left": "ls", "right": "rs", "center": "ms"}[align]
        g = int(255 * gray)
        self.d.text((x * self.s, y * self.s), str(s), fill=(g, g, g), font=self._font(size, bold), anchor=anchor)

    def line(self, x1, y1, x2, y2, width=0.6, gray=0.0):
        g = int(255 * gray)
        self.d.line([(x1 * self.s, y1 * self.s), (x2 * self.s, y2 * self.s)], fill=(g, g, g), width=max(1, int(width * self.s)))

    def rect(self, x, y, w, h, fill=None, width=0.6):
        f = None if fill is None else (int(255 * fill),) * 3
        self.d.rectangle([x * self.s, y * self.s, (x + w) * self.s, (y + h) * self.s], fill=f, outline=(0, 0, 0),
                         width=max(1, int(width * self.s)))


# --- formatting ---------------------------------------------------------------
def amt(x: float) -> str:
    return f"{x:,.2f}"


def qty(x: float) -> str:
    return f"{x:g}"


def fmt_date(iso: str, style: str) -> str:
    d = date.fromisoformat(iso)
    if style == "us":
        return d.strftime("%m/%d/%Y")
    if style == "long":
        return d.strftime("%B %d, %Y").replace(" 0", " ")
    return d.strftime("%d-%b-%Y")


def clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


# --- layouts -------------------------------------------------------------------
def layout_classic(cv, inv: Invoice):
    """Code column, P.O. No. label, PH-style VAT summary."""
    cv.text(40, 60, inv.supplier_name.upper(), 15, bold=True)
    cv.text(40, 76, f"{inv.supplier_city}, Philippines", 9)
    cv.text(40, 89, f"VAT Reg. TIN: {inv.supplier_tin}", 9)
    cv.text(555, 60, "SALES INVOICE", 16, bold=True, align="right")
    cv.text(555, 80, f"No. {inv.invoice_number}", 10, align="right")
    cv.text(555, 94, f"Date: {fmt_date(inv.invoice_date, 'us')}", 10, align="right")
    cv.line(40, 108, 555, 108, 1.2)

    cv.text(40, 128, "SOLD TO:", 9, bold=True)
    for i, s in enumerate(BUYER):
        cv.text(95, 128 + i * 13, s, 9)
    cv.text(400, 128, "P.O. No.:", 9, bold=True)
    cv.text(450, 128, inv.po_ref_printed or "", 9)
    cv.text(400, 141, "Terms:", 9, bold=True)
    cv.text(450, 141, "30 days", 9)

    cols = [(40, "Item Code"), (115, "Description"), (350, "Qty"), (390, "Unit"), (480, "Unit Price"), (549, "Amount")]
    y = 185
    cv.rect(40, y - 13, 515, 18, fill=0.88)
    for x, h in cols:
        cv.text(x + (4 if x in (40, 115, 390) else 0), y, h, 9, bold=True, align="left" if x in (40, 115, 390) else "right")
    y += 20
    for l in inv.lines:
        cv.text(44, y, l.code or "", 8)
        cv.text(119, y, clip(l.description, 38), 9)
        cv.text(350, y, qty(l.qty), 9, align="right")
        cv.text(394, y, l.unit, 9)
        cv.text(480, y, amt(l.unit_price), 9, align="right")
        cv.text(549, y, amt(l.line_total), 9, align="right")
        y += 16
    cv.line(40, y, 555, y)
    y += 20
    for label, value, bold in [("VATable Sales", inv.subtotal, False), ("VAT (12%)", inv.vat, False), ("TOTAL AMOUNT DUE", inv.total, True)]:
        cv.text(470, y, label, 10 if bold else 9, bold=bold, align="right")
        cv.text(549, y, amt(value), 10 if bold else 9, bold=bold, align="right")
        y += 15
    cv.text(40, 780, "Received the above goods in good order and condition.", 8, gray=0.3)
    cv.line(40, 815, 200, 815)
    cv.text(40, 826, "Customer signature over printed name", 7, gray=0.3)


def layout_compact(cv, inv: Invoice):
    """No item codes, 'Your Ref' label, centered header, long dates."""
    cv.text(297, 55, inv.supplier_name, 16, bold=True, align="center")
    cv.text(297, 71, f"{inv.supplier_city}, Philippines  |  TIN {inv.supplier_tin}", 9, align="center")
    cv.line(60, 84, 535, 84)
    cv.text(297, 108, "INVOICE", 14, bold=True, align="center")

    cv.text(60, 135, f"Invoice # {inv.invoice_number}", 10, bold=True)
    cv.text(60, 150, f"Date: {fmt_date(inv.invoice_date, 'long')}", 10)
    if inv.po_ref_printed:
        cv.text(60, 165, f"Your Ref: {inv.po_ref_printed}", 10)
    cv.text(330, 135, "Bill to:", 10, bold=True)
    for i, s in enumerate(BUYER):
        cv.text(330, 150 + i * 13, s, 9)

    y = 215
    cv.line(60, y - 14, 535, y - 14, 1.0)
    for x, h, a in [(60, "Qty", "left"), (95, "Unit", "left"), (140, "Description", "left"), (455, "Price", "right"), (535, "Total", "right")]:
        cv.text(x, y, h, 10, bold=True, align=a)
    cv.line(60, y + 6, 535, y + 6, 1.0)
    y += 24
    for l in inv.lines:
        cv.text(60, y, qty(l.qty), 10)
        cv.text(95, y, l.unit, 10)
        cv.text(140, y, clip(l.description, 42), 10)
        cv.text(455, y, amt(l.unit_price), 10, align="right")
        cv.text(535, y, amt(l.line_total), 10, align="right")
        y += 18
    cv.line(330, y, 535, y)
    y += 18
    cv.text(455, y, "Subtotal", 10, align="right"); cv.text(535, y, amt(inv.subtotal), 10, align="right"); y += 16
    cv.text(455, y, "Add: 12% VAT", 10, align="right"); cv.text(535, y, amt(inv.vat), 10, align="right"); y += 18
    cv.text(455, y, "TOTAL", 12, bold=True, align="right"); cv.text(535, y, amt(inv.total), 12, bold=True, align="right")
    cv.text(297, 800, "Thank you for your business! Please pay within 30 days.", 9, align="center", gray=0.35)


def layout_statement(cv, inv: Invoice):
    """Boxed info panel, codes inside the description, numbered rows, dd-Mon-yyyy dates."""
    cv.rect(40, 40, 515, 70)
    cv.text(52, 62, inv.supplier_name, 14, bold=True)
    cv.text(52, 78, f"{inv.supplier_city}, Philippines", 9)
    cv.text(52, 92, f"VAT REG TIN {inv.supplier_tin}", 9)
    cv.text(543, 62, "CHARGE INVOICE", 13, bold=True, align="right")
    cv.text(543, 80, inv.invoice_number, 10, align="right")

    cv.rect(40, 122, 255, 66)
    cv.text(50, 138, "CUSTOMER", 8, bold=True, gray=0.3)
    for i, s in enumerate(BUYER):
        cv.text(50, 152 + i * 12, s, 8.5)
    cv.rect(300, 122, 255, 66)
    for i, (k, v) in enumerate([("Invoice Date", fmt_date(inv.invoice_date, "dmy")), ("Customer PO#", inv.po_ref_printed or "-"), ("Payment Terms", "Net 30")]):
        cv.text(310, 140 + i * 17, k, 9, bold=True)
        cv.text(420, 140 + i * 17, v, 9)

    y = 215
    cv.rect(40, y - 14, 515, 20, fill=0.15)
    for x, h, a in [(48, "#", "left"), (70, "Particulars", "left"), (380, "Quantity", "right"), (465, "Rate", "right"), (547, "Amount", "right")]:
        cv.text(x, y, h, 9, bold=True, align=a, gray=1.0)
    y += 22
    for i, l in enumerate(inv.lines, 1):
        desc = f"({l.code}) {l.description}" if l.code else l.description
        cv.text(48, y, str(i), 9)
        cv.text(70, y, clip(desc, 50), 9)
        cv.text(380, y, f"{qty(l.qty)} {l.unit}", 9, align="right")
        cv.text(465, y, amt(l.unit_price), 9, align="right")
        cv.text(547, y, amt(l.line_total), 9, align="right")
        cv.line(40, y + 6, 555, y + 6, 0.3, gray=0.6)
        y += 19
    y += 14
    cv.rect(350, y - 14, 205, 62)
    for label, value, bold in [("Net of VAT", inv.subtotal, False), ("VAT 12%", inv.vat, False), ("GRAND TOTAL (PHP)", inv.total, True)]:
        cv.text(362, y, label, 9.5, bold=bold)
        cv.text(547, y, amt(value), 9.5, bold=bold, align="right")
        y += 18


LAYOUTS = {"classic": layout_classic, "compact": layout_compact, "statement": layout_statement}


def render_pdf(inv: Invoice, layout: str, path: Path):
    cv = PdfCanvas(path)
    LAYOUTS[layout](cv, inv)
    cv.save()


def render_image(inv: Invoice, layout: str) -> Image.Image:
    cv = ImageCanvas()
    LAYOUTS[layout](cv, inv)
    return cv.img
