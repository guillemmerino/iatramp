from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from iatrain.engine.forms import BlockGenerationForm
from iatrain.engine.openai import OpenAITrainingError
from iatrain.engine.scoring import GenerationBlocked
from iatrain.engine.services import (
    apply_generation_run,
    create_block_generation_run,
    discard_generation_run,
    prepare_resume_generation_run,
)
from iatrain.models import BlockGenerationRun, TrainingSession, TrainingSessionRevision
from iatrain.services import organizations_available_to_coach
from iatrain.tasks import execute_block_generation_task
from iatrain.views.common import require_coach


def _session_for(user, pk):
    sessions = TrainingSession.objects.select_related("organization")
    if not getattr(user, "is_superuser", False):
        sessions = sessions.filter(organization__in=organizations_available_to_coach(user))
    return get_object_or_404(sessions, pk=pk)


def _revision_for(session, revision_id):
    return get_object_or_404(
        TrainingSessionRevision.objects.select_related("session", "session__organization"),
        pk=revision_id,
        session=session,
    )


def _run_for(session, run_id):
    return get_object_or_404(
        BlockGenerationRun.objects.select_related(
            "session_revision", "session_revision__session", "created_by"
        ),
        pk=run_id,
        session_revision__session=session,
    )


def _detail_url(session, revision, run=None):
    url = f"{reverse('iatrain_session_detail', args=(session.pk,))}?revision={revision.pk}"
    if run:
        url += f"&generation={run.pk}#generation-proposal"
    return url


def _dispatch_generation(run, user):
    try:
        execute_block_generation_task.delay(run.pk, user.pk)
    except Exception as error:
        run.status = run.Status.FAILED
        run.error_code = "generation_queue_unavailable"
        run.error_message = "No s’ha pogut iniciar el procés de generació en segon pla."
        run.progress_payload = {
            "stage": "failed",
            "message": run.error_message,
            "updated_at": timezone.now().isoformat(),
        }
        run.save()
        try:
            error.run = run
        except (AttributeError, TypeError):
            pass
        raise ValidationError(run.error_message) from error


def _safe_progress_events(trace):
    labels = {
        "search_exercises": "Cerca al catàleg",
        "get_exercise_details": "Comparació de finalistes",
        "get_prescription_guidance": "Revisió de dosificació",
        "check_participant_compatibility": "Compatibilitat individual",
        "find_compatible_alternatives": "Cerca d’alternatives individuals",
        "calculate_block_timing": "Càlcul temporal",
        "audit_block_draft": "Auditoria de l’esborrany",
    }
    events = []
    for row in trace[-10:]:
        tool = row.get("tool", "")
        if tool not in labels:
            continue
        detail = ""
        if tool == "search_exercises":
            detail = (
                f"{row.get('result_count', 0)} candidats mostrats de "
                f"{row.get('total_matches', 0)} coincidències"
            )
        elif tool in {
            "get_exercise_details",
            "get_prescription_guidance",
            "check_participant_compatibility",
            "find_compatible_alternatives",
        }:
            detail = f"{row.get('result_count', 0)} resultats revisats"
        elif tool == "calculate_block_timing":
            seconds = row.get("total_seconds")
            detail = f"{seconds} segons" if seconds is not None else "Temps recalculat"
        elif tool == "audit_block_draft":
            detail = (
                "Esborrany correcte"
                if row.get("audit_valid")
                else "S’han detectat ajustos pendents"
            )
        events.append(
            {
                "sequence": row.get("sequence"),
                "label": labels[tool],
                "detail": detail,
                "ok": row.get("status") == "ok",
            }
        )
    return events


@login_required
@require_POST
def block_generation_create(request, pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    revision = _revision_for(session, request.POST.get("revision"))
    if revision.status != revision.Status.DRAFT:
        raise PermissionDenied("Només es pot generar sobre una versió en esborrany.")
    if not revision.participant_plans.exists():
        messages.error(request, "Afegeix almenys un participant abans de generar el bloc.")
        return redirect(_detail_url(session, revision))
    used = sum(revision.blocks.values_list("planned_duration_minutes", flat=True))
    remaining = max(revision.planned_duration_minutes - used, 0)
    form = BlockGenerationForm(request.POST, maximum_duration=remaining)
    if not form.is_valid():
        message = " ".join(
            error for errors in form.errors.values() for error in errors
        )
        messages.error(request, message or "Revisa la petició de generació.")
        return redirect(_detail_url(session, revision))
    run = None
    try:
        run = create_block_generation_run(
            user=request.user,
            revision=revision,
            prompt=form.cleaned_data["prompt"],
            duration_minutes=form.cleaned_data["duration_minutes"],
            block_role=form.cleaned_data["block_role"],
        )
        _dispatch_generation(run, request.user)
    except (OpenAITrainingError, GenerationBlocked, ValidationError) as error:
        run = getattr(error, "run", None)
        messages.error(request, str(error))
    else:
        messages.info(request, "Generació iniciada. Pots seguir-ne el progrés en directe.")
    return redirect(_detail_url(session, revision, run))


@login_required
@require_POST
def block_generation_refine(request, pk, run_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    parent = _run_for(session, run_pk)
    revision = parent.session_revision
    refinable = parent.status in {
        parent.Status.PROPOSED,
        parent.Status.REVIEW_REQUIRED,
    } or (
        parent.status == parent.Status.AWAITING_DECISION
        and parent.decision_payload.get("kind") == "intent_clarification"
    )
    if not refinable or revision.status != revision.Status.DRAFT:
        raise PermissionDenied("Aquesta proposta ja no es pot reformular.")
    instruction = " ".join(request.POST.get("instruction", "").split())
    if not instruction:
        messages.error(request, "Escriu què vols canviar.")
        return redirect(_detail_url(session, revision, parent))
    run = None
    try:
        run = create_block_generation_run(
            user=request.user,
            revision=revision,
            prompt=parent.prompt,
            duration_minutes=parent.request_payload["planned_duration_minutes"],
            block_role=parent.request_payload["block_role"],
            parent_run=parent,
            refinement=instruction,
        )
        _dispatch_generation(run, request.user)
    except (OpenAITrainingError, GenerationBlocked, ValidationError) as error:
        run = getattr(error, "run", None)
        messages.error(request, str(error))
    else:
        messages.info(request, "Reformulació iniciada. Pots seguir-ne el progrés.")
    return redirect(_detail_url(session, revision, run or parent))


@login_required
@require_POST
def block_generation_decide(request, pk, run_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    run = _run_for(session, run_pk)
    revision = run.session_revision
    if revision.status != revision.Status.DRAFT:
        raise PermissionDenied("Només es pot generar sobre una versió en esborrany.")
    decisions = {
        key.removeprefix("decision_"): value
        for key, value in request.POST.items()
        if key.startswith("decision_") and value
    }
    try:
        run = prepare_resume_generation_run(
            user=request.user,
            run=run,
            decisions=decisions,
        )
        _dispatch_generation(run, request.user)
    except (OpenAITrainingError, GenerationBlocked, ValidationError) as error:
        failed_run = getattr(error, "run", None)
        messages.error(request, str(error))
        return redirect(_detail_url(session, revision, failed_run or run))
    messages.info(request, "Decisions rebudes. La planificació continua en segon pla.")
    return redirect(_detail_url(session, revision, run))


@login_required
@require_GET
def block_generation_status(request, pk, run_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    run = _run_for(session, run_pk)
    trace = run.agent_trace or []
    search_rows = [
        row
        for row in trace
        if row.get("tool") in {"search_exercises", "find_compatible_alternatives"}
        and row.get("status") == "ok"
    ]
    candidate_ids = {
        int(value)
        for row in search_rows
        for value in row.get("exercise_revision_ids", [])
    }
    elapsed = max(int((timezone.now() - run.created_at).total_seconds()), 0)
    terminal = run.status != run.Status.PROCESSING
    payload = {
        "status": run.status,
        "status_label": run.get_status_display(),
        "terminal": terminal,
        "progress": {
            "stage": run.progress_payload.get("stage", "processing"),
            "message": run.progress_payload.get(
                "message", "Preparant la generació…"
            ),
            "elapsed_seconds": elapsed,
        },
        "stats": {
            "tool_calls": len(trace),
            "searches": len(search_rows),
            "unique_candidates": len(candidate_ids),
            "rounds": len(run.response_ids or []),
        },
        "events": _safe_progress_events(trace),
        "redirect_url": _detail_url(session, run.session_revision, run),
        "error_message": run.error_message if run.status == run.Status.FAILED else "",
        "poll_after_ms": 1500,
    }
    return JsonResponse(payload)


@login_required
@require_POST
def block_generation_apply(request, pk, run_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    run = _run_for(session, run_pk)
    try:
        apply_generation_run(
            user=request.user,
            run=run,
            acknowledge_review=request.POST.get("acknowledge_review") == "yes",
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect(_detail_url(session, run.session_revision, run))
    messages.success(request, "Bloc afegit a la sessió.")
    return redirect(_detail_url(session, run.session_revision))


@login_required
@require_POST
def block_generation_discard(request, pk, run_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    run = _run_for(session, run_pk)
    try:
        discard_generation_run(run=run)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Proposta descartada.")
    return redirect(_detail_url(session, run.session_revision))
