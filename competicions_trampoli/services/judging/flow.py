from __future__ import annotations

import copy

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from ...models.inscripcions import Inscripcio
from ...models.judging import (
    JudgePortalAssignment,
    JudgeScoreDraft,
    JudgeScoringLane,
    JudgeScoringWindow,
)
from ...models.scoring import ScoreRevision, TeamCompetitiveSubject
from ...scoring_engine import ScoringEngine
from ...services.scoring.judge_presence import (
    build_runtime_inputs_from_canonical,
    is_strict_presence_field,
    persist_inputs_after_compute,
    presence_key,
)
from ...services.scoring.publication import score_write_context
from ...services.scoring.schema_resolution import resolve_scoring_schema_for_comp_aparell
from ...services.scoring.scoring_subjects import subject_entry_model
from ...services.scoring.team_scoring import (
    logical_team_inputs_to_runtime_inputs,
    runtime_schema_for_comp_aparell,
)
from .subject_scope import subject_matches_scope
from .submissions import (
    _allowed_input_codes_for_schema,
    _apply_sanitized_patch,
    persist_subject_score_patch,
)


ACTIVE_WINDOW_STATUSES = {
    JudgeScoringWindow.Status.OPEN,
}
PENDING_WINDOW_STATUSES = {
    JudgeScoringWindow.Status.CLOSING,
    JudgeScoringWindow.Status.LOCKED,
}


def _phase_filter(phase):
    return {"fase__isnull": True} if phase is None else {"fase": phase}


def lane_for_scope(scope, *, enabled_only=True):
    qs = JudgeScoringLane.objects.filter(
        competicio=scope.competicio,
        comp_aparell=scope.comp_aparell,
        **_phase_filter(scope.phase),
    )
    if enabled_only:
        qs = qs.filter(is_enabled=True)
    return qs.select_related("controller_assignment", "controller_assignment__judge_token").first()


def assignment_is_controller(lane, assignment) -> bool:
    return bool(lane and assignment and lane.controller_assignment_id == getattr(assignment, "id", None))


def assignment_can_view_scoring_preview(lane, assignment) -> bool:
    if assignment_is_controller(lane, assignment):
        return True
    return any(
        str(item.get("role") or "standard").strip().lower() == "supervisor"
        for item in (getattr(assignment, "permissions", None) or [])
        if isinstance(item, dict)
    )


def require_controller(lane, assignment):
    if lane is None or not lane.is_enabled:
        raise ValidationError("El mode guiat no esta actiu en aquest aparell/fase.")
    if not assignment_is_controller(lane, assignment):
        raise PermissionDenied("Aquest acces no controla el flux de puntuacio.")


def active_window_for_lane(lane, *, for_update=False):
    qs = JudgeScoringWindow.objects.filter(lane=lane, status__in=ACTIVE_WINDOW_STATUSES)
    if for_update:
        qs = qs.select_for_update()
    return qs.order_by("-sequence", "-id").first()


def _window_for_action(lane, window_id, *, statuses, for_update=False):
    qs = JudgeScoringWindow.objects.filter(lane=lane, pk=window_id, status__in=statuses)
    if for_update:
        qs = qs.select_for_update()
    return qs.first()


def _clean_competition_context(value):
    if not isinstance(value, dict):
        return {}
    clean = {}
    for key in ("section_key", "section_label", "group_key", "group_label"):
        text = str(value.get(key) or "").strip()
        if text:
            clean[key] = text[:200]
    for key in ("franja_id", "group_index", "subject_index", "queue_index"):
        try:
            number = int(value.get(key))
        except (TypeError, ValueError):
            continue
        if number >= 0:
            clean[key] = number
    return clean


def _assignment_snapshot(lane, *, competition_context=None):
    assignments = (
        JudgePortalAssignment.objects
        .filter(
            competicio=lane.competicio,
            comp_aparell=lane.comp_aparell,
            is_active=True,
            judge_token__is_active=True,
            judge_token__revoked_at__isnull=True,
            **_phase_filter(lane.fase),
        )
        .order_by("ordre", "id")
    )
    snapshot = {
        "assignment_ids": list(assignments.values_list("id", flat=True)),
        "controller_assignment_id": lane.controller_assignment_id,
        "lane_version": int(lane.version),
    }
    clean_context = _clean_competition_context(competition_context)
    if clean_context:
        snapshot["competition_context"] = clean_context
    return snapshot


@transaction.atomic
def open_scoring_window(*, lane, assignment, subject_kind, subject_id, exercici, competition_context=None):
    lane = JudgeScoringLane.objects.select_for_update().get(pk=lane.pk)
    require_controller(lane, assignment)
    if active_window_for_lane(lane, for_update=True) is not None:
        raise ValidationError("Ja hi ha una puntuacio oberta en aquest aparell/fase.")
    pending_exists = JudgeScoringWindow.objects.select_for_update().filter(
        lane=lane,
        subject_kind=str(subject_kind or "inscripcio"),
        subject_id=int(subject_id),
        exercici=max(1, int(exercici or 1)),
        status__in=PENDING_WINDOW_STATUSES,
    ).exists()
    if pending_exists:
        raise ValidationError("Aquesta actuacio ja te una nota pendent. Reobre-la en lloc de crear-ne una de nova.")
    last_sequence = (
        JudgeScoringWindow.objects.filter(lane=lane).aggregate(value=Max("sequence"))["value"] or 0
    )
    window = JudgeScoringWindow.objects.create(
        lane=lane,
        sequence=int(last_sequence) + 1,
        subject_kind=str(subject_kind or "inscripcio"),
        subject_id=int(subject_id),
        exercici=max(1, int(exercici or 1)),
        status=JudgeScoringWindow.Status.OPEN,
        opened_by_assignment_id=assignment.id,
        configuration_snapshot=_assignment_snapshot(lane, competition_context=competition_context),
    )
    lane.version += 1
    lane.save(update_fields=["version", "updated_at"])
    return window


@transaction.atomic
def start_closing_window(*, lane, assignment, window_id):
    lane = JudgeScoringLane.objects.select_for_update().get(pk=lane.pk)
    require_controller(lane, assignment)
    window = active_window_for_lane(lane, for_update=True)
    if window is None or int(window.id) != int(window_id):
        raise ValidationError("La puntuacio activa ha canviat.")
    if window.status != JudgeScoringWindow.Status.OPEN:
        raise ValidationError("La puntuacio ja no esta oberta.")
    window.status = JudgeScoringWindow.Status.CLOSING
    window.closing_at = timezone.now()
    window.closed_by_assignment_id = assignment.id
    window.save(update_fields=["status", "closing_at", "closed_by_assignment", "updated_at"])
    lane.version += 1
    lane.save(update_fields=["version", "updated_at"])
    return window


@transaction.atomic
def reopen_scoring_window(*, lane, assignment, window_id):
    lane = JudgeScoringLane.objects.select_for_update().get(pk=lane.pk)
    require_controller(lane, assignment)
    if active_window_for_lane(lane, for_update=True) is not None:
        raise ValidationError("Tanca la puntuacio activa abans de reobrir una nota pendent.")
    window = _window_for_action(
        lane,
        window_id,
        statuses=PENDING_WINDOW_STATUSES,
        for_update=True,
    )
    if window is None:
        raise ValidationError("Aquesta puntuacio no es pot reobrir.")
    window.status = JudgeScoringWindow.Status.OPEN
    window.closing_at = None
    window.locked_at = None
    window.error_message = ""
    window.save(update_fields=["status", "closing_at", "locked_at", "error_message", "updated_at"])
    lane.version += 1
    lane.save(update_fields=["version", "updated_at"])
    return window


@transaction.atomic
def cancel_scoring_window(*, lane, assignment, window_id):
    lane = JudgeScoringLane.objects.select_for_update().get(pk=lane.pk)
    require_controller(lane, assignment)
    window = _window_for_action(
        lane,
        window_id,
        statuses=ACTIVE_WINDOW_STATUSES | PENDING_WINDOW_STATUSES,
        for_update=True,
    )
    if window is None:
        raise ValidationError("Aquesta puntuacio ja no es pot cancel·lar.")
    window.status = JudgeScoringWindow.Status.CANCELLED
    window.closed_by_assignment_id = assignment.id
    window.save(update_fields=["status", "closed_by_assignment", "updated_at"])
    window.score_drafts.all().delete()
    lane.version += 1
    lane.save(update_fields=["version", "updated_at"])
    return window


def _merge_normalized_patch(target, patch):
    for code, payload in (patch or {}).items():
        if isinstance(payload, dict) and "__set_list__" in payload:
            current = target.setdefault(code, {"__set_list__": []})
            current.setdefault("__set_list__", []).extend(copy.deepcopy(payload.get("__set_list__") or []))
            if payload.get("__preserve_presence__"):
                current["__preserve_presence__"] = True
            continue
        if isinstance(payload, dict) and "__set_matrix__" in payload:
            current = target.setdefault(code, {"__set_matrix__": []})
            current.setdefault("__set_matrix__", []).extend(copy.deepcopy(payload.get("__set_matrix__") or []))
            continue
        target[code] = copy.deepcopy(payload)
    return target


def _subject_for_window(window):
    if window.subject_kind == "team_unit":
        team_subject = TeamCompetitiveSubject.objects.select_related("equip", "context").get(
            pk=window.subject_id,
            competicio=window.lane.competicio,
            comp_aparell=window.lane.comp_aparell,
        )
        return {
            "subject_kind": "team_unit",
            "subject_id": int(team_subject.id),
            "team_subject": team_subject,
            "equip": team_subject.equip,
            "context": team_subject.context,
        }
    inscripcio = Inscripcio.objects.get(pk=window.subject_id, competicio=window.lane.competicio)
    return {
        "subject_kind": "inscripcio",
        "subject_id": int(inscripcio.id),
        "inscripcio": inscripcio,
    }


@transaction.atomic
def finalize_scoring_window(*, lane, assignment, window_id):
    lane = JudgeScoringLane.objects.select_for_update().get(pk=lane.pk)
    require_controller(lane, assignment)
    window = _window_for_action(
        lane,
        window_id,
        statuses=PENDING_WINDOW_STATUSES,
        for_update=True,
    )
    if window is None:
        raise ValidationError("Primer has de tancar la puntuacio.")

    window.status = JudgeScoringWindow.Status.LOCKED
    window.locked_at = timezone.now()
    window.save(update_fields=["status", "locked_at", "updated_at"])

    drafts = list(
        JudgeScoreDraft.objects.select_for_update()
        .filter(scoring_window=window)
        .order_by("role", "updated_at", "id")
    )
    combined_patch = {}
    # Els supervisors s'apliquen al final i, per tant, prevalen en el seu camp.
    for draft in [item for item in drafts if item.role != "supervisor"]:
        _merge_normalized_patch(combined_patch, draft.normalized_inputs_patch)
    for draft in [item for item in drafts if item.role == "supervisor"]:
        _merge_normalized_patch(combined_patch, draft.normalized_inputs_patch)
    _merge_normalized_patch(combined_patch, _presence_override_patch(window))
    if not combined_patch:
        # Tancar un torn sense canvis es una operacio valida: allibera la pista
        # sense crear cap revisio ni alterar la nota oficial que ja pugui existir.
        window.status = JudgeScoringWindow.Status.FINALIZED
        window.finalized_by_assignment_id = assignment.id
        window.finalized_at = timezone.now()
        window.error_message = ""
        window.save(update_fields=[
            "status",
            "finalized_by_assignment",
            "finalized_at",
            "error_message",
            "updated_at",
        ])
        JudgeScoreDraft.objects.filter(scoring_window=window).delete()
        lane.version += 1
        lane.save(update_fields=["version", "updated_at"])
        return window, None

    preview = build_scoring_window_preview(window)
    for code, values in (preview.get("presence") or {}).items():
        combined_patch[presence_key(code)] = list(values)

    subject = _subject_for_window(window)
    source = (
        ScoreRevision.Source.SUPERVISOR
        if any(item.role == "supervisor" for item in drafts)
        else ScoreRevision.Source.JUDGE
    )
    actor_token = getattr(assignment, "token", None) or getattr(assignment, "judge_token", None)
    with score_write_context(source=source, judge_token=actor_token):
        entry = persist_subject_score_patch(
            competicio=lane.competicio,
            comp_aparell=lane.comp_aparell,
            exercici=window.exercici,
            subject=subject,
            phase=lane.fase,
            patch=combined_patch,
        )

    window.status = JudgeScoringWindow.Status.FINALIZED
    window.finalized_by_assignment_id = assignment.id
    window.finalized_at = timezone.now()
    window.final_inputs = copy.deepcopy(entry.inputs or {})
    window.final_outputs = copy.deepcopy(entry.outputs or {})
    window.final_total = entry.total
    window.error_message = ""
    window.save(update_fields=[
        "status",
        "finalized_by_assignment",
        "finalized_at",
        "final_inputs",
        "final_outputs",
        "final_total",
        "error_message",
        "updated_at",
    ])
    JudgeScoreDraft.objects.filter(scoring_window=window).delete()
    lane.version += 1
    lane.save(update_fields=["version", "updated_at"])
    return window, entry


def _subject_label(window):
    if window.subject_kind == "team_unit":
        item = TeamCompetitiveSubject.objects.select_related("equip").filter(pk=window.subject_id).first()
        return str(getattr(getattr(item, "equip", None), "nom", None) or f"Equip {window.subject_id}")
    item = Inscripcio.objects.filter(pk=window.subject_id).first()
    return str(getattr(item, "nom_i_cognoms", None) or getattr(item, "nom", None) or f"Inscripcio {window.subject_id}")


def _subject_labels_for_windows(windows):
    items = list(windows or [])
    individual_ids = {int(item.subject_id) for item in items if item.subject_kind != "team_unit"}
    team_ids = {int(item.subject_id) for item in items if item.subject_kind == "team_unit"}
    labels = {
        ("inscripcio", int(item.id)): str(item.nom_i_cognoms or getattr(item, "nom", None) or f"Inscripcio {item.id}")
        for item in Inscripcio.objects.filter(pk__in=individual_ids)
    }
    for item in TeamCompetitiveSubject.objects.filter(pk__in=team_ids).select_related("equip"):
        labels[("team_unit", int(item.id))] = str(getattr(item.equip, "nom", None) or f"Equip {item.id}")
    return labels


def _window_competition_context(window):
    snapshot = window.configuration_snapshot if isinstance(window.configuration_snapshot, dict) else {}
    return _clean_competition_context(snapshot.get("competition_context"))


def _window_presence_overrides(window):
    snapshot = window.configuration_snapshot if isinstance(window.configuration_snapshot, dict) else {}
    raw = snapshot.get("presence_overrides")
    if not isinstance(raw, dict):
        return {}
    clean = {}
    for code, by_judge in raw.items():
        if not isinstance(by_judge, dict):
            continue
        values = {}
        for judge_index, value in by_judge.items():
            try:
                idx = max(1, int(judge_index))
            except (TypeError, ValueError):
                continue
            if isinstance(value, bool):
                values[str(idx)] = value
        if values:
            clean[str(code)] = values
    return clean


def _presence_override_patch(window):
    patch = {}
    for code, by_judge in _window_presence_overrides(window).items():
        patch[presence_key(code)] = {
            "__set_presence__": [(int(judge_index) - 1, value) for judge_index, value in by_judge.items()]
        }
    return patch


def _runtime_schema_for_window(window, subject):
    _schema_obj, base_schema = resolve_scoring_schema_for_comp_aparell(window.lane.comp_aparell)
    team_subject = subject.get("team_subject") if window.subject_kind == "team_unit" else None
    member_count = len(getattr(team_subject, "member_ids", []) or []) if team_subject is not None else 0
    return base_schema, runtime_schema_for_comp_aparell(
        base_schema,
        window.lane.comp_aparell,
        member_count=member_count,
    )


def _current_window_inputs(window, subject, base_schema):
    lookup = {
        "competicio": window.lane.competicio,
        "comp_aparell": window.lane.comp_aparell,
        "fase": window.lane.fase,
        "exercici": window.exercici,
    }
    if window.subject_kind == "team_unit":
        lookup["team_subject"] = subject["team_subject"]
    else:
        lookup["inscripcio"] = subject["inscripcio"]
    entry = subject_entry_model(window.lane.comp_aparell).objects.filter(**lookup).first()
    current = entry.inputs if entry is not None and isinstance(entry.inputs, dict) else {}
    if window.subject_kind == "team_unit":
        current = logical_team_inputs_to_runtime_inputs(current, subject["team_subject"], base_schema)
    return current


def _presence_payload(inputs, schema):
    effective = {}
    for field in schema.get("fields") or []:
        if not isinstance(field, dict) or not field.get("code") or not is_strict_presence_field(field):
            continue
        code = str(field["code"])
        n_judges = max(1, int(((field.get("judges") or {}).get("count")) or 1))
        raw = inputs.get(presence_key(code)) if isinstance(inputs, dict) else None
        effective[code] = [bool(raw[idx]) if isinstance(raw, list) and idx < len(raw) else False for idx in range(n_judges)]
    return effective


def _automatic_presence_from_drafts(inputs, schema, drafts):
    touched = {}
    for draft in drafts:
        for code, payload in (draft.normalized_inputs_patch or {}).items():
            code = str(code)
            if code.startswith("__crash__") or code.startswith("__presence__"):
                continue
            indexes = touched.setdefault(code, set())
            if isinstance(payload, dict) and isinstance(payload.get("__set_list__"), list):
                indexes.update(int(pair[0]) for pair in payload["__set_list__"] if isinstance(pair, (list, tuple)) and len(pair) >= 2)
            if isinstance(payload, dict) and isinstance(payload.get("__set_matrix__"), list):
                indexes.update(int(item[0]) for item in payload["__set_matrix__"] if isinstance(item, (list, tuple)) and len(item) >= 3)
    automatic = {}
    for field in schema.get("fields") or []:
        if not isinstance(field, dict) or not field.get("code") or not is_strict_presence_field(field):
            continue
        code = str(field["code"])
        n_judges = max(1, int(((field.get("judges") or {}).get("count")) or 1))
        raw = inputs.get(code) if isinstance(inputs, dict) else None
        ftype = str(field.get("type") or "number")
        values = []
        for idx in range(n_judges):
            present = False
            if idx in touched.get(code, set()) and isinstance(raw, list) and idx < len(raw):
                value = raw[idx]
                if ftype == "matrix":
                    present = isinstance(value, list) and any(item not in (None, "") for item in value)
                else:
                    present = value not in (None, "")
            values.append(present)
        automatic[code] = values
    return automatic


def build_scoring_window_preview(window):
    subject = _subject_for_window(window)
    base_schema, schema = _runtime_schema_for_window(window, subject)
    current_inputs = _current_window_inputs(window, subject, base_schema)
    combined_patch = {}
    drafts = list(window.score_drafts.order_by("role", "updated_at", "id"))
    for draft in [item for item in drafts if item.role != "supervisor"]:
        _merge_normalized_patch(combined_patch, draft.normalized_inputs_patch)
    for draft in [item for item in drafts if item.role == "supervisor"]:
        _merge_normalized_patch(combined_patch, draft.normalized_inputs_patch)
    automatic_inputs = _apply_sanitized_patch(current_inputs, combined_patch, schema)
    automatic_presence = _automatic_presence_from_drafts(automatic_inputs, schema, drafts)
    for code, values in automatic_presence.items():
        automatic_inputs[presence_key(code)] = values
    effective_inputs = _apply_sanitized_patch(automatic_inputs, _presence_override_patch(window), schema)
    allowed = _allowed_input_codes_for_schema(schema)
    clean_inputs = {key: value for key, value in effective_inputs.items() if key in allowed}
    runtime_inputs = build_runtime_inputs_from_canonical(clean_inputs, schema)
    result = ScoringEngine(schema).compute(runtime_inputs)
    canonical_inputs = persist_inputs_after_compute(clean_inputs, result.inputs, schema)
    overrides = _window_presence_overrides(window)
    override_payload = {}
    for code, presence in _presence_payload(canonical_inputs, schema).items():
        by_judge = overrides.get(code, {})
        override_payload[code] = [by_judge.get(str(idx + 1)) for idx in range(len(presence))]
    return {
        "inputs": canonical_inputs,
        "outputs": result.outputs,
        "total": float(result.total),
        "automatic_presence": automatic_presence,
        "presence": _presence_payload(canonical_inputs, schema),
        "presence_overrides": override_payload,
    }


@transaction.atomic
def set_scoring_window_presence_override(*, lane, assignment, window_id, field_code, judge_index, state):
    lane = JudgeScoringLane.objects.select_for_update().get(pk=lane.pk)
    require_controller(lane, assignment)
    window = active_window_for_lane(lane, for_update=True)
    if window is None or int(window.id) != int(window_id):
        raise ValidationError("La puntuacio activa ha canviat.")
    subject = _subject_for_window(window)
    _base_schema, schema = _runtime_schema_for_window(window, subject)
    code = str(field_code or "").strip()
    field = next((item for item in schema.get("fields") or [] if str(item.get("code") or "") == code), None)
    if not field or not is_strict_presence_field(field):
        raise ValidationError("Aquest camp no admet presencia individual de jutges.")
    n_judges = max(1, int(((field.get("judges") or {}).get("count")) or 1))
    try:
        judge_index = int(judge_index)
    except (TypeError, ValueError):
        judge_index = 0
    if judge_index < 1 or judge_index > n_judges:
        raise ValidationError("L'index de jutge no es valid.")
    if state not in {None, True, False}:
        raise ValidationError("L'estat de presencia no es valid.")

    snapshot = copy.deepcopy(window.configuration_snapshot if isinstance(window.configuration_snapshot, dict) else {})
    overrides = _window_presence_overrides(window)
    by_judge = dict(overrides.get(code, {}))
    if state is None:
        by_judge.pop(str(judge_index), None)
    else:
        by_judge[str(judge_index)] = bool(state)
    if by_judge:
        overrides[code] = by_judge
    else:
        overrides.pop(code, None)
    snapshot["presence_overrides"] = overrides
    events = list(snapshot.get("presence_override_events") or [])
    events.append({
        "field_code": code,
        "judge_index": judge_index,
        "state": state,
        "assignment_id": assignment.id,
        "at": timezone.now().isoformat(),
    })
    snapshot["presence_override_events"] = events[-200:]
    window.configuration_snapshot = snapshot
    window.save(update_fields=["configuration_snapshot", "updated_at"])
    lane.version += 1
    lane.save(update_fields=["version", "updated_at"])
    return window


def _window_progress_payload(window, *, subject_label=None):
    draft_count = getattr(window, "draft_count", None)
    if draft_count is None:
        draft_count = window.score_drafts.count()
    return {
        "id": window.id,
        "sequence": int(window.sequence),
        "status": window.status,
        "subject_kind": window.subject_kind,
        "subject_id": int(window.subject_id),
        "subject_label": subject_label or _subject_label(window),
        "exercici": int(window.exercici),
        "draft_count": int(draft_count or 0),
        "competition_context": _window_competition_context(window),
        "opened_at": window.opened_at.isoformat() if window.opened_at else None,
        "closing_at": window.closing_at.isoformat() if window.closing_at else None,
        "finalized_at": window.finalized_at.isoformat() if window.finalized_at else None,
        "error": window.error_message,
    }


def serialize_flow_state(*, lane, assignment):
    window = active_window_for_lane(lane)
    is_controller = assignment_is_controller(lane, assignment)
    pending_windows = []
    history_windows = []
    if is_controller:
        pending_windows = list(
            JudgeScoringWindow.objects
            .filter(lane=lane, status__in=PENDING_WINDOW_STATUSES)
            .annotate(draft_count=Count("score_drafts"))
            .order_by("sequence", "id")
        )
        history_windows = list(
            JudgeScoringWindow.objects
            .filter(lane=lane)
            .annotate(draft_count=Count("score_drafts"))
            .order_by("-sequence", "-id")[:1000]
        )
        history_windows.reverse()
    label_map = _subject_labels_for_windows(
        list(history_windows) + list(pending_windows) + ([window] if window is not None else [])
    )
    label_for = lambda item: label_map.get(
        ("team_unit" if item.subject_kind == "team_unit" else "inscripcio", int(item.subject_id)),
        None,
    )
    payload = {
        "mode": "guided",
        "lane_id": lane.id,
        "lane_version": int(lane.version),
        "is_controller": is_controller,
        "has_controller": bool(lane.controller_assignment_id),
        "window": None,
        "pending_windows": [
            _window_progress_payload(item, subject_label=label_for(item))
            for item in pending_windows
        ],
        "history_windows": [
            _window_progress_payload(item, subject_label=label_for(item))
            for item in history_windows
        ],
    }
    if window is None:
        return payload
    try:
        subject = _subject_for_window(window)
        is_assigned = subject_matches_scope(
            subject,
            getattr(assignment, "subject_scope", {}) or {},
            competicio=lane.competicio,
        )
    except (Inscripcio.DoesNotExist, TeamCompetitiveSubject.DoesNotExist):
        is_assigned = False
    draft_rows = list(
        window.score_drafts.values("submitted_by_assignment_id", "submitted_by_token__label", "updated_at")
    )
    statuses = {}
    for row in draft_rows:
        assignment_id = row["submitted_by_assignment_id"]
        if assignment_id is None:
            continue
        statuses[str(assignment_id)] = {
            "assignment_id": assignment_id,
            "label": row["submitted_by_token__label"] or f"Jutge {assignment_id}",
            "state": "synced",
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
    payload["window"] = {
        "id": window.id,
        "sequence": int(window.sequence),
        "status": window.status,
        "subject_kind": window.subject_kind,
        "subject_id": int(window.subject_id),
        "subject_label": label_for(window) or _subject_label(window),
        "is_assigned": bool(is_assigned),
        "exercici": int(window.exercici),
        "draft_count": len(draft_rows),
        "opened_at": window.opened_at.isoformat() if window.opened_at else None,
        "closing_at": window.closing_at.isoformat() if window.closing_at else None,
        "judge_statuses": list(statuses.values()),
        "competition_context": _window_competition_context(window),
        "error": window.error_message,
    }
    if is_assigned and assignment_can_view_scoring_preview(lane, assignment):
        try:
            payload["preview"] = build_scoring_window_preview(window)
        except (ScoringError, ValidationError) as exc:
            payload["preview"] = None
            payload["preview_error"] = str(exc)
    return payload
