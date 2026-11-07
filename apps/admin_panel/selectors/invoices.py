"""Read-only invoice queries used by apps/admin_panel/views/invoices.py."""

from django.db import connection

VALID_FOLDERS = [
    "no_discount",
    "10_percent",
    "25_percent",
    "50_percent",
    "1re",
    "others",
]


def get_folder_label(folder):
    """Return the display label for an invoice discount folder."""
    labels = {
        "no_discount": "No Discount",
        "10_percent": "10%",
        "25_percent": "25%",
        "50_percent": "50%",
        "1re": "₹1 (Special)",
    }
    return labels.get(folder, "Others")


def fetch_invoice_kpis():
    """Return (total_count, total_revenue, folder_counts) across all invoices."""
    with connection.cursor() as cursor:
        # 1. Total KPIs
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM invoices")
        row = cursor.fetchone()
        total_count = row[0] if row else 0
        total_revenue = row[1] if row else 0

        # 2. Folder Aggregations
        cursor.execute("""
            SELECT discount_folder, COUNT(*), COALESCE(SUM(total_amount), 0)
            FROM invoices
            GROUP BY discount_folder
        """)
        folder_rows = cursor.fetchall()

    # Initialize default counts
    folder_counts = {
        "all": {"total": total_count, "revenue": total_revenue},
        "no_discount": {"total": 0, "revenue": 0},
        "10_percent": {"total": 0, "revenue": 0},
        "25_percent": {"total": 0, "revenue": 0},
        "50_percent": {"total": 0, "revenue": 0},
        "1re": {"total": 0, "revenue": 0},
        "others": {"total": 0, "revenue": 0},
    }

    for f_row in folder_rows:
        f_name, f_count, f_rev = f_row[0], f_row[1], f_row[2]
        if f_name in folder_counts:
            folder_counts[f_name] = {"total": f_count, "revenue": f_rev}
        else:
            folder_counts["others"]["total"] += f_count
            folder_counts["others"]["revenue"] += f_rev

    return total_count, total_revenue, folder_counts


def _invoice_filter_sql(folder, search):
    """Return (where_sql, params) for the invoice list folder/search filters."""
    where_clauses = []
    params = []

    if folder != "all" and folder in VALID_FOLDERS:
        where_clauses.append("discount_folder = %s")
        params.append(folder)

    if search:
        search_term = f"%{search}%"
        where_clauses.append(
            "(invoice_number LIKE %s OR agent_name LIKE %s OR agent_email LIKE %s OR razorpay_payment_id LIKE %s)"
        )
        params.extend([search_term, search_term, search_term, search_term])

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)
    return where_sql, params


def count_filtered_invoices(folder, search):
    """Return the number of invoices matching the folder/search filters."""
    where_sql, params = _invoice_filter_sql(folder, search)
    count_query = f"SELECT COUNT(*) FROM invoices {where_sql}"
    with connection.cursor() as cursor:
        cursor.execute(count_query, params)
        return cursor.fetchone()[0]


def fetch_invoice_page(folder, search, per_page, offset):
    """Return one page of filtered invoice dicts (newest first) with folder_label."""
    where_sql, params = _invoice_filter_sql(folder, search)
    list_query = f"""
            SELECT id, invoice_number, agent_name, agent_email, plan_name,
                   total_amount, discount_percent, promo_code, discount_folder,
                   synced_to_sheet, synced_at, created_at
            FROM invoices
            {where_sql}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
    list_params = params + [per_page, offset]
    with connection.cursor() as cursor:
        cursor.execute(list_query, list_params)

        columns = [col[0] for col in cursor.description]
        invoices = []
        for row in cursor.fetchall():
            inv = dict(zip(columns, row))
            inv["folder_label"] = get_folder_label(inv["discount_folder"])
            invoices.append(inv)
    return invoices


def fetch_invoice_sheet_url():
    """Return the saved Apps Script sync URL, or None."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT value FROM site_settings WHERE `key` = 'invoice_google_sheet_url'"
        )
        row = cursor.fetchone()
    return row[0] if row else None


def fetch_invoice_sheet_view_url():
    """Return the saved spreadsheet view URL, or None."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT value FROM site_settings WHERE `key` = 'invoice_google_sheet_view_url'"
        )
        row_view = cursor.fetchone()
    return row_view[0] if row_view else None


def fetch_unsynced_invoice_count():
    """Return the number of invoices not yet synced to the sheet."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM invoices WHERE synced_to_sheet = 0")
        return cursor.fetchone()[0]


def fetch_invoice_row(invoice_id):
    """Return the full invoices row as a dict, or None if not found."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM invoices WHERE id = %s", [invoice_id])
        if not cursor.description:
            return None
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        if not row:
            return None
        return dict(zip(columns, row))


def fetch_agent_profile_state(agent_id):
    """Return the agent profile's state value, or None."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT state FROM agent_profiles WHERE agent_id = %s LIMIT 1", [agent_id]
        )
        prow = cursor.fetchone()
    return prow[0] if prow else None
