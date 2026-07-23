from __future__ import annotations

import copy

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from ...models.inscripcions import Inscripcio
from ...models.judging import (
    JudgePortalAssignment,
    JudgeScoreDraft,
    JudgeScoringLane,
    JudgeScoringWindow,
)
from ...models.scoring import ScoreRevision, TeamCompetitiveSubject
from ...services.scoring.publication import score_write_context
from .subject_scope import subject_matches_scope
from .submissions import persist_subject_score_patch


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


def _assignment_snapshot(lane):
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
    return {
        "assignment_ids": list(assignments.values_list("id", flat=True)),
        "controller_assignment_id": lane.controller_assignment_id,
        "lane_version": int(lane.version),
    }


@transaction.atomic
def open_scoring_window(*, lane, assignment, subject_kind, subject_id, exercici):
    lane = JudgeScoringLane.objects.select_for_update().get(pk=lane.pk)
    require_controller(lane, assignment)
    if active_window_for_lane(lane, for_update=True) is not None:
        raise ValidationError("Ja hi ha una puntuacio oberta en aquest aparell/fase.")
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
        configuration_snapshot=_assignment_snapshot(lane),
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


def serialize_flow_state(*, lane, assignment):
    window = active_window_for_lane(lane)
    is_controller = assignment_is_controller(lane, assignment)
    pending_windows = []
    if is_controller:
        pending_windows = list(
            JudgeScoringWindow.objects
            .filter(lane=lane, status__in=PENDING_WINDOW_STATUSES)
            .order_by("sequence", "id")
        )
    payload = {
        "mode": "guided",
        "lane_id": lane.id,
        "lane_version": int(lane.version),
        "is_controller": is_controller,
        "has_controller": bool(lane.controller_assignment_id),
        "window": None,
        "pending_windows": [
            {
                "id": item.id,
                "sequence": int(item.sequence),
                "status": item.status,
                "subject_kind": item.subject_kind,
                "subject_id": int(item.subject_id),
                "subject_label": _subject_label(item),
                "exercici": int(item.exercici),
                "closing_at": item.closing_at.isoformat() if item.closing_at else None,
                "draft_count": item.score_drafts.count(),
            }
            for item in pending_windows
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
        "subject_label": _subject_label(window),
        "is_assigned": bool(is_assigned),
        "exercici": int(window.exercici),
        "opened_at": window.opened_at.isoformat() if window.opened_at else None,
        "closing_at": window.closing_at.isoformat() if window.closing_at else None,
        "judge_statuses": list(statuses.values()),
        "error": window.error_message,
    }
    return payload
