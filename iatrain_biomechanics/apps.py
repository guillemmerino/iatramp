from django.apps import AppConfig


class IatrainBiomechanicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "iatrain_biomechanics"
    verbose_name = "IA Train · Biomecànica funcional"

    def ready(self):
        from core.identity_merge import register_person_merge_handler
        from iatrain_motion.dependencies import register_motion_dependency_handler

        from .dependencies import motion_dependency_issues
        from .identity import merge_biomechanics_identity

        register_person_merge_handler("iatrain_biomechanics", merge_biomechanics_identity)
        register_motion_dependency_handler("iatrain_biomechanics", motion_dependency_issues)

