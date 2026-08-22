from django.test import SimpleTestCase

from apps.agents.services.feature_unlock import (
    OverlayPlan,
    evaluate_unlock_rules,
    needs_activity_eval_for_directory,
    overlay_plan,
    sanitize_unlock_rules,
)
from apps.agents.views.dashboard import PlanFeatureProxy, _resolve_agent_plan


CERT_RULE = {
    'id': 'r1',
    'enabled': True,
    'feature': 'edit_profile_certifications',
    'plans': ['starter'],
    'match': 'all',
    'conditions': [
        {'metric': 'reviews', 'op': 'gte', 'value': 10},
        {'metric': 'referrals', 'op': 'gte', 'value': 5},
    ],
}


class FakePlan:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FeatureUnlockEvaluatorTests(SimpleTestCase):
    def test_and_passes_when_all_metrics_met(self):
        extra = evaluate_unlock_rules(
            agent=None,
            plan_slug='starter',
            metrics={'reviews': 10, 'referrals': 5},
            rules=[CERT_RULE],
        )
        self.assertIn('show_agent_certificate', extra)

    def test_and_fails_when_one_metric_is_short(self):
        extra = evaluate_unlock_rules(
            agent=None,
            plan_slug='starter',
            metrics={'reviews': 10, 'referrals': 2},
            rules=[CERT_RULE],
        )
        self.assertEqual(extra, set())

    def test_or_passes_if_any_condition_passes(self):
        rule = dict(CERT_RULE, match='any')
        extra = evaluate_unlock_rules(
            agent=None,
            plan_slug='starter',
            metrics={'reviews': 10, 'referrals': 0},
            rules=[rule],
        )
        self.assertIn('show_agent_certificate', extra)

    def test_rule_ignored_when_plan_slug_not_in_plans(self):
        extra = evaluate_unlock_rules(
            agent=None,
            plan_slug='professional',
            metrics={'reviews': 50, 'referrals': 50},
            rules=[CERT_RULE],
        )
        self.assertEqual(extra, set())

    def test_disabled_rule_ignored(self):
        rule = dict(CERT_RULE, enabled=False)
        extra = evaluate_unlock_rules(
            agent=None,
            plan_slug='starter',
            metrics={'reviews': 50, 'referrals': 50},
            rules=[rule],
        )
        self.assertEqual(extra, set())

    def test_empty_rules_unlock_nothing(self):
        extra = evaluate_unlock_rules(
            agent=None,
            plan_slug='starter',
            metrics={'reviews': 50},
            rules=[],
        )
        self.assertEqual(extra, set())


class OverlayPlanTests(SimpleTestCase):
    def test_overlay_adds_feature_without_removing_plan_features(self):
        base = FakePlan(show_agent_certificate=False, show_performance_stats=True)
        wrapped = overlay_plan(base, {'show_agent_certificate'})
        self.assertTrue(wrapped.show_agent_certificate)
        self.assertTrue(wrapped.show_performance_stats)

    def test_plan_checkbox_feature_stays_on_when_metrics_fail(self):
        base = PlanFeatureProxy(['edit_profile_certifications', 'dashboard_stats'])
        extra = evaluate_unlock_rules(
            agent=None,
            plan_slug='starter',
            metrics={'reviews': 1, 'referrals': 0},
            rules=[CERT_RULE],
        )
        wrapped = overlay_plan(base, extra)
        self.assertTrue(wrapped.show_agent_certificate)
        self.assertTrue(wrapped.show_performance_stats)
        self.assertFalse(wrapped.show_career_timeline)

    def test_overlay_does_not_override_none_fail_open(self):
        self.assertIsNone(overlay_plan(None, {'show_agent_certificate'}))
        self.assertIsNone(_resolve_agent_plan('', agent=object()))
        self.assertIsNone(_resolve_agent_plan(None))

    def test_overlay_skipped_when_no_extras(self):
        base = FakePlan(show_portfolio=False)
        self.assertIs(overlay_plan(base, set()), base)

    def test_overlay_plan_is_truthy(self):
        wrapped = OverlayPlan(FakePlan(show_portfolio=False), {'show_portfolio'})
        self.assertTrue(bool(wrapped))


class DirectoryShortCircuitTests(SimpleTestCase):
    def test_skip_when_already_listed(self):
        base = FakePlan(is_listed_in_directory=True)
        self.assertFalse(needs_activity_eval_for_directory(
            base, 'starter',
            rules=[{
                'enabled': True,
                'feature': 'agent_directory_visibility',
                'plans': ['starter'],
                'match': 'all',
                'conditions': [{'metric': 'reviews', 'op': 'gte', 'value': 1}],
            }],
        ))

    def test_skip_when_no_directory_rule(self):
        base = FakePlan(is_listed_in_directory=False)
        self.assertFalse(needs_activity_eval_for_directory(
            base, 'starter', rules=[CERT_RULE]
        ))

    def test_evaluate_when_locked_and_directory_rule_exists(self):
        base = FakePlan(is_listed_in_directory=False)
        self.assertTrue(needs_activity_eval_for_directory(
            base, 'starter',
            rules=[{
                'enabled': True,
                'feature': 'agent_directory_visibility',
                'plans': ['starter'],
                'match': 'all',
                'conditions': [{'metric': 'reviews', 'op': 'gte', 'value': 1}],
            }],
        ))

    def test_skip_when_base_plan_is_none(self):
        self.assertFalse(needs_activity_eval_for_directory(None, 'starter', rules=[CERT_RULE]))


class SanitizeUnlockRulesTests(SimpleTestCase):
    def test_drops_unknown_metrics_and_empty_rules(self):
        cleaned = sanitize_unlock_rules([
            {
                'feature': 'edit_profile_certifications',
                'plans': ['starter'],
                'match': 'all',
                'enabled': True,
                'conditions': [
                    {'metric': 'not_a_real_metric', 'op': 'gte', 'value': 1},
                ],
            },
            {
                'feature': 'edit_profile_certifications',
                'plans': ['nope'],
                'conditions': [{'metric': 'reviews', 'op': 'gte', 'value': 10}],
            },
        ])
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]['plans'], ['free_trial', 'starter', 'professional', 'exclusive'])
        self.assertEqual(cleaned[0]['conditions'][0]['value'], 10.0)
