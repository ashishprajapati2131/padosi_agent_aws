"""Markers for the admin "testing mode" fake referrals (Paldi / championship).

Test referrals never touch Razorpay. Their subscriptions use these id
prefixes and their agents this email domain, so invoicing, welcome emails,
the invoice retry job and the public directory can skip them: the invoice
number sequence is never consumed by test data.
"""
TEST_ORDER_PREFIX = 'order_TESTREF'
TEST_PAYMENT_PREFIX = 'pay_TESTREF'
TEST_EMAIL_DOMAIN = 'paldi-test.invalid'


def is_test_email(email):
    return str(email or '').strip().lower().endswith('@' + TEST_EMAIL_DOMAIN)


def is_test_subscription(subscription):
    if not subscription:
        return False
    if str(getattr(subscription, 'razorpay_payment_id', '') or '').startswith(TEST_PAYMENT_PREFIX):
        return True
    if str(getattr(subscription, 'razorpay_order_id', '') or '').startswith(TEST_ORDER_PREFIX):
        return True
    agent = getattr(subscription, 'agent', None)
    return bool(agent and is_test_email(getattr(agent, 'email', '')))
