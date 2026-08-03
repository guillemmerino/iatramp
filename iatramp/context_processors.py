from django.conf import settings
from django.urls import NoReverseMatch, reverse

from .access import get_internal_nav_apps


def _is_competicions_app(request):
    resolver_match = getattr(request, "resolver_match", None)
    path = str(getattr(request, "path", "") or "")
    if path.startswith(("/competicions/", "/competicio/", "/trampoli/", "/scoring/", "/judge/", "/public/live/")):
        return True
    if not resolver_match:
        return False
    func = getattr(resolver_match, "func", None)
    view_class = getattr(func, "view_class", None)
    module = getattr(view_class or func, "__module__", "")
    return str(module).startswith("competicions_trampoli.")


def _active_competicio_id(request):
    resolver_match = getattr(request, "resolver_match", None)
    kwargs = getattr(resolver_match, "kwargs", None) or {}
    for key in ("pk", "competicio_id"):
        try:
            return int(kwargs.get(key))
        except (TypeError, ValueError):
            continue
    return None


def _safe_reverse(name, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return ""


def _active_dock_section(url_name):
    url_name = str(url_name or "")
    if url_name in {"competicions_home", "created"}:
        return "home"
    if url_name in {"qr_admin_home", "qr_admin_detail", "judges_qr_home", "judges_qr_print", "public_live_qr_home", "public_live_qr_print"}:
        return "notes"
    if "inscripcio" in url_name or "inscripcions" in url_name or url_name == "import":
        return "inscripcions"
    if "rotacions" in url_name:
        return "rotacions"
    if "classificacio" in url_name or "classificacions" in url_name or "public_live" in url_name:
        return "classificacions"
    if "notes" in url_name or "scoring" in url_name or "judge" in url_name or "token" in url_name or url_name == "trampoli_save":
        return "notes"
    if "aparell" in url_name or "fases" in url_name:
        return "fases"
    if url_name == "trampoli_config":
        return "config"
    return ""


def _dock_icon_path(section):
    icon_names = {
        "home": "home",
        "inscripcions": "inscripcions",
        "fases": "fases",
        "rotacions": "rotacions",
        "classificacions": "classificacions",
        "notes": "notes",
        "config": "configuracio",
    }
    return "dock/{}.png".format(icon_names.get(section, "home"))


def _font_config():
    family = getattr(settings, "COMPETICIONS_APP_FONT_FAMILY", "") or "Poppins"
    family_css = ', '.join([f'"{family}"', '"Segoe UI"', 'Arial', 'sans-serif'])
    return {
        "competicio_font_family": family,
        "competicio_font_family_css": family_css,
        "competicio_font_folder": getattr(settings, "COMPETICIONS_APP_FONT_FOLDER", ""),
        "competicio_font_faces": [],
    }


def _build_competition_dock(request, is_competicions_app):
    if not is_competicions_app or "competicions_trampoli" not in getattr(settings, "INSTALLED_APPS", ()):
        return []

    from iatramp.access import user_has_any_global_group
    from competicions_trampoli.access import GLOBAL_COMPETICIONS_GROUPS, user_has_competicio_capability
    from competicions_trampoli.models import Competicio

    resolver_match = getattr(request, "resolver_match", None)
    url_name = getattr(resolver_match, "url_name", "") or ""
    active_section = _active_dock_section(url_name)
    competicio_id = _active_competicio_id(request)
    items = [{"label": "Competicions", "section": "home", "url": _safe_reverse("competicions_home")}]

    if competicio_id is None:
        can_manage = user_has_any_global_group(getattr(request, "user", None), GLOBAL_COMPETICIONS_GROUPS)
        items.extend([
            {"label": "Aparells globals", "section": "fases", "url": _safe_reverse("aparells_list") if can_manage else ""},
            {"label": "Plantilles", "section": "classificacions", "url": _safe_reverse("classificacio_template_global_list") if can_manage else ""},
        ])
    else:
        competicio = Competicio.objects.filter(pk=competicio_id).only("id").first()
        if competicio:
            user = getattr(request, "user", None)
            te_notes = getattr(competicio, "te_notes", False)
            has_notes = bool(te_notes() if callable(te_notes) else te_notes)
            pk = competicio.id
            candidates = [
                (user_has_competicio_capability(user, competicio, "inscripcions.view"), "Inscripcions", "inscripcions", "inscripcions_list"),
                (user_has_competicio_capability(user, competicio, "scoring.edit"), "Aparells i Fases", "fases", "trampoli_fases"),
                (user_has_competicio_capability(user, competicio, "rotacions.view"), "Rotacions", "rotacions", "rotacions_planner"),
                (user_has_competicio_capability(user, competicio, "classificacions.view"), "Classificacions", "classificacions", "classificacions_home"),
                (has_notes and user_has_competicio_capability(user, competicio, "scoring.view"), "Notes i QRs", "notes", "scoring_notes_home"),
                (has_notes and user_has_competicio_capability(user, competicio, "scoring.edit"), "Configuracio", "config", "trampoli_config"),
            ]
            items.extend({"label": label, "section": section, "url": _safe_reverse(url_name, pk)} for allowed, label, section, url_name in candidates if allowed)

    return [{**item, "active": item["section"] == active_section, "icon_path": _dock_icon_path(item["section"])} for item in items if item.get("url")]


def app_env(request):
    app_env = getattr(settings, "APP_ENV", "dev")
    is_competicions_app = _is_competicions_app(request)
    resolver_match = getattr(request, "resolver_match", None)
    url_name = getattr(resolver_match, "url_name", "") or ""
    active_section = _active_dock_section(url_name) if is_competicions_app else ""
    if active_section in {"", "home", "config"}:
        active_section = "general" if is_competicions_app else ""
    dock_items = _build_competition_dock(request, is_competicions_app)
    dock_help_topic = "competition_intro" if dock_items and _active_competicio_id(request) is not None else ""
    internal_nav_apps = get_internal_nav_apps(getattr(request, "user", None), request=request)
    return {
        "APP_ENV": app_env,
        "IS_DEV": app_env == "dev",
        "IS_PROD": app_env == "prod",
        "is_internal_env": False,
        "internal_nav_apps": internal_nav_apps,
        "has_active_internal_nav_app": any(app["active"] for app in internal_nav_apps),
        "has_any_internal_app_access": bool(internal_nav_apps),
        "is_prod_competition_shell": app_env == "prod",
        "is_competicions_app": is_competicions_app,
        "competition_active_section": active_section,
        "competition_dock_items": dock_items,
        "has_competition_dock": bool(dock_items),
        "competition_dock_help_topic": dock_help_topic,
        **_font_config(),
    }
