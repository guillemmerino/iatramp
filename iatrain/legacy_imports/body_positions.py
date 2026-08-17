from dataclasses import dataclass

from django.db import transaction

from iatrain.models import KnowledgeConcept, KnowledgeRelation

from .main_elements import LEGACY_PROJECT, LEGACY_TABLE


BODY_POSITIONS = (
    {
        "code": "tuck",
        "name": "Posició agrupada",
        "aliases": ["Agrupada", "Agrupat", "Tuck"],
        "description": (
            "Configuració corporal en què malucs i genolls es flexionen i el cos "
            "es manté recollit durant l'element."
        ),
    },
    {
        "code": "pike",
        "name": "Posició carpada",
        "aliases": ["Carpa", "Pike"],
        "description": (
            "Configuració corporal amb flexió dels malucs i les cames esteses durant "
            "l'element."
        ),
    },
    {
        "code": "straight",
        "name": "Posició en planxa",
        "aliases": ["Planxa", "Estesa", "Straight"],
        "description": (
            "Configuració corporal estesa, sense flexió marcada dels malucs ni dels "
            "genolls durant l'element."
        ),
    },
)


# Only legacy rows whose name explicitly makes the position part of the
# element's identity are proposed here. A legacy ``body_shape`` value alone is
# not enough: entries such as Bot, Cody or Rudy may describe an execution shape
# without proving that the position defines a distinct element.
DEFINING_POSITION_LEGACY_IDS = {
    "tuck": frozenset((2, 10, 12, 15, 23, 27, 29, 31, 34, 36, 38, 41, 43, 46)),
    "pike": frozenset((4, 11, 13, 16, 28, 30, 32, 35, 37, 39, 42, 44, 47)),
    "straight": frozenset((14, 17, 24, 33, 40, 45, 48)),
}


@dataclass(frozen=True)
class BodyPositionImportSummary:
    positions_created: int = 0
    positions_existing: int = 0
    relations_created: int = 0
    relations_existing: int = 0
    relations_skipped_conflict: int = 0


def _legacy_source_for(concept, legacy_id):
    for source in list((concept.attributes or {}).get("legacy_sources") or []):
        if (
            source.get("project") == LEGACY_PROJECT
            and source.get("table") == LEGACY_TABLE
            and source.get("legacy_id") == legacy_id
        ):
            return source
    return None


def _position_concept(*, definition, author):
    existing = KnowledgeConcept.objects.filter(
        name__iexact=definition["name"],
        kind=KnowledgeConcept.Kind.BODY_POSITION,
        discipline__iexact="trampoline",
    ).first()
    if existing is not None:
        return existing, False

    concept = KnowledgeConcept(
        name=definition["name"],
        description=definition["description"],
        kind=KnowledgeConcept.Kind.BODY_POSITION,
        discipline="trampoline",
        editorial_status=KnowledgeConcept.EditorialStatus.DRAFT,
        authored_by=author,
        attributes={
            "body_shape_code": definition["code"],
            "aliases": definition["aliases"],
            "needs_review": True,
        },
    )
    concept.full_clean()
    concept.save()
    return concept, True


@transaction.atomic
def import_body_positions(*, author):
    """Create body-position concepts and conservative draft legacy edges."""
    positions = {}
    positions_created = 0
    positions_existing = 0
    relations_created = 0
    relations_existing = 0
    relations_skipped_conflict = 0

    for definition in BODY_POSITIONS:
        position, created = _position_concept(definition=definition, author=author)
        positions[definition["code"]] = position
        if created:
            positions_created += 1
        else:
            positions_existing += 1

    skills = KnowledgeConcept.objects.filter(
        kind=KnowledgeConcept.Kind.SKILL,
        discipline__iexact="trampoline",
    ).order_by("id")
    skills_by_legacy_id = {}
    for skill in skills:
        for source in list((skill.attributes or {}).get("legacy_sources") or []):
            if source.get("project") == LEGACY_PROJECT and source.get("table") == LEGACY_TABLE:
                skills_by_legacy_id[source.get("legacy_id")] = skill

    for position_code, legacy_ids in DEFINING_POSITION_LEGACY_IDS.items():
        target = positions[position_code]
        for legacy_id in sorted(legacy_ids):
            source = skills_by_legacy_id.get(legacy_id)
            if source is None:
                continue
            existing = KnowledgeRelation.objects.filter(
                source=source,
                relation_type=KnowledgeRelation.RelationType.HAS_DEFINING_POSITION,
            ).first()
            if existing is not None:
                if existing.target_id == target.pk:
                    relations_existing += 1
                else:
                    relations_skipped_conflict += 1
                continue

            legacy_source = _legacy_source_for(source, legacy_id)
            original_name = legacy_source.get("original_name", source.name)
            relation = KnowledgeRelation(
                source=source,
                target=target,
                relation_type=KnowledgeRelation.RelationType.HAS_DEFINING_POSITION,
                rationale=(
                    f"Proposta derivada del registre legacy «{original_name}», que fa "
                    "explícita la posició com a part de la identitat de l'element; "
                    "pendent de revisió editorial."
                ),
                editorial_status=KnowledgeRelation.EditorialStatus.DRAFT,
                authored_by=author,
            )
            relation.full_clean()
            relation.save()
            relations_created += 1

    return BodyPositionImportSummary(
        positions_created=positions_created,
        positions_existing=positions_existing,
        relations_created=relations_created,
        relations_existing=relations_existing,
        relations_skipped_conflict=relations_skipped_conflict,
    )

