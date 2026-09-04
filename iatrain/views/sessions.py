from copy import deepcopy

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from iatrain.models import (
    BlockGenerationRun,
    PhysicalExercisePrescription,
    SessionGoal,
    SessionItemAthleteAdjustment,
    SessionParticipantPlan,
    TrainingBlock,
    TrainingSession,
    TrainingSessionItem,
    TrainingSessionRevision,
)
from iatrain.engine.forms import BlockGenerationForm
from iatrain.services import organizations_available_to_coach, person_for_user
from iatrain.training.forms import (
    SessionGoalForm,
    SessionItemAthleteAdjustmentForm,
    SessionParticipantForm,
    TrainingBlockForm,
    TrainingItemForm,
)
from iatrain.training.services import (
    approve_session_revision,
    propose_session_revision,
    reopen_session_revision,
)
from iatrain_exercises.models import ExerciseObjective, ExerciseRevision

from .common import base_context, require_coach


def _sessions_for(user):
    sessions = TrainingSession.objects.select_related(
        "organization", "training_group", "gym", "responsible_coach__person"
    )
    if getattr(user, "is_superuser", False):
        return sessions
    return sessions.filter(organization__in=organizations_available_to_coach(user))


def _session_for(user, pk):
    return get_object_or_404(_sessions_for(user), pk=pk)


def _revision_for(session, requested=None):
    revisions = session.revisions.all()
    if requested:
        return get_object_or_404(revisions, pk=requested)
    return revisions.order_by("-revision_number").first()


def _next_index(queryset):
    return (queryset.aggregate(value=Max("sequence_index"))["value"] or 0) + 1


def _revision_url(session, revision):
    return f"{reverse('iatrain_session_detail', args=(session.pk,))}?revision={revision.pk}"


def _generation_preview(run, revision):
    if not run or not run.proposal_payload:
        return None
    payload = deepcopy(run.proposal_payload)
    request = payload.get("request", {})
    objective = request.get("objective", {})
    quality_labels = dict(ExerciseObjective.Objective.choices)
    pattern_labels = dict(ExerciseRevision.MovementPattern.choices)
    objective["primary_quality_label"] = quality_labels.get(
        objective.get("primary_quality"), objective.get("primary_quality", "")
    )
    objective["movement_pattern_labels"] = [
        pattern_labels.get(value, value)
        for value in objective.get("movement_patterns", [])
    ]
    request["target_intensity_label"] = {
        "low": "Baixa",
        "moderate": "Moderada",
        "high": "Alta",
        "very_high": "Molt alta",
    }.get(request.get("target_intensity"), request.get("target_intensity", ""))
    participant_labels = {
        plan.pk: plan.athlete_profile.person.display_name
        for plan in revision.participant_plans.all()
    }
    condition_labels = {
        condition.pk: condition.title
        for plan in revision.participant_plans.prefetch_related(
            "athlete_profile__conditions"
        )
        for condition in plan.athlete_profile.conditions.all()
    }
    participant_modes = {
        "shared": "Compartida",
        "personalized": "Personalitzada",
        "excluded": "Exclosa del bloc",
    }
    for participant in payload.get("participants", []):
        participant["participant_name"] = participant_labels.get(
            participant["participant_plan_id"], "Gimnasta"
        )
        participant["mode_label"] = participant_modes.get(
            participant.get("mode"), participant.get("mode", "")
        )
        for decision in participant.get("condition_decisions", []):
            decision["condition_title"] = condition_labels.get(
                decision.get("condition_id"), "Condició"
            )
            decision["action_label"] = {
                "not_applicable": "No afecta aquest bloc",
                "monitor": "Monitoratge",
                "modify": "Modificació",
                "replace": "Substitució",
                "skip": "Omissió",
            }.get(decision.get("action"), decision.get("action", ""))
    exercise_ids = set()
    for item in payload.get("items", []):
        dose = item.get("dose") or {}
        if dose.get("exercise_revision_id"):
            exercise_ids.add(dose["exercise_revision_id"])
        for alternative in item.get("alternatives", []):
            exercise_ids.add(alternative["exercise_revision_id"])
        for adjustment in item.get("athlete_adjustments", []):
            if adjustment.get("replacement_exercise_revision_id"):
                exercise_ids.add(adjustment["replacement_exercise_revision_id"])
    exercise_labels = {
        row.pk: row.exercise.name
        for row in ExerciseRevision.objects.filter(pk__in=exercise_ids).select_related("exercise")
    }
    for item in payload.get("items", []):
        dose = item.get("dose") or {}
        item["exercise_name"] = exercise_labels.get(dose.get("exercise_revision_id"), item["title"])
        for alternative in item.get("alternatives", []):
            alternative["exercise_name"] = exercise_labels.get(
                alternative["exercise_revision_id"], "Alternativa"
            )
        for adjustment in item.get("athlete_adjustments", []):
            adjustment["participant_name"] = participant_labels.get(
                adjustment["participant_plan_id"], "Gimnasta"
            )
            adjustment["replacement_exercise_name"] = exercise_labels.get(
                adjustment.get("replacement_exercise_revision_id"), ""
            )
            adjustment["station_remainder_label"] = {
                "rest": "recuperació",
                "reset": "recol·locació tècnica",
                "monitor": "monitoratge",
            }.get(adjustment.get("station_remainder_action"), "")
    seconds = payload.get("estimated_duration_seconds", 0)
    payload["estimated_duration_label"] = f"{seconds / 60:.1f}".replace(".0", "") + " min"
    try:
        payload["confidence_percent"] = int(float(payload.get("confidence") or 0) * 100)
    except (TypeError, ValueError):
        payload["confidence_percent"] = 0
    trace = run.agent_trace or []
    candidate_ids = {
        int(value)
        for row in trace
        if row.get("tool") in {"search_exercises", "find_compatible_alternatives"}
        and row.get("status") == "ok"
        for value in row.get("exercise_revision_ids", [])
    }
    search_rows = [
        row
        for row in trace
        if row.get("tool") in {"search_exercises", "find_compatible_alternatives"}
    ]
    payload["agent_audit"] = {
        "model_name": run.model_name,
        "tool_calls": len(trace),
        "searches": len(search_rows),
        "unique_candidates": len(candidate_ids),
        "selected_exercises": len(
            {
                (item.get("dose") or {}).get("exercise_revision_id")
                for item in payload.get("items", [])
                if (item.get("dose") or {}).get("exercise_revision_id")
            }
        ),
        "timing_checked": any(
            row.get("tool") == "calculate_block_timing" and row.get("status") == "ok"
            for row in trace
        ),
        "review": (run.validation_payload or {}).get("independent_review"),
        "context_metrics": (run.validation_payload or {}).get("context_metrics", {}),
    }
    payload["planning_brief"] = deepcopy(run.planning_payload or {})
    payload["review_required"] = bool(
        (run.validation_payload or {}).get("review_required")
    )
    payload["review_issues"] = deepcopy(
        (run.validation_payload or {}).get("review_issues", [])
    )
    item_labels = {
        int(item.get("sequence_index", 0)): item.get("title", "Ítem")
        for item in payload.get("items", [])
    }
    for issue in payload["review_issues"]:
        issue["participant_names"] = [
            participant_labels.get(int(value), f"Participant {value}")
            for value in issue.get("participant_plan_ids", [])
        ]
        issue["item_names"] = [
            item_labels.get(int(value), f"Ítem {value}")
            for value in issue.get("sequence_indices", [])
        ]
    return payload


def _generation_decision_preview(run, revision):
    if not run or run.status != run.Status.AWAITING_DECISION:
        return None
    payload = deepcopy(run.decision_payload)
    plans = {
        plan.pk: plan
        for plan in revision.participant_plans.select_related("athlete_profile__person")
    }
    for issue in payload.get("issues", []):
        plan = plans.get(issue.get("participant_plan_id"))
        issue["participant_name"] = (
            plan.athlete_profile.person.display_name if plan else "Planificació del bloc"
        )
        issue["athlete_profile_id"] = plan.athlete_profile_id if plan else None
    return payload


@login_required
def session_list(request):
    require_coach(request)
    status = request.GET.get("status", "")
    sessions = _sessions_for(request.user).prefetch_related("revisions")
    if status:
        sessions = sessions.filter(lifecycle_status=status)
    context = base_context(request)
    context.update(
        {
            "training_sessions": sessions.order_by("-scheduled_start", "-id"),
            "selected_status": status,
            "session_statuses": TrainingSession.LifecycleStatus.choices,
        }
    )
    return render(request, "iatrain/sessions/list.html", context)


@login_required
def session_detail(request, pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    revision = _revision_for(session, request.GET.get("revision") or request.POST.get("revision"))
    if revision is None:
        raise PermissionDenied
    action = request.POST.get("action", "")
    participant_form = SessionParticipantForm(
        request.POST if action == "participant" else None,
        user=request.user,
        organization=session.organization,
        prefix="participant",
    )
    goal_form = SessionGoalForm(
        request.POST if action == "goal" else None,
        prefix="goal",
    )
    block_form = TrainingBlockForm(
        request.POST if action == "block" else None,
        prefix="block",
        initial={
            "sequence_index": _next_index(revision.blocks),
            "planned_duration_minutes": 10,
            "rounds": 1,
            "rest_between_rounds_seconds": 0,
        },
    )
    if request.method == "POST" and action:
        if revision.status != revision.Status.DRAFT:
            messages.error(request, "Aquesta versió ja no es pot editar.")
            return redirect(_revision_url(session, revision))
        form = {
            "participant": participant_form,
            "goal": goal_form,
            "block": block_form,
        }.get(action)
        if form is None:
            raise PermissionDenied
        if form.is_valid():
            try:
                _save_revision_part(action, form, revision)
            except (ValidationError, IntegrityError) as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Sessió actualitzada.")
                return redirect(_revision_url(session, revision))

    revision = (
        TrainingSessionRevision.objects.filter(pk=revision.pk)
        .select_related("session", "created_by", "approved_by")
        .prefetch_related(
            "participant_plans__athlete_profile__person",
            "goals",
            "blocks__items__physical_prescription__exercise_revision__exercise",
            "blocks__items__alternatives__exercise_revision__exercise",
            "blocks__items__athlete_adjustments__participant_plan__athlete_profile__person",
            "blocks__items__athlete_adjustments__replacement_exercise_revision__exercise",
            "blocks__participant_assignments__participant_plan__athlete_profile__person",
        )
        .get()
    )
    used_minutes = sum(revision.blocks.values_list("planned_duration_minutes", flat=True))
    remaining_minutes = max(revision.planned_duration_minutes - used_minutes, 0)
    selected_generation = None
    generation_id = request.GET.get("generation")
    if generation_id:
        selected_generation = get_object_or_404(
            BlockGenerationRun.objects.select_related("created_by", "parent_run"),
            pk=generation_id,
            session_revision=revision,
        )
    generation_form = BlockGenerationForm(
        maximum_duration=remaining_minutes,
        initial={
            "duration_minutes": min(12, remaining_minutes) if remaining_minutes else 1,
            "block_role": TrainingBlock.Role.MAIN,
        },
    )
    context = base_context(request)
    context.update(
        {
            "training_session": session,
            "revision": revision,
            "session_revisions": session.revisions.order_by("-revision_number"),
            "participant_form": participant_form,
            "goal_form": goal_form,
            "block_form": block_form,
            "can_edit_revision": revision.status == revision.Status.DRAFT,
            "remaining_minutes": remaining_minutes,
            "generation_form": generation_form,
            "generation_run": selected_generation,
            "generation_preview": _generation_preview(selected_generation, revision),
            "generation_decisions": _generation_decision_preview(
                selected_generation, revision
            ),
            "openai_training_configured": bool(getattr(settings, "OPENAI_API_KEY", "")),
        }
    )
    return render(request, "iatrain/sessions/detail.html", context)


def _save_revision_part(action, form, revision):
    if action == "participant":
        if (
            revision.session.session_scope == TrainingSession.Scope.INDIVIDUAL
            and revision.participant_plans.exists()
        ):
            raise ValidationError("Una sessió individual només pot tenir un gimnasta.")
        return SessionParticipantPlan.objects.create(
            session_revision=revision,
            athlete_profile=form.cleaned_data["athlete_profile"],
        )
    if action == "goal":
        description = form.cleaned_data["description"]
        base_code = slugify(description)[:68] or "objectiu"
        code = base_code
        suffix = 2
        while revision.goals.filter(domain=form.cleaned_data["domain"], code=code).exists():
            code = f"{base_code}-{suffix}"
            suffix += 1
        return SessionGoal.objects.create(
            session_revision=revision,
            code=code,
            source=SessionGoal.Source.COACH,
            **form.cleaned_data,
        )
    if action == "block":
        return TrainingBlock.objects.create(
            session_revision=revision,
            **form.cleaned_data,
        )
    raise PermissionDenied


@login_required
def session_item_create(request, pk, block_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    block = get_object_or_404(
        TrainingBlock.objects.select_related("session_revision"),
        pk=block_pk,
        session_revision__session=session,
    )
    if block.session_revision.status != TrainingSessionRevision.Status.DRAFT:
        raise PermissionDenied("Aquesta versió ja no es pot editar.")
    owner = person_for_user(request.user)
    form = TrainingItemForm(
        request.POST or None,
        owner=owner,
        initial={
            "sequence_index": _next_index(block.items),
            "item_type": TrainingSessionItem.ItemType.PHYSICAL_EXERCISE,
            "sets": 1,
            "setup_seconds": 0,
            "rest_after_seconds": 0,
            "rest_between_sets_seconds": 0,
            "intensity_metric": PhysicalExercisePrescription.IntensityMetric.NONE,
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            item = _save_item_form(form, block=block)
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Ítem afegit.")
            return redirect(_revision_url(session, block.session_revision))
    context = base_context(request)
    context.update(
        {
            "form": form,
            "form_title": f"Afegir ítem · {block.name}",
            "submit_label": "Afegir ítem",
            "form_tone": "tone-training",
        }
    )
    return render(request, "iatrain/components/form.html", context)


def _save_item_form(form, *, block, item=None):
    values = form.cleaned_data.copy()
    prescription_values = {
        key: values.pop(key)
        for key in (
            "exercise_revision",
            "dose_mode",
            "sets",
            "repetitions",
            "duration_seconds",
            "intensity_metric",
            "intensity_value",
            "rest_between_sets_seconds",
        )
    }
    with transaction.atomic():
        is_manual_edit = item is not None
        if item is None:
            item = TrainingSessionItem(block=block)
        for field, value in values.items():
            if field == "setup_seconds":
                value = value or 0
            setattr(item, field, value)
        if is_manual_edit:
            item.knowledge_support = {}
        item.save()
        if item.item_type == TrainingSessionItem.ItemType.PHYSICAL_EXERCISE:
            try:
                prescription = item.physical_prescription
            except PhysicalExercisePrescription.DoesNotExist:
                prescription = PhysicalExercisePrescription(session_item=item)
            for field, value in prescription_values.items():
                if field in {"sets"}:
                    value = value or 1
                if field in {"rest_between_sets_seconds"}:
                    value = value or 0
                if field == "intensity_metric":
                    value = value or PhysicalExercisePrescription.IntensityMetric.NONE
                setattr(prescription, field, value)
            prescription.save()
        elif hasattr(item, "physical_prescription"):
            item.physical_prescription.delete()
    return item


@login_required
def session_block_edit(request, pk, block_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    block = get_object_or_404(
        TrainingBlock.objects.select_related("session_revision"),
        pk=block_pk,
        session_revision__session=session,
    )
    if block.session_revision.status != TrainingSessionRevision.Status.DRAFT:
        raise PermissionDenied("Aquesta versió ja no es pot editar.")
    initial = {
        field: getattr(block, field)
        for field in TrainingBlockForm.base_fields
    }
    form = TrainingBlockForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        for field, value in form.cleaned_data.items():
            setattr(block, field, value)
        try:
            block.save()
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Bloc actualitzat.")
            return redirect(_revision_url(session, block.session_revision))
    context = base_context(request)
    context.update(
        {"form": form, "form_title": "Editar bloc", "submit_label": "Desar bloc"}
    )
    return render(request, "iatrain/components/form.html", context)


@login_required
def session_item_edit(request, pk, item_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    item = get_object_or_404(
        TrainingSessionItem.objects.select_related(
            "block__session_revision", "physical_prescription__exercise_revision"
        ),
        pk=item_pk,
        block__session_revision__session=session,
    )
    if item.block.session_revision.status != TrainingSessionRevision.Status.DRAFT:
        raise PermissionDenied("Aquesta versió ja no es pot editar.")
    initial = {
        field: getattr(item, field)
        for field in (
            "sequence_index",
            "item_type",
            "title",
            "instructions",
            "coaching_cues",
            "setup_seconds",
            "planned_duration_seconds",
            "rest_after_seconds",
            "selection_rationale",
            "is_optional",
        )
    }
    try:
        prescription = item.physical_prescription
    except PhysicalExercisePrescription.DoesNotExist:
        prescription = None
    if prescription:
        for field in (
            "exercise_revision",
            "dose_mode",
            "sets",
            "repetitions",
            "duration_seconds",
            "intensity_metric",
            "intensity_value",
            "rest_between_sets_seconds",
        ):
            initial[field] = getattr(prescription, field)
    form = TrainingItemForm(
        request.POST or None,
        owner=person_for_user(request.user),
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        try:
            _save_item_form(form, block=item.block, item=item)
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Ítem actualitzat.")
            return redirect(_revision_url(session, item.block.session_revision))
    context = base_context(request)
    context.update(
        {"form": form, "form_title": "Editar ítem", "submit_label": "Desar ítem"}
    )
    return render(request, "iatrain/components/form.html", context)


@login_required
def session_item_adjustment_edit(request, pk, adjustment_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    adjustment = get_object_or_404(
        SessionItemAthleteAdjustment.objects.select_related(
            "session_item__block__session_revision",
            "participant_plan__athlete_profile__person",
            "replacement_exercise_revision__exercise",
        ),
        pk=adjustment_pk,
        session_item__block__session_revision__session=session,
    )
    revision = adjustment.session_item.block.session_revision
    if revision.status != TrainingSessionRevision.Status.DRAFT:
        raise PermissionDenied("Aquesta versió ja no es pot editar.")
    form = SessionItemAthleteAdjustmentForm(
        request.POST or None,
        instance=adjustment,
        owner=person_for_user(request.user),
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                updated = form.save(commit=False)
                if updated.action != SessionItemAthleteAdjustment.Action.REPLACE:
                    updated.replacement_exercise_revision = None
                if updated.action == SessionItemAthleteAdjustment.Action.SKIP:
                    for field in (
                        "sets", "repetitions", "duration_seconds", "load_value",
                        "intensity_value", "rest_between_sets_seconds",
                    ):
                        setattr(updated, field, None)
                    updated.load_unit = ""
                    updated.intensity_metric = ""
                    updated.station_remainder_action = ""
                updated.professional_justification = {}
                updated.full_clean()
                updated.save()
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Adaptació individual actualitzada.")
            return redirect(_revision_url(session, revision))
    participant_name = adjustment.participant_plan.athlete_profile.person.display_name
    context = base_context(request)
    context.update(
        {
            "form": form,
            "form_title": f"Editar adaptació · {participant_name}",
            "submit_label": "Desar adaptació",
        }
    )
    return render(request, "iatrain/components/form.html", context)


@login_required
@require_POST
def session_item_delete(request, pk, item_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    item = get_object_or_404(
        TrainingSessionItem.objects.select_related("block__session_revision"),
        pk=item_pk,
        block__session_revision__session=session,
    )
    revision = item.block.session_revision
    item.delete()
    messages.success(request, "Ítem retirat.")
    return redirect(_revision_url(session, revision))


@login_required
@require_POST
def session_participant_delete(request, pk, participant_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    participant = get_object_or_404(
        SessionParticipantPlan.objects.select_related("session_revision"),
        pk=participant_pk,
        session_revision__session=session,
    )
    revision = participant.session_revision
    try:
        participant.delete()
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Participant retirat.")
    return redirect(_revision_url(session, revision))


@login_required
@require_POST
def session_goal_delete(request, pk, goal_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    goal = get_object_or_404(
        SessionGoal.objects.select_related("session_revision"),
        pk=goal_pk,
        session_revision__session=session,
    )
    revision = goal.session_revision
    try:
        goal.delete()
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Objectiu retirat.")
    return redirect(_revision_url(session, revision))


@login_required
@require_POST
def session_block_delete(request, pk, block_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    block = get_object_or_404(
        TrainingBlock.objects.select_related("session_revision"),
        pk=block_pk,
        session_revision__session=session,
    )
    revision = block.session_revision
    if block.items.exists():
        messages.error(request, "Retira primer els ítems del bloc.")
    else:
        try:
            block.delete()
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Bloc retirat.")
    return redirect(_revision_url(session, revision))


@login_required
@require_POST
def session_revision_transition(request, pk, revision_pk):
    require_coach(request)
    session = _session_for(request.user, pk)
    revision = get_object_or_404(session.revisions, pk=revision_pk)
    action = request.POST.get("action")
    try:
        if action == "propose":
            propose_session_revision(user=request.user, revision=revision)
            label = "Versió enviada a revisió."
        elif action == "reopen":
            reopen_session_revision(user=request.user, revision=revision)
            label = "Versió reoberta."
        elif action == "approve":
            approve_session_revision(user=request.user, revision=revision)
            label = "Versió aprovada."
        else:
            raise PermissionDenied
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, label)
    return redirect(_revision_url(session, revision))
