"""
Admin-controlled distributor / sub-distributor password reset.

Run: python manage.py test apps.distributors.test_password_reset
"""
from unittest.mock import patch

from django.test import TestCase, RequestFactory, Client
from django.contrib.auth.models import User as DjangoUser, Group
from django.contrib.messages.storage.fallback import FallbackStorage

from password_hashing import hash_password, check_password_hash
from apps.admin_panel.models import User as LaravelUser
from apps.distributors.models import SubDistributor


def _attach_messages(request):
    request.session = {}
    setattr(request, '_messages', FallbackStorage(request))
    return request


class AdminDistributorResetTests(TestCase):
    def setUp(self):
        self.dist = LaravelUser.objects.create(
            fullname='Dist One', email='dist1@example.com',
            password=hash_password('oldpass123'), role='distributor', status='active')

    def _post(self, data, admin_pk=1):
        from apps.admin_panel.views.distributors import distributor_reset_password
        req = _attach_messages(RequestFactory().post('/admin/distributors/reset-password/', data))
        with patch('apps.admin_panel.views.distributors._get_admin_from_session', return_value=admin_pk):
            return distributor_reset_password(req)

    def test_reset_sets_new_password(self):
        resp = self._post({'distributor_id': self.dist.id, 'password': 'newpass123', 'confirm_password': 'newpass123'})
        self.assertEqual(resp.status_code, 302)
        self.dist.refresh_from_db()
        self.assertTrue(check_password_hash('newpass123', self.dist.password))
        self.assertFalse(check_password_hash('oldpass123', self.dist.password))

    def test_short_password_rejected(self):
        self._post({'distributor_id': self.dist.id, 'password': 'short', 'confirm_password': 'short'})
        self.dist.refresh_from_db()
        self.assertTrue(check_password_hash('oldpass123', self.dist.password))

    def test_mismatch_rejected(self):
        self._post({'distributor_id': self.dist.id, 'password': 'newpass123', 'confirm_password': 'different1'})
        self.dist.refresh_from_db()
        self.assertTrue(check_password_hash('oldpass123', self.dist.password))

    def test_requires_admin(self):
        resp = self._post({'distributor_id': self.dist.id, 'password': 'newpass123', 'confirm_password': 'newpass123'}, admin_pk=None)
        self.assertEqual(resp.status_code, 302)  # redirect to admin_login
        self.dist.refresh_from_db()
        self.assertTrue(check_password_hash('oldpass123', self.dist.password))


class AdminSubDistributorResetTests(TestCase):
    def setUp(self):
        self.sub = SubDistributor.objects.create(
            distributor_id=1, fullname='Sub One', email='sub1@example.com',
            mobile='9000000001', password=hash_password('oldsub123'), code='SUB1')

    def test_admin_resets_sub(self):
        from apps.admin_panel.views.distributors import subdistributor_reset_password
        req = _attach_messages(RequestFactory().post('/admin/distributors/sub/reset-password/',
                               {'sub_distributor_id': self.sub.id, 'password': 'newsub123', 'confirm_password': 'newsub123'}))
        with patch('apps.admin_panel.views.distributors._get_admin_from_session', return_value=1):
            resp = subdistributor_reset_password(req)
        self.assertEqual(resp.status_code, 302)
        self.sub.refresh_from_db()
        self.assertTrue(check_password_hash('newsub123', self.sub.password))


class ParentPortalSubResetTests(TestCase):
    def setUp(self):
        self.parent = LaravelUser.objects.create(
            fullname='Parent', email='parent@example.com',
            password=hash_password('parentpw1'), role='distributor', status='active')
        self.django_user = DjangoUser.objects.create_user(
            username='parent@example.com', email='parent@example.com', password='x')
        grp, _ = Group.objects.get_or_create(name='distributor')
        self.django_user.groups.add(grp)
        self.my_sub = SubDistributor.objects.create(
            distributor_id=self.parent.id, fullname='My Sub', email='mysub@example.com',
            mobile='9000000002', password=hash_password('oldsub123'), code='MYSUB')
        self.other_sub = SubDistributor.objects.create(
            distributor_id=99999, fullname='Other Sub', email='other@example.com',
            mobile='9000000003', password=hash_password('oldsub123'), code='OTHERSUB')
        self.client = Client()
        self.client.force_login(self.django_user)

    def test_parent_resets_own_sub(self):
        url = f'/distributor/sub-distributors/{self.my_sub.id}/reset-password/'
        resp = self.client.post(url, {'password': 'freshsub123', 'confirm_password': 'freshsub123'})
        self.assertEqual(resp.status_code, 302)
        self.my_sub.refresh_from_db()
        self.assertTrue(check_password_hash('freshsub123', self.my_sub.password))

    def test_parent_cannot_reset_others_sub(self):
        url = f'/distributor/sub-distributors/{self.other_sub.id}/reset-password/'
        resp = self.client.post(url, {'password': 'freshsub123', 'confirm_password': 'freshsub123'})
        self.assertEqual(resp.status_code, 404)
        self.other_sub.refresh_from_db()
        self.assertTrue(check_password_hash('oldsub123', self.other_sub.password))

    def test_short_password_rejected(self):
        url = f'/distributor/sub-distributors/{self.my_sub.id}/reset-password/'
        self.client.post(url, {'password': 'short', 'confirm_password': 'short'})
        self.my_sub.refresh_from_db()
        self.assertTrue(check_password_hash('oldsub123', self.my_sub.password))
