"""
WhatsApp Agent Bot — URL Configuration

All bot endpoints are grouped under the /wa-bot/ prefix.
"""

from django.urls import path
from . import views
from . import simulator_views

app_name = 'wa_agent_bot'

urlpatterns = [
    path('webhook/', views.webhook_receiver, name='webhook_receiver'),
    path('health/', views.bot_health, name='bot_health'),
    path('razorpay-webhook/', views.razorpay_webhook, name='razorpay_webhook'),
    path('payment-callback/', views.payment_callback, name='payment_callback'),

    # Live Browser Simulator
    path('simulator/', simulator_views.simulator_page, name='simulator_page'),
    path('simulator/send/', simulator_views.simulator_send, name='simulator_send'),
    path('simulator/poll/', simulator_views.simulator_poll, name='simulator_poll'),
    path('simulator/reset/', simulator_views.simulator_reset, name='simulator_reset'),
    path('simulator/simulate-payment/', simulator_views.simulator_payment, name='simulator_payment'),
    path('simulator/toggle/', simulator_views.simulator_toggle, name='simulator_toggle'),
]

