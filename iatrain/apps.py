from django.apps import AppConfig


class IatrainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "iatrain"

    def ready(self):
        from core.assistant import register_assistant_provider
        from core.identity_merge import register_person_merge_handler

        from .assistant import iatrain_assistant_provider
        from .identity import merge_iatrain_identity

        register_assistant_provider(iatrain_assistant_provider)
        register_person_merge_handler("iatrain", merge_iatrain_identity)
    verbose_name = "IA Train"
