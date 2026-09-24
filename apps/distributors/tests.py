"""
Tests for the Sub-Distributor flow.

Covers three sub-flows:
  1. SubDistributor model (unique code, password hashing)
  2. Sub-Distributor dedicated portal (login / logout / dashboard access guard)
  3. Public candidate join (invite link -> account creation + auto-login)
  4. Distributor-side management (create / toggle status / list / isolation)

Run:  python manage.py test apps.distributors
"""
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group

from password_hashing import hash_password, check_password_hash
from apps.distributors.models import SubDistributor
from apps.admin_panel.models import User as LaravelUser
from apps.agents.models import Agent


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_sub_distributor(distributor_id=1, email='sub@example.com', mobile='9876543210',
                         password='secret123', status='active', fullname='Sub One'):
    return SubDistributor.objects.create(
        distributor_id=distributor_id,
        fullname=fullname,
        email=email,
        mobile=mobile,
        password=hash_password(password),
        code=SubDistributor.generate_unique_code(distributor_id, fullname),
        status=status,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Model
# ─────────────────────────────────────────────────────────────────────────────

class SubDistributorModelTest(TestCase):
    def test_generate_unique_code_is_unique_and_prefixed(self):
        c1 = SubDistributor.generate_unique_code(5, 'Ramesh')
        # Reserve it so the next call must produce a different one
        SubDistributor.objects.create(
            distributor_id=5, fullname='Ramesh', email='r@x.com', mobile='9000000000',
            password=hash_password('x'), code=c1, status='active',
        )
        c2 = SubDistributor.generate_unique_code(5, 'Ramesh')
        self.assertTrue(c1.startswith('SUB5RAM'))
        self.assertNotEqual(c1, c2)

    def test_password_hash_roundtrip(self):
        sd = make_sub_distributor(password='MyPass@99')
        self.assertNotEqual(sd.password, 'MyPass@99')          # stored hashed
        self.assertTrue(check_password_hash('MyPass@99', sd.password))
        self.assertFalse(check_password_hash('wrong', sd.password))

    def test_agent_count_helpers(self):
        sd = make_sub_distributor()
        Agent.objects.create(fullname='A1', email='a1@x.com', mobile='9111111111',
                             sub_distributor_id=sd.id, status='active')
        Agent.objects.create(fullname='A2', email='a2@x.com', mobile='9222222222',
                             sub_distributor_id=sd.id, status='pending_payment')
        self.assertEqual(sd.get_total_agents_count(), 2)
        self.assertEqual(sd.get_active_agents_count(), 1)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Sub-Distributor Portal auth
# ─────────────────────────────────────────────────────────────────────────────

class SubDistributorPortalAuthTest(TestCase):
    def setUp(self):
        self.sd = make_sub_distributor(email='portal@example.com', mobile='9998887770',
                                       password='pass1234')
        self.login_url = reverse('distributors:sub_distributor_login')
        self.dash_url = reverse('distributors:sub_distributor_dashboard')

    def test_login_with_email_success(self):
        resp = self.client.post(self.login_url, {'identifier': 'portal@example.com', 'password': 'pass1234'})
        self.assertRedirects(resp, self.dash_url, fetch_redirect_response=False)
        self.assertEqual(self.client.session.get('sub_distributor_id'), self.sd.id)

    def test_login_with_mobile_success(self):
        resp = self.client.post(self.login_url, {'identifier': '9998887770', 'password': 'pass1234'})
        self.assertRedirects(resp, self.dash_url, fetch_redirect_response=False)
        self.assertEqual(self.client.session.get('sub_distributor_id'), self.sd.id)

    def test_login_wrong_password_rejected(self):
        resp = self.client.post(self.login_url, {'identifier': 'portal@example.com', 'password': 'nope'})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self.client.session.get('sub_distributor_id'))

    def test_login_unknown_identifier_rejected(self):
        resp = self.client.post(self.login_url, {'identifier': 'ghost@example.com', 'password': 'pass1234'})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self.client.session.get('sub_distributor_id'))

    def test_login_suspended_account_blocked(self):
        self.sd.status = 'suspended'
        self.sd.save(update_fields=['status'])
        resp = self.client.post(self.login_url, {'identifier': 'portal@example.com', 'password': 'pass1234'})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self.client.session.get('sub_distributor_id'))

    def test_dashboard_requires_login(self):
        resp = self.client.get(self.dash_url)
        self.assertRedirects(resp, self.login_url, fetch_redirect_response=False)

    def _portal_session(self):
        from apps.distributors.views.sub_distributors import SUB_DIST_PORTAL_KEY
        session = self.client.session
        session[SUB_DIST_PORTAL_KEY] = self.sd.id
        session['sub_distributor_id'] = self.sd.id
        session.save()

    def test_dashboard_accessible_when_logged_in(self):
        self._portal_session()
        resp = self.client.get(self.dash_url)
        self.assertEqual(resp.status_code, 200)

    def test_pre_upgrade_login_session_still_works(self):
        """Sessions created by the old login (id + code, no portal key) stay logged in."""
        session = self.client.session
        session['sub_distributor_id'] = self.sd.id
        session['sub_distributor_code'] = self.sd.code
        session.save()
        resp = self.client.get(self.dash_url)
        self.assertEqual(resp.status_code, 200)

    def test_referral_link_does_not_grant_portal_access(self):
        """Regression: /join/<code>/ stores sub_distributor_id for attribution;
        that alone must never authenticate the sub-distributor portal."""
        self.sd.code = 'SDTEST01'
        self.sd.save(update_fields=['code'])
        self.client.get(reverse('agents:referral_join', args=[self.sd.code]))
        self.assertEqual(self.client.session.get('sub_distributor_id'), self.sd.id)
        resp = self.client.get(self.dash_url)
        self.assertRedirects(resp, self.login_url, fetch_redirect_response=False)

    def test_dashboard_guard_flushes_suspended_session(self):
        self._portal_session()
        # Suspend after login -> next request must kick them out
        self.sd.status = 'suspended'
        self.sd.save(update_fields=['status'])
        resp = self.client.get(self.dash_url)
        self.assertRedirects(resp, self.login_url, fetch_redirect_response=False)
        self.assertIsNone(self.client.session.get('sub_distributor_id'))

    def test_logout_clears_session(self):
        self._portal_session()
        resp = self.client.get(reverse('distributors:sub_distributor_logout'))
        self.assertRedirects(resp, self.login_url, fetch_redirect_response=False)
        self.assertIsNone(self.client.session.get('sub_distributor_id'))

    def test_login_updates_last_login_at(self):
        self.assertIsNone(self.sd.last_login_at)
        self.client.post(self.login_url, {'identifier': 'portal@example.com', 'password': 'pass1234'})
        self.sd.refresh_from_db()
        self.assertIsNotNone(self.sd.last_login_at)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Public candidate join
# ─────────────────────────────────────────────────────────────────────────────

class SubDistributorPublicJoinTest(TestCase):
    def setUp(self):
        self.distributor = LaravelUser.objects.create(
            fullname='Parent Dist', email='parent@example.com',
            password=hash_password('x'), role='distributor', status='active',
        )
        self.dist_code = f"DIST{self.distributor.id}"
        self.join_url = reverse('distributors:sub_distributor_join', args=[self.dist_code])
        self.dash_url = reverse('distributors:sub_distributor_dashboard')

    def test_join_invalid_code_shows_error(self):
        resp = self.client.get(reverse('distributors:sub_distributor_join', args=['DIST999999']))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Invalid', status_code=200)

    def test_join_get_valid_code_renders_form(self):
        resp = self.client.get(self.join_url)
        self.assertEqual(resp.status_code, 200)

    def test_join_post_creates_and_autologs_in(self):
        resp = self.client.post(self.join_url, {
            'fullname': 'New Sub', 'email': 'newsub@example.com', 'mobile': '9123456789',
            'password': 'abcdef', 'confirm_password': 'abcdef',
        })
        self.assertRedirects(resp, self.dash_url, fetch_redirect_response=False)
        sd = SubDistributor.objects.filter(email='newsub@example.com').first()
        self.assertIsNotNone(sd)
        self.assertEqual(sd.distributor_id, self.distributor.id)
        self.assertEqual(self.client.session.get('sub_distributor_id'), sd.id)
        self.assertTrue(check_password_hash('abcdef', sd.password))

    def test_join_password_mismatch_rejected(self):
        resp = self.client.post(self.join_url, {
            'fullname': 'X', 'email': 'x@example.com', 'mobile': '9123456700',
            'password': 'abcdef', 'confirm_password': 'zzzzzz',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SubDistributor.objects.filter(email='x@example.com').exists())

    def test_join_short_password_rejected(self):
        resp = self.client.post(self.join_url, {
            'fullname': 'X', 'email': 'short@example.com', 'mobile': '9123456701',
            'password': '123', 'confirm_password': '123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SubDistributor.objects.filter(email='short@example.com').exists())

    def test_join_duplicate_email_rejected(self):
        make_sub_distributor(email='dupe@example.com', distributor_id=self.distributor.id)
        resp = self.client.post(self.join_url, {
            'fullname': 'Dupe', 'email': 'dupe@example.com', 'mobile': '9123456702',
            'password': 'abcdef', 'confirm_password': 'abcdef',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SubDistributor.objects.filter(email='dupe@example.com').count(), 1)

    def test_join_then_portal_login_end_to_end(self):
        self.client.post(self.join_url, {
            'fullname': 'E2E Sub', 'email': 'e2e@example.com', 'mobile': '9123456703',
            'password': 'abcdef', 'confirm_password': 'abcdef',
        })
        self.client.get(reverse('distributors:sub_distributor_logout'))
        resp = self.client.post(reverse('distributors:sub_distributor_login'),
                                {'identifier': 'e2e@example.com', 'password': 'abcdef'})
        self.assertRedirects(resp, self.dash_url, fetch_redirect_response=False)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Distributor-side management
# ─────────────────────────────────────────────────────────────────────────────

class SubDistributorManagementTest(TestCase):
    def setUp(self):
        self.group, _ = Group.objects.get_or_create(name='distributor')
        self.django_user = User.objects.create_user(
            username='dist@example.com', email='dist@example.com', password='pw')
        self.django_user.groups.add(self.group)
        self.laravel_user = LaravelUser.objects.create(
            fullname='Dist Owner', email='dist@example.com',
            password=hash_password('pw'), role='distributor', status='active')
        self.client.force_login(self.django_user)
        self.index_url = reverse('distributors:sub_distributors_index')
        self.create_url = reverse('distributors:sub_distributor_create')

    def test_index_requires_distributor(self):
        self.client.logout()
        resp = self.client.get(self.index_url)
        self.assertEqual(resp.status_code, 302)  # bounced to login

    def test_index_loads_for_distributor(self):
        resp = self.client.get(self.index_url)
        self.assertEqual(resp.status_code, 200)

    def test_index_shows_sub_distributor_login_link(self):
        resp = self.client.get(self.index_url)
        self.assertEqual(resp.status_code, 200)
        login_path = reverse('distributors:sub_distributor_login')
        self.assertIn('sub_login_url', resp.context)
        self.assertIn(login_path, resp.context['sub_login_url'])
        # The login link is rendered on the page so the distributor can copy/share it
        self.assertContains(resp, resp.context['sub_login_url'])

    def test_create_sub_distributor_success(self):
        resp = self.client.post(self.create_url, {
            'fullname': 'Created Sub', 'email': 'created@example.com',
            'mobile': '9555000111', 'password': 'temp1234', 'notes': 'vip',
        })
        self.assertRedirects(resp, self.index_url, fetch_redirect_response=False)
        sd = SubDistributor.objects.filter(email='created@example.com').first()
        self.assertIsNotNone(sd)
        self.assertEqual(sd.distributor_id, self.laravel_user.id)
        self.assertEqual(sd.status, 'active')
        self.assertTrue(check_password_hash('temp1234', sd.password))

    def test_create_missing_fields_rejected(self):
        resp = self.client.post(self.create_url, {
            'fullname': 'No Email', 'email': '', 'mobile': '9555000112', 'password': 'temp1234',
        })
        self.assertRedirects(resp, self.index_url, fetch_redirect_response=False)
        self.assertFalse(SubDistributor.objects.filter(fullname='No Email').exists())

    def test_create_duplicate_email_rejected(self):
        make_sub_distributor(email='taken@example.com', distributor_id=self.laravel_user.id)
        resp = self.client.post(self.create_url, {
            'fullname': 'Dup', 'email': 'taken@example.com',
            'mobile': '9555000113', 'password': 'temp1234',
        })
        self.assertRedirects(resp, self.index_url, fetch_redirect_response=False)
        self.assertEqual(SubDistributor.objects.filter(email='taken@example.com').count(), 1)

    def test_toggle_status_active_to_suspended_and_back(self):
        sd = make_sub_distributor(email='toggle@example.com', distributor_id=self.laravel_user.id)
        url = reverse('distributors:sub_distributor_toggle_status', args=[sd.id])
        self.client.post(url)
        sd.refresh_from_db()
        self.assertEqual(sd.status, 'suspended')
        self.client.post(url)
        sd.refresh_from_db()
        self.assertEqual(sd.status, 'active')

    def test_toggle_other_distributors_sub_is_forbidden(self):
        # Sub owned by a DIFFERENT distributor id
        other = make_sub_distributor(email='other@example.com', distributor_id=99999)
        url = reverse('distributors:sub_distributor_toggle_status', args=[other.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 404)
        other.refresh_from_db()
        self.assertEqual(other.status, 'active')  # unchanged

    def test_view_agents_of_sub_distributor(self):
        sd = make_sub_distributor(email='withagents@example.com', distributor_id=self.laravel_user.id)
        Agent.objects.create(fullname='Ag1', email='ag1@example.com', mobile='9333000111',
                             sub_distributor_id=sd.id, distributor_id=self.laravel_user.id, status='active')
        url = reverse('distributors:sub_distributor_agents', args=[sd.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_count'], 1)
        self.assertEqual(resp.context['active_count'], 1)

    def _agents_for(self, sd, statuses, prefix):
        for i, status in enumerate(statuses):
            Agent.objects.create(
                fullname=f'{prefix}{i}', email=f'{prefix}{i}@example.com',
                mobile=f'9{ord(prefix[0]) % 10}{i:08d}',
                sub_distributor_id=sd.id, distributor_id=self.laravel_user.id, status=status,
            )

    def test_index_per_sub_distributor_counts_match_old_per_row_counts(self):
        sd1 = make_sub_distributor(email='c1@example.com', distributor_id=self.laravel_user.id)
        sd2 = make_sub_distributor(email='c2@example.com', mobile='9876543211', distributor_id=self.laravel_user.id)
        sd3 = make_sub_distributor(email='c3@example.com', mobile='9876543212', distributor_id=self.laravel_user.id)
        self._agents_for(sd1, ['active', 'active', 'pending_payment'], 'x')
        self._agents_for(sd2, ['incomplete'], 'y')
        resp = self.client.get(self.index_url)
        self.assertEqual(resp.status_code, 200)
        rows = {row['obj'].id: row for row in resp.context['sub_distributors']}
        self.assertEqual((rows[sd1.id]['total_agents'], rows[sd1.id]['active_agents'], rows[sd1.id]['pending_agents']), (3, 2, 1))
        self.assertEqual((rows[sd2.id]['total_agents'], rows[sd2.id]['active_agents'], rows[sd2.id]['pending_agents']), (1, 0, 1))
        self.assertEqual((rows[sd3.id]['total_agents'], rows[sd3.id]['active_agents'], rows[sd3.id]['pending_agents']), (0, 0, 0))

    def test_distributor_dashboard_trend_and_top_sub_distributors(self):
        sd = make_sub_distributor(email='top@example.com', distributor_id=self.laravel_user.id)
        self._agents_for(sd, ['active', 'pending_payment'], 'z')
        resp = self.client.get(reverse('distributors:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['trendData']), 6)
        self.assertEqual(resp.context['trendData'][-1], 2)  # both created this month
        top = {row['obj'].id: row for row in resp.context['topSubDistributors']}
        self.assertEqual((top[sd.id]['total_agents'], top[sd.id]['active_agents']), (2, 1))

    def test_agents_list_shows_active_plan(self):
        from datetime import datetime, timedelta
        from apps.agents.models import AgentSubscription
        agent = Agent.objects.create(
            fullname='Planned', email='planned@example.com', mobile='9333000222',
            distributor_id=self.laravel_user.id, status='active',
        )
        AgentSubscription.objects.create(
            agent=agent, selected_plan="Professional's Plan", registration_amount=4999,
            payment_status='completed', status='active',
            starts_at=datetime.now(), expires_at=datetime.now() + timedelta(days=365),
        )
        resp = self.client.get(reverse('distributors:agents_index'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Professional&#x27;s Plan")
