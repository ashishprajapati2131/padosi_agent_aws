"""/account-deletion/status/{ref} needs no login, so it must not hand out personal data (audit API1)."""

import unittest
from datetime import datetime
from unittest.mock import MagicMock

from fastapi_app.routers.account_deletion import get_deletion_status


class DeletionStatusMaskingTests(unittest.TestCase):
    def test_personal_data_is_masked_and_staff_notes_hidden(self):
        del_req = MagicMock(
            reference_id="DEL-20261107-0123456789ABCDEF",
            status="PENDING",
            is_verified=True,
            email="parth.sadhu@example.com",
            mobile="+91 98765 43210",
            identifier="parth.sadhu@example.com",
            admin_notes="called the agent, KYC mismatch",
            rejection_reason=None,
            reason="other",
            created_at=datetime(2026, 11, 7, 10, 0),
            processed_at=None,
            data_retention_summary={"fullname": "Parth Kumar Sadhu"},
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = del_req

        res = get_deletion_status(del_req.reference_id, db)

        self.assertEqual(res.fullname, "Parth K. S.")
        self.assertEqual(res.email, "pa***@example.com")
        self.assertEqual(res.mobile, "******3210")
        self.assertEqual(res.admin_notes, "")
        self.assertEqual(res.status_display, "Pending Review")

    def test_email_identifier_is_not_shown_as_name(self):
        del_req = MagicMock(
            reference_id="DEL-X", status="PENDING", is_verified=False, email=None, mobile=None,
            identifier="someone@example.com", admin_notes=None, rejection_reason=None, reason=None,
            created_at=None, processed_at=None, data_retention_summary={},
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = del_req
        res = get_deletion_status("DEL-X", db)
        self.assertIsNone(res.fullname)
        self.assertIsNone(res.email)
