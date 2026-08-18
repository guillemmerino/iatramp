"""Single transactional boundary for professional knowledge governance."""

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    ElementRotation,
    ElementRotationSegment,
    KnowledgeConcept,
    KnowledgeEditorialEvent,
    KnowledgeRelation,
)
from .services import person_for_user


ALLOWED_TRANSITIONS = {
    KnowledgeConcept.EditorialStatus.DRAFT: {
        KnowledgeConcept.EditorialStatus.VALIDATED,
        KnowledgeConcept.EditorialStatus.RETIRED,
    },
    KnowledgeConcept.EditorialStatus.VALIDATED: {
        KnowledgeConcept.EditorialStatus.DRAFT,
        KnowledgeConcept.EditorialStatus.RETIRED,
    },
    KnowledgeConcept.EditorialStatus.RETIRED: {
        KnowledgeConcept.EditorialStatus.DRAFT,
    },
}


@dataclass(frozen=True)
class EditorialTransition:
    instance: object
    previous_status: str


def _reviewer_for_user(user):
    if not getattr(user, "is_authenticated", False) or not user.is_superuser:
        raise PermissionDenied("Només un superusuari pot governar coneixement professional.")
    reviewer = person_for_user(user)
    if reviewer is None:
        raise ValidationError("El revisor necessita una identitat activa.")
    return reviewer


def _validate_transition(previous_status, target_status):
    known_statuses = set(ALLOWED_TRANSITIONS)
    if target_status not in known_statuses:
        raise ValidationError("Estat editorial desconegut.")
    if target_status == previous_status:
        return
    if target_status not in ALLOWED_TRANSITIONS[previous_status]:
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


def _concept_snapshot(concept):
    return {
        "name": concept.name,
        "description": concept.description,
        "kind": concept.kind,
        "discipline": concept.discipline,
        "attributes": concept.attributes,
        "authored_by_id": concept.authored_by_id,
    }


def _relation_snapshot(relation):
    return {
        "source_id": relation.source_id,
        "target_id": relation.target_id,
        "relation_type": relation.relation_type,
        "rationale": relation.rationale,
        "authored_by_id": relation.authored_by_id,
    }


def _rotation_snapshot(rotation, segments):
    return {
        "element_id": rotation.element_id,
        "transverse_quarters": rotation.transverse_quarters,
        "transverse_direction": rotation.transverse_direction,
        "segments": [
            {
                "sequence_index": segment.sequence_index,
                "longitudinal_half_turns": segment.longitudinal_half_turns,
            }
            for segment in segments
        ],
        "provenance": rotation.provenance,
        "authored_by_id": rotation.authored_by_id,
    }


def _apply_transition(*, instance, previous_status, target_status, reviewer):
    instance.editorial_status = target_status
    update_fields = ["editorial_status", "updated_at"]
    if target_status == KnowledgeConcept.EditorialStatus.VALIDATED:
        instance.last_validated_by = reviewer
        instance.last_validated_at = timezone.now()
        update_fields.extend(("last_validated_by", "last_validated_at"))
    instance.full_clean()
    instance.save(update_fields=tuple(update_fields))


@transaction.atomic
def transition_knowledge_concept(*, user, concept, target_status, reason=""):
    reviewer = _reviewer_for_user(user)
    concept = KnowledgeConcept.objects.select_for_update().get(pk=concept.pk)
    previous_status = concept.editorial_status
    _validate_transition(previous_status, target_status)
    if target_status == previous_status:
        return EditorialTransition(concept, previous_status)

    if previous_status == KnowledgeConcept.EditorialStatus.VALIDATED and (
        target_status != KnowledgeConcept.EditorialStatus.VALIDATED
    ):
        connected = list(
            KnowledgeRelation.objects.select_for_update().filter(
                Q(source=concept) | Q(target=concept),
                editorial_status=KnowledgeRelation.EditorialStatus.VALIDATED,
            )
        )
        if connected:
            raise ValidationError(
                "Reobre o retira primer les relacions validades connectades al concepte."
            )
        validated_rotation = ElementRotation.objects.select_for_update().filter(
            element=concept,
            editorial_status=KnowledgeConcept.EditorialStatus.VALIDATED,
        ).exists()
        if validated_rotation:
            raise ValidationError(
                "Reobre o retira primer el perfil de rotació validat del concepte."
            )

    _apply_transition(
        instance=concept,
        previous_status=previous_status,
        target_status=target_status,
        reviewer=reviewer,
    )
    _record_event(
        instance=concept,
        previous_status=previous_status,
        reviewer=reviewer,
        reason=reason,
        snapshot=_concept_snapshot(concept),
    )
    return EditorialTransition(concept, previous_status)


@transaction.atomic
def transition_knowledge_relation(*, user, relation, target_status, reason=""):
    reviewer = _reviewer_for_user(user)
    relation = KnowledgeRelation.objects.select_for_update().get(pk=relation.pk)
    previous_status = relation.editorial_status
    _validate_transition(previous_status, target_status)
    if target_status == previous_status:
        return EditorialTransition(relation, previous_status)

    endpoints = {
        concept.pk: concept
        for concept in KnowledgeConcept.objects.select_for_update()
        .filter(pk__in=(relation.source_id, relation.target_id))
        .order_by("pk")
    }
    relation.source = endpoints[relation.source_id]
    relation.target = endpoints[relation.target_id]
    if target_status == KnowledgeRelation.EditorialStatus.VALIDATED and (
        relation.source.editorial_status != KnowledgeConcept.EditorialStatus.VALIDATED
        or relation.target.editorial_status != KnowledgeConcept.EditorialStatus.VALIDATED
    ):
        raise ValidationError("Valida primer els dos conceptes connectats per aquesta relació.")
    _apply_transition(
        instance=relation,
        previous_status=previous_status,
        target_status=target_status,
        reviewer=reviewer,
    )
    _record_event(
        instance=relation,
        previous_status=previous_status,
        reviewer=reviewer,
        reason=reason,
        snapshot=_relation_snapshot(relation),
    )
    return EditorialTransition(relation, previous_status)


@transaction.atomic
def transition_element_rotation(*, user, rotation, target_status, reason=""):
    reviewer = _reviewer_for_user(user)
    rotation = ElementRotation.objects.select_for_update().select_related("element").get(
        pk=rotation.pk
    )
    previous_status = rotation.editorial_status
    _validate_transition(previous_status, target_status)
    if target_status == previous_status:
        return EditorialTransition(rotation, previous_status)

    KnowledgeConcept.objects.select_for_update().get(pk=rotation.element_id)
    segments = list(
        ElementRotationSegment.objects.select_for_update()
        .filter(rotation=rotation)
        .order_by("sequence_index")
    )
    if target_status == KnowledgeConcept.EditorialStatus.VALIDATED:
        actual_indexes = [segment.sequence_index for segment in segments]
        expected_indexes = list(range(1, rotation.expected_segment_count + 1))
        if actual_indexes != expected_indexes:
            raise ValidationError(
                "El perfil necessita tots els segments esperats, ordenats i sense buits."
            )

    _apply_transition(
        instance=rotation,
        previous_status=previous_status,
        target_status=target_status,
        reviewer=reviewer,
    )
    _record_event(
        instance=rotation,
        previous_status=previous_status,
        reviewer=reviewer,
        reason=reason,
        snapshot=_rotation_snapshot(rotation, segments),
    )
    return EditorialTransition(rotation, previous_status)
