from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from apps.admin_panel.middleware import AdminPermissionMiddleware
from apps.admin_panel.views.content import (
    _sample_manage_agent_context,
    manage_agent_preview,
    manage_agent_toggle,
)
from apps.agents.views.dashboard import PlanFeatureProxy


class ManageAgentUrlTests(SimpleTestCase):
    def test_preview_url_resolves(self):
        match = resolve('/admin/content/plans/manage-agent/starter/')
        self.assertEqual(match.url_name, 'admin_content_plans_manage_agent')
        self.assertEqual(match.kwargs.get('plan_slug'), 'starter')

    def test_toggle_url_resolves(self):
        match = resolve('/admin/content/plans/manage-agent/starter/toggle/')
        self.assertEqual(match.url_name, 'admin_content_plans_manage_agent_toggle')

    def test_reverse_preview_url(self):
        self.assertEqual(
            reverse('admin_content_plans_manage_agent', kwargs={'plan_slug': 'professional'}),
            '/admin/content/plans/manage-agent/professional/',
        )

    def test_preview_and_toggle_require_content_permission(self):
        middleware = AdminPermissionMiddleware(lambda request: None)
        self.assertEqual(middleware.get_required_permission('admin_content_plans_manage_agent'), 'content')
        self.assertEqual(middleware.get_required_permission('admin_content_plans_manage_agent_toggle'), 'content')

    def test_preview_redirects_when_not_logged_in(self):
        request = RequestFactory().get('/admin/content/plans/manage-agent/starter/')
        response = manage_agent_preview(request, 'starter')
        self.assertEqual(response.status_code, 302)

    def test_toggle_forbidden_when_not_logged_in(self):
        request = RequestFactory().post(
            '/admin/content/plans/manage-agent/starter/toggle/',
            data='{}',
            content_type='application/json',
        )
        response = manage_agent_toggle(request, 'starter')
        self.assertEqual(response.status_code, 403)


def _preview_template_context(plan_slug='exclusive', tab='dashboard'):
    request = RequestFactory().get(f'/admin/content/plans/manage-agent/{plan_slug}/')
    request.user = SimpleNamespace(is_authenticated=False, role='')
    request.session = {}
    ctx = _sample_manage_agent_context(plan_slug)
    ctx.update({
        'request': request,
        'csrf_token': 'test',
        'admin_lock_preview': True,
        'preview_plan_slug': plan_slug,
        'preview_plan_label': 'Exclusive Plan',
        'preview_tab': tab,
        'agent_plan': PlanFeatureProxy(['dashboard_stats', 'edit_profile']),
        'feature_unlock_hints_json': '{}',
        'preview_enabled_features': ['dashboard_stats'],
        'preview_enabled_features_json': '["dashboard_stats"]',
        'preview_unlock_builder': {'metrics': {}, 'opLabels': {}, 'segments': []},
        'preview_unlock_builder_json': '{}',
        'preview_feature_labels_json': '{}',
        'show_calculators_nav': False,
        'footer_settings': {
            'site_logo': '',
            'site_name': 'PadosiAgent',
            'contact_email': 'a@b.c',
            'contact_phone': '',
            'contact_address': '',
            'social_links': {},
        },
        'default_canonical_url': '/',
        'default_meta_title': 't',
        'default_meta_description': 'd',
        'default_og_image': '',
        'hide_header': True,
        'hide_footer': True,
        'base_template': 'admin/base.html',
        'is_super_admin': True,
        'logged_in_admin': SimpleNamespace(name='Admin', role='super'),
    })
    return ctx


class ManageAgentPreviewRenderTests(SimpleTestCase):
    def test_sample_agent_has_reversible_public_profile_slug(self):
        ctx = _sample_manage_agent_context('exclusive')
        slug = ctx['agent'].agent_slug
        self.assertTrue(slug)
        self.assertEqual(
            reverse('agents:agent_public_profile', kwargs={'slug': slug}),
            f'/profile/{slug}/',
        )
        self.assertEqual(ctx['profile'].slug, slug)

    def test_agent_card_profile_url_uses_sample_slug(self):
        from django.template import Context, Template
        ctx = _sample_manage_agent_context('exclusive')
        html = Template(
            "{% load static %}"
            "{% with agent_slug=agent.agent_slug %}"
            "{% if agent_slug %}{% url 'agents:agent_public_profile' slug=agent_slug %}{% else %}#{% endif %}"
            "{% endwith %}"
        ).render(Context(ctx))
        self.assertEqual(html.strip(), '/profile/sample-agent/')

    def test_empty_slug_does_not_reverse(self):
        from django.template import Context, Template
        html = Template(
            "{% if agent_slug %}{% url 'agents:agent_public_profile' slug=agent_slug %}{% else %}#{% endif %}"
        ).render(Context({'agent_slug': ''}))
        self.assertEqual(html.strip(), '#')

    def test_edit_profile_preview_renders(self):
        html = render_to_string('agents/edit_profile.html', _preview_template_context(tab='edit_profile'))
        self.assertIn('edit-profile-card', html)
        self.assertIn('admin-sidebar', html)
        self.assertIn('edit_profile_basic', html)
        self.assertIn('edit_profile_additional', html)

    def test_dashboard_preview_omits_priority_support_button(self):
        from pathlib import Path
        from django.conf import settings
        source = Path(settings.BASE_DIR) / 'templates' / 'agents' / 'dashboard.html'
        text = source.read_text(encoding='utf-8')
        self.assertIn('not admin_lock_preview and agent_plan and agent_plan.premium_priority_support', text)

    def test_other_features_preview_renders(self):
        html = render_to_string(
            'admin/content/manage_agent_other.html',
            _preview_template_context(tab='other'),
        )
        self.assertIn('agent_directory_visibility', html)
        self.assertIn('premium_support', html)
        self.assertIn('manageAgentMatch', html)
        self.assertIn('All conditions (AND)', html)
        self.assertIn('ma-dd', html)

    def test_unlock_builder_includes_metrics(self):
        from apps.admin_panel.views.content import _preview_unlock_builder
        builder = _preview_unlock_builder()
        self.assertIn('reviews', builder['metrics'])
        self.assertTrue(builder['metrics']['reviews']['label'])
        self.assertIn('gte', builder['metrics']['reviews']['operators'])

    def test_preview_context_does_not_blank_admin_sidebar_identity(self):
        ctx = _sample_manage_agent_context('free_trial')
        self.assertNotIn('is_super_admin', ctx)
        self.assertNotIn('admin_permissions', ctx)
        self.assertNotIn('logged_in_admin', ctx)
