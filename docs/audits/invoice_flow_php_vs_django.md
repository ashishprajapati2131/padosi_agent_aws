# Invoice Flow Audit — PHP (Laravel) vs Django

**Date:** 2026-08-09
**Scope:** Manual invoice creation (`/admin/invoices/create`), invoice number generation,
invoice PDF/preview templates, and the invoice list page.
**Reference:** PHP code in `app/Http/Controllers/Admin/AdminInvoiceController.php`,
`app/Services/InvoiceService.php`, `resources/views/admin/invoices/*.blade.php`,
`resources/views/invoices/*.blade.php`. Django code under `src/apps/admin_panel/`
and `src/apps/agents/`.

---

## 1. Create page (`admin/invoices/create`)

| # | Aspect | PHP | Django (before fix) | Status |
|---|--------|-----|---------------------|--------|
| 1 | Custom invoice number input (optional) | Yes — placeholder `PA/26-27/00099`, auto-generate if empty | Missing | ✅ Fixed |
| 2 | Duplicate invoice number check | Yes — error + input preserved | Missing — DB unique constraint caused `IntegrityError` (500) | ✅ Fixed |
| 3 | Auto invoice number format | `PA/YY-YY/XXXXX` (financial-year based) | `INV-M-YYYYMMDD-XXXXX` (random) | ✅ Fixed |
| 4 | Razorpay Payment ID field | Yes — saved to `razorpay_payment_id` | Missing | ✅ Fixed |
| 5 | Email on submit | None | Forced Brevo email send | ✅ Kept as **optional** (`send_email` checkbox) |
| 6 | Success/error handling | PRG redirect + session flash | Re-render (double-submit risk) | ✅ Fixed (messages framework) |
| 7 | Repopulate inputs on error (`old()`) | Yes (`old('name')` …) | No | ✅ Fixed (session `invoice_old`) |
| 8 | Dismissible flash alerts | Yes (`alert-dismissible`) | Plain `{% if error %}` | ✅ Fixed (global messages block in base.html) |
| 9 | Dummy agent lookup | `withTrashed()->firstOrCreate` | `get_or_create` | Minor — kept `get_or_create` (Django has no soft-delete agent) |
| 10 | Amount validation | `is_numeric` → error + input | `float()` try/except | ✅ Fixed (now PRG + input preserved) |
| 11 | Promo verify AJAX | JSON endpoint | JSON endpoint | Same (already matched) |

## 2. Invoice number generation

PHP has **one** generator (`InvoiceService::generateInvoiceNumber()`):
- Prefix `PA/{yy}-{yy}/` — financial year resets on **April 1**
  (`start_year = now.year if now.month >= 4 else now.year - 1`)
- Next number = `MAX(CAST(SUBSTRING(invoice_number, len(prefix)+1) AS UNSIGNED)) + 1`
  across rows with the current prefix; falls back to **42** when no `PA/…` row exists
- 5-digit zero-padded sequence, collision-safety loop

Django had **three divergent implementations**, all using the wrong format:
- `apps/admin_panel/views/invoices.py` → `INV-M-YYYYMMDD-XXXXX` (random)
- `apps/admin_panel/services/pdf_generator.py` → `INV-YYYY-XXXXX` (calendar-year count)
- `apps/agents/services/invoice.py` → `INV-YYYY-XXXXX` (calendar-year count)

**Fix:** one shared `generate_invoice_number()` in `apps/agents/services/invoice.py`
replicating the PHP logic exactly; the other two implementations now delegate to it.
Applies to both the manual flow and the payment flow (PHP uses the same generator for both).

## 3. Invoice PDF template (`pdf.html` vs `invoice_pdf.blade.php`)

| # | Difference | Status |
|---|------------|--------|
| 1 | SAC Code column (9983) — PHP has 5 columns (`#`, Service Details, SAC, Base Price, Amount); Django had 4 | ✅ Fixed |
| 2 | Footer contact line "If you have any questions concerning this invoice…" | ✅ Fixed |
| 3 | "✨ Promo Applied" vs "• Promo Applied" | ✅ Fixed |
| 4 | Rupee symbol: PHP uses safe `&#8377;` DejaVu span (`{!! $rs !!}`); Django used literal `₹` (may render as box in xhtml2pdf) | ✅ Fixed |
| 5 | Item description: PHP `plan_type` else-branch = "1 Year Professional" (manual invoices); Django left bare "PadosiAgent Subscription" | ✅ Fixed |
| 6 | Footnote "*Inclusive of IGST ₹X" vs "*Inclusive of CGST ₹X + SGST ₹Y" (PHP distinguishes; Django used one generic line) | ✅ Fixed |
| 7 | PAID stamp (rotated bordered badge) vs page watermark | ✅ Fixed — stamp markup matches PHP |
| 8 | Status badge hardcoded PAID in PHP PDF | ✅ Fixed |
| 9 | Column widths `5/42/15/18/20%` | ✅ Fixed |

## 4. Preview template (`preview.html` vs `invoice_preview.blade.php`)

| # | Difference | Status |
|---|------------|--------|
| 1 | **Bug:** `logo_src` never passed by `preview_invoice` view → logo never rendered (fallback text always shown) | ✅ Fixed — view now embeds base64 logo like PHP |
| 2 | SAC Code column (9983) missing | ✅ Fixed |
| 3 | Footer contact line missing | ✅ Fixed |
| 4 | GST footnote variants (IGST vs CGST+SGST) | ✅ Fixed |
| 5 | Bill-to state fallback to agent profile state | ✅ Fixed |
| 6 | Status badge logic (`paid`/`completed`/has payment id → PAID) | Already matched |

## 5. Invoice list page (`admin/invoices/index`)

| # | Difference | Status |
|---|------------|--------|
| 1 | **Bug:** template used `unsynced_invoice_count` but the view never provided it → "🔄 Sync N to Sheet" button permanently hidden | ✅ Fixed |
| 2 | `syncSheet` shows count + spinner message | ✅ Fixed (`sync_sheet` now flashes result) |
| 3 | `saveSheetUrl` success flash | ✅ Fixed |
| 4 | Folder counts, search, sheet URL card | Already matched |

## 6. Out of scope / notes

- No database schema changes required (all fixes are code/template-level; `invoices` table already has `razorpay_payment_id` etc.).
- Dummy agent lookup uses `get_or_create`; PHP uses `firstOrCreate(withTrashed)`. Equivalent in practice because Django's `Agent` has no soft-delete.
- The hardcoded `42` fallback in the PHP sequence was replicated deliberately for byte-for-byte parity.

## 7. Storage crash found during verification (2026-08-09, second pass)

| # | Issue | Fix | Status |
|---|-------|-----|--------|
| 1 | **Crash (500):** `FileNotFoundError` writing PDFs. `PA/26-27/00998.pdf` contains `/`, so the file path nests below the discount folder (`no_discount/PA/26-27/`). PHP's `Storage::put` auto-creates directories; Django's `open()` does not. Affected both the admin flow (`generate_invoice_pdf`) and the payment flow (`InvoiceService.generate_pdf`). | `os.makedirs(os.path.dirname(path), exist_ok=True)` before `open()` in both generators. | ✅ Fixed |
| 2 | `get_pdf_absolute_path` assumed a flat `folder/filename` layout (`parts[-2]` = folder), which fails for nested `invoices/no_discount/PA/26-27/XXXXX.pdf` (would resolve to folder `26-27`). Broke download & sheet sync for the new numbering. | Resolve the whole relative path from the invoice root (`get_invoice_root() / path` after stripping the `invoices/` prefix). | ✅ Fixed |
| 3 | Download `Content-Disposition` filename lost the `PA/26-27` prefix (Django sanitizes slashes out of `filename="PA/26-27/00997.pdf"` → `00997.pdf`); PHP sends the full number. | Replace `/` with `-` → `PA-26-27-00997.pdf`. | ✅ Fixed |

Verification: manual POST through the running server succeeded for custom number, duplicate number
(error + preserved inputs), auto number (`PA/26-27/01001`), no-email path (PDF only), preview
(logo + SAC 9983) and download (application/pdf).
