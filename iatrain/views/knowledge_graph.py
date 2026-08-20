import json

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from iatrain.models import ElementNotation, ElementRotation, KnowledgeConcept, KnowledgeRelation
from iatrain.editorial import (
    transition_knowledge_concept,
    transition_knowledge_relation,
)
from iatrain.views.common import base_context
from iatrain_motion.editorial import transition_motion_concept, transition_motion_relation
from iatrain_motion.models import MotionConcept, MotionRelation
from iatrain_biomechanics.models import MuscleActionFunction, MuscleStabilizationFunction


EDITORIAL_STATUSES = {
    KnowledgeConcept.EditorialStatus.DRAFT,
    KnowledgeConcept.EditorialStatus.VALIDATED,
    KnowledgeConcept.EditorialStatus.RETIRED,
}


def _require_superuser(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        raise PermissionDenied("Aquesta eina és exclusiva per a superusuaris.")


def _concept_payload(concept):
    try:
        rotation = concept.rotation_profile
    except ElementRotation.DoesNotExist:
        rotation_payload = None
    else:
        notations = list(concept.rotation_notations.all())
        primary_notation = next(
            (
                notation
                for notation in notations
                if notation.parse_status == ElementNotation.ParseStatus.PARSED
            ),
            notations[0] if notations else None,
        )
        rotation_payload = {
            "transverseQuarters": rotation.transverse_quarters,
            "transverseDirection": rotation.transverse_direction,
            "halfTurns": [
                segment.longitudinal_half_turns
                for segment in rotation.segments.all()
            ],
            "status": rotation.editorial_status,
            "lastValidatedBy": (
                rotation.last_validated_by.display_name
                if rotation.last_validated_by_id
                else ""
            ),
            "lastValidatedAt": (
                rotation.last_validated_at.isoformat()
                if rotation.last_validated_at
                else ""
            ),
            "rawNotation": primary_notation.raw_notation if primary_notation else "",
            "normalizedNotation": (
                primary_notation.normalized_notation if primary_notation else ""
            ),
            "parseStatus": primary_notation.parse_status if primary_notation else "",
            "isAbbreviated": (
                primary_notation.is_abbreviated if primary_notation else False
            ),
            "directionSource": (
                primary_notation.direction_source if primary_notation else "unknown"
            ),
            "positionSource": (
                primary_notation.position_source if primary_notation else "unknown"
            ),
            "positionSymbol": (
                primary_notation.position_symbol if primary_notation else ""
            ),
        }
    return {
        "id": concept.pk,
        "name": concept.name,
        "description": concept.description,
        "kind": concept.kind,
        "discipline": concept.discipline,
        "status": concept.editorial_status,
        "lastValidatedBy": (
            concept.last_validated_by.display_name if concept.last_validated_by_id else ""
        ),
        "lastValidatedAt": (
            concept.last_validated_at.isoformat() if concept.last_validated_at else ""
        ),
        "author": concept.authored_by.display_name,
        "attributes": concept.attributes,
        "rotation": rotation_payload,
        "createdAt": concept.created_at.isoformat(),
        "updatedAt": concept.updated_at.isoformat(),
    }


def _relation_payload(relation):
    return {
        "id": relation.pk,
        "source": relation.source_id,
        "target": relation.target_id,
        "relationType": relation.relation_type,
        "rationale": relation.rationale,
        "status": relation.editorial_status,
        "lastValidatedBy": (
            relation.last_validated_by.display_name if relation.last_validated_by_id else ""
        ),
        "lastValidatedAt": (
            relation.last_validated_at.isoformat() if relation.last_validated_at else ""
        ),
        "author": relation.authored_by.display_name,
        "createdAt": relation.created_at.isoformat(),
        "updatedAt": relation.updated_at.isoformat(),
    }


def _motion_concept_payload(concept):
    return {
        "id": concept.pk,
        "code": concept.code,
        "name": concept.name,
        "description": concept.definition,
        "kind": concept.kind,
        "laterality": concept.laterality,
        "discipline": "anatomia funcional",
        "status": concept.editorial_status,
        "lastValidatedBy": (
            concept.last_validated_by.display_name if concept.last_validated_by_id else ""
        ),
        "lastValidatedAt": (
            concept.last_validated_at.isoformat() if concept.last_validated_at else ""
        ),
        "author": concept.authored_by.display_name,
        "attributes": {"provenance": concept.provenance},
        "createdAt": concept.created_at.isoformat(),
        "updatedAt": concept.updated_at.isoformat(),
    }


def _motion_relation_payload(relation):
    return {
        "id": relation.pk,
        "source": relation.source_id,
        "target": relation.target_id,
        "relationType": relation.relation_type,
        "rationale": relation.rationale,
        "status": relation.editorial_status,
        "lastValidatedBy": (
            relation.last_validated_by.display_name if relation.last_validated_by_id else ""
        ),
        "lastValidatedAt": (
            relation.last_validated_at.isoformat() if relation.last_validated_at else ""
        ),
        "author": relation.authored_by.display_name,
        "attributes": {"provenance": relation.provenance},
        "createdAt": relation.created_at.isoformat(),
        "updatedAt": relation.updated_at.isoformat(),
    }


def _muscle_action_function_payload(function):
    return {
        "id": f"action-{function.pk}",
        "source": function.muscle_id,
        "target": function.action_id,
        "relationType": "contributes_to_action",
        "rationale": function.statement,
        "status": function.editorial_status,
        "author": function.authored_by.display_name,
        "attributes": {
            "contributionClass": function.contribution_class,
            "context": function.context.code if function.context_id else None,
            "conditions": function.conditions,
            "limitations": function.limitations,
        },
        "createdAt": function.created_at.isoformat(),
        "updatedAt": function.updated_at.isoformat(),
    }


def _stabilization_function_payload(function):
    target = function.target_joint or function.target_segment
    return {
        "id": f"stabilization-{function.pk}",
        "source": function.muscle_id,
        "target": target.pk,
        "relationType": (
            "stabilizes_joint" if function.target_joint_id else "stabilizes_segment"
        ),
        "rationale": function.statement,
        "status": function.editorial_status,
        "author": function.authored_by.display_name,
        "attributes": {
            "stabilizationType": function.stabilization_type,
            "context": function.context.code if function.context_id else None,
            "conditions": function.conditions,
            "limitations": function.limitations,
        },
        "createdAt": function.created_at.isoformat(),
        "updatedAt": function.updated_at.isoformat(),
    }


@require_GET
def knowledge_graph(request):
    _require_superuser(request)
    context = base_context(request)
    context.update(
        {
            "concept_count": KnowledgeConcept.objects.count(),
            "relation_count": KnowledgeRelation.objects.count(),
            "draft_count": KnowledgeConcept.objects.filter(
                editorial_status=KnowledgeConcept.EditorialStatus.DRAFT
            ).count(),
            "motion_concept_count": MotionConcept.objects.count(),
            "motion_relation_count": MotionRelation.objects.count(),
            "biomechanical_function_count": (
                MuscleActionFunction.objects.count()
                + MuscleStabilizationFunction.objects.count()
            ),
        }
    )
    return render(request, "iatrain/knowledge_graph/index.html", context)


@require_GET
def knowledge_graph_data(request):
    _require_superuser(request)
    domain = request.GET.get("domain", "technical")
    if domain == "motion":
        concepts = MotionConcept.objects.select_related(
            "authored_by", "last_validated_by"
        ).order_by("id")
        relations = MotionRelation.objects.select_related(
            "source", "target", "authored_by", "last_validated_by"
        ).order_by("id")
        return JsonResponse(
            {
                "domain": "motion",
                "nodes": [_motion_concept_payload(concept) for concept in concepts],
                "links": [_motion_relation_payload(relation) for relation in relations],
            }
        )
    if domain == "biomechanics":
        action_functions = list(
            MuscleActionFunction.objects.select_related(
                "muscle", "action", "context", "authored_by"
            ).order_by("id")
        )
        stabilization_functions = list(
            MuscleStabilizationFunction.objects.select_related(
                "muscle", "target_joint", "target_segment", "context", "authored_by"
            ).order_by("id")
        )
        endpoint_ids = {
            endpoint_id
            for function in action_functions
            for endpoint_id in (function.muscle_id, function.action_id)
        }
        endpoint_ids.update(
            endpoint_id
            for function in stabilization_functions
            for endpoint_id in (
                function.muscle_id,
                function.target_joint_id,
                function.target_segment_id,
            )
            if endpoint_id
        )
        stable_relations = list(
            MotionRelation.objects.select_related(
                "source", "target", "authored_by", "last_validated_by"
            ).filter(
                relation_type__in=(
                    MotionRelation.RelationType.MEMBER_OF_MUSCLE_GROUP,
                    MotionRelation.RelationType.SPANS_JOINT,
                )
            ).order_by("id")
        )
        endpoint_ids.update(
            endpoint_id
            for relation in stable_relations
            for endpoint_id in (relation.source_id, relation.target_id)
        )
        concepts = MotionConcept.objects.select_related(
            "authored_by", "last_validated_by"
        ).filter(pk__in=endpoint_ids).order_by("id")
        return JsonResponse(
            {
                "domain": "biomechanics",
                "readOnly": True,
                "nodes": [_motion_concept_payload(concept) for concept in concepts],
                "links": (
                    [_motion_relation_payload(relation) for relation in stable_relations]
                    + [_muscle_action_function_payload(function) for function in action_functions]
                    + [
                        _stabilization_function_payload(function)
                        for function in stabilization_functions
                    ]
                ),
            }
        )
    if domain != "technical":
        return JsonResponse({"error": "Domini de graf desconegut."}, status=400)
    concepts = (
        KnowledgeConcept.objects.select_related(
            "authored_by", "last_validated_by", "rotation_profile__last_validated_by"
        )
        .prefetch_related("rotation_profile__segments", "rotation_notations")
        .order_by("id")
    )
    relations = KnowledgeRelation.objects.select_related(
        "source", "target", "authored_by", "last_validated_by"
    ).order_by("id")
    return JsonResponse(
        {
            "domain": "technical",
            "nodes": [_concept_payload(concept) for concept in concepts],
            "links": [_relation_payload(relation) for relation in relations],
        }
    )


def _requested_status(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError as exc:
        raise ValidationError("La petició no conté JSON vàlid.") from exc
    status = payload.get("status")
    if status not in EDITORIAL_STATUSES:
        raise ValidationError("Estat editorial desconegut.")
    return status


def _validation_error_response(exc):
    if hasattr(exc, "message_dict"):
        message = " ".join(
            message
            for messages in exc.message_dict.values()
            for message in messages
        )
    else:
        message = " ".join(exc.messages)
    return JsonResponse({"error": message}, status=400)


def _log_status_change(*, request, instance, previous_status):
    LogEntry.objects.log_action(
        user_id=request.user.pk,
        content_type_id=ContentType.objects.get_for_model(instance).pk,
        object_id=str(instance.pk),
        object_repr=str(instance),
        action_flag=CHANGE,
        change_message=(
            f"Estat editorial canviat de {previous_status} a {instance.editorial_status} "
            "des del graf de coneixement 3D."
        ),
    )


@require_POST
def knowledge_concept_status(request, pk):
    _require_superuser(request)
    concept = get_object_or_404(KnowledgeConcept, pk=pk)
    try:
        status = _requested_status(request)
        transition = transition_knowledge_concept(
            user=request.user,
            concept=concept,
            target_status=status,
        )
        concept = transition.instance
        if transition.previous_status != status:
            _log_status_change(
                request=request,
                instance=concept,
                previous_status=transition.previous_status,
            )
    except ValidationError as exc:
        return _validation_error_response(exc)
    return JsonResponse({"node": _concept_payload(concept)})


@require_POST
def knowledge_relation_status(request, pk):
    _require_superuser(request)
    relation = get_object_or_404(KnowledgeRelation, pk=pk)
    try:
        status = _requested_status(request)
        transition = transition_knowledge_relation(
            user=request.user,
            relation=relation,
            target_status=status,
        )
        relation = transition.instance
        if transition.previous_status != status:
            _log_status_change(
                request=request,
                instance=relation,
                previous_status=transition.previous_status,
            )
    except ValidationError as exc:
        return _validation_error_response(exc)
    return JsonResponse({"link": _relation_payload(relation)})


@require_POST
def motion_concept_status(request, pk):
    _require_superuser(request)
    concept = get_object_or_404(MotionConcept, pk=pk)
    try:
        status = _requested_status(request)
        transition = transition_motion_concept(
            user=request.user,
            concept=concept,
            target_status=status,
        )
        concept = transition.instance
        if transition.previous_status != status:
            _log_status_change(
                request=request,
                instance=concept,
                previous_status=transition.previous_status,
            )
    except ValidationError as exc:
        return _validation_error_response(exc)
    return JsonResponse({"node": _motion_concept_payload(concept)})


@require_POST
def motion_relation_status(request, pk):
    _require_superuser(request)
    relation = get_object_or_404(MotionRelation, pk=pk)
    try:
        status = _requested_status(request)
        transition = transition_motion_relation(
            user=request.user,
            relation=relation,
            target_status=status,
        )
        relation = transition.instance
        if transition.previous_status != status:
            _log_status_change(
                request=request,
                instance=relation,
                previous_status=transition.previous_status,
            )
    except ValidationError as exc:
        return _validation_error_response(exc)
    return JsonResponse({"link": _motion_relation_payload(relation)})
