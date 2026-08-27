import inspect

from django.test import SimpleTestCase

from apps.agents.views import dashboard as dashboard_views


class AgentDashboardJsonShadowTests(SimpleTestCase):
    def test_agent_dashboard_does_not_shadow_json(self):
        code = dashboard_views.agent_dashboard.__code__
        self.assertNotIn('json', code.co_varnames)
        self.assertNotIn('json', code.co_names)

    def test_dashboard_module_functions_do_not_import_json_locally(self):
        shadowed = []
        for name, func in inspect.getmembers(dashboard_views, inspect.isfunction):
            if getattr(func, '__module__', '') != dashboard_views.__name__:
                continue
            if 'json' in func.__code__.co_varnames:
                shadowed.append(name)
        self.assertEqual(shadowed, [])
