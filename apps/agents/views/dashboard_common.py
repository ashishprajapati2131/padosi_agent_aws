"""Shared helpers for the agent dashboard view modules (split out of dashboard.py):
plan resolution (PlanFeatureProxy, _resolve_agent_plan) and the dashboard logger."""

import logging
from apps.agents.services.feature_unlock import (
    EDIT_PROFILE_CHILD_FEATURES,
    FEATURE_ATTR_MAP,
    evaluate_unlock_rules,
    filter_overlay_extras,
    normalize_plan_slug,
    overlay_plan,
    resolve_plan_entitlements,
)
from apps.home.models import SiteSetting

# Same logger name as before the split, so log records keep their "name".
logger = logging.getLogger("apps.agents.views.dashboard")


class PlanFeatureProxy:
    """
    Lightweight proxy that exposes .show_* attributes from plan_features_config
    (the Plans & Pricing admin checkbox grid).  Allows the dashboard template to
    use the same {{ agent_plan.show_X }} syntax regardless of which backend
    (SiteSetting JSON or SubscriptionPlan model) resolved the plan.

    Feature string → show_* attribute mapping:
      dashboard_stats       → show_performance_stats
      lead_management       → show_recent_leads
      sales_insights        → show_sales_insights
      rank_boost_tips       → show_rank_boost_tips
      view_public_profile   → show_view_public_profile_btn
      edit_profile          → show_edit_profile_full
      edit_profile_basic    → show_edit_profile_basic
      edit_profile_professional → show_edit_profile_professional
      edit_profile_portfolio    → show_edit_profile_portfolio
      edit_profile_additional   → show_edit_profile_additional
      manage_portfolio      → show_portfolio
      upload_achievements   → show_achievement
      view_reviews          → show_review_management
      public_profile        → show_profile_section
      agent_directory_visibility → is_listed_in_directory
      receive_leads         → show_new_business_leads
      lead_preferences      → show_lead_preferences
      lead_portfolio_analysis → show_lead_portfolio_analysis
      lead_claims_support   → show_lead_claims_support
      premium_support       → premium_priority_support
      visibility_aio        → show_visibility_aio
      visibility_geo        → show_visibility_geo
      visibility_seo        → show_visibility_seo
      visibility_priority_ranking → show_visibility_priority_ranking
    """

    # Maps feature slug → list of show_* attr names it enables
    FEATURE_MAP = FEATURE_ATTR_MAP

    def __init__(self, enabled_features):
        """
        enabled_features: list of feature slugs from plan_features_config,
        e.g. ['dashboard_stats', 'lead_management', 'sales_insights']
        """
        feats = set(enabled_features or [])
        # Legacy: edit_profile alone implied all four steps. Once steps are saved
        # explicitly, each step is independently lockable.
        if "edit_profile" in feats and not any(
            step in feats for step in EDIT_PROFILE_CHILD_FEATURES
        ):
            feats.update(EDIT_PROFILE_CHILD_FEATURES)
        self._enabled = set()
        for feat in feats:
            for attr in self.FEATURE_MAP.get(feat, []):
                self._enabled.add(attr)

    def __getattr__(self, name):
        # Any show_* attribute returns True only if it is in enabled set
        if name.startswith("show_") or name in (
            "is_listed_in_directory",
            "premium_priority_support",
        ):
            return name in self._enabled
        raise AttributeError(name)

    def __getitem__(self, name):
        return getattr(self, name)


def _resolve_base_agent_plan(plan_type):
    """
    Dual-system plan resolver (checkbox grid, then SubscriptionPlan).

    Lookup order:
      1a. normalize_plan_slug(plan_type) -> check SiteSettings
      1b. Numeric ID -> look up SubscriptionPlan by ID -> use its slug -> check SiteSettings
      1c. Unknown slug -> look up SubscriptionPlan by slug/name -> use its slug -> check SiteSettings
      2.  Fall back to SubscriptionPlan model booleans directly

    Returns None when nothing matches -> template shows all features (fail-safe).
    """
    if not plan_type:
        return None
    pt = str(plan_type).strip()
    if not pt:
        return None

    # -- Priority 1: plan_features_config (Plans & Pricing admin checkbox grid)
    try:
        from apps.home.models import SiteSetting

        features_config = SiteSetting.get_value("plan_features_config") or {}

        def _check_site_settings(slug_to_try):
            """Return PlanFeatureProxy for known plan slugs (canonical starter/pro rules)."""
            if not slug_to_try:
                return None
            canonical_slug = normalize_plan_slug(slug_to_try)
            if canonical_slug in ("starter", "professional", "exclusive", "free_trial"):
                enabled = resolve_plan_entitlements(canonical_slug, features_config)
                return PlanFeatureProxy(enabled)
            enabled = features_config.get(slug_to_try)
            if isinstance(enabled, list):
                return PlanFeatureProxy(
                    resolve_plan_entitlements(slug_to_try, features_config)
                )
            return None

        # 1a: Direct normalize -- handles 'starter', 'basic', 'standard', 'professional', etc.
        slug = normalize_plan_slug(pt)
        result = _check_site_settings(slug)
        if result is not None:
            return result

        # 1b: Numeric ID -- look up SubscriptionPlan by ID, use its slug for SiteSettings
        if pt.isdigit():
            try:
                from apps.agents.models import SubscriptionPlan as _SP

                plan_by_id = _SP.objects.filter(id=int(pt)).first()
                if plan_by_id and plan_by_id.slug:
                    result = _check_site_settings(plan_by_id.slug)
                    if result is not None:
                        return result
                    result = _check_site_settings(normalize_plan_slug(plan_by_id.slug))
                    if result is not None:
                        return result
            except Exception:
                pass

        # 1c: Unknown slug -- look up SubscriptionPlan by slug or name, use its slug for SiteSettings
        if not pt.isdigit() and slug not in features_config:
            try:
                from apps.agents.models import SubscriptionPlan as _SP

                plan_by_slug = _SP.objects.filter(slug=pt).first()
                if not plan_by_slug:
                    plan_by_slug = _SP.objects.filter(
                        name__icontains=pt, is_active=True
                    ).first()
                if plan_by_slug and plan_by_slug.slug:
                    result = _check_site_settings(plan_by_slug.slug)
                    if result is not None:
                        return result
                    result = _check_site_settings(
                        normalize_plan_slug(plan_by_slug.slug)
                    )
                    if result is not None:
                        return result
            except Exception:
                pass

    except Exception:
        pass

    # -- Priority 2: SubscriptionPlan model -----------------------------------
    try:
        from apps.agents.models import SubscriptionPlan

        # Tier 2a: numeric ID
        if pt.isdigit():
            plan = SubscriptionPlan.objects.filter(id=int(pt)).first()
            if plan:
                return plan
        # Tier 2b: exact name match
        plan = SubscriptionPlan.objects.filter(name__iexact=pt, is_active=True).first()
        if plan:
            return plan
        # Tier 2c: keyword-contains fallback
        SLUG_KEYWORDS = {
            "free_trial": ["free", "trial"],
            "starter": ["starter", "basic"],
            "basic": ["basic", "starter"],
            "professional": ["professional", "pro"],
            "standard": ["standard"],
            "exclusive": ["exclusive"],
        }
        keywords = SLUG_KEYWORDS.get(pt.lower(), [pt])
        for kw in keywords:
            plan = SubscriptionPlan.objects.filter(
                name__icontains=kw, is_active=True
            ).first()
            if plan:
                return plan
    except Exception:
        pass

    return None


def _resolve_agent_plan(plan_type, agent=None):
    """
    Resolve plan entitlements, then optionally overlay activity-unlock extras.

    Passing agent=None keeps the original plan-only behaviour (used by the
    Find Agents directory short-circuit). Unknown plans still return None
    (fail-open) and are never wrapped.
    """
    base = _resolve_base_agent_plan(plan_type)
    if base is None or agent is None:
        return base
    plan_slug = normalize_plan_slug(plan_type)
    features_config = SiteSetting.get_value("plan_features_config") or {}
    extra = set(evaluate_unlock_rules(agent, plan_slug))
    try:
        from apps.agents.services.review_growth import extra_unlock_attrs

        extra |= extra_unlock_attrs(agent)
    except Exception:
        logger.exception("Review-growth unlock overlay failed")
    extra = filter_overlay_extras(plan_slug, extra, features_config)
    return overlay_plan(base, extra)
