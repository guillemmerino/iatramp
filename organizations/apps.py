from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "organizations"
    verbose_name = "Organitzacions"

    def ready(self):
        from core.identity_merge import register_person_merge_handler

        from .identity import merge_organization_identity

        register_person_merge_handler("organizations", merge_organization_identity)
