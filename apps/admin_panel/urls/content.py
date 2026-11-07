"""Admin routes served by views/content.py."""
from django.urls import path

from ..views import content

urlpatterns = [
    path('admin/content/about/',          content.about,          name='admin_content_about'),
    path('admin/content/about/update/',   content.update_about,   name='admin_content_about_update'),
    path('admin/content/invite-studio/',        content.invite_studio,        name='admin_content_invite_studio'),
    path('admin/content/invite-studio/update/', content.update_invite_studio, name='admin_content_invite_studio_update'),
    path('admin/content/faqs/',                          content.faqs,                name='admin_content_faqs'),
    path('admin/content/faqs/settings/update/',          content.faq_settings_update, name='admin_content_faqs_settings_update'),
    path('admin/content/faqs/store/',                    content.faq_store,           name='admin_content_faqs_store'),
    path('admin/content/faqs/<int:faq_id>/update/',      content.faq_update,          name='admin_content_faqs_update'),
    path('admin/content/faqs/toggle/',                   content.faq_toggle,          name='admin_content_faqs_toggle'),
    path('admin/content/contact/',         content.contact,        name='admin_content_contact'),
    path('admin/content/contact/update/',  content.update_contact, name='admin_content_contact_update'),
    path('admin/content/banners/',         content.banners,         name='admin_content_banners'),
    path('admin/content/banners/update/',  content.update_banners,  name='admin_content_banners_update'),
    path('admin/content/registration-cards/',        content.registration_cards,        name='admin_content_registration_cards'),
    path('admin/content/registration-cards/update/', content.update_registration_cards, name='admin_content_registration_cards_update'),
    path('admin/content/plans/',           content.plans,           name='admin_content_plans'),
    path('admin/content/plans/update/',    content.update_plans,    name='admin_content_plans_update'),
    path('admin/content/plans/exclusive/update/', content.update_exclusive_config, name='admin_content_exclusive_plans_update'),
    path('admin/content/plans/update-features/', content.update_plan_features, name='admin_content_plans_update_features'),
    path('admin/content/plans/update-unlock-rules/', content.update_feature_unlock_rules, name='admin_content_plans_update_unlock_rules'),
    path('admin/content/plans/update-qr-service/', content.update_qr_service, name='admin_content_plans_update_qr_service'),
    path('admin/content/plans/update-review-growth/', content.update_review_growth, name='admin_content_plans_update_review_growth'),
    path('admin/content/plans/manage-agent/<str:plan_slug>/', content.manage_agent_preview, name='admin_content_plans_manage_agent'),
    path('admin/content/plans/manage-agent/<str:plan_slug>/toggle/', content.manage_agent_toggle, name='admin_content_plans_manage_agent_toggle'),
]
