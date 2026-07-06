import json

from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from iatramp.access import require_app_access

from ..access import user_has_competicio_capability
from ..models import Competicio
from ..services.avatar.conversation import (
    AvatarConversationError,
    build_program_context,
    call_openai_responses,
    clean_history,
    clean_user_text,
)


def _json_payload(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_competicio(request, payload):
    raw_id = payload.get("competicio_id")
    if raw_id in {None, ""}:
        return None
    try:
        competicio_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    competicio = Competicio.objects.filter(pk=competicio_id).first()
    if competicio is None:
        return None
    if not user_has_competicio_capability(request.user, competicio, "competition.view"):
        raise PermissionDenied("No tens permisos per conversar sobre aquesta competicio.")
    return competicio


@require_POST
@login_required
@require_app_access("competicions")
def avatar_conversation_reply(request):
    payload = _json_payload(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "Peticio JSON invalida."}, status=400)

    message = clean_user_text(payload.get("message"))
    if not message:
        return JsonResponse({"ok": False, "error": "Escriu una pregunta abans d'enviar."}, status=400)

    competicio = _resolve_competicio(request, payload)
    context = build_program_context(request, payload, competicio=competicio)
    history = clean_history(payload.get("history"))

    try:
        reply = call_openai_responses(message=message, history=history, context=context)
    except AvatarConversationError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=503)

    return JsonResponse({"ok": True, "reply": reply})
