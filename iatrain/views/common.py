from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.utils.http import url_has_allowed_host_and_scheme

from iatrain.services import person_for_user


PERSPECTIVE_SESSION_KEY = "iatrain_perspective"


def safe_next(request, fallback="iatrain_home"):
    target = request.POST.get("next")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def profiles_for(person):
    profiles = {}
    if person:
        for key, related_name in (("athlete", "athlete_profile"), ("coach", "coach_profile")):
            try:
                profiles[key] = getattr(person, related_name)
            except ObjectDoesNotExist:
                profiles[key] = None
    return profiles


def perspective_for(request, profiles):
    active = [key for key, profile in profiles.items() if profile and profile.is_active]
    selected = request.session.get(PERSPECTIVE_SESSION_KEY)
    if selected not in active:
        selected = "coach" if "coach" in active else (active[0] if active else None)
        if selected:
            request.session[PERSPECTIVE_SESSION_KEY] = selected
        else:
            request.session.pop(PERSPECTIVE_SESSION_KEY, None)
    return selected


def base_context(request):
    person = person_for_user(request.user)
    profiles = profiles_for(person)
    perspective = perspective_for(request, profiles) if person else None
    return {
        "iatrain_person": person,
        "sport_profiles": profiles,
        "perspective": perspective,
    }


def require_coach(request):
    if not request.user.is_authenticated:
        raise PermissionDenied
    person = person_for_user(request.user)
    try:
        valid = person and person.coach_profile.is_active
    except ObjectDoesNotExist:
        valid = False
    if not valid:
        raise PermissionDenied("Cal un perfil d’entrenador actiu.")
    return person
