import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from competicions_trampoli.tests.base import _BaseTrampoliDataMixin


class AvatarConversationTests(_BaseTrampoliDataMixin, TestCase):
    def setUp(self):
        self.competicio = self._create_competicio("Open Cup")
        self.url = reverse("avatar_conversation_reply")

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_requires_login(self):
        response = self._post({"message": "Com funcionen les inscripcions?"})

        self.assertEqual(response.status_code, 302)

    @override_settings(OPENAI_API_KEY="")
    def test_returns_clear_error_when_openai_key_is_missing(self):
        self._login_competicio_user(self.competicio)

        response = self._post({"message": "Que puc fer aqui?", "competicio_id": self.competicio.id})

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertIn("OPENAI_API_KEY", body["error"])

    @override_settings(OPENAI_API_KEY="test-key", OPENAI_AVATAR_MODEL="test-model")
    def test_returns_assistant_reply(self):
        self._login_competicio_user(self.competicio)

        with patch(
            "competicions_trampoli.views.avatar_conversation.call_openai_responses",
            return_value="Pots gestionar inscripcions des del panell Inscripcions.",
        ) as mocked_call:
            response = self._post({
                "message": "On gestiono les inscripcions?",
                "competicio_id": self.competicio.id,
                "page_title": "Inscripcions",
                "path": "/competicio/1/inscripcions/",
                "topic": "competition_inscriptions",
                "history": [{"role": "assistant", "content": "Hola"}],
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "Pots gestionar inscripcions des del panell Inscripcions.")
        call_kwargs = mocked_call.call_args.kwargs
        self.assertEqual(call_kwargs["message"], "On gestiono les inscripcions?")
        self.assertIn("Open Cup", call_kwargs["context"])
        self.assertEqual(call_kwargs["history"], [{"role": "assistant", "content": "Hola"}])

    @override_settings(OPENAI_API_KEY="test-key")
    def test_rejects_competicio_without_view_permission(self):
        other_competicio = self._create_competicio("Private Cup")
        self._login_competicio_user(self.competicio)

        response = self._post({"message": "Parla'm d'aquesta competicio", "competicio_id": other_competicio.id})

        self.assertEqual(response.status_code, 403)
