"""Bounded professional-knowledge projections for the training agent."""

from django.db.models import Case, IntegerField, Q, Value, When

from iatrain_motion.models import EditorialStatus, MotionConcept, MotionRelation


PROFESSIONAL_CONCEPT_KINDS = (
    MotionConcept.Kind.SEGMENT,
    MotionConcept.Kind.JOINT,
    MotionConcept.Kind.JOINT_ACTION,
    MotionConcept.Kind.MUSCLE,
    MotionConcept.Kind.MUSCLE_GROUP,
)


def search_professional_concepts(*, query, kinds=(), limit=20):
    """Resolve natural-language targets to validated canonical graph concepts."""

    requested_kinds = tuple(kinds) or PROFESSIONAL_CONCEPT_KINDS
    queryset = MotionConcept.objects.filter(
        editorial_status=EditorialStatus.VALIDATED,
        kind__in=requested_kinds,
    )
    tokens = [part for part in str(query or "").split() if len(part) >= 2][:8]
    if tokens:
        text_filter = Q()
        score = Value(0, output_field=IntegerField())
        for token in tokens:
            text_filter |= (
                Q(code__icontains=token)
                | Q(name__icontains=token)
                | Q(definition__icontains=token)
            )
            score = score + Case(
                When(code__icontains=token, then=Value(6)),
                When(name__icontains=token, then=Value(5)),
                When(definition__icontains=token, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        queryset = queryset.filter(text_filter)
        queryset = queryset.annotate(match_score=score).order_by(
            "-match_score", "kind", "name", "pk"
        )
    else:
        queryset = queryset.order_by("kind", "name", "pk")
    rows = list(queryset[: max(1, min(int(limit), 30))])
    concept_ids = [row.pk for row in rows]
    relations = MotionRelation.objects.filter(
        Q(source_id__in=concept_ids) | Q(target_id__in=concept_ids),
        editorial_status=EditorialStatus.VALIDATED,
    ).select_related("source", "target")
    relations_by_concept = {}
    for relation in relations:
        if relation.source_id in concept_ids:
            relations_by_concept.setdefault(relation.source_id, []).append(
                {
                    "direction": "outgoing",
                    "relation_type": relation.relation_type,
                    "source_code": relation.source.code,
                    "source_name": relation.source.name,
                    "source_kind": relation.source.kind,
                    "target_code": relation.target.code,
                    "target_name": relation.target.name,
                    "target_kind": relation.target.kind,
                }
            )
        if relation.target_id in concept_ids:
            relations_by_concept.setdefault(relation.target_id, []).append(
                {
                    "direction": "incoming",
                    "relation_type": relation.relation_type,
                    "source_code": relation.source.code,
                    "source_name": relation.source.name,
                    "source_kind": relation.source.kind,
                    "target_code": relation.target.code,
                    "target_name": relation.target.name,
                    "target_kind": relation.target.kind,
                }
            )
    return {
        "query": str(query or ""),
        "results": [
            {
                "concept_code": row.code,
                "name": row.name,
                "kind": row.kind,
                "definition": row.definition,
                "relations": relations_by_concept.get(row.pk, []),
                "editorial_status": row.editorial_status,
            }
            for row in rows
        ],
        "policy": {
            "validated_only": True,
            "absence_is_not_prohibition": True,
        },
    }


def _evidence_payload(link):
    evidence = link.evidence
    return {
        "code": evidence.code,
        "title": evidence.title,
        "source_type": evidence.source_type,
        "identifier": evidence.identifier,
        "url": evidence.url,
    }


def build_exercise_knowledge_support(*, revisions, max_claims_per_exercise=40):
    """Return auditable exercise -> phase -> professional-basis paths.

    Only validated professional dependencies and non-pending private links can
    support a grounded claim. A draft exercise may still be inspected when the
    caller has separately authorized it, but its editorial status remains visible.
    """

    results = []
    sources = {}
    for revision in revisions:
        phases = revision.phases.prefetch_related(
            "actions__action",
            "muscle_roles__muscle",
            "muscle_roles__action_function__action",
            "muscle_roles__action_function__context",
            "muscle_roles__action_function__evidence_links__evidence",
            "muscle_roles__stabilization_function__target_joint",
            "muscle_roles__stabilization_function__target_segment",
            "muscle_roles__stabilization_function__context",
            "muscle_roles__stabilization_function__evidence_links__evidence",
        )
        claims = []
        omitted = 0
        for phase in phases:
            for link in phase.actions.all():
                if (
                    link.action.editorial_status != EditorialStatus.VALIDATED
                    or link.verification_state == link.VerificationState.PENDING
                ):
                    continue
                claim = {
                    "claim_id": f"exercise:{revision.pk}:phase_action:{link.pk}",
                    "exercise_revision_id": revision.pk,
                    "phase_code": phase.code,
                    "phase_name": phase.name,
                    "phase_intent": phase.intent,
                    "claim_type": "joint_action",
                    "action_code": link.action.code,
                    "action_name": link.action.name,
                    "muscle_code": "",
                    "muscle_name": "",
                    "muscle_role": "",
                    "basis_type": "motion_concept",
                    "basis_code": link.action.code,
                    "target_code": link.action.code,
                    "expected_contraction": "not_applicable",
                    "verification_state": link.verification_state,
                    "rationale": link.rationale,
                    "evidence_codes": [],
                    "limitations": [
                        "Descriu una acció prevista de la fase; no és una mesura cinemàtica observada."
                    ],
                }
                if len(claims) < max_claims_per_exercise:
                    claims.append(claim)
                else:
                    omitted += 1
            for role in phase.muscle_roles.all():
                basis = role.action_function or role.stabilization_function
                if (
                    role.muscle.editorial_status != EditorialStatus.VALIDATED
                    or basis is None
                    or basis.editorial_status != EditorialStatus.VALIDATED
                    or role.verification_state == role.VerificationState.PENDING
                ):
                    continue
                if role.action_function_id:
                    basis_type = "action_function"
                    action_code = basis.action.code
                    action_name = basis.action.name
                    target_code = basis.action.code
                else:
                    basis_type = "stabilization_function"
                    action_code = ""
                    action_name = ""
                    target_code = (basis.target_joint or basis.target_segment).code
                evidence_rows = [
                    _evidence_payload(link) for link in basis.evidence_links.all()
                ]
                for source in evidence_rows:
                    sources[source["code"]] = source
                limitations = [
                    "És una inferència funcional; no confirma activació muscular real."
                ]
                if basis.limitations.strip():
                    limitations.append(basis.limitations.strip())
                claim = {
                    "claim_id": f"exercise:{revision.pk}:muscle_role:{role.pk}",
                    "exercise_revision_id": revision.pk,
                    "phase_code": phase.code,
                    "phase_name": phase.name,
                    "phase_intent": phase.intent,
                    "claim_type": "muscle_role",
                    "action_code": action_code,
                    "action_name": action_name,
                    "muscle_code": role.muscle.code,
                    "muscle_name": role.muscle.name,
                    "muscle_role": role.role,
                    "basis_type": basis_type,
                    "basis_code": basis.code,
                    "target_code": target_code,
                    "expected_contraction": role.expected_contraction,
                    "verification_state": role.verification_state,
                    "rationale": role.rationale,
                    "evidence_codes": [row["code"] for row in evidence_rows],
                    "limitations": limitations,
                }
                if len(claims) < max_claims_per_exercise:
                    claims.append(claim)
                else:
                    omitted += 1
        results.append(
            {
                "exercise_revision_id": revision.pk,
                "exercise_code": revision.exercise.code,
                "exercise_name": revision.exercise.name,
                "exercise_editorial_status": revision.editorial_status,
                "support_status": "grounded" if claims else "knowledge_gap",
                "claims": claims,
                "omitted_claims": omitted,
            }
        )
    return {
        "results": results,
        "sources": list(sources.values()),
        "policy": {
            "professional_dependencies_validated_only": True,
            "pending_links_excluded": True,
            "activation_is_observed": False,
            "absence_is_not_prohibition": True,
        },
    }
