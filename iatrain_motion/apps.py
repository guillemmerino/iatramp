from django.apps import AppConfig


class IatrainMotionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "iatrain_motion"
    verbose_name = "IA Train · Anatomia i moviment"

    def ready(self):
        from core.identity_merge import register_person_merge_handler

        from .identity import merge_motion_identity

        register_person_merge_handler("iatrain_motion", merge_motion_identity)
