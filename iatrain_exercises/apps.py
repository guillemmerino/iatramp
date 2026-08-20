from django.apps import AppConfig


class IatrainExercisesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "iatrain_exercises"
    verbose_name = "IA Train · Catàleg privat d'exercicis"

    def ready(self):
        from core.identity_merge import register_person_merge_handler
        from iatrain_biomechanics.dependencies import (
            register_biomechanics_dependency_handler,
        )
        from iatrain_motion.dependencies import register_motion_dependency_handler

        from .dependencies import biomechanics_dependency_issues, motion_dependency_issues
        from .identity import merge_exercises_identity

        register_person_merge_handler("iatrain_exercises", merge_exercises_identity)
        register_motion_dependency_handler("iatrain_exercises", motion_dependency_issues)
        register_biomechanics_dependency_handler(
            "iatrain_exercises", biomechanics_dependency_issues
        )
