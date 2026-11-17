"""Admin panel module registry: the one place that declares admin modules and route access.

Adding an admin module:
  1. add an AdminModule to MODULES (permission key, label shown in the staff editor,
     route a staff member with only this permission lands on);
  2. add each of its url names to ROUTE_PERMISSIONS (a route missing here is Super Admin only);
  3. regenerate the RBAC snapshot (see CLAUDE.md, Testing) and review the diff.

Used by: AdminPermissionMiddleware (access + landing route) and the admin editor
(permission checkboxes). The sidebar (templates/admin/base.html) still checks keys by hand.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AdminModule:
    key: str
    label: str
    default_route: str | None  # None: grants no admin page to land on
    children: tuple = ()  # narrower sub-permissions: AdminModule(...) entries


MODULES = (
    AdminModule("dashboard", "Dashboard View", "admin_dashboard"),
    AdminModule("agents", "Active Agents", "admin_agents"),
    AdminModule(
        "approvals",
        "Pending Approvals",
        "admin_agents_approvals",
        children=(
            AdminModule(
                "approvals_awaiting_verification",
                "Awaiting Verification Only",
                "admin_agents_approvals",
            ),
            AdminModule(
                "approvals_missing_licenses",
                "Missing IRDAI Licenses Only",
                "admin_agents_approvals",
            ),
        ),
    ),
    AdminModule("blacklisted_agents", "Blacklisted Agents", "admin_blacklisted_agents"),
    AdminModule(
        "pending_registrations",
        "Registration Pending",
        "admin_agents_pending_registrations",
    ),
    AdminModule("distributors", "Distributors", "admin_distributors"),
    AdminModule("insurance", "Insurance Companies", "admin_insurance_index"),
    AdminModule(
        "insurance_approvals",
        "Insurance Onboarding Approvals",
        "admin_insurance_approvals_index",
    ),
    AdminModule("users", "Clients / Users Registry", "admin_users"),
    AdminModule("events", "Event Management", "admin_events_index"),
    AdminModule("subscriptions", "Renewal Tracker", "admin_subscriptions_index"),
    AdminModule("leads", "Agent Leads", "admin_leads_index"),
    AdminModule("contacts", "Contact Inbox", "admin_contacts_index"),
    AdminModule("reviews", "Review Moderation", "admin_reviews_index"),
    AdminModule("notifications", "Push Notifications", "agent_notify"),
    AdminModule("content", "Content Control", "admin_content_about"),
    AdminModule("revenue", "Revenue Tracking", "admin_revenue"),
    AdminModule("invoices", "Invoices", "admin_invoices"),
    AdminModule("promo_codes", "Promo Codes", "admin_promo_codes"),
    AdminModule("free_trial", "Free Trial Manager", "admin_free_trial"),
    AdminModule("referrals", "Referral System", "admin_referrals_index"),
    AdminModule("finance_accounts", "Finance Accounts", "admin_finance_index"),
    AdminModule("export", "Export Manager", "export_index"),
    AdminModule("qr_generator", "QR Generator", "admin_qr_files_index"),
    AdminModule("geocoding", "Geocoding Manager", "admin_geocoding_index"),
    AdminModule("pincode", "Pincode Database Manager", "admin_pincode_index"),
    AdminModule(
        "analytics",
        "Analytics, Activity Logs & Threat Intelligence",
        "advanced_analytics",
    ),
    AdminModule("error_logs", "Error Logs", "admin_error_logs_index"),
    AdminModule("feature_flags", "Feature Flags Control Center", "admin_feature_flags"),
    AdminModule(
        "site_settings", "Site Settings, SEO & Security Rules", "admin_settings_general"
    ),
    AdminModule("email_templates", "Email & PDF Templates", "admin_settings_templates"),
    AdminModule("server_health", "Server Health", "admin_system_health"),
    AdminModule("logs", "Logs", "admin_system_logs"),
    AdminModule("api_logs", "API Logs", "admin_system_api_logs"),
    AdminModule("backups", "Backups", "admin_system_backups"),
    AdminModule("sessions", "Session & Device Management", "admin_sessions_index"),
    AdminModule("app_version", "App Version Control", "admin_app_version"),
    # Sidebar link to /api/docs only; no admin page, so no landing route (it used to point at the
    # dashboard, which needs 'dashboard' -> endless redirect for staff holding only this key).
    AdminModule("fastapi_services", "FastAPI Services", None),
)

# url_name -> permission key, or a tuple of keys (any one is enough). Exact names only.
# Not listed (Super Admin only): auth routes are public; admin_admins_* and delete/destroy
# routes are blocked for staff by separate rules in middleware/rbac.py.
ROUTE_PERMISSIONS = {
    # ── Dashboard ─────────────────────────────────────────────────
    "admin_dashboard": "dashboard",
    # ── Agents ────────────────────────────────────────────────────
    "admin_agents": "agents",
    "admin_agents_manage": "agents",
    "admin_agents_manage_alt": "agents",
    # Approvals staff approve/reject from the queue; the view limits them
    # to agents awaiting approval.
    "admin_agents_toggle_status": ("agents", "approvals"),
    "admin_agents_toggle_account": "agents",
    "admin_agents_update_badge": "agents",
    "admin_agents_update_irdai_license": "agents",
    "admin_agents_save_notes": "agents",
    "admin_agents_bulk_action": ("agents", "approvals"),
    "admin_agents_delete": "agents",
    "admin_agents_irdai_verify": "agents",
    "admin_agents_amfi_verify": "agents",
    "admin_agents_update_visibility": "agents",
    "admin_agents_update_achievement_limit": "agents",
    "admin_agents_update_plan": "agents",
    "admin_agents_toggle_review_approval": "agents",
    "admin_agents_update_profile": "agents",
    "admin_agents_get_agent_json": "agents",
    "admin_agents_get_edit_logs": "agents",
    "admin_agents_edit_profile": "agents",
    "admin_agents_full_update_profile": "agents",
    "admin_agents_verify_pending_payment": "agents",
    # ── Approvals / Pending / Blacklist ───────────────────────────
    "admin_agents_approvals": "approvals",
    "admin_agents_pending_registrations": "pending_registrations",
    "admin_agents_pending": "pending_registrations",
    "admin_blacklisted_agents": "blacklisted_agents",
    "ajax_blacklist_approve": "approvals",
    "ajax_blacklist_confirm": "approvals",
    "ajax_blacklist_remove": "approvals",
    # ── Distributors ──────────────────────────────────────────────
    "admin_distributors": "distributors",
    "admin_distributors_create": "distributors",
    "admin_distributors_store": "distributors",
    "admin_distributor_toggle_status": "distributors",
    "admin_distributor_reset_password": "distributors",
    "admin_subdistributor_reset_password": "distributors",
    "admin_distributor_detail": "distributors",
    # ── Insurance Companies ───────────────────────────────────────
    "admin_insurance_index": "insurance",
    "admin_insurance_create": "insurance",
    "admin_insurance_store": "insurance",
    "admin_insurance_show": "insurance",
    "admin_insurance_toggle_status": "insurance",
    # ── Insurance Approvals ───────────────────────────────────────
    "admin_insurance_approvals_index": "insurance_approvals",
    "admin_insurance_approvals_process": "insurance_approvals",
    "admin_insurance_approvals_approve_onboarding": "insurance_approvals",
    "admin_insurance_approvals_reject_onboarding": "insurance_approvals",
    # ── Clients / Users ───────────────────────────────────────────
    "admin_users": "users",
    "admin_users_edit": "users",
    "admin_users_update": "users",
    # ── Events ────────────────────────────────────────────────────
    "admin_events_index": "events",
    "admin_events_show": "events",
    "admin_events_export": "events",
    # ── Subscriptions ─────────────────────────────────────────────
    "admin_subscriptions_index": "subscriptions",
    "admin_delete_subscription": "subscriptions",
    "admin_plans_index": "subscriptions",
    "admin_plan_create": "subscriptions",
    "admin_plan_edit": "subscriptions",
    "admin_plan_delete": "subscriptions",
    # ── Leads ─────────────────────────────────────────────────────
    "admin_leads_index": "leads",
    "admin_leads_update_status": "leads",
    "admin_quick_registration_leads": "leads",
    "admin_quick_registration_lead_delete": "leads",
    "admin_quick_registration_leads_export_csv": "leads",
    "admin_quick_registration_leads_export_xlsx": "leads",
    # ── Contacts ──────────────────────────────────────────────────
    "admin_contacts_index": "contacts",
    "admin_contacts_show": "contacts",
    "admin_contacts_update_status": "contacts",
    "admin_contacts_delete": "contacts",
    "admin_contacts_assign": "contacts",
    "admin_contacts_set_priority": "contacts",
    "admin_contacts_reply": "contacts",
    # ── Reviews ───────────────────────────────────────────────────
    "admin_reviews_index": "reviews",
    "admin_reviews_toggle_approval": "reviews",
    "admin_reviews_bulk_approve": "reviews",
    "admin_reviews_delete": "reviews",
    # ── Notifications / Broadcast ─────────────────────────────────
    "agent_notify": "notifications",
    "agent_notify_send": "notifications",
    "agent_notify_broadcast": "notifications",
    "broadcast_index": "notifications",
    "broadcast_send": "notifications",
    # ── Content & CMS (incl. homepage + hero editors) ─────────────
    # Note: admin_settings_homepage* and admin_settings_hero_section*
    # map to 'content' (sidebar: Content Control), NOT 'site_settings'.
    "admin_content_about": "content",
    # Visiting Card Studio (sidebar: Content Control)
    "admin_digital_card_studio": "content",
    "admin_digital_card_studio_direct": "content",
    "admin_digital_card_studio_update": "content",
    "admin_digital_card_agent_toggle": "content",
    "admin_digital_card_agent_detail": "content",
    "admin_digital_card_agent_save": "content",
    "admin_content_about_update": "content",
    "admin_content_faqs": "content",
    "admin_content_faqs_settings_update": "content",
    "admin_content_faqs_store": "content",
    "admin_content_faqs_update": "content",
    "admin_content_faqs_toggle": "content",
    "admin_content_calculators": "content",
    "admin_content_calculators_edit": "content",
    "admin_content_calculators_toggle": "content",
    "admin_content_calculators_category": "content",
    "admin_content_calculator_categories_save": "content",
    "admin_content_calculator_categories_toggle": "content",
    "admin_content_calculator_categories_delete": "content",
    "admin_content_contact": "content",
    "admin_content_contact_update": "content",
    "admin_content_banners": "content",
    "admin_content_banners_update": "content",
    "admin_profile_banners_index": ("content", "agents"),
    "admin_profile_banner_upload": ("content", "agents"),
    "admin_profile_banner_toggle": ("content", "agents"),
    "admin_profile_banner_delete": ("content", "agents"),
    "admin_profile_banner_settings_save": ("content", "agents"),
    "admin_content_registration_cards": "content",
    "admin_content_registration_cards_update": "content",
    "admin_content_plans": "content",
    "admin_content_plans_update": "content",
    "admin_content_plans_update_features": "content",
    "admin_content_exclusive_plans_update": "content",
    "admin_content_plans_update_unlock_rules": "content",
    "admin_content_plans_update_qr_service": "content",
    "admin_content_plans_update_review_growth": "content",
    "admin_content_plans_manage_agent": "content",
    "admin_content_plans_manage_agent_toggle": "content",
    "admin_settings_homepage": "content",
    "admin_settings_homepage_update": "content",
    "admin_settings_hero_section": "content",
    "admin_settings_hero_section_update": "content",
    "admin_pages_index": "content",
    "admin_pages_create": "content",
    "admin_pages_store": "content",
    "admin_pages_edit": "content",
    "admin_pages_update": "content",
    "admin_pages_delete": "content",
    "admin_coming_soon_index": "content",
    "admin_coming_soon_save": "content",
    "admin_coming_soon_feature_save": "content",
    "admin_coming_soon_feature_toggle": "content",
    "admin_coming_soon_feature_delete": "content",
    "admin_coming_soon_feature_reorder": "content",
    "admin_coming_soon_feature_seed": "content",
    "admin_google_review_config_save": "content",
    "admin_google_review_toggle": "content",
    # ── Revenue ───────────────────────────────────────────────────
    "admin_revenue": "revenue",
    "admin_search": "dashboard",
    # ── Invoices ──────────────────────────────────────────────────
    "admin_invoices": "invoices",
    # Previously missing from the map (staff locked out); opened 2026-11-07.
    "admin_invoice_sync_single": "invoices",
    "admin_pincode_heatmap": "pincode",
    "admin_pincode_heatmap_lookup": "pincode",
    "admin_toggle_heatmap_flag": "pincode",
    "admin_content_invite_studio": "content",
    "admin_content_invite_studio_update": "content",
    "admin_settings_banner_popup": "site_settings",
    "admin_save_banner_settings": "site_settings",
    "admin_save_popup_settings": "site_settings",
    "admin_toggle_banner_popup": "site_settings",
    "admin_deletion_requests": "blacklisted_agents",
    "admin_activate_account": "blacklisted_agents",
    "admin_terminate_account": "blacklisted_agents",
    "admin_reject_deletion_request": "blacklisted_agents",
    "admin_invoices_create": "invoices",
    "admin_invoices_verify_promo": "invoices",
    "admin_invoice_preview": "invoices",
    "admin_invoice_download": "invoices",
    "admin_invoice_save_sheet_url": "invoices",
    "admin_invoice_sync_sheet": "invoices",
    "admin_invoice_open_sheet": "invoices",
    # ── Promo Codes ───────────────────────────────────────────────
    "admin_promo_codes": "promo_codes",
    "admin_promo_code_store": "promo_codes",
    "admin_promo_code_update": "promo_codes",
    "admin_promo_code_toggle_status": "promo_codes",
    # ── Free Trial ────────────────────────────────────────────────
    "admin_free_trial": "free_trial",
    "admin_ft_update_config": "free_trial",
    "admin_ft_update_discount": "free_trial",
    "admin_ft_update_referral_config": "free_trial",
    "admin_ft_force_test_credit": "free_trial",
    "admin_ft_generate_promo": "free_trial",
    "admin_ft_update_promo": "free_trial",
    "admin_ft_toggle_promo": "free_trial",
    "admin_ft_delete_promo": "free_trial",
    "admin_ft_history": "free_trial",
    "admin_ft_analytics_data": "free_trial",
    # ── Referrals ─────────────────────────────────────────────────
    "admin_referrals_index": "referrals",
    "admin_referrals_toggle_code": "referrals",
    "admin_referrals_mark_claimed": "referrals",
    "admin_referrals_generate_missing": "referrals",
    "admin_referrals_update_tiers": "referrals",
    # ── Finance & Accounts ────────────────────────────────────────
    "admin_finance_index": "finance_accounts",
    "admin_finance_mark_payment": "finance_accounts",
    # ── Export Center ─────────────────────────────────────────────
    "export_index": "export",
    "export_agents": "export",
    "export_leads": "export",
    "export_contacts": "export",
    "export_subscriptions": "export",
    "export_reviews": "export",
    "export_pending": "export",
    # ── QR Generator ──────────────────────────────────────────────
    "admin_qr_files_index": "qr_generator",
    "admin_qr_files_store": "qr_generator",
    "admin_qr_files_update": "qr_generator",
    "admin_qr_files_delete": "qr_generator",
    # ── Geocoding ─────────────────────────────────────────────────
    "admin_geocoding_index": "geocoding",
    "admin_geocoding_single": "geocoding",
    "admin_geocoding_batch": "geocoding",
    "admin_geocoding_stats": "geocoding",
    # ── Pincode ───────────────────────────────────────────────────
    "admin_pincode_index": "pincode",
    "admin_pincode_upload": "pincode",
    "admin_pincode_import": "pincode",
    "admin_pincode_districts": "pincode",
    "admin_pincode_sample": "pincode",
    "admin_pincode_export": "pincode",
    "admin_pincode_delete_state": "pincode",
    # ── Find Agent Locator (Pincode & Lat/Lng) ────────────────────
    "admin_find_agent_locator": ("pincode", "geocoding", "agents"),
    "admin_find_agent_locator_extract": ("pincode", "geocoding", "agents"),
    "admin_find_agent_locator_save_pincode": ("pincode", "geocoding", "agents"),
    "admin_find_agent_locator_search_agents": (
        "pincode",
        "geocoding",
        "agents",
    ),
    "admin_find_agent_locator_assign_agent": ("pincode", "geocoding", "agents"),
    "admin_find_agent_locator_create_agent": ("pincode", "geocoding", "agents"),
    "admin_find_agent_locator_live_preview": ("pincode", "geocoding", "agents"),
    "admin_find_agent_locator_unlink_agent": ("pincode", "geocoding", "agents"),
    # ── Analytics / Advanced / Error Logs / Threats ───────────────
    "advanced_analytics": "analytics",
    "advanced_activity_logs": "analytics",
    "advanced_activity_logs_delete": "analytics",
    "admin_error_logs_index": "error_logs",
    "admin_error_logs_show": "error_logs",
    "admin_error_logs_delete": "error_logs",
    # ── Feature Flags (sidebar shows them for either permission) ──
    "admin_feature_flags": ("feature_flags", "site_settings"),
    "admin_feature_flag_toggle": ("feature_flags", "site_settings"),
    "admin_feature_flag_create": ("feature_flags", "site_settings"),
    "admin_feature_flag_update": ("feature_flags", "site_settings"),
    "admin_feature_flag_delete": ("feature_flags", "site_settings"),
    # ── Agent Card Themes ─────────────────────────────────────────
    "admin_agent_card_themes": ("content", "site_settings"),
    "admin_agent_card_theme_save": ("content", "site_settings"),
    "admin_agent_card_theme_activate": ("content", "site_settings"),
    "admin_agent_card_theme_delete": ("content", "site_settings"),
    "admin_agent_card_theme_preset": ("content", "site_settings"),
    "admin_agent_card_theme_import": ("content", "site_settings"),
    "admin_agent_card_theme_export": ("content", "site_settings"),
    "admin_agent_card_theme_flag": ("feature_flags", "site_settings"),
    "admin_agent_card_theme_preview": ("content", "site_settings"),
    "security_threat_logs": "analytics",
    "security_threat_logs_delete": "analytics",
    # ── Investment Types ──────────────────────────────────────────
    "admin_investment_types_index": "content",
    "admin_investment_types_store": "content",
    "admin_investment_types_update": "content",
    "admin_investment_types_delete": "content",
    "admin_investment_types_toggle": "content",
    # ── Site Settings / Security (blocked IPs) ────────────────────
    "admin_settings_general": "site_settings",
    "admin_settings_seo": "site_settings",
    "admin_link_og_save": "site_settings",
    "admin_link_og_delete": "site_settings",
    "admin_link_og_toggle": "site_settings",
    "admin_settings_security": "site_settings",
    "admin_settings_templates": "email_templates",
    # admin_settings_templates_update is deliberately absent: writing Django
    # template source to disk is Super Admin only (deny-by-default for staff).
    "admin_settings_update": "site_settings",
    "security_blocked_ips": "site_settings",
    "security_block_ip": "site_settings",
    "security_unblock_ip": "site_settings",
    # ── System ────────────────────────────────────────────────────
    "admin_system_health": "server_health",
    "admin_system_logs": "logs",
    "admin_system_api_logs": "api_logs",
    "admin_system_backups": "backups",
    "admin_system_run_backup": "backups",
    "admin_system_download_backup": "backups",
    "admin_system_clear_cache": "server_health",
    "admin_system_recovery_action": "server_health",
    # ── Session & Device Management (module #15) ──────────────────
    "admin_sessions_index": "sessions",
    "admin_sessions_revoke": "sessions",
    # ── App Version Control (module #16) ──────────────────────────
    "admin_app_version": "app_version",
    "admin_app_version_save": "app_version",
}


def iter_modules():
    """Every module and sub-permission, parents before their children, in editor order."""
    for module in MODULES:
        yield module
        yield from module.children


def permission_choices():
    """Shape used by the admin editor template: [{'key', 'label', 'children': [...]}]."""
    choices = []
    for m in MODULES:
        item = {"key": m.key, "label": m.label}
        if m.children:
            item["children"] = [{"key": c.key, "label": c.label} for c in m.children]
        choices.append(item)
    return choices


def required_permission(url_name):
    return ROUTE_PERMISSIONS.get(url_name) if url_name else None


def landing_route(permissions):
    """First route (in module order) a staff member with these permission keys may open."""
    granted = set(permissions or [])
    for module in iter_modules():
        if module.key in granted and module.default_route:
            return module.default_route
    return None


class _Everything:
    """nav_open for Super Admins: every route is open."""

    def __contains__(self, item):
        return True


EVERYTHING = _Everything()


def open_route_names(permissions, is_super):
    """Url names this admin may open, for the sidebar (same rule as AdminPermissionMiddleware)."""
    if is_super:
        return EVERYTHING
    granted = set(permissions or [])

    def has(perm):
        if perm == "approvals":
            return bool(
                granted
                & {"approvals_awaiting_verification", "approvals_missing_licenses"}
            )
        return perm in granted

    names = set()
    for name, perm in ROUTE_PERMISSIONS.items():
        perms = perm if isinstance(perm, tuple) else (perm,)
        if any(has(p) for p in perms):
            names.add(name)
    return names
