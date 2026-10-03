---
name: invoice-generator
description: Invoice generator. Use when the user says "create an invoice", "make an invoice for", "generate an invoice", "invoice template", "free invoice generator", "bill my client for", "write an invoice for 10 hours at $80", or "send an invoice to". Turns a plain-language request ("invoice Acme for 12 hours of design at 90 EUR, 25% VAT, due in 14 days") into a professional PDF invoice with correct subtotal, tax per rate, discount, total, due date and payment details. Supports any currency, VAT/GST/MVA, European number format and translated labels.
---

# Invoice Generator

Turn a sentence like "invoice Northwind for 32 hours at 95 EUR plus hosting" into a finished PDF.

## Steps

1. **Collect the facts.** Pull everything you can from the request and the conversation. Only ask for what is truly missing, in **one** short question:
   - required: seller name, client name, at least one line item (description + price)
   - nice to have: addresses, emails, tax ID / VAT number, bank details, currency, tax rate, payment terms
   - **Reuse details:** look for `invoice-profile.json` in the current folder (seller + payment details from last time). If it exists, use it and don't ask again. After the first invoice, offer to save the seller and payment details there.
2. **Invoice number.** Use the number the user gives. Otherwise look for earlier `Invoice-*.pdf` files in the folder and suggest the next one (`2026-014` → `2026-015`); if there are none, use `<year>-001`.
3. **Write the JSON** to a temp file following `example-invoice.json` (in this skill's folder). Field reference:
   - `number`, `issue_date` (YYYY-MM-DD, default today), `due_date` **or** `payment_terms_days` (default 14)
   - `currency` (`"USD"`, `"EUR"`, `"NOK"`, `"$"` ...), `number_format`: `"en"` → 1,234.50 · `"eu"` → 1 234,50
   - `seller` / `client`: `name`, `address` (use `\n` for line breaks), `email`, `phone`, `tax_id`; seller may have `logo` (path to PNG/JPG)
   - `items`: `description`, `quantity`, `unit` (e.g. `"h"`), `unit_price`, `tax_rate` (percent, e.g. 25)
   - `discount` (amount), `payment`: `bank`, `account`, `iban`, `swift`, `reference`, `link`; `notes`
   - `labels` to translate, e.g. Norwegian: `{"invoice":"Faktura","number":"Fakturanr.","issue_date":"Fakturadato","due_date":"Forfallsdato","bill_to":"Til","from":"Fra","description":"Beskrivelse","quantity":"Antall","unit_price":"Pris","tax":"MVA","amount":"Beløp","subtotal":"Sum eks. MVA","total":"Å betale","payment":"Betaling","notes":"Merknad","tax_id":"Org.nr.","reference":"KID"}`
   Write the labels in the user's language when they wrote to you in a language other than English.
4. **Check dependencies** once: `python -c "import reportlab"`; if it fails, `pip install reportlab`.
5. **Render:**
   ```bash
   python scripts/make_invoice.py invoice.json -o "Invoice-2026-015.pdf"
   ```
6. **Verify** the printed totals against a quick mental check (hours × rate, tax %). If anything is off, fix the JSON and re-render.
7. **Report back:** path to the PDF, the total and the due date in one line. Offer: a short email to send with it, saving `invoice-profile.json`, or an `.xlsx` invoice log.

## Rules

- Never guess the tax rate. If the user didn't give one and it isn't in the profile, ask together with the other missing details or leave tax out and say so.
- Amounts are what the user said; don't round prices.
- Delete the temp JSON after rendering unless the user wants to keep it.
- This makes a clean commercial invoice; it does not check local legal requirements (e.g. mandatory fields for VAT invoices in a given country). Mention this once if the user seems to rely on it for compliance.
