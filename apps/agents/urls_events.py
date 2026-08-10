from django.urls import path
from .views import events

app_name = 'events'

urlpatterns = [
    # ── Public Event Registration Funnel (mirrors Laravel events.* routes) ──
    path('register/', events.show_form,      name='register.form'),
    path('register/', events.register,       name='register.submit'),
    path('plans/',    events.show_plans,     name='plans'),
    path('plans/',    events.select_plan,    name='plans.submit'),
    path('payment/',  events.show_payment,   name='payment'),
    path('payment/success/', events.payment_success, name='payment.success'),
    path('payment/failure/', events.payment_failure, name='payment.failure'),
    path('success/',  events.show_success,   name='success'),
    path('verify-promo/', events.verify_promo_code, name='verify.promo'),
]