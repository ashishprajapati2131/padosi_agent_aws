"""Read-only queries for the admin events pages (views/events.py)."""

from django.db import connection

EVENT_LIST_QUERY = """
    SELECT
        e.id,
        e.name,
        e.description,
        e.event_date,
        COUNT(a.id) as total_count,
        SUM(
            CASE
                WHEN a.registration_step = 1
                THEN 1
                ELSE 0
            END
        ) as step1_count,
        SUM(
            CASE
                WHEN a.registration_step = 2
                THEN 1
                ELSE 0
            END
        ) as step2_count,
        SUM(
            CASE
                WHEN a.registration_step = 3
                THEN 1
                ELSE 0
            END
        ) as step3_count
    FROM events e
    LEFT JOIN agents a
        ON e.id = a.event_id
    GROUP BY e.id
    ORDER BY e.event_date DESC
    """

REGISTRANTS_QUERY = """
        SELECT
            a.id,
            a.fullname,
            a.email,
            a.mobile,
            a.agent_pincode AS pincode,
            a.referred_by_code AS promocode,
            a.registration_step AS current_step,
            a.created_at,
            a.status,

            s.selected_plan,
            s.payment_status,
            s.razorpay_order_id,
            s.razorpay_payment_id,

            GROUP_CONCAT(
                DISTINCT iseg.segment_type
            ) AS insurance_segments

        FROM agents a

        LEFT JOIN agent_subscriptions s
            ON a.id = s.agent_id
            AND s.id = (
                SELECT MAX(id)
                FROM agent_subscriptions
                WHERE agent_id = a.id
            )

        LEFT JOIN agent_insurance_segments iseg
            ON a.id = iseg.agent_id

        WHERE a.event_id = %s

        GROUP BY
            a.id,
            s.selected_plan,
            s.payment_status,
            s.razorpay_order_id,
            s.razorpay_payment_id

        ORDER BY a.created_at DESC
        """


def fetch_event_list():
    """Return all events with registrant counts per registration step, newest first."""
    events = []
    with connection.cursor() as cursor:
        cursor.execute(EVENT_LIST_QUERY)
        columns = [col[0] for col in cursor.description]
        for row in cursor.fetchall():
            events.append(dict(zip(columns, row)))
    return events


def fetch_event(event_id):
    """Return the event row as a dict, or None if it does not exist."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM events WHERE id = %s LIMIT 1", [event_id])
        event_row = cursor.fetchone()
        if not event_row:
            return None
        event_columns = [col[0] for col in cursor.description]
        return dict(zip(event_columns, event_row))


def fetch_event_registrants(event_id):
    """Return the event's registrants (raw rows as dicts), newest first."""
    with connection.cursor() as cursor:
        cursor.execute(REGISTRANTS_QUERY, [event_id])
        reg_columns = [col[0] for col in cursor.description]
        return [dict(zip(reg_columns, row)) for row in cursor.fetchall()]
