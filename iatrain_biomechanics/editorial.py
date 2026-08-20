from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import Person
from iatrain.models import KnowledgeEditorialEvent
from iatrain_motion.models import EditorialStatus, MotionConcept

from .checks import audit_action_function, audit_stabilization_function
from .models import (
    BiomechanicalContext,
    MuscleActionFunction,
    MuscleStabilizationFunction,
)


ALLOWED_TRANSITIONS = {
    EditorialStatus.DRAFT: {EditorialStatus.VALIDATED, EditorialStatus.RETIRED},
    EditorialStatus.VALIDATED: {EditorialStatus.DRAFT, EditorialStatus.RETIRED},
    EditorialStatus.RETIRED: {EditorialStatus.DRAFT},
}


@dataclass(frozen=True)
class EditorialTransition:
    instance: object
    previous_status: str


def _reviewer_for_user(user):
    if not getattr(user, "is_authenticated", False) or not user.is_superuser:
        raise PermissionDenied("Només un superusuari pot governar coneixement professional.")
    try:
        reviewer = user.person
    except Person.DoesNotExist as exc:
        raise ValidationError("El revisor necessita una identitat.") from exc
    if not reviewer.is_active:
        raise ValidationError("El revisor necessita una identitat activa.")
    return reviewer


def _validate_transition(previous_status, target_status):
    if target_status not in ALLOWED_TRANSITIONS:
        raise ValidationError("Estat editorial desconegut.")
    if target_status != previous_status and target_status not in ALLOWED_TRANSITIONS[previous_status]:
        raise ValidationError(
            f"Transició editorial no permesa: {previous_status} → {target_status}."
        )


def _apply_transition(instance, target_status, reviewer):
    instance.editorial_status = target_status
    update_fields = ["editorial_status", "updated_at"]
    if target_status == EditorialStatus.VALIDATED:
        instance.last_validated_by = reviewer
        instance.last_validated_at = timezone.now()
        update_fields.extend(("last_validated_by", "last_validated_at"))
    instance.full_clean()
    instance.save(update_fields=tuple(update_fields))


def _record_event(instance, previous_status, reviewer, reason, snapshot):
    event = KnowledgeEditorialEvent(
        target_model=instance._meta.label_lower,
        target_id=instance.pk,
        target_repr=str(instance),
        from_status=previous_status,
        to_status=instance.editorial_status,
        decided_by=reviewer,
        reason=str(reason or "").strip(),
        snapshot=snapshot,
    )
    event.full_clean()
    event.save()


@transaction.atomic
def transition_biomechanical_context(*, user, context, target_status, reason=""):
    reviewer = _reviewer_for_user(user)
    context = BiomechanicalContext.objects.select_for_update().get(pk=context.pk)
    previous_status = context.editorial_status
    _validate_transition(previous_status, target_status)
    if previous_status == target_status:
        return EditorialTransition(context, previous_status)
    list(context.angle_constraints.select_for_update())
    if target_status == EditorialStatus.VALIDATED:
        invalid_schemas = context.angle_constraints.exclude(
            angle_definition__schema__editorial_status=EditorialStatus.VALIDATED
        )
        if invalid_schemas.exists():
            raise ValidationError(
                "Les restriccions angulars necessiten esquemes canònics validats."
            )
    if previous_status == EditorialStatus.VALIDATED:
        dependent_count = (
            context.muscle_action_functions.filter(editorial_status=EditorialStatus.VALIDATED).count()
            + context.muscle_stabilization_functions.filter(
                editorial_status=EditorialStatus.VALIDATED
            ).count()
        )
        if dependent_count:
            raise ValidationError("Reobre primer les funcions validades que utilitzen el context.")
    _apply_transition(context, target_status, reviewer)
    _record_event(
        context,
        previous_status,
        reviewer,
        reason,
        {
            "code": context.code,
            "name": context.name,
            "description": context.description,
            "kinetic_chain": context.kinetic_chain,
            "loading_conditions": context.loading_conditions,
            "angle_constraint_count": context.angle_constraints.count(),
            "provenance": context.provenance,
            "authored_by_id": context.authored_by_id,
        },
    )
    return EditorialTransition(context, previous_status)


@transaction.atomic
def transition_muscle_action_function(*, user, function, target_status, reason=""):
    reviewer = _reviewer_for_user(user)
    function = MuscleActionFunction.objects.select_for_update().get(pk=function.pk)
    list(
        MotionConcept.objects.select_for_update().filter(
            pk__in=(function.muscle_id, function.action_id)
        )
    )
    if function.context_id:
        BiomechanicalContext.objects.select_for_update().get(pk=function.context_id)
    previous_status = function.editorial_status
    _validate_transition(previous_status, target_status)
    if previous_status == target_status:
        return EditorialTransition(function, previous_status)
    list(function.evidence_links.select_for_update())
    if target_status == EditorialStatus.VALIDATED:
        issues = audit_action_function(function, require_validated=True)
        if issues:
            raise ValidationError("La funció no és validable:\n- " + "\n- ".join(issues))
    _apply_transition(function, target_status, reviewer)
    _record_event(
        function,
        previous_status,
        reviewer,
        reason,
        {
            "code": function.code,
            "muscle_id": function.muscle_id,
            "action_id": function.action_id,
            "context_id": function.context_id,
            "contribution_class": function.contribution_class,
            "statement": function.statement,
            "conditions": function.conditions,
            "limitations": function.limitations,
            "evidence_ids": list(function.evidence_links.values_list("evidence_id", flat=True)),
            "provenance": function.provenance,
            "authored_by_id": function.authored_by_id,
        },
    )
    return EditorialTransition(function, previous_status)


@transaction.atomic
def transition_muscle_stabilization_function(*, user, function, target_status, reason=""):
    reviewer = _reviewer_for_user(user)
    function = MuscleStabilizationFunction.objects.select_for_update().get(pk=function.pk)
    endpoint_ids = [function.muscle_id, function.target_joint_id, function.target_segment_id]
    list(
        MotionConcept.objects.select_for_update().filter(
            pk__in=[value for value in endpoint_ids if value]
        )
    )
    if function.context_id:
        BiomechanicalContext.objects.select_for_update().get(pk=function.context_id)
    previous_status = function.editorial_status
    _validate_transition(previous_status, target_status)
    if previous_status == target_status:
        return EditorialTransition(function, previous_status)
    list(function.evidence_links.select_for_update())
    if target_status == EditorialStatus.VALIDATED:
        issues = audit_stabilization_function(function, require_validated=True)
        if issues:
            raise ValidationError("La funció no és validable:\n- " + "\n- ".join(issues))
    _apply_transition(function, target_status, reviewer)
    target = function.target_joint or function.target_segment
    _record_event(
        function,
        previous_status,
        reviewer,
        reason,
        {
            "code": function.code,
            "muscle_id": function.muscle_id,
            "target_id": target.pk,
            "target_kind": target.kind,
            "context_id": function.context_id,
            "stabilization_type": function.stabilization_type,
            "statement": function.statement,
            "conditions": function.conditions,
            "limitations": function.limitations,
            "evidence_ids": list(function.evidence_links.values_list("evidence_id", flat=True)),
            "provenance": function.provenance,
            "authored_by_id": function.authored_by_id,
        },
    )
    return EditorialTransition(function, previous_status)
