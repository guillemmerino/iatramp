"""Transactional editorial policy for the anatomical-kinematic subgraph."""

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import Person
from iatrain.models import KnowledgeEditorialEvent

from .checks import audit_skeleton_schema
from .models import EditorialStatus, MotionConcept, MotionRelation, SkeletonSchema


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


def _record_event(*, instance, previous_status, reviewer, reason, snapshot):
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


def _apply_transition(*, instance, target_status, reviewer):
    instance.editorial_status = target_status
    update_fields = ["editorial_status", "updated_at"]
    if target_status == EditorialStatus.VALIDATED:
        instance.last_validated_by = reviewer
        instance.last_validated_at = timezone.now()
        update_fields.extend(("last_validated_by", "last_validated_at"))
    instance.full_clean()
    instance.save(update_fields=tuple(update_fields))


def _validated_schema_uses_relation(relation):
    schemas = SkeletonSchema.objects.select_for_update().filter(
        editorial_status=EditorialStatus.VALIDATED
    )
    relation_type = relation.relation_type
    if relation_type == MotionRelation.RelationType.PROXIMAL_SEGMENT:
        return schemas.filter(
            joints__concept_id=relation.source_id,
            joints__proximal_segment__concept_id=relation.target_id,
        ).exists()
    if relation_type == MotionRelation.RelationType.DISTAL_SEGMENT:
        return schemas.filter(
            joints__concept_id=relation.source_id,
            joints__distal_segment__concept_id=relation.target_id,
        ).exists()
    action_filter = Q(angle_definitions__positive_action_id=relation.source_id) | Q(
        angle_definitions__negative_action_id=relation.source_id
    )
    if relation_type == MotionRelation.RelationType.ACTION_AT_JOINT:
        return schemas.filter(
            action_filter,
            angle_definitions__joint__concept_id=relation.target_id,
        ).exists()
    if relation_type == MotionRelation.RelationType.PRIMARY_PLANE:
        return schemas.filter(
            action_filter,
            angle_definitions__plane_id=relation.target_id,
        ).exists()
    if relation_type == MotionRelation.RelationType.PRIMARY_AXIS:
        return schemas.filter(
            action_filter,
            angle_definitions__axis_id=relation.target_id,
        ).exists()
    return False


@transaction.atomic
def transition_motion_concept(*, user, concept, target_status, reason=""):
    reviewer = _reviewer_for_user(user)
    concept = MotionConcept.objects.select_for_update().get(pk=concept.pk)
    previous_status = concept.editorial_status
    _validate_transition(previous_status, target_status)
    if target_status == previous_status:
        return EditorialTransition(concept, previous_status)

    if previous_status == EditorialStatus.VALIDATED:
        connected = MotionRelation.objects.select_for_update().filter(
            Q(source=concept) | Q(target=concept),
            editorial_status=EditorialStatus.VALIDATED,
        )
        if connected.exists():
            raise ValidationError(
                "Reobre o retira primer les relacions validades connectades al concepte."
            )
        referenced_by_schema = SkeletonSchema.objects.select_for_update().filter(
            Q(segments__concept=concept)
            | Q(joints__concept=concept)
            | Q(angle_definitions__positive_action=concept)
            | Q(angle_definitions__negative_action=concept)
            | Q(angle_definitions__plane=concept)
            | Q(angle_definitions__axis=concept),
            editorial_status=EditorialStatus.VALIDATED,
        )
        if referenced_by_schema.exists():
            raise ValidationError(
                "Reobre o retira primer els esquemes canònics validats que utilitzen el concepte."
            )

    _apply_transition(instance=concept, target_status=target_status, reviewer=reviewer)
    _record_event(
        instance=concept,
        previous_status=previous_status,
        reviewer=reviewer,
        reason=reason,
        snapshot={
            "code": concept.code,
            "name": concept.name,
            "definition": concept.definition,
            "kind": concept.kind,
            "laterality": concept.laterality,
            "provenance": concept.provenance,
            "authored_by_id": concept.authored_by_id,
        },
    )
    return EditorialTransition(concept, previous_status)


@transaction.atomic
def transition_motion_relation(*, user, relation, target_status, reason=""):
    reviewer = _reviewer_for_user(user)
    relation = MotionRelation.objects.select_for_update().get(pk=relation.pk)
    previous_status = relation.editorial_status
    _validate_transition(previous_status, target_status)
    if target_status == previous_status:
        return EditorialTransition(relation, previous_status)

    endpoints = {
        node.pk: node
        for node in MotionConcept.objects.select_for_update()
        .filter(pk__in=(relation.source_id, relation.target_id))
        .order_by("pk")
    }
    relation.source = endpoints[relation.source_id]
    relation.target = endpoints[relation.target_id]
    if (
        previous_status == EditorialStatus.VALIDATED
        and target_status != EditorialStatus.VALIDATED
        and _validated_schema_uses_relation(relation)
    ):
        raise ValidationError(
            "Reobre o retira primer els esquemes canònics validats que depenen de la relació."
        )
    _apply_transition(instance=relation, target_status=target_status, reviewer=reviewer)
    _record_event(
        instance=relation,
        previous_status=previous_status,
        reviewer=reviewer,
        reason=reason,
        snapshot={
            "source_id": relation.source_id,
            "target_id": relation.target_id,
            "relation_type": relation.relation_type,
            "rationale": relation.rationale,
            "provenance": relation.provenance,
            "authored_by_id": relation.authored_by_id,
        },
    )
    return EditorialTransition(relation, previous_status)


@transaction.atomic
def transition_skeleton_schema(*, user, schema, target_status, reason=""):
    reviewer = _reviewer_for_user(user)
    schema = SkeletonSchema.objects.select_for_update().get(pk=schema.pk)
    previous_status = schema.editorial_status
    _validate_transition(previous_status, target_status)
    if target_status == previous_status:
        return EditorialTransition(schema, previous_status)

    list(schema.landmarks.select_for_update())
    list(schema.segments.select_for_update())
    list(schema.joints.select_for_update())
    list(schema.angle_definitions.select_for_update())
    if target_status == EditorialStatus.VALIDATED:
        issues = audit_skeleton_schema(schema, require_validated_semantics=True)
        if issues:
            raise ValidationError("L'esquema canònic no és validable:\n- " + "\n- ".join(issues))

    _apply_transition(instance=schema, target_status=target_status, reviewer=reviewer)
    _record_event(
        instance=schema,
        previous_status=previous_status,
        reviewer=reviewer,
        reason=reason,
        snapshot={
            "code": schema.code,
            "version": schema.version,
            "name": schema.name,
            "spatial_dimensions": schema.spatial_dimensions,
            "length_unit": schema.length_unit,
            "angle_unit": schema.angle_unit,
            "coordinate_convention": schema.coordinate_convention,
            "neutral_pose": schema.neutral_pose,
            "landmark_count": schema.landmarks.count(),
            "segment_count": schema.segments.count(),
            "joint_count": schema.joints.count(),
            "angle_definition_count": schema.angle_definitions.count(),
            "authored_by_id": schema.authored_by_id,
        },
    )
    return EditorialTransition(schema, previous_status)
