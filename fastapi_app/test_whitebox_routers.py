"""
White-box test suite for FastAPI routers and core services:
1. AppVersionService & semver comparison logic (_version_tuple, _compare, check)
2. PincodeService validation, error handling, mock upstream HTTP responses
3. Leads router IDOR protection, status validation, and access gating
"""

import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
import httpx

from fastapi_app.services.app_version_service import (
    AppVersionService,
    _version_tuple,
    _compare,
)
from fastapi_app.schemas.app_version import AppVersionResponse
from fastapi_app.services.pincode_service import PincodeService
from fastapi_app.routers.leads import get_lead_detail, update_status
from fastapi_app.schemas.leads import LeadStatusUpdate


class AppVersionServiceWhiteBoxTests(unittest.TestCase):
    """White-box tests for semver parsing, comparison, and app update checks."""

    def test_version_tuple_parsing(self):
        # Empty and None evaluate to (0,) because "".split(".") -> [""] -> [0]
        self.assertEqual(_version_tuple(None), (0,))
        self.assertEqual(_version_tuple(""), (0,))
        self.assertEqual(_version_tuple("   "), (0,))

        # Standard numbers
        self.assertEqual(_version_tuple("1.2.3"), (1, 2, 3))
        self.assertEqual(_version_tuple("2.0"), (2, 0))

        # Malformed parts fallback to 0
        self.assertEqual(_version_tuple("1.beta.3"), (1, 0, 3))
        self.assertEqual(_version_tuple("v1.2"), (0, 2))

    def test_version_compare_branches(self):
        # Equal versions
        self.assertEqual(_compare("1.0.0", "1.0.0"), 0)
        self.assertEqual(_compare("1.0", "1.0.0"), 0)
        self.assertEqual(_compare(None, None), 0)

        # a < b
        self.assertEqual(_compare("1.0.0", "1.0.1"), -1)
        self.assertEqual(_compare("1.9.9", "2.0.0"), -1)
        self.assertEqual(_compare("1.2", "1.2.1"), -1)

        # a > b
        self.assertEqual(_compare("1.0.1", "1.0.0"), 1)
        self.assertEqual(_compare("2.0.0", "1.9.9"), 1)
        self.assertEqual(_compare("1.3.0", "1.2.9"), 1)

    def test_check_platform_fallback_and_no_active_config(self):
        db = MagicMock()
        # Invalid platform should fallback to "android"
        with patch("fastapi_app.services.app_version_service.AppVersionRepository") as MockRepo:
            repo_instance = MagicMock()
            repo_instance.get_active_by_platform.return_value = None
            MockRepo.return_value = repo_instance

            resp = AppVersionService.check(db, platform="unsupported_os", current_version="1.0.0")

            self.assertEqual(resp.platform, "android")
            self.assertFalse(resp.update_available)
            self.assertFalse(resp.update_required)
            self.assertFalse(resp.force_update)
            self.assertEqual(resp.latest_version, "1.0.0")

    def test_check_update_available_and_force_update(self):
        db = MagicMock()
        mock_row = MagicMock(
            latest_version="2.0.0",
            min_supported_version="1.5.0",
            force_update=True,
            update_message="Critical security patch",
            store_url="https://play.google.com/store/apps/details?id=com.padosiagent",
        )

        with patch("fastapi_app.services.app_version_service.AppVersionRepository") as MockRepo:
            repo_instance = MagicMock()
            repo_instance.get_active_by_platform.return_value = mock_row
            MockRepo.return_value = repo_instance

            # Case A: Current version is below min_supported -> force update required
            resp_force = AppVersionService.check(db, platform="android", current_version="1.2.0")
            self.assertTrue(resp_force.update_available)
            self.assertTrue(resp_force.update_required)
            self.assertTrue(resp_force.force_update)
            self.assertEqual(resp_force.update_message, "Critical security patch")

            # Case B: Current version is between min_supported and latest -> optional update
            resp_soft = AppVersionService.check(db, platform="android", current_version="1.6.0")
            self.assertTrue(resp_soft.update_available)
            self.assertFalse(resp_soft.update_required)
            self.assertTrue(resp_soft.force_update)

            # Case C: Current version is latest -> no update
            resp_latest = AppVersionService.check(db, platform="android", current_version="2.0.0")
            self.assertFalse(resp_latest.update_available)
            self.assertFalse(resp_latest.update_required)


class PincodeServiceWhiteBoxTests(unittest.TestCase):
    """White-box tests for PincodeService validation and API handling."""

    def test_invalid_pincode_format_raises_422(self):
        # Shorter than 6 digits
        with self.assertRaises(HTTPException) as ctx:
            PincodeService.validate_and_fetch_pincode("12345")
        self.assertEqual(ctx.exception.status_code, 422)

        # Longer than 6 digits
        with self.assertRaises(HTTPException) as ctx:
            PincodeService.validate_and_fetch_pincode("1234567")
        self.assertEqual(ctx.exception.status_code, 422)

        # Non-numeric
        with self.assertRaises(HTTPException) as ctx:
            PincodeService.validate_and_fetch_pincode("38000A")
        self.assertEqual(ctx.exception.status_code, 422)

    @patch("httpx.Client")
    def test_upstream_service_failure_raises_503(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.RequestError("Network error")
        mock_client_cls.return_value = mock_client

        with self.assertRaises(HTTPException) as ctx:
            PincodeService.validate_and_fetch_pincode("380001")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("timed out or is unavailable", ctx.exception.detail)

    @patch("httpx.Client")
    def test_upstream_http_status_not_200_raises_503(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = MagicMock(status_code=502)
        mock_client_cls.return_value = mock_client

        with self.assertRaises(HTTPException) as ctx:
            PincodeService.validate_and_fetch_pincode("380001")
        self.assertEqual(ctx.exception.status_code, 503)

    @patch("httpx.Client")
    def test_pincode_not_found_raises_404(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        # API returns empty list or Status: Error
        mock_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"Status": "Error", "Message": "No records found"}]
        )
        mock_client_cls.return_value = mock_client

        with self.assertRaises(HTTPException) as ctx:
            PincodeService.validate_and_fetch_pincode("999999")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("not found", ctx.exception.detail)

    @patch("httpx.Client")
    def test_pincode_success_and_district_fallback(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{
                "Status": "Success",
                "PostOffice": [
                    {"Name": "Ahmedabad G.P.O.", "District": "Ahmedabad", "State": "Gujarat"}
                ]
            }]
        )
        mock_client_cls.return_value = mock_client

        res = PincodeService.validate_and_fetch_pincode("380001")
        self.assertEqual(res.pincode, "380001")
        self.assertEqual(res.city_name, "Ahmedabad")
        self.assertEqual(len(res.postal_data), 1)


class LeadsRouterWhiteBoxTests(unittest.TestCase):
    """White-box tests for IDOR prevention, status validation, and lock verification."""

    def setUp(self):
        self.agent = MagicMock(id=101, full_name="Agent Smith")
        self.other_agent = MagicMock(id=102, full_name="Agent Doe")
        self.db = MagicMock()
        self.repo = MagicMock()

    @patch("fastapi_app.routers.leads.LockUnlockService")
    def test_get_lead_detail_authorized(self, mock_lock_cls):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock

        expected_lead = MagicMock(id=50, agent_id=101, name="John Doe")
        self.repo.get_by_id.return_value = expected_lead

        lead = get_lead_detail(
            lead_id=50,
            current_agent=self.agent,
            db=self.db,
            repo=self.repo
        )

        self.assertEqual(lead, expected_lead)
        self.repo.get_by_id.assert_called_once_with(101, 50)
        mock_lock.require_feature_unlocked.assert_called_once_with(self.agent, "lead_management")

    @patch("fastapi_app.routers.leads.LockUnlockService")
    def test_get_lead_detail_idor_or_nonexistent_returns_404(self, mock_lock_cls):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock

        # Simulating that lead #50 does not belong to agent #101
        self.repo.get_by_id.return_value = None

        with self.assertRaises(HTTPException) as ctx:
            get_lead_detail(
                lead_id=50,
                current_agent=self.agent,
                db=self.db,
                repo=self.repo
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Lead not found or does not belong", ctx.exception.detail)

    @patch("fastapi_app.routers.leads.LockUnlockService")
    def test_update_status_invalid_value_raises_422(self, mock_lock_cls):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock

        payload = LeadStatusUpdate(status="invalid_stage")

        with self.assertRaises(HTTPException) as ctx:
            update_status(
                lead_id=50,
                payload=payload,
                current_agent=self.agent,
                db=self.db,
                repo=self.repo
            )
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("Invalid status", ctx.exception.detail)

    @patch("fastapi_app.routers.leads.LockUnlockService")
    def test_update_status_valid_success(self, mock_lock_cls):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock

        updated_lead = MagicMock(id=50, status="contacted")
        self.repo.update_lead_status.return_value = updated_lead

        payload = LeadStatusUpdate(status="contacted")
        res = update_status(
            lead_id=50,
            payload=payload,
            current_agent=self.agent,
            db=self.db,
            repo=self.repo
        )

        self.assertEqual(res.status, "contacted")
        self.repo.update_lead_status.assert_called_once_with(
            agent_id=101,
            lead_id=50,
            status="contacted"
        )


if __name__ == "__main__":
    unittest.main()
