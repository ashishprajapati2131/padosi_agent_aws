"""
Regression tests for wholesale / private-file security fixes:
open redirects, RFQ attachment type checks, private file headers,
wholesale admin permission and login throttling.
"""
import os
import shutil
import tempfile
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.admin_panel.models.admin_auth import Admin
from apps.agents.models import Agent, AgentSubscription
from apps.home.models.site_setting import SiteSetting
from apps.wholesale.adapters.auth_bridge import is_wholesale_admin, safe_next_url
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.inquiry import BuyerInquiry, InquiryMessage
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.profile import WholesalerProfile


class WholesaleSecurityBase(TestCase):
    def setUp(self):
        SiteSetting.set_value('wholesale_marketplace_enabled', '1', group='general')
        self.user = User.objects.create_user('ws_sec', 'ws_sec@example.com', 'TestPassword123!')
        self.profile = WholesalerProfile.objects.create(
            user=self.user, business_name='Sec Supplies', contact_person='Sec',
            email='ws_sec@example.com', phone='9898000101', city='Ahmedabad',
            state='Gujarat', verification_status='APPROVED',
        )
        category = ProductCategory.objects.create(name='Sec Cat', slug='sec-cat', is_active=True)
        self.product = WholesaleProduct.objects.create(
            wholesaler=self.profile, category=category, title='Sec Folder', slug='sec-folder',
            sku='WS-SEC-001', short_description='x', description='x', moq=1,
            base_price=Decimal('10.00'), suggested_retail_price=Decimal('20.00'),
            approval_status='PUBLISHED',
        )


class OpenRedirectTests(WholesaleSecurityBase):
    def test_safe_next_url_rejects_external(self):
        request = RequestFactory().get('/')
        self.assertEqual(safe_next_url(request, 'https://evil.example/x', '/home/'), '/home/')
        self.assertEqual(safe_next_url(request, '//evil.example/x', '/home/'), '/home/')
        self.assertEqual(safe_next_url(request, '/wholesale/catalog/', '/home/'), '/wholesale/catalog/')

    def test_login_ignores_external_next(self):
        url = reverse('wholesale:wholesaler_login') + '?next=https://evil.example/phish'
        resp = self.client.post(url, {'email': 'ws_sec@example.com', 'password': 'TestPassword123!'})
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.example', resp['Location'])

    def test_rfq_ignores_external_referer(self):
        url = reverse('wholesale:submit_rfq', kwargs={'product_id': self.product.id})
        resp = self.client.post(url, {}, HTTP_REFERER='https://evil.example/')
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.example', resp['Location'])


class RfqAttachmentTests(WholesaleSecurityBase):
    def test_html_attachment_rejected(self):
        inquiry = BuyerInquiry.objects.create(
            product=self.product, wholesaler=self.profile, buyer_name='B', buyer_email='b@example.com',
            buyer_phone='9898000102', delivery_pincode='380015', delivery_city='Ahmedabad',
            requested_quantity=5,
        )
        self.client.force_login(self.user)
        evil = SimpleUploadedFile('quote.html', b'<script>alert(1)</script>', content_type='text/html')
        resp = self.client.post(
            reverse('wholesale:rfq_reply', kwargs={'inquiry_id': inquiry.id}),
            {'message': 'see attached', 'attachment': evil},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(InquiryMessage.objects.filter(inquiry=inquiry).exists())


class WholesaleAdminPermissionTests(TestCase):
    def _request(self, admin):
        request = RequestFactory().get('/')
        request.session = {'admin_id': admin.pk}
        request.user = type('Anon', (), {'is_authenticated': False})()
        return request

    def test_staff_admin_without_wholesale_permission_is_not_wholesale_admin(self):
        admin = Admin.objects.create(name='S', email='s@example.com', password='x', role='staff', permissions=['agents'])
        self.assertFalse(is_wholesale_admin(self._request(admin)))

    def test_staff_admin_with_wholesale_permission_and_super_admin(self):
        staff = Admin.objects.create(name='W', email='w@example.com', password='x', role='staff', permissions=['wholesale'])
        sup = Admin.objects.create(name='U', email='u@example.com', password='x', role='super', permissions=[])
        self.assertTrue(is_wholesale_admin(self._request(staff)))
        self.assertTrue(is_wholesale_admin(self._request(sup)))


class WholesaleLoginThrottleTests(WholesaleSecurityBase):
    def test_throttled_login_refused(self):
        with patch('apps.agents.views.auth.check_login_throttle', return_value=False):
            resp = self.client.post(
                reverse('wholesale:wholesaler_login'),
                {'email': 'ws_sec@example.com', 'password': 'TestPassword123!'},
            )
        self.assertEqual(resp.status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)


class PrivateFileHeaderTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        user = User.objects.create_user('pf@example.com', 'pf@example.com', None)
        self.agent = Agent.objects.create(
            user=user, fullname='PF Agent', email='pf@example.com', mobile='9876500199',
            status='active', plan_type='starter',
        )
        AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan", registration_amount=Decimal('1999.00'),
            payment_status='completed', status='active',
            razorpay_order_id=f'order_PF{self.agent.pk}', razorpay_payment_id=f'pay_PF{self.agent.pk}',
        )
        folder = os.path.join(self.media, 'app', 'private', 'agents', str(self.agent.pk))
        os.makedirs(folder)
        with open(os.path.join(folder, 'page.html'), 'wb') as fh:
            fh.write(b'<script>alert(1)</script>')
        self.client.force_login(user)

    def test_private_file_sends_nosniff_csp_and_attachment(self):
        with override_settings(MEDIA_ROOT=self.media):
            resp = self.client.get(reverse('serve_private_file', args=[f'agents/{self.agent.pk}/page.html']))
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp['X-Content-Type-Options'], 'nosniff')
            self.assertIn('sandbox', resp['Content-Security-Policy'])
            self.assertTrue(resp['Content-Disposition'].startswith('attachment'))
            resp.close()
