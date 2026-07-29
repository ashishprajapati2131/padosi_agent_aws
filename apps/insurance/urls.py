from django.urls import path
from .views import dashboard, profile, subusers, agents, approvals, payments, notify

app_name = 'insurance'

urlpatterns = [
    path('dashboard/', dashboard.dashboard, name='dashboard'),
    
    path('profile/', profile.profile_edit, name='profile'),
    
    path('subusers/', subusers.subusers_index, name='subusers_index'),
    path('subusers/store/', subusers.subusers_store, name='subusers_store'),
    path('subusers/<int:user_id>/reset-password/', subusers.subusers_reset_password, name='subusers_reset_password'),
    path('subusers/toggle-status/', subusers.subusers_toggle_status, name='subusers_toggle_status'),
    
    path('agents/', agents.agents_index, name='agents_index'),
    path('agents/create/', agents.agents_create, name='agents_create'),
    path('agents/store/', agents.agents_store, name='agents_store'),
    path('agents/<int:agent_id>/', agents.agents_show, name='agents_show'),
    path('agents/<int:agent_id>/request-status-change/', agents.request_status_change, name='request_status_change'),
    
    path('agents/cart/add/', agents.add_to_cart, name='add_to_cart'),
    path('agents/cart/remove/', agents.remove_from_cart, name='remove_from_cart'),
    path('agents/cart/clear/', agents.clear_cart, name='clear_cart'),
    path('agents/cart/checkout/', agents.checkout_cart, name='checkout_cart'),
    path('agents/cart/checkout-success/', agents.checkout_cart, name='checkout_online_success'),
    
    path('approvals/', approvals.approvals_index, name='approvals_index'),
    path('approvals/<int:agent_id>/approve/', approvals.approvals_approve, name='approvals_approve'),
    path('approvals/<int:agent_id>/reject/', approvals.approvals_reject, name='approvals_reject'),
    
    path('payments/', payments.payments_index, name='payments_index'),
    path('payments/<int:agent_id>/record/', payments.record_payment, name='record_payment'),
    path('payments/<int:agent_id>/create-razorpay-order/', payments.create_razorpay_order, name='create_razorpay_order'),
    path('payments/<int:agent_id>/handle-success/', payments.handle_payment_success, name='handle_payment_success'),
    
    path('notify/', notify.notify_form, name='notify_form'),
    path('notify/send/', notify.notify_send, name='notify_send'),
]
