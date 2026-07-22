import json

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from ...models.inscripcions import Inscripcio
from ...models.judging import JudgeDeviceToken, JudgeScoreDraft
from ...services.inscripcions.admission import load_excluded_app_ids_by_inscripcio
from ...services.judging.subject_scope import (
    filter_inscripcions_queryset_by_subject_scope,
    filter_team_subject_ids_by_subject_scope,
)
from ...services.judging.supervision import (
    field_requires_supervision,
    normalize_judge_role,
    token_is_supervisor_for_field,
)
from ...services.scoring.schema_resolution import resolve_scoring_schema_for_comp_aparell
from ...services.scoring.scoring_subjects import resolve_scoring_subject, serialize_subject_payload
from ...services.scoring.team_scoring import (
    build_team_subjects_for_comp_aparell,
    is_team_context_app,
    runtime_schema_for_comp_aparell,
)
from ...services.scoring.team_subject_contract import build_team_subject_registry
from ...services.shared.incremental_feeds import (
    apply_single_model_cursor,
    build_single_model_feed_meta,
    parse_feed_cursor,
)
from ._assignment_scope import (
    assignment_id_from_request,
    clamp_exercici_for_scope,
    ensure_subject_allowed_for_assignment,
    ensure_subject_scoreable_for_scope,
    resolve_assignment_scope_for_request,
)
from .permissions import (
    _normalize_permissions,
    _resolve_permissions_for_subject,
    _sanitize_patch_by_permissions,
)


JUDGE_DRAFT_UPDATES_LIMIT = 500


def _base_code(code):
    clean = str(code or "")
    return clean[len("__crash__"):] if clean.startswith("__crash__") else clean


def _group_by_runtime_field(patch):
    grouped = {}
    for code, value in (patch or {}).items():
        grouped.setdefault(_base_code(code), {})[str(code)] = value
    return grouped


def _permission_meta(permissions, runtime_code):
    for permission in permissions or []:
        candidate = str(permission.get("runtime_field_code") or permission.get("field_code") or "").strip()
        if candidate != runtime_code:
            continue
        return {
            "field_code": str(permission.get("field_code") or runtime_code),
            "judge_index": max(1, int(permission.get("judge_index") or 1)),
            "item_start": max(1, int(permission.get("item_start") or 1)),
            "item_count": permission.get("item_count"),
            "role": normalize_judge_role(permission.get("role")),
        }
    return {
        "field_code": runtime_code,
        "judge_index": 1,
        "item_start": 1,
        "item_count": None,
        "role": "standard",
    }


def _draft_payload(draft):
    return {
        "id": draft.id,
        "version": draft.version,
        "field_code": draft.field_code,
        "runtime_field_code": draft.runtime_field_code,
        "exercici": draft.exercici,
        **serialize_subject_payload(draft.subject_kind, draft.subject_id),
        "judge_index": draft.judge_index,
        "item_start": draft.item_start,
        "item_count": draft.item_count,
        "role": draft.role,
        "inputs_patch": draft.inputs_patch or {},
        "normalized_inputs_patch": draft.normalized_inputs_patch or {},
        "submitted_by_token_id": str(draft.submitted_by_token_id),
        "submitted_by_assignment_id": draft.submitted_by_assignment_id,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    }


def _runtime_code_allowed(scope, runtime_code):
    runtime_code = str(runtime_code or "").strip()
    for permission in _normalize_permissions(scope.permissions):
        base = str(permission.get("runtime_field_code") or permission.get("field_code") or "").strip()
        if runtime_code == base:
            return True
        field_code = str(permission.get("field_code") or "").strip()
        if field_code and runtime_code.startswith(f"{field_code}__m"):
            slot_raw = runtime_code.rsplit("__m", 1)[-1]
            if not slot_raw.isdigit():
                continue
            mode = str(permission.get("member_mode") or "all")
            slots = {int(value) for value in (permission.get("member_slots") or [])}
            if mode == "all" or int(slot_raw) in slots:
                return True
    return False


def _allowed_subject_ids(scope):
    if is_team_context_app(scope.comp_aparell):
        registry = build_team_subject_registry(scope.competicio, scope.comp_aparell)
        return set(
            filter_team_subject_ids_by_subject_scope(
                registry["all_by_id"],
                scope.subject_scope,
                competicio=scope.competicio,
            )
        )
    excluded = load_excluded_app_ids_by_inscripcio(scope.competicio, [scope.comp_aparell.id])
    excluded_ids = [key for key, app_ids in excluded.items() if int(scope.comp_aparell.id) in app_ids]
    qs = Inscripcio.objects.filter(competicio=scope.competicio).exclude(id__in=excluded_ids)
    qs = filter_inscripcions_queryset_by_subject_scope(qs, scope.subject_scope)
    return set(qs.values_list("id", flat=True))


@require_POST
@transaction.atomic
def judge_draft_update(request, token):
    tok = get_object_or_404(JudgeDeviceToken.objects.select_for_update(), pk=token)
    if not tok.is_valid():
        return JsonResponse({"ok": False, "error": "Token invalid o revocat"}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "JSON invalid"}, status=400)

    scope, scope_error = resolve_assignment_scope_for_request(tok, assignment_id_from_request(request, payload))
    if scope_error is not None:
        return scope_error
    patch = payload.get("inputs_patch") or {}
    if not isinstance(patch, dict) or not patch:
        return JsonResponse({"ok": False, "error": "inputs_patch ha de ser un objecte no buit"}, status=400)

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
    subject, error_response = resolve_scoring_subject(
        scope.competicio,
        scope.comp_aparell,
        subject_payload,
        eligible_team_ids=team_ids,
    )
    if error_response is not None:
        return error_response
    for checker in (ensure_subject_scoreable_for_scope, ensure_subject_allowed_for_assignment):
        error_response = checker(scope, subject)
        if error_response is not None:
            return error_response

    permissions = _normalize_permissions(scope.permissions)
    resolved_permissions = _resolve_permissions_for_subject(permissions, scope.comp_aparell, subject)
    allowed_codes = {
        str(item.get("runtime_field_code") or item.get("field_code") or "")
        for item in resolved_permissions
    }
    allowed_patch_codes = allowed_codes | {f"__crash__{code}" for code in allowed_codes}
    if not set(patch).issubset(allowed_patch_codes):
        return JsonResponse({"ok": False, "error": "Intentes editar un camp no autoritzat"}, status=403)

    _schema_obj, base_schema = resolve_scoring_schema_for_comp_aparell(scope.comp_aparell)
    team_subject = subject.get("team_subject") if subject.get("subject_kind") == "team_unit" else None
    member_count = len(getattr(team_subject, "member_ids", []) or []) if team_subject is not None else 0
    schema = runtime_schema_for_comp_aparell(base_schema, scope.comp_aparell, member_count=member_count)
    patch = dict(patch)
    for code in list(patch):
        if not str(code).startswith("__crash__"):
            continue
        runtime_code = _base_code(code)
        requires_supervisor = field_requires_supervision(
            competicio=scope.competicio,
            comp_aparell=scope.comp_aparell,
            phase=scope.phase,
            runtime_field_code=runtime_code,
        )
        is_supervisor = token_is_supervisor_for_field(
            token=tok,
            assignment=scope.assignment,
            comp_aparell=scope.comp_aparell,
            runtime_field_code=runtime_code,
        )
        if requires_supervisor and not is_supervisor:
            patch.pop(code, None)
            continue
        if requires_supervisor and is_supervisor:
            field = next((item for item in schema.get("fields", []) if item.get("code") == runtime_code), {})
            n_judges = max(1, int(((field.get("judges") or {}).get("count")) or 1))
            raw = patch[code]
            value = next((item for item in raw if item not in (None, 0, "0")), 0) if isinstance(raw, list) else raw
            patch[code] = [value] * n_judges

    sanitized = _sanitize_patch_by_permissions(schema, resolved_permissions, patch)
    raw_by_field = _group_by_runtime_field(patch)
    clean_by_field = _group_by_runtime_field(sanitized)
    try:
        client_sequence = max(0, int(payload.get("client_sequence") or 0))
    except (TypeError, ValueError):
        client_sequence = 0
    rows = []
    for runtime_code, normalized_patch in clean_by_field.items():
        meta = _permission_meta(resolved_permissions, runtime_code)
        lookup = {
            "competicio": scope.competicio,
            "comp_aparell": scope.comp_aparell,
            "fase": scope.phase,
            "submitted_by_token": tok,
            "submitted_by_assignment_id": scope.assignment_id,
            "subject_kind": str(subject["subject_kind"]),
            "subject_id": int(subject["subject_id"]),
            "exercici": clamp_exercici_for_scope(scope, payload.get("exercici")),
            "runtime_field_code": runtime_code,
        }
        draft = JudgeScoreDraft.objects.select_for_update().filter(**lookup).order_by("-id").first()
        if draft is None:
            draft = JudgeScoreDraft(**lookup)
        else:
            draft.version += 1
        draft.field_code = meta["field_code"]
        draft.judge_index = meta["judge_index"]
        draft.item_start = meta["item_start"]
        draft.item_count = meta["item_count"]
        draft.role = meta["role"]
        draft.inputs_patch = raw_by_field.get(runtime_code, {})
        draft.normalized_inputs_patch = normalized_patch
        draft.client_sequence = max(draft.client_sequence, client_sequence)
        draft.save()
        rows.append(draft)
    tok.touch()
    return JsonResponse({"ok": True, "drafts": [_draft_payload(item) for item in rows]})


@require_GET
def judge_draft_updates(request, token):
    tok = get_object_or_404(JudgeDeviceToken, pk=token)
    if not tok.is_valid():
        return JsonResponse({"ok": False, "error": "Token invalid o revocat"}, status=403)
    scope, scope_error = resolve_assignment_scope_for_request(tok, assignment_id_from_request(request))
    if scope_error is not None:
        return scope_error
    cursor = parse_feed_cursor(request)
    qs = JudgeScoreDraft.objects.filter(
        competicio=scope.competicio,
        comp_aparell=scope.comp_aparell,
        fase=scope.phase,
        subject_id__in=_allowed_subject_ids(scope),
    )
    raw_exercises = request.GET.getlist("exercici")
    if raw_exercises:
        qs = qs.filter(exercici__in=[clamp_exercici_for_scope(scope, value) for value in raw_exercises])
    qs = apply_single_model_cursor(qs.order_by("updated_at", "id"), cursor)
    rows = [
        item for item in qs[: JUDGE_DRAFT_UPDATES_LIMIT + 1]
        if _runtime_code_allowed(scope, item.runtime_field_code)
    ]
    page_rows = rows[:JUDGE_DRAFT_UPDATES_LIMIT]
    meta = build_single_model_feed_meta(rows, limit=JUDGE_DRAFT_UPDATES_LIMIT, cursor=cursor)
    return JsonResponse({
        "ok": True,
        "drafts": [_draft_payload(item) for item in page_rows],
        "next_since": meta["next_since"],
        "next_after_id": meta["next_after_id"],
        "has_more": meta["has_more"],
    })
