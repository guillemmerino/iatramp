from django.urls import NoReverseMatch, reverse

from core.assistant import AssistantContext


_COMPETITION_PREFIXES = (
    "/competicions/",
    "/competicio/",
    "/trampoli/",
    "/scoring/",
    "/judge/",
    "/public/live/",
)


def _is_competitions_request(request):
    path = str(getattr(request, "path", "") or "")
    if path.startswith(_COMPETITION_PREFIXES):
        return True
    resolver_match = getattr(request, "resolver_match", None)
    func = getattr(resolver_match, "func", None)
    view_class = getattr(func, "view_class", None)
    module = getattr(view_class or func, "__module__", "")
    return str(module).startswith("competicions_trampoli.")


def _competition_id(request):
    resolver_match = getattr(request, "resolver_match", None)
    kwargs = getattr(resolver_match, "kwargs", None) or {}
    for key in ("pk", "competicio_id"):
        try:
            return int(kwargs.get(key))
        except (TypeError, ValueError):
            continue
    return None


def _chat_url():
    try:
        return reverse("avatar_conversation_reply")
    except NoReverseMatch:
        return ""


def competition_assistant_provider(request):
    """Provide competition-specific content while core owns presentation and runtime."""

    if not _is_competitions_request(request):
        return None

    messages = {}
    initial_topic = "welcome"
    if _competition_id(request) is not None:
        from .services.avatar.competition.overview import AVATAR_MESSAGES

        messages = AVATAR_MESSAGES
        initial_topic = "competition_intro"

    return AssistantContext(
        module="competicions_trampoli",
        messages=messages,
        initial_topic=initial_topic,
        chat_url=_chat_url(),
    )
