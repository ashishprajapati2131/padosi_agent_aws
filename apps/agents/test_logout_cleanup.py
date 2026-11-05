import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

User = get_user_model()


class LogoutCleanupTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_client_logout_cleanses_referer_pincode_and_session(self):
        # Create client user
        user = User.objects.create_user(
            username='client_test@example.com',
            email='client_test@example.com',
            password='password123'
        )
        from apps.agents.models import Client
        Client.objects.create(user=user, mobile='9876543210', pincode='380015')
        self.client.force_login(user)

        # Set location and pincode in session
        session = self.client.session
        session['last_pincode'] = '380015'
        session['detected_area'] = 'Satellite, Ahmedabad'
        session['last_location'] = 'Ahmedabad'
        session.save()

        # Submit logout with referer containing pincode
        response = self.client.post(
            '/logout/',
            HTTP_REFERER='http://testserver/find-agents/?pincode=380015&ServiceType=New+Policy',
            HTTP_HOST='testserver'
        )

        self.assertEqual(response.status_code, 302)
        # Verify pincode is stripped from redirect URL
        redirect_url = response['Location']
        self.assertNotIn('pincode=380015', redirect_url)
        self.assertNotIn('ServiceType', redirect_url)
        self.assertIn('/find-agents/', redirect_url)

        # Verify session is cleaned
        clean_session = self.client.session
        self.assertNotIn('last_pincode', clean_session)
        self.assertNotIn('detected_area', clean_session)
        self.assertNotIn('last_location', clean_session)

    def test_guest_visitor_logout_from_find_agents_cleans_session(self):
        # Visitor with guest session
        session = self.client.session
        session['quick_lead_user'] = {'fullname': 'Guest User', 'mobile': '9876543210'}
        session['last_pincode'] = '380054'
        session.save()

        response = self.client.post(
            '/logout/',
            HTTP_REFERER='http://testserver/find-agents/?pincode=380054',
            HTTP_HOST='testserver'
        )

        self.assertEqual(response.status_code, 302)
        self.assertNotIn('pincode=380054', response['Location'])
        self.assertIn('/find-agents/', response['Location'])

        clean_session = self.client.session
        self.assertNotIn('quick_lead_user', clean_session)
        self.assertNotIn('last_pincode', clean_session)
