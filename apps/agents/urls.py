from django.urls import path
from .views import registration, auth, dashboard, gbp as gbp_views, bio_generator, career_timeline as career_timeline_views

app_name = 'agents'

urlpatterns = [
    path('agent-registration/', registration.agent_registration, name='agent_registration'),
    path('agent-send-otp/',     registration.send_otp,           name='agent_send_otp'),
    path('agent-verify-otp/',   registration.verify_otp,         name='agent_verify_otp'),
    path('agent-register-step1/', registration.register_step1,   name='agent_register_step1'),
    path('agent-register-step2/', registration.register_step2,   name='agent_register_step2'),
    path('chooseplan/',         registration.chooseplan,         name='chooseplan'),
    path('agent-register-complete/', registration.agent_register_complete, name='agent_register_complete'),
    path('payment-success/',    registration.payment_success,    name='payment_success'),
    path('payment-failure/',    registration.payment_failure,    name='payment_failure'),
    path('agent-registration/success/', registration.agent_register_success, name='agent_register_success'),
    path('agent-registration/failed/', registration.agent_register_failed, name='agent_register_failed'),
    path('test-real-webhook/',          registration.test_real_webhook,          name='test_real_webhook'),
    path('razorpay-webhook/',   registration.razorpay_webhook,   name='razorpay_webhook'),
    path('agent/verify-promo/', registration.agent_verify_promo, name='agent_verify_promo'),
    path('agent-login/',        auth.agent_login,                name='agent_login'),
    path('forgot-password/',    auth.forgot_password,            name='forgot_password'),
    path('reset-password/<str:uidb64>/<str:token>/', auth.reset_password, name='reset_password'),
    path('agent-logout/',       auth.agent_logout,               name='agent_logout'),
    path('logout/',             auth.logout_view,                name='logout'),
    path('agent/dashboard/',    dashboard.agent_dashboard,       name='agent_dashboard'),
    path('agent/referral/',     dashboard.referral,              name='agent_referral'),
    path('profile/<str:slug>/', dashboard.agent_public_profile,  name='agent_public_profile'),
    path('profile/<str:slug>/review/', dashboard.store_review,   name='agent_store_review'),
    path('agent/edit-profile/', dashboard.edit_profile,         name='agent_edit_profile'),
    path('agent/update-profile/', dashboard.update_profile,     name='agent_update_profile'),
    path('agent/push-token/',   dashboard.agent_push_token,      name='agent_push_token'),
    path('agent/upgrade-plan/', dashboard.agent_upgrade_plan,    name='agent_upgrade_plan'),
    path('agent/referral-info/', dashboard.referral_info,        name='agent_referral_info'),
    path('join/ad/', registration.fb_ad_signup, name='fb_ad_signup'),
    path('join/<str:ref_code>/', registration.referral_join,     name='referral_join'),
    path('auth/google/', auth.redirectToGoogle,                  name='google_auth'),
    path('auth/google/callback/', auth.handleGoogleCallback,    name='google_auth_callback'),
    path('auth/google/get-session-data/', auth.getGoogleSessionData, name='google_auth_get_session_data'),
    path('auth/google/user-data/', auth.getGoogleUserData,      name='google_auth_user_data'),
    path('auth/google/clear-session/', auth.clearGoogleSession,  name='google_auth_clear_session'),
    path('agent/leads/capture/', dashboard.agent_capture_lead,   name='agent_leads_capture'),
    path('agent/leads/update-status/', dashboard.update_lead_status, name='update_lead_status'),
    path('client/quick-register/', registration.client_quick_register, name='client_quick_register'),
    path('og-image/<int:agent_id>/preview.jpg', dashboard.agent_og_image, name='agent_og_image'),

    # ── Google Business Profile OAuth & API ──────────────────────────────────
    path('agent/gbp/auth/',     gbp_views.agent_gbp_auth,     name='agent_gbp_auth'),
    path('agent/gbp/callback/', gbp_views.agent_gbp_callback, name='agent_gbp_callback'),
    path('agent/gbp/status/',   gbp_views.agent_gbp_status,   name='agent_gbp_status'),
    path('agent/gbp/save-url/', gbp_views.agent_gbp_save_url, name='agent_gbp_save_url'),

    # ── AI Bio Generator ─────────────────────────────────────────────────────
    path('agent/generate-bio/', bio_generator.generate_professional_bio, name='agent_generate_bio'),

    # ── Career Timeline API (read-only) ──────────────────────────────────────
    path('agent/career-timeline/suggestions/', career_timeline_views.career_timeline_suggestions, name='agent_career_timeline_suggestions'),

    # ── Catch-all public agent profile share route ────────────────────────────
    path('agent/<str:slug>/',   dashboard.agent_public_share_profile, name='agent_public_share_profile'),
]

