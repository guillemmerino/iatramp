from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from iatrain.engine.forms import BlockGenerationForm
from iatrain.engine.openai import OpenAITrainingError
from iatrain.engine.scoring import GenerationBlocked
from iatrain.engine.services import (
    apply_generation_run,
    discard_generation_run,
    generate_block_run,
    resume_generation_run,
)
from iatrain.models import BlockGenerationRun, TrainingSession, TrainingSessionRevision
from iatrain.services import organizations_available_to_coach
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
        run = generate_block_run(
            user=request.user,
            revision=revision,
            prompt=form.cleaned_data["prompt"],
            duration_minutes=form.cleaned_data["duration_minutes"],
            block_role=form.cleaned_data["block_role"],
        )
    except (OpenAITrainingError, GenerationBlocked, ValidationError) as error:
        run = getattr(error, "run", None)
        messages.error(request, str(error))
    else:
        if run.status == run.Status.AWAITING_DECISION:
            messages.info(request, "Cal una decisió abans de completar la proposta.")
        else:
            messages.success(request, "Proposta preparada. Revisa-la abans d'afegir-la.")
    return redirect(_detail_url(session, revision, run))


@login_required
@require_POST
def block_generation_refine(request, pk, run_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    parent = _run_for(session, run_pk)
    revision = parent.session_revision
    refinable = parent.status == parent.Status.PROPOSED or (
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
        run = generate_block_run(
            user=request.user,
            revision=revision,
            prompt=parent.prompt,
            duration_minutes=parent.request_payload["planned_duration_minutes"],
            block_role=parent.request_payload["block_role"],
            parent_run=parent,
            refinement=instruction,
        )
    except (OpenAITrainingError, GenerationBlocked, ValidationError) as error:
        run = getattr(error, "run", None)
        messages.error(request, str(error))
    else:
        messages.success(request, "Proposta reformulada.")
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
        run = resume_generation_run(
            user=request.user,
            run=run,
            decisions=decisions,
        )
    except (GenerationBlocked, ValidationError) as error:
        failed_run = getattr(error, "run", None)
        messages.error(request, str(error))
        return redirect(_detail_url(session, revision, failed_run or run))
    if run.status == run.Status.AWAITING_DECISION:
        messages.info(request, "Encara falta resoldre alguna decisió del grup.")
    else:
        messages.success(request, "Proposta personalitzada preparada.")
    return redirect(_detail_url(session, revision, run))


@login_required
@require_POST
def block_generation_apply(request, pk, run_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    run = _run_for(session, run_pk)
    try:
        apply_generation_run(user=request.user, run=run)
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
