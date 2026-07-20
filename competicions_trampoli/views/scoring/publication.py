import json

from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from ...models import Competicio, Inscripcio
from ...models.judging import JudgeScoreSubmission
from ...models.scoring import (
    ScorePublicationPolicy,
    ScoreRevision,
    TeamCompetitiveSubject,
)
from ...services.scoring.publication import publish_revision, reject_revision


ACTIVITY_LIMIT = 60


def _json_body(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _subject_labels(revisions):
    ins_ids = {item.subject_id for item in revisions if item.subject_kind == "inscripcio"}
    team_ids = {item.subject_id for item in revisions if item.subject_kind == "team_unit"}
    ins = {
        item.id: {
            "name": str(getattr(item, "nom_i_cognoms", "") or item),
            "meta": str(getattr(item, "entitat", "") or ""),
        }
        for item in Inscripcio.objects.filter(id__in=ins_ids)
    }
    teams = {
        item.id: {
            "name": str(item.label or getattr(item.equip, "nom", "") or item.equip),
            "meta": str(getattr(item.context, "name", "") or getattr(item.context, "nom", "") or "Equip"),
        }
        for item in TeamCompetitiveSubject.objects.filter(id__in=team_ids).select_related("equip", "context")
    }
    return ins, teams


def _serialize_revision(item, ins_labels, team_labels):
    subject = (team_labels if item.subject_kind == "team_unit" else ins_labels).get(item.subject_id, {})
    actor = "Sistema"
    if item.actor_user_id:
        actor = item.actor_user.get_full_name() or item.actor_user.get_username()
    elif item.actor_judge_token_id:
        actor = item.actor_judge_token.label or str(item.actor_judge_token_id)
    state = None
    try:
        state = item.current_for_states.first() or item.published_for_states.first()
    except Exception:
        state = None
    published_revision = getattr(state, "published_revision", None)
    published_total = float(published_revision.total) if published_revision else None
    return {
        "id": item.id,
        "subject_kind": item.subject_kind,
        "subject_id": item.subject_id,
        "subject_name": subject.get("name") or f"{item.subject_kind}:{item.subject_id}",
        "subject_meta": subject.get("meta") or "",
        "comp_aparell_id": item.comp_aparell_id,
        "app_label": item.comp_aparell.display_nom,
        "fase_id": item.fase_id,
        "fase_label": str(getattr(item.fase, "nom", "") or "") if item.fase_id else "",
        "exercici": item.exercici,
        "total": float(item.total),
        "published_total": published_total,
        "is_correction": published_revision is not None and published_revision.id != item.id,
        "source": item.source,
        "source_label": item.get_source_display(),
        "actor": actor,
        "status": item.publication_status,
        "status_label": item.get_publication_status_display(),
        "review_note": item.review_note,
        "created_at": item.created_at.isoformat(),
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }


def _serialize_submission(item, ins_labels, team_labels):
    subject = (team_labels if item.subject_kind == "team_unit" else ins_labels).get(item.subject_id, {})
    return {
        "id": f"submission:{item.id}",
        "submission_id": item.id,
        "subject_kind": item.subject_kind,
        "subject_id": item.subject_id,
        "subject_name": subject.get("name") or f"{item.subject_kind}:{item.subject_id}",
        "subject_meta": subject.get("meta") or "",
        "comp_aparell_id": item.comp_aparell_id,
        "app_label": item.comp_aparell.display_nom,
        "fase_id": item.fase_id,
        "fase_label": str(getattr(item.fase, "nom", "") or "") if item.fase_id else "",
        "exercici": item.exercici,
        "total": None,
        "published_total": None,
        "is_correction": False,
        "source": "judge",
        "source_label": "Jutge",
        "actor": item.submitted_by_token.label or str(item.submitted_by_token_id),
        "status": "supervisor_pending",
        "status_label": "Pendent de supervisor",
        "review_note": "",
        "created_at": item.created_at.isoformat(),
        "reviewed_at": None,
    }


def _filtered_revisions(request, competicio):
    qs = (
        ScoreRevision.objects
        .filter(competicio=competicio)
        .select_related("comp_aparell", "fase", "actor_user", "actor_judge_token")
        .prefetch_related("current_for_states__published_revision", "published_for_states__published_revision")
    )
    status = str(request.GET.get("status") or "").strip()
    source = str(request.GET.get("source") or "").strip()
    app_id = str(request.GET.get("comp_aparell_id") or "").strip()
    query = str(request.GET.get("q") or "").strip()
    if status in ScoreRevision.PublicationStatus.values:
        qs = qs.filter(publication_status=status)
    if source in ScoreRevision.Source.values:
        qs = qs.filter(source=source)
    if app_id.isdigit():
        qs = qs.filter(comp_aparell_id=int(app_id))
    if query:
        matching_ins_ids = Inscripcio.objects.filter(
            competicio=competicio,
            nom_i_cognoms__icontains=query,
        ).values_list("id", flat=True)
        matching_team_ids = TeamCompetitiveSubject.objects.filter(
            competicio=competicio,
        ).filter(Q(label__icontains=query) | Q(equip__nom__icontains=query)).values_list("id", flat=True)
        qs = qs.filter(
            Q(subject_kind="inscripcio", subject_id__in=matching_ins_ids)
            | Q(subject_kind="team_unit", subject_id__in=matching_team_ids)
        )
    return qs.order_by("-created_at", "-id")


@require_GET
def scoring_publication_activity(request, pk):
    competicio = get_object_or_404(Competicio, pk=pk)
    status = str(request.GET.get("status") or "").strip()
    source = str(request.GET.get("source") or "").strip()
    revisions = [] if status == "supervisor_pending" else list(_filtered_revisions(request, competicio)[:ACTIVITY_LIMIT])
    submissions = []
    if status in {"", "supervisor_pending"} and source in {"", "judge"}:
        submissions_qs = (
            JudgeScoreSubmission.objects
            .filter(competicio=competicio, status=JudgeScoreSubmission.Status.PENDING)
            .select_related("comp_aparell", "fase", "submitted_by_token")
            .order_by("-created_at", "-id")
        )
        app_id = str(request.GET.get("comp_aparell_id") or "").strip()
        if app_id.isdigit():
            submissions_qs = submissions_qs.filter(comp_aparell_id=int(app_id))
        query = str(request.GET.get("q") or "").strip()
        if query:
            matching_ins_ids = Inscripcio.objects.filter(
                competicio=competicio, nom_i_cognoms__icontains=query
            ).values_list("id", flat=True)
            matching_team_ids = TeamCompetitiveSubject.objects.filter(
                competicio=competicio,
            ).filter(Q(label__icontains=query) | Q(equip__nom__icontains=query)).values_list("id", flat=True)
            submissions_qs = submissions_qs.filter(
                Q(subject_kind="inscripcio", subject_id__in=matching_ins_ids)
                | Q(subject_kind="team_unit", subject_id__in=matching_team_ids)
            )
        submissions = list(submissions_qs[:ACTIVITY_LIMIT])
    label_refs = list(revisions) + list(submissions)
    ins_labels, team_labels = _subject_labels(label_refs)
    activity = [_serialize_revision(item, ins_labels, team_labels) for item in revisions]
    activity.extend(_serialize_submission(item, ins_labels, team_labels) for item in submissions)
    activity.sort(key=lambda item: item["created_at"], reverse=True)
    return JsonResponse({
        "ok": True,
        "activity": activity[:ACTIVITY_LIMIT],
        "limit": ACTIVITY_LIMIT,
    })


@require_GET
def scoring_publication_status(request, pk):
    competicio = get_object_or_404(Competicio, pk=pk)
    mode = (
        ScorePublicationPolicy.objects
        .filter(competicio=competicio)
        .values_list("mode", flat=True)
        .first()
        or ScorePublicationPolicy.Mode.AUTO
    )
    counts = {
        key: ScoreRevision.objects.filter(competicio=competicio, publication_status=key).count()
        for key in ScoreRevision.PublicationStatus.values
    }
    counts["supervisor_pending"] = JudgeScoreSubmission.objects.filter(
        competicio=competicio,
        status=JudgeScoreSubmission.Status.PENDING,
    ).count()
    latest = (
        ScoreRevision.objects
        .filter(competicio=competicio, publication_status=ScoreRevision.PublicationStatus.PUBLISHED)
        .order_by("-reviewed_at", "-created_at")
        .first()
    )
    return JsonResponse({
        "ok": True,
        "mode": mode,
        "mode_label": dict(ScorePublicationPolicy.Mode.choices).get(mode, mode),
        "counts": counts,
        "last_published_at": (
            (latest.reviewed_at or latest.created_at).isoformat() if latest else None
        ),
    })


@require_POST
def scoring_publication_policy(request, pk):
    competicio = get_object_or_404(Competicio, pk=pk)
    payload = _json_body(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "JSON invalid"}, status=400)
    mode = str(payload.get("mode") or "").strip()
    if mode not in ScorePublicationPolicy.Mode.values:
        return JsonResponse({"ok": False, "error": "Mode de publicacio invalid."}, status=400)
    pending_count = ScoreRevision.objects.filter(
        competicio=competicio,
        publication_status=ScoreRevision.PublicationStatus.PENDING,
    ).count()
    if mode == ScorePublicationPolicy.Mode.AUTO and pending_count:
        return JsonResponse({
            "ok": False,
            "error": f"Cal resoldre les {pending_count} revisions pendents abans d'activar la publicacio automatica.",
        }, status=409)
    policy, _ = ScorePublicationPolicy.objects.update_or_create(
        competicio=competicio,
        defaults={"mode": mode, "changed_by": request.user},
    )
    return JsonResponse({"ok": True, "mode": policy.mode, "mode_label": policy.get_mode_display()})


@require_POST
def scoring_publication_publish(request, pk):
    competicio = get_object_or_404(Competicio, pk=pk)
    payload = _json_body(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "JSON invalid"}, status=400)
    raw_ids = payload.get("revision_ids") or []
    if not isinstance(raw_ids, list):
        return JsonResponse({"ok": False, "error": "revision_ids ha de ser una llista."}, status=400)
    ids = []
    for raw in raw_ids[:500]:
        try:
            ids.append(int(raw))
        except Exception:
            continue
    if not ids:
        return JsonResponse({"ok": False, "error": "No hi ha revisions seleccionades."}, status=400)
    valid_ids = set(
        ScoreRevision.objects.filter(
            competicio=competicio,
            id__in=ids,
            publication_status=ScoreRevision.PublicationStatus.PENDING,
        ).values_list("id", flat=True)
    )
    published = []
    errors = []
    for revision_id in ids:
        if revision_id not in valid_ids:
            errors.append({"id": revision_id, "error": "La revisio no esta pendent."})
            continue
        try:
            with transaction.atomic():
                publish_revision(revision_id, user=request.user)
            published.append(revision_id)
        except (ValueError, ScoreRevision.DoesNotExist) as exc:
            errors.append({"id": revision_id, "error": str(exc)})
    return JsonResponse(
        {
            "ok": bool(published),
            "published_ids": published,
            "errors": errors,
            "warning": f"{len(errors)} revisions no s'han pogut publicar." if errors and published else "",
        },
        status=200 if published else 409,
    )


@require_POST
def scoring_publication_reject(request, pk):
    competicio = get_object_or_404(Competicio, pk=pk)
    payload = _json_body(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "JSON invalid"}, status=400)
    try:
        revision_id = int(payload.get("revision_id"))
    except Exception:
        return JsonResponse({"ok": False, "error": "Falta revision_id."}, status=400)
    note = str(payload.get("note") or "").strip()
    if not note:
        return JsonResponse({"ok": False, "error": "Cal indicar el motiu del rebuig."}, status=400)
    revision = get_object_or_404(ScoreRevision, pk=revision_id, competicio=competicio)
    try:
        reject_revision(revision.id, user=request.user, note=note)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=409)
    return JsonResponse({"ok": True, "revision_id": revision.id})
