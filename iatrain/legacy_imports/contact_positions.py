from dataclasses import dataclass

from django.db import transaction

from iatrain.models import KnowledgeConcept, KnowledgeRelation

from .main_elements import CONTACT_POSITIONS, LEGACY_PROJECT, LEGACY_TABLE


CONTACT_POSITION_DEFINITIONS = (
    {
        "code": "feet",
        "name": "Contacte dempeus",
        "aliases": ["Dempeus", "De peu", "Feet"],
        "description": (
            "Configuració de contacte amb la tela del trampolí sobre els peus, "
            "utilitzada com a inici o final d'un element."
        ),
    },
    {
        "code": "seat",
        "name": "Contacte assegut",
        "aliases": ["Assegut", "Seat"],
        "description": (
            "Configuració de contacte asseguda sobre la tela del trampolí, amb les "
            "cames esteses cap endavant."
        ),
    },
    {
        "code": "front",
        "name": "Contacte de pit",
        "aliases": ["De pit", "Pit", "Front"],
        "description": (
            "Configuració de contacte frontal amb la tela del trampolí, habitualment "
            "anomenada caiguda de pit."
        ),
    },
    {
        "code": "back",
        "name": "Contacte d'esquena",
        "aliases": ["D'esquena", "Esquena", "Back"],
        "description": (
            "Configuració de contacte dorsal amb la tela del trampolí, habitualment "
            "anomenada caiguda d'esquena."
        ),
    },
    {
        "code": "all_fours",
        "name": "Contacte de quatre potes",
        "aliases": ["Quatre potes", "All fours"],
        "description": (
            "Configuració de contacte sobre mans i genolls utilitzada en determinades "
            "progressions d'entrenament. La seva admissibilitat competitiva depèn de "
            "les regles aplicables i no de l'estat editorial del concepte."
        ),
    },
)


@dataclass(frozen=True)
class ContactPositionImportSummary:
    positions_created: int = 0
    positions_existing: int = 0
    start_relations_created: int = 0
    start_relations_existing: int = 0
    end_relations_created: int = 0
    end_relations_existing: int = 0
    relations_skipped_conflict: int = 0
    unsupported_legacy_contacts: int = 0


def _contact_concept(*, definition, author):
    existing = KnowledgeConcept.objects.filter(
        name__iexact=definition["name"],
        kind=KnowledgeConcept.Kind.CONTACT_POSITION,
        discipline__iexact="trampoline",
    ).first()
    if existing is not None:
        return existing, False

    concept = KnowledgeConcept(
        name=definition["name"],
        description=definition["description"],
        kind=KnowledgeConcept.Kind.CONTACT_POSITION,
        discipline="trampoline",
        editorial_status=KnowledgeConcept.EditorialStatus.DRAFT,
        authored_by=author,
        attributes={
            "contact_code": definition["code"],
            "aliases": definition["aliases"],
            "needs_review": True,
        },
    )
    concept.full_clean()
    concept.save()
    return concept, True


def _legacy_sources(concept):
    return [
        source
        for source in list((concept.attributes or {}).get("legacy_sources") or [])
        if source.get("project") == LEGACY_PROJECT and source.get("table") == LEGACY_TABLE
    ]


def _create_relation(*, source, target, relation_type, legacy_source, author):
    existing = KnowledgeRelation.objects.filter(
        source=source,
        relation_type=relation_type,
    ).first()
    if existing is not None:
        return "existing" if existing.target_id == target.pk else "conflict"

    contact_role = (
        "configuració inicial"
        if relation_type == KnowledgeRelation.RelationType.STARTS_FROM_CONTACT
        else "configuració final"
    )
    raw_contact = (
        legacy_source.get("legacy_start_position")
        if relation_type == KnowledgeRelation.RelationType.STARTS_FROM_CONTACT
        else legacy_source.get("legacy_end_position")
    )
    original_name = legacy_source.get("original_name", source.name)
    relation = KnowledgeRelation(
        source=source,
        target=target,
        relation_type=relation_type,
        rationale=(
            f"Proposta derivada del registre legacy «{original_name}», que indica "
            f"«{raw_contact}» com a {contact_role}; pendent de revisió editorial."
        ),
        editorial_status=KnowledgeRelation.EditorialStatus.DRAFT,
        authored_by=author,
    )
    relation.full_clean()
    relation.save()
    return "created"


@transaction.atomic
def import_contact_positions(*, author):
    """Create contact-position concepts and draft start/end relations."""
    positions = {}
    positions_created = 0
    positions_existing = 0
    start_relations_created = 0
    start_relations_existing = 0
    end_relations_created = 0
    end_relations_existing = 0
    relations_skipped_conflict = 0
    unsupported_legacy_contacts = 0

    for definition in CONTACT_POSITION_DEFINITIONS:
        position, created = _contact_concept(definition=definition, author=author)
        positions[definition["code"]] = position
        if created:
            positions_created += 1
        else:
            positions_existing += 1

    skills = KnowledgeConcept.objects.filter(
        kind=KnowledgeConcept.Kind.SKILL,
        discipline__iexact="trampoline",
    ).order_by("id")
    for skill in skills:
        sources = _legacy_sources(skill)
        if not sources:
            continue
        legacy_source = sources[0]
        relation_specs = (
            (
                KnowledgeRelation.RelationType.STARTS_FROM_CONTACT,
                legacy_source.get("legacy_start_position"),
            ),
            (
                KnowledgeRelation.RelationType.ENDS_IN_CONTACT,
                legacy_source.get("legacy_end_position"),
            ),
        )
        for relation_type, raw_contact in relation_specs:
            contact_code = CONTACT_POSITIONS.get(raw_contact)
            target = positions.get(contact_code)
            if target is None:
                unsupported_legacy_contacts += 1
                continue
            result = _create_relation(
                source=skill,
                target=target,
                relation_type=relation_type,
                legacy_source=legacy_source,
                author=author,
            )
            if result == "conflict":
                relations_skipped_conflict += 1
            elif relation_type == KnowledgeRelation.RelationType.STARTS_FROM_CONTACT:
                if result == "created":
                    start_relations_created += 1
                else:
                    start_relations_existing += 1
            elif result == "created":
                end_relations_created += 1
            else:
                end_relations_existing += 1

    return ContactPositionImportSummary(
        positions_created=positions_created,
        positions_existing=positions_existing,
        start_relations_created=start_relations_created,
        start_relations_existing=start_relations_existing,
        end_relations_created=end_relations_created,
        end_relations_existing=end_relations_existing,
        relations_skipped_conflict=relations_skipped_conflict,
        unsupported_legacy_contacts=unsupported_legacy_contacts,
    )

