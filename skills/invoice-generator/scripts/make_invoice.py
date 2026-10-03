#!/usr/bin/env python3
"""Render a professional invoice PDF from a JSON description.

Usage:
    python make_invoice.py invoice.json [-o invoice.pdf]

JSON fields (see ../example-invoice.json):
    number*, issue_date (YYYY-MM-DD, default today), due_date or payment_terms_days,
    currency (default "USD"), number_format ("en" 1,234.50 | "eu" 1 234,50),
    seller* {name*, address, email, phone, tax_id, logo}, client* {name*, address, email, tax_id},
    items* [{description*, quantity (default 1), unit (optional), unit_price*, tax_rate (percent)}],
    discount (amount), payment {bank, account, iban, swift, reference, link}, notes, title,
    labels {..} to translate any label (e.g. {"invoice": "Faktura"}).

Prints a JSON summary (totals, output path). Requires: reportlab (pip install reportlab)
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ImportError:  # pragma: no cover
    sys.exit("Missing dependency: reportlab. Run: pip install reportlab")

LABELS = {
    "invoice": "Invoice", "number": "Invoice no.", "issue_date": "Issue date", "due_date": "Due date",
    "bill_to": "Bill to", "from": "From", "description": "Description", "quantity": "Qty",
    "unit_price": "Unit price", "tax": "Tax", "amount": "Amount", "subtotal": "Subtotal",
    "discount": "Discount", "total": "Total due", "payment": "Payment details", "notes": "Notes",
    "tax_id": "Tax ID", "reference": "Reference",
}
ACCENT = colors.HexColor("#1F3A5F")


def esc(value):
    return escape(str(value)).replace("\n", "<br/>")


def fail(msg):
    sys.exit(f"Invalid invoice data: {msg}")


def money(value, data):
    text = f"{value:,.2f}"
    if data.get("number_format") == "eu":
        text = text.replace(",", " ").replace(".", ",")
    return f"{text} {data['currency']}"


def to_number(value, field):
    try:
        return float(value)
    except (TypeError, ValueError):
        fail(f"{field} must be a number, got {value!r}")


def load(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(str(exc))
    for key in ("number", "seller", "client", "items"):
        if not data.get(key):
            fail(f"'{key}' is required")
    for party in ("seller", "client"):
        if not data[party].get("name"):
            fail(f"'{party}.name' is required")
    data.setdefault("currency", "USD")
    try:
        issue = date.fromisoformat(data.get("issue_date") or date.today().isoformat())
        due = (date.fromisoformat(data["due_date"]) if data.get("due_date")
               else issue + timedelta(days=int(data.get("payment_terms_days", 14))))
    except ValueError as exc:
        fail(f"dates must be YYYY-MM-DD ({exc})")
    data["issue_date"], data["due_date"] = issue.isoformat(), due.isoformat()
    return data


def compute(data):
    lines, subtotal, taxes = [], 0.0, {}
    for i, item in enumerate(data["items"], start=1):
        if not item.get("description"):
            fail(f"item {i} needs a description")
        qty = to_number(item.get("quantity", 1), f"item {i} quantity")
        price = to_number(item.get("unit_price"), f"item {i} unit_price")
        rate = to_number(item.get("tax_rate", 0), f"item {i} tax_rate")
        amount = round(qty * price, 2)
        subtotal += amount
        if rate:
            taxes[rate] = taxes.get(rate, 0.0) + amount * rate / 100
        lines.append({**item, "quantity": qty, "unit_price": price, "tax_rate": rate, "amount": amount})
    discount = to_number(data.get("discount", 0), "discount")
    if discount and subtotal:  # spread discount proportionally over tax bases
        factor = (subtotal - discount) / subtotal
        taxes = {r: v * factor for r, v in taxes.items()}
    taxes = {r: round(v, 2) for r, v in taxes.items()}
    total = round(subtotal - discount + sum(taxes.values()), 2)
    return lines, round(subtotal, 2), discount, taxes, total


def party_block(title, party, styles, labels):
    parts = [f"<font color='#6B7280' size=8>{title.upper()}</font>", f"<b>{esc(party['name'])}</b>"]
    parts += [esc(party[k]) for k in ("address", "email", "phone") if party.get(k)]
    if party.get("tax_id"):
        parts.append(f"{labels['tax_id']}: {esc(party['tax_id'])}")
    return Paragraph("<br/>".join(parts), styles["Normal"])


def fmt_qty(q):
    return f"{q:g}"


def build(data, output):
    labels = {**LABELS, **data.get("labels", {})}
    lines, subtotal, discount, taxes, total = compute(data)
    styles = getSampleStyleSheet()
    styles["Normal"].fontSize, styles["Normal"].leading = 9.5, 13
    right = ParagraphStyle("right", parent=styles["Normal"], alignment=2)
    title_style = ParagraphStyle("title", parent=styles["Title"], alignment=0, textColor=ACCENT, fontSize=24)

    story = []
    logo = data["seller"].get("logo")
    head_left = Paragraph(data.get("title") or labels["invoice"], title_style)
    if logo and Path(logo).is_file():
        head_left = Image(logo, width=40 * mm, height=16 * mm, kind="proportional")
    meta = Paragraph(
        f"<b>{labels['number']}:</b> {data['number']}<br/>"
        f"<b>{labels['issue_date']}:</b> {data['issue_date']}<br/>"
        f"<b>{labels['due_date']}:</b> {data['due_date']}", right)
    story.append(Table([[head_left, meta]], colWidths=[100 * mm, 70 * mm]))
    story.append(Spacer(1, 10 * mm))
    story.append(Table([[party_block(labels["from"], data["seller"], styles, labels),
                         party_block(labels["bill_to"], data["client"], styles, labels)]],
                       colWidths=[85 * mm, 85 * mm], style=[("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(Spacer(1, 10 * mm))

    show_tax = any(l["tax_rate"] for l in lines)
    header = [labels["description"], labels["quantity"], labels["unit_price"]]
    header += [labels["tax"]] if show_tax else []
    header += [labels["amount"]]
    rows = [header]
    for l in lines:
        qty = fmt_qty(l["quantity"]) + (f" {l['unit']}" if l.get("unit") else "")
        row = [Paragraph(esc(l["description"]), styles["Normal"]), qty, money(l["unit_price"], data)]
        row += [f"{l['tax_rate']:g}%"] if show_tax else []
        row += [money(l["amount"], data)]
        rows.append(row)
    widths = [80 * mm, 20 * mm, 30 * mm] + ([12 * mm] if show_tax else []) + [28 * mm]
    if not show_tax:
        widths[0] += 12 * mm
    items = Table(rows, colWidths=widths, repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F5F8")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [items, Spacer(1, 4 * mm)]

    totals = [[labels["subtotal"], money(subtotal, data)]]
    if discount:
        totals.append([labels["discount"], "-" + money(discount, data)])
    for rate, amount in sorted(taxes.items()):
        totals.append([f"{labels['tax']} {rate:g}%", money(amount, data)])
    totals.append([labels["total"], money(total, data)])
    t = Table(totals, colWidths=[40 * mm, 35 * mm], hAlign="RIGHT")
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("LINEABOVE", (0, -1), (-1, -1), 1, ACCENT), ("TEXTCOLOR", (0, -1), (-1, -1), ACCENT),
    ]))
    story += [t, Spacer(1, 10 * mm)]

    pay = data.get("payment") or {}
    pay_lines = [f"{k.upper() if k in ('iban', 'swift') else k.capitalize()}: {esc(v)}"
                 for k, v in pay.items() if v and k not in ("reference", "link")]
    if pay.get("reference"):
        pay_lines.append(f"{labels['reference']}: {esc(pay['reference'])}")
    if pay.get("link"):
        pay_lines.append(f"<link href='{esc(pay['link'])}' color='blue'>{esc(pay['link'])}</link>")
    for heading, body in ((labels["payment"], "<br/>".join(pay_lines)),
                          (labels["notes"], esc(data.get("notes", "")))):
        if body:
            story.append(Paragraph(f"<font color='#6B7280' size=8>{heading.upper()}</font><br/>{body}",
                                   styles["Normal"]))
            story.append(Spacer(1, 5 * mm))

    output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"{labels['invoice']} {data['number']}", author=data["seller"]["name"])
    doc.build(story)
    return {"output": str(output), "number": data["number"], "issue_date": data["issue_date"],
            "due_date": data["due_date"], "subtotal": subtotal, "discount": discount,
            "tax": {f"{r:g}%": v for r, v in taxes.items()}, "total": total, "currency": data["currency"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json_file")
    ap.add_argument("-o", "--output", help="Output PDF (default: Invoice-<number>.pdf)")
    args = ap.parse_args()
    data = load(args.json_file)
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in str(data["number"]))
    output = Path(args.output or f"Invoice-{safe}.pdf")
    print(json.dumps(build(data, output), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
