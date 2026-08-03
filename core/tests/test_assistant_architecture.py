from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import resolve, reverse

from core.assistant import get_assistant_context


class AssistantRegistryTests(SimpleTestCase):
    def test_competitions_registers_content_without_core_importing_the_module(self):
        request = RequestFactory().get("/competicio/7/rotacions/")
        request.resolver_match = resolve("/competicio/7/rotacions/")

        context = get_assistant_context(request)

        self.assertIsNotNone(context)
        self.assertEqual(context.module, "competicions_trampoli")
        self.assertEqual(context.initial_topic, "competition_intro")
        self.assertIn("competition_intro", context.messages)
        self.assertEqual(context.chat_url, reverse("avatar_conversation_reply"))

        core_sources = (
            Path(settings.BASE_DIR, "core", "assistant", "registry.py").read_text(encoding="utf-8")
            + Path(settings.BASE_DIR, "core", "context_processors.py").read_text(encoding="utf-8")
        )
        self.assertNotIn("competicions_trampoli", core_sources)

    def test_shared_component_and_runtime_are_owned_by_core(self):
        component = Path(
            settings.BASE_DIR, "core", "templates", "core", "components", "avatar_helper.html"
        ).read_text(encoding="utf-8")
        javascript = Path(settings.BASE_DIR, "core", "static", "core", "avatar_helper.js").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("<style>", component)
        self.assertNotIn("<script>", component)
        self.assertIn("data-avatar-assets-prefix", component)
        self.assertIn("helper.dataset.avatarAssetsPrefix", javascript)
        self.assertIsNotNone(finders.find("core/avatar_helper.css"))
        self.assertIsNotNone(finders.find("core/avatar_helper.js"))
        self.assertIsNotNone(finders.find("core/avatar/greeting_2.png"))


class AssistantIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="assistant_architecture_admin",
            email="assistant-architecture@example.com",
            password="test-pass",
        )
        self.client.force_login(self.user)

    def test_competitions_renders_one_core_assistant_with_core_assets(self):
        response = self.client.get(reverse("competicions_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="avatar-helper ', count=1)
        self.assertContains(response, "/static/core/avatar_helper.css")
        self.assertContains(response, "/static/core/avatar_helper.js")
        self.assertContains(response, "/static/core/avatar/controls/avatar_in.png")
        self.assertContains(response, 'data-avatar-module="competicions_trampoli"')
        self.assertContains(response, reverse("avatar_conversation_reply"))
        self.assertNotContains(response, "/static/general/avatar_in.png")

    def test_platform_home_loads_runtime_without_inventing_module_content(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/static/core/avatar_helper.css")
        self.assertContains(response, "/static/core/avatar_helper.js")
        self.assertNotContains(response, 'class="avatar-helper ')
