from django.apps import AppConfig


class CompeticionsTrampoliConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'competicions_trampoli'

    def ready(self):
        from . import signals  # noqa: F401
        from core.assistant import register_assistant_provider

        from .assistant import competition_assistant_provider

        register_assistant_provider(competition_assistant_provider)
