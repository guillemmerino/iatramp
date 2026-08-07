from django.apps import AppConfig


class IatrainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "iatrain"

    def ready(self):
        from core.assistant import register_assistant_provider

        from .assistant import iatrain_assistant_provider

        register_assistant_provider(iatrain_assistant_provider)
    verbose_name = "IA Train"
