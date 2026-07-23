import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from ...models.judging import JudgeDeviceToken
from ...scoring_engine import ScoringError
from ...services.judging.flow import (
    cancel_scoring_window,
    finalize_scoring_window,
    lane_for_scope,
    open_scoring_window,
    reopen_scoring_window,
    serialize_flow_state,
    start_closing_window,
)
from ...services.scoring.scoring_subjects import resolve_scoring_subject
from ...services.scoring.team_scoring import build_team_subjects_for_comp_aparell, is_team_context_app
from ._assignment_scope import (
    assignment_id_from_request,
    clamp_exercici_for_scope,
    ensure_subject_allowed_for_assignment,
    ensure_subject_scoreable_for_scope,
    resolve_assignment_scope_for_request,
)


def _token_and_scope(request, token, payload=None):
    tok = get_object_or_404(JudgeDeviceToken, pk=token)
    if not tok.is_valid():
        return tok, None, JsonResponse({"ok": False, "error": "Token invalid o revocat"}, status=403)
    scope, error = resolve_assignment_scope_for_request(tok, assignment_id_from_request(request, payload))
    return tok, scope, error


def _json_payload(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return None, JsonResponse({"ok": False, "error": "JSON invalid"}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse({"ok": False, "error": "El payload ha de ser un objecte JSON"}, status=400)
    return payload, None


def _flow_error(exc):
    if isinstance(exc, PermissionDenied):
        status = 403
    elif isinstance(exc, ScoringError):
        status = 400
    else:
        status = 409
    messages = getattr(exc, "messages", None)
    return JsonResponse({"ok": False, "error": "; ".join(messages) if messages else str(exc)}, status=status)


@require_GET
def judge_flow_state(request, token):
    tok, scope, error = _token_and_scope(request, token)
    if error is not None:
        return error
    lane = lane_for_scope(scope)
    if lane is None:
        return JsonResponse({"ok": True, "mode": "free", "window": None})
    tok.touch()
    return JsonResponse({"ok": True, **serialize_flow_state(lane=lane, assignment=scope.assignment)})


@require_POST
def judge_flow_open(request, token):
    payload, error = _json_payload(request)
    if error is not None:
        return error
    tok, scope, error = _token_and_scope(request, token, payload)
    if error is not None:
        return error
    lane = lane_for_scope(scope)
    if lane is None:
        return JsonResponse({"ok": False, "error": "El mode guiat no esta actiu."}, status=409)
    subject_payload = {
        "subject_kind": payload.get("subject_kind"),
        "subject_id": payload.get("subject_id"),
        "inscripcio_id": payload.get("inscripcio_id"),
    }
    team_ids = None
    if is_team_context_app(scope.comp_aparell):
        team_ids = [
            int(item["subject_id"])
            for item in build_team_subjects_for_comp_aparell(scope.competicio, scope.comp_aparell)[0]
            if int(scope.comp_aparell.id) in (item.get("allowed_app_ids") or [])
        ]
    subject, subject_error = resolve_scoring_subject(
        scope.competicio,
        scope.comp_aparell,
        subject_payload,
        eligible_team_ids=team_ids,
    )
    if subject_error is not None:
        return subject_error
    for checker in (ensure_subject_scoreable_for_scope, ensure_subject_allowed_for_assignment):
        subject_error = checker(scope, subject)
        if subject_error is not None:
            return subject_error
    try:
        window = open_scoring_window(
            lane=lane,
            assignment=scope.assignment,
            subject_kind=subject["subject_kind"],
            subject_id=subject["subject_id"],
            exercici=clamp_exercici_for_scope(scope, payload.get("exercici")),
        )
    except (PermissionDenied, ValidationError) as exc:
        return _flow_error(exc)
    tok.touch()
    return JsonResponse({
        "ok": True,
        "window_id": window.id,
        **serialize_flow_state(lane=lane_for_scope(scope), assignment=scope.assignment),
    })


def _window_action(request, token, action):
    payload, error = _json_payload(request)
    if error is not None:
        return error
    tok, scope, error = _token_and_scope(request, token, payload)
    if error is not None:
        return error
    lane = lane_for_scope(scope)
    if lane is None:
        return JsonResponse({"ok": False, "error": "El mode guiat no esta actiu."}, status=409)
    try:
        window_id = int(payload.get("window_id") or 0)
    except (TypeError, ValueError):
        window_id = 0
    if not window_id:
        return JsonResponse({"ok": False, "error": "Cal indicar la finestra activa."}, status=400)
    try:
        result = action(lane=lane, assignment=scope.assignment, window_id=window_id)
    except (PermissionDenied, ValidationError, ScoringError) as exc:
        return _flow_error(exc)
    window = result[0] if isinstance(result, tuple) else result
    tok.touch()
    return JsonResponse({
        "ok": True,
        "window_id": window.id,
        **serialize_flow_state(lane=lane_for_scope(scope), assignment=scope.assignment),
    })


@require_POST
def judge_flow_close(request, token):
    return _window_action(request, token, start_closing_window)


@require_POST
def judge_flow_finalize(request, token):
    return _window_action(request, token, finalize_scoring_window)


@require_POST
def judge_flow_reopen(request, token):
    return _window_action(request, token, reopen_scoring_window)


@require_POST
def judge_flow_cancel(request, token):
    return _window_action(request, token, cancel_scoring_window)
