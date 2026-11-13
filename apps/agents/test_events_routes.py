"""Audit AG14: every /events/ URL name still reverses and resolves, and the
live entry points (verify-promo, payment success, webhook fulfilment) are wired.

register.submit / plans.submit share their path with the GET views, so POSTs
land on show_form / show_plans. Their names stay because the event templates
reverse them (register.html, plans.html)."""
from django.test import SimpleTestCase
from django.urls import resolve, reverse

from apps.agents import urls_events
from apps.agents.views import events, registration

SHADOWED = {'register.submit': events.show_form, 'plans.submit': events.show_plans}


class EventsRoutesTests(SimpleTestCase):
    def test_every_events_url_resolves(self):
        for p in urls_events.urlpatterns:
            with self.subTest(name=p.name):
                func = resolve(reverse(f'events:{p.name}')).func
                self.assertIs(func, SHADOWED.get(p.name, p.callback))

    def test_verify_promo_resolves(self):
        self.assertEqual(reverse('events:verify.promo'), '/events/verify-promo/')
        self.assertIs(resolve('/events/verify-promo/').func, events.verify_promo_code)

    def test_payment_success_resolves(self):
        self.assertIs(resolve('/events/payment/success/').func, events.payment_success)

    def test_webhook_fulfilment_entry(self):
        self.assertEqual(resolve('/razorpay-webhook/').func.__wrapped__, registration.razorpay_webhook)
        self.assertTrue(callable(events.fulfil_event_registration))
        self.assertTrue(issubclass(events.EventPaymentRejected, Exception))
