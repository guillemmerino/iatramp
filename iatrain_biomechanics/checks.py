from django.db.models import Q

from iatrain_motion.models import EditorialStatus, MotionConcept, MotionRelation

from .models import MuscleActionFunction, MuscleStabilizationFunction


def _relation_queryset(*, include_drafts):
    queryset = MotionRelation.objects.exclude(editorial_status=EditorialStatus.RETIRED)
    if not include_drafts:
        queryset = queryset.filter(editorial_status=EditorialStatus.VALIDATED)
    return queryset


def action_joint(action, *, include_drafts):
    relations = list(
        _relation_queryset(include_drafts=include_drafts).filter(
            source=action,
            relation_type=MotionRelation.RelationType.ACTION_AT_JOINT,
        )
    )
    return relations[0].target if len(relations) == 1 else None


def _muscle_has_group(muscle, *, include_drafts):
    return _relation_queryset(include_drafts=include_drafts).filter(
        source=muscle,
        relation_type=MotionRelation.RelationType.MEMBER_OF_MUSCLE_GROUP,
    ).exists()


def audit_action_function(function, *, require_validated=False):
    issues = []
    include_drafts = not require_validated
    if function.muscle.kind != MotionConcept.Kind.MUSCLE:
        issues.append(f"{function.code}: l'origen no és un múscul.")
    if function.action.kind != MotionConcept.Kind.JOINT_ACTION:
        issues.append(f"{function.code}: el destí no és una acció articular.")
    if not _muscle_has_group(function.muscle, include_drafts=include_drafts):
        issues.append(f"{function.code}: el múscul no pertany a cap grup muscular disponible.")
    if require_validated:
        for concept in (function.muscle, function.action):
            if concept.editorial_status != EditorialStatus.VALIDATED:
                issues.append(f"{function.code}: {concept.code} encara no està validat.")
        if function.context_id and function.context.editorial_status != EditorialStatus.VALIDATED:
            issues.append(f"{function.code}: el context encara no està validat.")
    joint = action_joint(function.action, include_drafts=include_drafts)
    if joint is None:
        issues.append(f"{function.code}: l'acció no té exactament una articulació disponible.")
    elif not _relation_queryset(include_drafts=include_drafts).filter(
        source=function.muscle,
        target=joint,
        relation_type=MotionRelation.RelationType.SPANS_JOINT,
    ).exists():
        issues.append(
            f"{function.code}: {function.muscle.code} no declara que travessa {joint.code}."
        )
    if require_validated and not function.evidence_links.filter(
        relationship__in=("supports", "qualifies")
    ).exists():
        issues.append(f"{function.code}: falta evidència que sostingui o matisi l'afirmació.")
    return issues


def audit_stabilization_function(function, *, require_validated=False):
    issues = []
    include_drafts = not require_validated
    if function.muscle.kind != MotionConcept.Kind.MUSCLE:
        issues.append(f"{function.code}: l'origen no és un múscul.")
    if not _muscle_has_group(function.muscle, include_drafts=include_drafts):
        issues.append(f"{function.code}: el múscul no pertany a cap grup muscular disponible.")
    target = function.target_joint or function.target_segment
    if target is None:
        issues.append(f"{function.code}: falta l'objectiu estabilitzat.")
    if require_validated:
        for concept in filter(None, (function.muscle, target)):
            if concept.editorial_status != EditorialStatus.VALIDATED:
                issues.append(f"{function.code}: {concept.code} encara no està validat.")
        if function.context_id and function.context.editorial_status != EditorialStatus.VALIDATED:
            issues.append(f"{function.code}: el context encara no està validat.")
    if function.target_joint_id and not _relation_queryset(include_drafts=include_drafts).filter(
        source=function.muscle,
        target=function.target_joint,
        relation_type=MotionRelation.RelationType.SPANS_JOINT,
    ).exists():
        issues.append(
            f"{function.code}: {function.muscle.code} no declara que travessa "
            f"{function.target_joint.code}."
        )
    if require_validated and not function.evidence_links.filter(
        relationship__in=("supports", "qualifies")
    ).exists():
        issues.append(f"{function.code}: falta evidència que sostingui o matisi l'afirmació.")
    return issues


def audit_biomechanics(*, include_drafts=False):
    concept_filter = {} if include_drafts else {"editorial_status": EditorialStatus.VALIDATED}
    relation_qs = _relation_queryset(include_drafts=include_drafts)
    muscles = MotionConcept.objects.filter(
        kind=MotionConcept.Kind.MUSCLE,
        **concept_filter,
    ).exclude(editorial_status=EditorialStatus.RETIRED)
    groups = MotionConcept.objects.filter(
        kind=MotionConcept.Kind.MUSCLE_GROUP,
        **concept_filter,
    ).exclude(editorial_status=EditorialStatus.RETIRED)
    issues = []
    for muscle in muscles:
        if not relation_qs.filter(
            source=muscle,
            relation_type=MotionRelation.RelationType.MEMBER_OF_MUSCLE_GROUP,
        ).exists():
            issues.append(f"{muscle.code}: no pertany a cap grup muscular.")
        if not relation_qs.filter(
            source=muscle,
            relation_type=MotionRelation.RelationType.SPANS_JOINT,
        ).exists():
            issues.append(f"{muscle.code}: no declara cap articulació travessada.")
    for group in groups:
        if not relation_qs.filter(
            target=group,
            relation_type=MotionRelation.RelationType.MEMBER_OF_MUSCLE_GROUP,
        ).exists():
            issues.append(f"{group.code}: no conté cap múscul.")

    status_filter = {} if include_drafts else {"editorial_status": EditorialStatus.VALIDATED}
    action_functions = MuscleActionFunction.objects.filter(**status_filter).exclude(
        editorial_status=EditorialStatus.RETIRED
    ).select_related("muscle", "action", "context")
    for function in action_functions:
        issues.extend(audit_action_function(function, require_validated=not include_drafts))
        if include_drafts and not function.evidence_links.filter(
            relationship__in=("supports", "qualifies")
        ).exists():
            issues.append(f"{function.code}: falta evidència de suport o qualificació.")
    stabilization_functions = MuscleStabilizationFunction.objects.filter(**status_filter).exclude(
        editorial_status=EditorialStatus.RETIRED
    ).select_related("muscle", "target_joint", "target_segment", "context")
    for function in stabilization_functions:
        issues.extend(audit_stabilization_function(function, require_validated=not include_drafts))
        if include_drafts and not function.evidence_links.filter(
            relationship__in=("supports", "qualifies")
        ).exists():
            issues.append(f"{function.code}: falta evidència de suport o qualificació.")
    return issues
