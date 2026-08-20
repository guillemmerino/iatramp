from collections import OrderedDict
from django.core.paginator import Paginator
from django.db.models import OuterRef, Prefetch, Q, Subquery
from django.urls import reverse

from iatrain.library_visuals import exercise_illustration, family_illustration
from iatrain.models import KnowledgeConcept, KnowledgeRelation
from iatrain_exercises.models import (
    ExerciseObjective,
    ExercisePhase,
    ExerciseRevision,
)
from iatrain_motion.models import EditorialStatus


DOMAIN_ALL = "all"
DOMAIN_PHYSICAL = "physical"
DOMAIN_TECHNICAL = "technical"

ORIGIN_ALL = "all"
ORIGIN_PERSONAL = "personal"
ORIGIN_PROFESSIONAL = "professional"

RELATION_LABELS = {
    KnowledgeRelation.RelationType.REQUIRES: "Requereix",
    KnowledgeRelation.RelationType.PROGRESSES_TO: "Progressa cap a",
    KnowledgeRelation.RelationType.HAS_DEFINING_POSITION: "Posició característica",
    KnowledgeRelation.RelationType.STARTS_FROM_CONTACT: "Comença des de",
    KnowledgeRelation.RelationType.ENDS_IN_CONTACT: "Acaba en",
    KnowledgeRelation.RelationType.CORRECTS: "Corregeix",
    KnowledgeRelation.RelationType.CONDITIONS: "Condiciona",
    KnowledgeRelation.RelationType.TRAINS: "Entrena",
}

TECHNICAL_KIND_LABELS = {
    KnowledgeConcept.Kind.SKILL: "Element tècnic",
    KnowledgeConcept.Kind.EXERCISE: "Exercici tècnic",
}

def family_movement_badge(code):
    """Return a short, stable label only for unambiguous movement directions."""
    normalized = str(code or "").casefold()
    rules = (
        ("external_rotation", "ROT EXT", "Rotació externa"),
        ("internal_rotation", "ROT INT", "Rotació interna"),
        ("abduction", "AB", "Abducció"),
        ("adduction", "AD", "Adducció"),
    )
    for token, short_label, full_label in rules:
        if token in normalized:
            return {"short": short_label, "full": full_label}
    if normalized.endswith("_rotation"):
        return {"short": "ROT", "full": "Rotació"}
    if normalized.endswith("_flexion") or normalized.endswith("_curl"):
        return {"short": "FLEX", "full": "Flexió"}
    if normalized.endswith("_extension"):
        return {"short": "EXT", "full": "Extensió"}
    return None


def _matching_choice_codes(query, choices):
    normalized = query.casefold()
    return [
        value
        for value, label in choices
        if normalized in value.casefold() or normalized in str(label).casefold()
    ]


def _latest_personal_revisions(owner):
    latest_revision = (
        ExerciseRevision.objects.filter(exercise_id=OuterRef("exercise_id"))
        .order_by("-revision_number", "-pk")
        .values("pk")[:1]
    )
    return (
        ExerciseRevision.objects.filter(
            pk=Subquery(latest_revision),
            exercise__catalog__owner=owner,
            exercise__catalog__is_active=True,
            exercise__is_active=True,
            exercise__kind="variant",
        )
        .select_related("exercise", "exercise__parent", "exercise__catalog")
        .prefetch_related("equipment_requirements__equipment")
    )


def _physical_revision_for_detail(revision_id):
    phase_queryset = ExercisePhase.objects.prefetch_related(
        "actions__action",
        "muscle_roles__muscle",
        "muscle_roles__action_function",
        "muscle_roles__stabilization_function",
    )
    return (
        ExerciseRevision.objects.select_related(
            "exercise",
            "exercise__parent",
            "exercise__catalog",
            "authored_by",
        )
        .prefetch_related(
            "objectives",
            "equipment_requirements__equipment",
            "constraints",
            Prefetch("phases", queryset=phase_queryset),
        )
        .get(pk=revision_id)
    )


def _professional_concepts(*, include_drafts):
    visible_relations = KnowledgeRelation.objects.select_related("source", "target").exclude(
        editorial_status=KnowledgeRelation.EditorialStatus.RETIRED
    )
    if not include_drafts:
        visible_relations = visible_relations.filter(
            editorial_status=KnowledgeRelation.EditorialStatus.VALIDATED
        )
    queryset = KnowledgeConcept.objects.filter(
        discipline="trampoline",
        kind__in=(KnowledgeConcept.Kind.SKILL, KnowledgeConcept.Kind.EXERCISE),
    )
    if not include_drafts:
        queryset = queryset.filter(
            editorial_status=KnowledgeConcept.EditorialStatus.VALIDATED
        )
    return queryset.select_related("authored_by").prefetch_related(
        Prefetch("outgoing_relations", queryset=visible_relations, to_attr="library_outgoing"),
        Prefetch("incoming_relations", queryset=visible_relations, to_attr="library_incoming"),
    )


def _physical_search(queryset, query):
    if not query:
        return queryset
    modality_codes = _matching_choice_codes(query, ExerciseRevision.Modality.choices)
    execution_codes = _matching_choice_codes(query, ExerciseRevision.ExecutionType.choices)
    difficulty_codes = _matching_choice_codes(query, ExerciseRevision.Difficulty.choices)
    laterality_codes = _matching_choice_codes(query, ExerciseRevision.Laterality.choices)
    chain_codes = _matching_choice_codes(query, ExerciseRevision.KineticChain.choices)
    pattern_codes = _matching_choice_codes(query, ExerciseRevision.MovementPattern.choices)
    objective_codes = _matching_choice_codes(query, ExerciseObjective.Objective.choices)
    return queryset.filter(
        Q(exercise__name__icontains=query)
        | Q(exercise__parent__name__icontains=query)
        | Q(description__icontains=query)
        | Q(setup__icontains=query)
        | Q(execution__icontains=query)
        | Q(coaching_cues__icontains=query)
        | Q(objectives__objective__icontains=query)
        | Q(equipment_requirements__equipment__name__icontains=query)
        | Q(phases__actions__action__name__icontains=query)
        | Q(phases__actions__action__code__icontains=query)
        | Q(phases__muscle_roles__muscle__name__icontains=query)
        | Q(phases__muscle_roles__muscle__code__icontains=query)
        | Q(modality__in=modality_codes)
        | Q(execution_type__in=execution_codes)
        | Q(difficulty__in=difficulty_codes)
        | Q(laterality__in=laterality_codes)
        | Q(kinetic_chain__in=chain_codes)
        | Q(movement_pattern__in=pattern_codes)
        | Q(objectives__objective__in=objective_codes)
    ).distinct()


def _technical_search(queryset, query, *, include_drafts):
    if not query:
        return queryset
    visible_relation_statuses = [KnowledgeRelation.EditorialStatus.VALIDATED]
    if include_drafts:
        visible_relation_statuses.append(KnowledgeRelation.EditorialStatus.DRAFT)
    return queryset.filter(
        Q(name__icontains=query)
        | Q(description__icontains=query)
        | Q(
            outgoing_relations__target__name__icontains=query,
            outgoing_relations__editorial_status__in=visible_relation_statuses,
        )
        | Q(
            incoming_relations__source__name__icontains=query,
            incoming_relations__editorial_status__in=visible_relation_statuses,
        )
    ).distinct()


def _with_item_query(request, item_key):
    params = request.GET.copy()
    params["item"] = item_key
    encoded = params.urlencode()
    return f"{reverse('iatrain_library')}?{encoded}" if encoded else reverse("iatrain_library")


def _with_page_query(request, page_number):
    params = request.GET.copy()
    params["page"] = page_number
    params.pop("item", None)
    return f"{reverse('iatrain_library')}?{params.urlencode()}"


def _physical_summary(request, revision):
    equipment = [link.equipment.name for link in revision.equipment_requirements.all()]
    movement_badge = family_movement_badge(revision.exercise.parent.code)
    illustration = exercise_illustration(revision.exercise.code, revision.exercise.name)
    return {
        "key": f"physical:{revision.pk}",
        "name": revision.exercise.name,
        "family": revision.exercise.parent.name,
        "domain": DOMAIN_PHYSICAL,
        "domain_label": "Preparació física",
        "kind_label": "Variant executable",
        "origin": ORIGIN_PERSONAL,
        "origin_label": "El meu catàleg",
        "status": revision.editorial_status,
        "status_label": revision.get_editorial_status_display(),
        "description": revision.description,
        "movement_badge": movement_badge,
        "illustration": illustration,
        "tags": [
            revision.get_movement_pattern_display(),
            revision.get_difficulty_display(),
            *equipment[:2],
        ],
        "model": revision,
        "detail_url": _with_item_query(request, f"physical:{revision.pk}"),
    }


def _technical_summary(request, concept):
    related_labels = []
    for relation in getattr(concept, "library_outgoing", []):
        if relation.relation_type in {
            KnowledgeRelation.RelationType.HAS_DEFINING_POSITION,
            KnowledgeRelation.RelationType.STARTS_FROM_CONTACT,
            KnowledgeRelation.RelationType.ENDS_IN_CONTACT,
        }:
            related_labels.append(relation.target.name)
    return {
        "key": f"technical:{concept.pk}",
        "name": concept.name,
        "family": "Tècnica de trampolí",
        "domain": DOMAIN_TECHNICAL,
        "domain_label": "Tècnica de trampolí",
        "kind_label": TECHNICAL_KIND_LABELS.get(concept.kind, concept.kind.replace("_", " ").title()),
        "origin": ORIGIN_PROFESSIONAL,
        "origin_label": "Base professional",
        "status": concept.editorial_status,
        "status_label": concept.get_editorial_status_display(),
        "description": concept.description,
        "tags": [TECHNICAL_KIND_LABELS.get(concept.kind, concept.kind), *related_labels[:2]],
        "model": concept,
        "detail_url": _with_item_query(request, f"technical:{concept.pk}"),
    }


def _group_results(items):
    groups = OrderedDict()
    for item in items:
        if item["domain"] == DOMAIN_PHYSICAL:
            revision = item["model"]
            group_key = f"physical-family:{revision.exercise.parent_id}"
            illustration = family_illustration(
                revision.exercise.parent.code,
                revision.exercise.parent.name,
            )
            group = groups.setdefault(
                group_key,
                {
                    "key": group_key,
                    "name": item["family"],
                    "domain": DOMAIN_PHYSICAL,
                    "domain_label": "Preparació física",
                    "origin_label": "El meu catàleg",
                    "description": "Família d’exercicis amb variants executables.",
                    "movement_badge": item["movement_badge"],
                    "illustration": illustration,
                    "items": [],
                },
            )
            group["items"].append(item)
        else:
            groups[item["key"]] = {
                "key": item["key"],
                "name": item["name"],
                "domain": DOMAIN_TECHNICAL,
                "domain_label": item["domain_label"],
                "origin_label": item["origin_label"],
                "description": item["description"],
                "items": [item],
            }
    for group in groups.values():
        group["items"].sort(key=lambda item: item["name"].casefold())
        group["item_count"] = len(group["items"])
        group["primary_item"] = group["items"][0]
    return sorted(
        groups.values(),
        key=lambda group: (group["name"].casefold(), group["domain"]),
    )


def _physical_detail(item):
    revision = _physical_revision_for_detail(item["model"].pk)
    phases = []
    for phase in revision.phases.all():
        actions = [
            {
                "name": link.action.name,
                "role": link.get_role_display(),
                "verification": link.get_verification_state_display(),
                "verification_code": link.verification_state,
                "rationale": link.rationale,
            }
            for link in phase.actions.all()
        ]
        muscles = []
        for role in phase.muscle_roles.all():
            basis = role.action_function or role.stabilization_function
            muscles.append(
                {
                    "name": role.muscle.name,
                    "role": role.get_role_display(),
                    "contraction": role.get_expected_contraction_display(),
                    "basis": basis.code,
                    "verification": role.get_verification_state_display(),
                    "verification_code": role.verification_state,
                    "rationale": role.rationale,
                }
            )
        phases.append(
            {
                "name": phase.name,
                "description": phase.description,
                "intent": phase.get_intent_display(),
                "phase_type": phase.get_phase_type_display(),
                "is_key": phase.is_key_phase,
                "actions": actions,
                "muscles": muscles,
            }
        )
    return {
        **item,
        "setup": revision.setup,
        "execution": revision.execution,
        "coaching_cues": revision.coaching_cues,
        "safety_notes": revision.safety_notes,
        "classification": [
            revision.get_modality_display(),
            revision.get_execution_type_display(),
            revision.get_difficulty_display(),
            revision.get_laterality_display(),
            revision.get_kinetic_chain_display(),
            revision.get_movement_pattern_display(),
        ],
        "objectives": [row.get_objective_display() for row in revision.objectives.all()],
        "equipment": [
            {"name": row.equipment.name, "requirement": row.get_requirement_display()}
            for row in revision.equipment_requirements.all()
        ],
        "constraints": [
            {
                "statement": row.statement,
                "kind": row.get_kind_display(),
                "severity": row.get_severity_display(),
            }
            for row in revision.constraints.all()
        ],
        "phases": phases,
        "revision_number": revision.revision_number,
        "author": revision.authored_by.display_name,
    }


def _technical_detail(item):
    concept = item["model"]
    connections = []
    for relation in getattr(concept, "library_outgoing", []):
        connections.append(
            {
                "label": RELATION_LABELS.get(relation.relation_type, relation.relation_type),
                "target": relation.target.name,
                "direction": "outgoing",
                "rationale": relation.rationale,
                "status": relation.get_editorial_status_display(),
            }
        )
    for relation in getattr(concept, "library_incoming", []):
        connections.append(
            {
                "label": RELATION_LABELS.get(relation.relation_type, relation.relation_type),
                "target": relation.source.name,
                "direction": "incoming",
                "rationale": relation.rationale,
                "status": relation.get_editorial_status_display(),
            }
        )
    attributes = [
        {"name": str(key).replace("_", " ").title(), "value": value}
        for key, value in concept.attributes.items()
        if isinstance(value, (str, int, float, bool))
    ]
    return {
        **item,
        "connections": connections,
        "attributes": attributes,
        "author": concept.authored_by.display_name,
    }


def build_library(*, request, owner):
    query = request.GET.get("q", "").strip()[:160]
    domain = request.GET.get("domain", DOMAIN_ALL)
    if domain not in {DOMAIN_ALL, DOMAIN_PHYSICAL, DOMAIN_TECHNICAL}:
        domain = DOMAIN_ALL
    origin = request.GET.get("origin", ORIGIN_ALL)
    if origin not in {ORIGIN_ALL, ORIGIN_PERSONAL, ORIGIN_PROFESSIONAL}:
        origin = ORIGIN_ALL
    status = request.GET.get("status", "all")
    if status not in {"all", EditorialStatus.DRAFT, EditorialStatus.VALIDATED, EditorialStatus.RETIRED}:
        status = "all"
    difficulty = request.GET.get("difficulty", "all")
    difficulty_values = {value for value, _ in ExerciseRevision.Difficulty.choices}
    if difficulty not in difficulty_values | {"all"}:
        difficulty = "all"
    pattern = request.GET.get("pattern", "all")
    pattern_values = {value for value, _ in ExerciseRevision.MovementPattern.choices}
    if pattern not in pattern_values | {"all"}:
        pattern = "all"

    include_physical = domain in {DOMAIN_ALL, DOMAIN_PHYSICAL} and origin in {
        ORIGIN_ALL,
        ORIGIN_PERSONAL,
    }
    include_technical = domain in {DOMAIN_ALL, DOMAIN_TECHNICAL} and origin in {
        ORIGIN_ALL,
        ORIGIN_PROFESSIONAL,
    }

    physical_base = _latest_personal_revisions(owner)
    technical_base = _professional_concepts(include_drafts=request.user.is_superuser)
    counts = {
        "physical": physical_base.exclude(editorial_status=EditorialStatus.RETIRED).count(),
        "technical": technical_base.exclude(
            editorial_status=KnowledgeConcept.EditorialStatus.RETIRED
        ).count(),
    }

    items = []
    if include_physical:
        physical = physical_base
        if status == "all":
            physical = physical.exclude(editorial_status=EditorialStatus.RETIRED)
        else:
            physical = physical.filter(editorial_status=status)
        if difficulty != "all":
            physical = physical.filter(difficulty=difficulty)
        if pattern != "all":
            physical = physical.filter(movement_pattern=pattern)
        physical = _physical_search(physical, query)
        items.extend(_physical_summary(request, revision) for revision in physical)

    if include_technical and difficulty == "all" and pattern == "all":
        technical = technical_base
        if status == "all":
            technical = technical.exclude(
                editorial_status=KnowledgeConcept.EditorialStatus.RETIRED
            )
        else:
            technical = technical.filter(editorial_status=status)
        technical = _technical_search(
            technical,
            query,
            include_drafts=request.user.is_superuser,
        )
        items.extend(_technical_summary(request, concept) for concept in technical)

    all_groups = _group_results(items)
    page_obj = Paginator(all_groups, 18).get_page(request.GET.get("page"))
    groups = list(page_obj.object_list)
    item_index = {item["key"]: item for group in groups for item in group["items"]}
    selected_key = request.GET.get("item", "")
    selected_item = item_index.get(selected_key)
    if selected_item is None and groups:
        selected_item = groups[0]["primary_item"]
    for group in groups:
        group["is_selected"] = bool(
            selected_item and any(item["key"] == selected_item["key"] for item in group["items"])
        )
    selected_detail = None
    if selected_item:
        selected_detail = (
            _physical_detail(selected_item)
            if selected_item["domain"] == DOMAIN_PHYSICAL
            else _technical_detail(selected_item)
        )

    active_filters = sum(
        bool(value and value != "all")
        for value in (domain, origin, status, difficulty, pattern)
    ) + bool(query)
    return {
        "query": query,
        "domain": domain,
        "origin": origin,
        "status": status,
        "difficulty": difficulty,
        "pattern": pattern,
        "difficulty_options": ExerciseRevision.Difficulty.choices,
        "pattern_options": ExerciseRevision.MovementPattern.choices,
        "groups": groups,
        "result_count": len(items),
        "group_count": len(all_groups),
        "page_obj": page_obj,
        "previous_url": _with_page_query(request, page_obj.previous_page_number())
        if page_obj.has_previous()
        else "",
        "next_url": _with_page_query(request, page_obj.next_page_number())
        if page_obj.has_next()
        else "",
        "selected_item": selected_detail,
        "counts": counts,
        "active_filters": active_filters,
        "clear_url": reverse("iatrain_library"),
    }
