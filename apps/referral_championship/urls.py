from django.urls import path
from apps.referral_championship.views import landing, agent_dashboard

app_name = 'championship'

urlpatterns = [
    # Public invitation landing
    path('', landing.referral_landing_page, {'ref_id': 'general'}, name='public_root'),
    path('join/<str:ref_id>/', landing.referral_landing_page, name='public_landing'),
    path('invite/<str:ref_id>/', landing.referral_landing_page, name='public_invite'),
    path('<str:ref_id>/', landing.referral_landing_page, name='public_slug'),

    # AJAX Gamification endpoints
    path('ajax/social-follow/', landing.record_social_follow_ajax, name='ajax_social_follow'),
    path('ajax/scratch-reveal/', landing.record_scratch_reveal_ajax, name='ajax_scratch_reveal'),
    path('ajax/track-google-review/', landing.track_google_review_ajax, name='ajax_track_google_review'),

    # Agent Dashboard
    path('agent/dashboard/', agent_dashboard.agent_championship_dashboard, name='agent_dashboard'),
    path('agent/claim/<int:slab_id>/', agent_dashboard.claim_reward_ajax, name='agent_claim_reward'),
    path('agent/qr-download/', agent_dashboard.download_qr_code, name='agent_qr_download'),
]
