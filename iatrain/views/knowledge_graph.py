import json

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from iatrain.models import ElementNotation, ElementRotation, KnowledgeConcept, KnowledgeRelation
from iatrain.views.common import base_context


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
        "author": relation.authored_by.display_name,
        "createdAt": relation.created_at.isoformat(),
        "updatedAt": relation.updated_at.isoformat(),
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
        }
    )
    return render(request, "iatrain/knowledge_graph/index.html", context)


@require_GET
def knowledge_graph_data(request):
    _require_superuser(request)
    concepts = (
        KnowledgeConcept.objects.select_related("authored_by", "rotation_profile")
        .prefetch_related("rotation_profile__segments", "rotation_notations")
        .order_by("id")
    )
    relations = KnowledgeRelation.objects.select_related(
        "source", "target", "authored_by"
    ).order_by("id")
    return JsonResponse(
        {
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
@transaction.atomic
def knowledge_concept_status(request, pk):
    _require_superuser(request)
    concept = get_object_or_404(
        KnowledgeConcept.objects.select_for_update().select_related("authored_by"),
        pk=pk,
    )
    try:
        status = _requested_status(request)
        if status == KnowledgeConcept.EditorialStatus.RETIRED:
            has_validated_relations = KnowledgeRelation.objects.filter(
                Q(source=concept) | Q(target=concept),
                editorial_status=KnowledgeRelation.EditorialStatus.VALIDATED,
            ).exists()
            if has_validated_relations:
                raise ValidationError(
                    "Retira primer les relacions validades connectades a aquest concepte."
                )
        previous_status = concept.editorial_status
        if previous_status != status:
            concept.editorial_status = status
            concept.full_clean()
            concept.save(update_fields=("editorial_status", "updated_at"))
            _log_status_change(
                request=request,
                instance=concept,
                previous_status=previous_status,
            )
    except ValidationError as exc:
        return _validation_error_response(exc)
    return JsonResponse({"node": _concept_payload(concept)})


@require_POST
@transaction.atomic
def knowledge_relation_status(request, pk):
    _require_superuser(request)
    relation = get_object_or_404(
        KnowledgeRelation.objects.select_for_update().select_related(
            "source", "target", "authored_by"
        ),
        pk=pk,
    )
    try:
        status = _requested_status(request)
        if status == KnowledgeRelation.EditorialStatus.VALIDATED and (
            relation.source.editorial_status
            != KnowledgeConcept.EditorialStatus.VALIDATED
            or relation.target.editorial_status
            != KnowledgeConcept.EditorialStatus.VALIDATED
        ):
            raise ValidationError(
                "Valida primer els dos conceptes connectats per aquesta relació."
            )
        previous_status = relation.editorial_status
        if previous_status != status:
            relation.editorial_status = status
            relation.full_clean()
            relation.save(update_fields=("editorial_status", "updated_at"))
            _log_status_change(
                request=request,
                instance=relation,
                previous_status=previous_status,
            )
    except ValidationError as exc:
        return _validation_error_response(exc)
    return JsonResponse({"link": _relation_payload(relation)})
