"""Audit 2026-10-01 F-10 (mobile): the app plans list must show what the
website upgrade checkout charges (same prices, trial-only discount, rounding)."""
import json
from datetime import datetime, timedelta

from django.test import SimpleTestCase


class MobilePlanPricingMatchesWebsiteTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        import fastapi_app.models  # noqa: F401  (register every table)
        from fastapi_app.database import Base

        engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=engine)
        cls.Session = sessionmaker(bind=engine)

    def setUp(self):
        from fastapi_app.models.site_setting import SiteSetting
        from fastapi_app.models.subscription_plan import SubscriptionPlan
        self.db = self.Session()
        for model in (SiteSetting, SubscriptionPlan):
            self.db.query(model).delete()
        self.db.add_all([
            SubscriptionPlan(name='Starter', slug='starter', sort_order=1, actual_price=2360.0,
                             discounted_price=799.0, is_active=True),
            SubscriptionPlan(name='Professional', slug='professional', sort_order=2, actual_price=9900.0,
                             discounted_price=1499.0, is_active=True),
            SiteSetting(key='pricing_config', group='pricing', value=json.dumps({
                'starter': {'full_price': 2359}, 'professional': {'full_price': 8258}})),
            SiteSetting(key='trial_upgrade_discount', group='pricing', value='20'),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _pro_price(self, **agent_fields):
        from fastapi_app.models.agent import Agent
        from fastapi_app.services.plan_service import PlanService
        agent = Agent(id=1, fullname='A', email='a@example.com', mobile='9000000061', agent_pincode='380001',
                      status='active', upgrade_discount_percent=0, **agent_fields)
        plans = PlanService(self.db).get_plans_list(agent).plans
        pro = next(p for p in plans if p.slug == 'professional')
        return pro.pricing

    def test_paid_starter_agent_sees_the_full_website_price(self):
        pricing = self._pro_price(plan_type='starter')
        self.assertEqual((pricing.final_price_inclusive_gst, pricing.agent_discount_pct), (8258.0, 0))

    def test_trial_agent_sees_the_website_trial_discount(self):
        pricing = self._pro_price(plan_type='free_trial', trial_ends_at=datetime.now() + timedelta(days=5))
        self.assertEqual((pricing.final_price_inclusive_gst, pricing.agent_discount_pct), (6606.0, 20))

    def test_pro_one_rupee_reward_still_shows(self):
        pricing = self._pro_price(plan_type='starter', referral_reward_type='pro_plan_1rs')
        self.assertEqual(pricing.final_price_inclusive_gst, 1.0)
