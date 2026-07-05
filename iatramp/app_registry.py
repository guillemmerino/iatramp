from django.conf import settings


def _has_active_competicio_membership(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if "competicions_trampoli" not in settings.INSTALLED_APPS:
        return False
    from competicions_trampoli.models import CompeticioMembership
    return CompeticioMembership.objects.filter(user=user, is_active=True).exists()


INTERNAL_APPS = {
    "competicions": {
        "label": "Competicions",
        "url_name": "competicions_home",
        "active_url_names": ("competicions_home", "created", "create"),
        "app_label": "competicions_trampoli",
        "groups": ("competicions_manager",),
        "extra_check": _has_active_competicio_membership,
        "image": "images/competicio_trampoli_ia.webp",
        "description": "Gestiona competicions, inscripcions i resultats.",
    },
}


def get_internal_app_config(app_key: str):
    return INTERNAL_APPS.get(app_key)


def is_internal_app_installed(app_key: str) -> bool:
    config = get_internal_app_config(app_key)
    return bool(config and config["app_label"] in settings.INSTALLED_APPS)