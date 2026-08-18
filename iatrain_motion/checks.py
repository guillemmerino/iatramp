from collections import defaultdict

from .models import (
    CanonicalJoint,
    CanonicalSegment,
    EditorialStatus,
    JointAngleDefinition,
    MotionConcept,
    MotionRelation,
    SkeletonSide,
)


def audit_motion_graph(*, include_drafts=False):
    """Return semantic integrity issues without mutating the professional graph."""
    concept_filter = {} if include_drafts else {"editorial_status": EditorialStatus.VALIDATED}
    relation_filter = {} if include_drafts else {"editorial_status": EditorialStatus.VALIDATED}
    concepts = list(MotionConcept.objects.filter(**concept_filter).exclude(editorial_status=EditorialStatus.RETIRED))
    relations = list(MotionRelation.objects.filter(**relation_filter).exclude(editorial_status=EditorialStatus.RETIRED))
    by_source = defaultdict(list)
    part_of = defaultdict(list)
    for relation in relations:
        by_source[(relation.source_id, relation.relation_type)].append(relation)
        if relation.relation_type == MotionRelation.RelationType.PART_OF:
            part_of[relation.source_id].append(relation.target_id)

    issues = []
    required_by_kind = {
        MotionConcept.Kind.JOINT: (
            MotionRelation.RelationType.PROXIMAL_SEGMENT,
            MotionRelation.RelationType.DISTAL_SEGMENT,
        ),
        MotionConcept.Kind.JOINT_ACTION: (
            MotionRelation.RelationType.ACTION_AT_JOINT,
            MotionRelation.RelationType.PRIMARY_PLANE,
            MotionRelation.RelationType.PRIMARY_AXIS,
        ),
    }
    for concept in concepts:
        for relation_type in required_by_kind.get(concept.kind, ()):
            count = len(by_source[(concept.pk, relation_type)])
            if count != 1:
                issues.append(f"{concept.code}: necessita exactament una relació {relation_type}; en té {count}.")

    visiting = set()
    visited = set()

    def visit(node_id):
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        if any(visit(parent_id) for parent_id in part_of[node_id]):
            return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    if any(visit(concept.pk) for concept in concepts if concept.kind == MotionConcept.Kind.SEGMENT):
        issues.append("La jerarquia part_of dels segments conté un cicle.")
    return issues


def audit_skeleton_schema(schema, *, require_validated_semantics=False):
    """Check that one measurable schema faithfully instantiates the semantic graph."""
    landmarks = list(schema.landmarks.all())
    segments = list(schema.segments.select_related("concept").all())
    joints = list(
        schema.joints.select_related(
            "concept", "center_landmark", "proximal_segment__concept", "distal_segment__concept"
        ).all()
    )
    angles = list(
        schema.angle_definitions.select_related(
            "joint__concept", "joint__proximal_segment", "joint__distal_segment",
            "positive_action", "negative_action", "plane", "axis"
        ).all()
    )
    issues = []
    if not landmarks:
        issues.append("L'esquema no conté cap punt canònic.")
    if not segments:
        issues.append("L'esquema no conté cap segment mesurable.")
    if not joints:
        issues.append("L'esquema no conté cap articulació canònica.")

    landmark_codes = {landmark.code for landmark in landmarks}
    for landmark in landmarks:
        if landmark.measurement_source == landmark.MeasurementSource.DERIVED:
            for input_code in landmark.derivation.get("inputs", []):
                if input_code not in landmark_codes:
                    issues.append(f"{landmark.code}: el punt d'entrada {input_code} no existeix.")
                if input_code == landmark.code:
                    issues.append(f"{landmark.code}: un punt no es pot derivar de si mateix.")

    for model_name, definitions in (("segment", segments), ("articulació", joints)):
        sides_by_concept = defaultdict(set)
        concepts = {}
        for definition in definitions:
            sides_by_concept[definition.concept_id].add(definition.side)
            concepts[definition.concept_id] = definition.concept
        for concept_id, sides in sides_by_concept.items():
            if concepts[concept_id].laterality == MotionConcept.Laterality.PAIRED and sides != {
                SkeletonSide.LEFT,
                SkeletonSide.RIGHT,
            }:
                issues.append(
                    f"{concepts[concept_id].code}: el {model_name} parell necessita costats esquerre i dret."
                )

    semantic_concepts = {
        definition.concept
        for definition in [*segments, *joints]
    }
    semantic_concepts.update(
        concept
        for angle in angles
        for concept in (angle.positive_action, angle.negative_action, angle.plane, angle.axis)
    )
    if require_validated_semantics:
        for concept in semantic_concepts:
            if concept.editorial_status != EditorialStatus.VALIDATED:
                issues.append(f"{concept.code}: el concepte semàntic encara no està validat.")

    relation_status_filter = (
        {"editorial_status": EditorialStatus.VALIDATED}
        if require_validated_semantics
        else {}
    )

    def semantic_edge_exists(source, relation_type, target):
        return MotionRelation.objects.filter(
            source=source,
            target=target,
            relation_type=relation_type,
            **relation_status_filter,
        ).exists()

    for joint in joints:
        expected = (
            (MotionRelation.RelationType.PROXIMAL_SEGMENT, joint.proximal_segment.concept),
            (MotionRelation.RelationType.DISTAL_SEGMENT, joint.distal_segment.concept),
        )
        for relation_type, segment_concept in expected:
            if not semantic_edge_exists(joint.concept, relation_type, segment_concept):
                issues.append(
                    f"{joint.code}: falta la relació semàntica {relation_type} cap a {segment_concept.code}."
                )

    for angle in angles:
        if angle.calculation_method == JointAngleDefinition.CalculationMethod.JOINT_COORDINATE_SYSTEM:
            capabilities = {
                angle.joint.proximal_segment.orientation_capability,
                angle.joint.distal_segment.orientation_capability,
            }
            if CanonicalSegment.OrientationCapability.FULL_3D not in capabilities or len(capabilities) != 1:
                issues.append(
                    f"{angle.code}: un sistema articular 3D necessita orientació 3D als dos segments."
                )
        for action in (angle.positive_action, angle.negative_action):
            expected = (
                (MotionRelation.RelationType.ACTION_AT_JOINT, angle.joint.concept),
                (MotionRelation.RelationType.PRIMARY_PLANE, angle.plane),
                (MotionRelation.RelationType.PRIMARY_AXIS, angle.axis),
            )
            for relation_type, target in expected:
                if not semantic_edge_exists(action, relation_type, target):
                    issues.append(
                        f"{angle.code}: {action.code} no té la relació {relation_type} esperada cap a {target.code}."
                    )
    return issues
