from dataclasses import dataclass

from django.db import transaction

from iatrain.models import KnowledgeConcept


LEGACY_PROJECT = "tramponline"
LEGACY_TABLE = "EntrenosApp_elementosprincipales"


# This is a faithful transcription of the 47 rows in
# tramponline/elementosprincipales.sql. Canonical names are intentionally
# Catalan proposals: every imported concept remains in draft until reviewed.
MAIN_ELEMENTS = (
    (1, "Bote", "Bot", 1, "En Plancha", "00", "DE PIE", "DE PIE"),
    (2, "Agrupado", "Agrupat", 1, "Agrupado", "00", "DE PIE", "DE PIE"),
    (3, "Carpa Abierta", "Carpa oberta", 1, None, "00", "DE PIE", "DE PIE"),
    (4, "Carpa Cerrada", "Carpa tancada", 1, "En Carpa", "00", "DE PIE", "DE PIE"),
    (5, "Medio Giro", "Mig gir", 1, "En Plancha", "01", "DE PIE", "DE PIE"),
    (6, "Giro Entero", "Gir complet", 1, "En Plancha", "02", "DE PIE", "DE PIE"),
    (7, "Caída a Sentado", "Caiguda assegut", 1, None, "00", "DE PIE", "SENTADO"),
    (8, "Caída a Pecho", "Caiguda de pit", 1, None, ".10", "DE PIE", "DE PECHO"),
    (9, "Caída a Espalda", "Caiguda d'esquena", 1, None, "10.", "DE PIE", "DE ESPALDAS"),
    (10, "Mortal Adelante Agrupado", "Mortal endavant agrupat", 2, "Agrupado", ".40", "DE PIE", "DE PIE"),
    (11, "Mortal Adelante en Carpa", "Mortal endavant carpat", 2, "En Carpa", ".40", "DE PIE", "DE PIE"),
    (12, "Barany Agrupado", "Barani agrupat", 2, "Agrupado", ".41", "DE PIE", "DE PIE"),
    (13, "Barany en Carpa", "Barani carpat", 2, "En Carpa", ".41", "DE PIE", "DE PIE"),
    (14, "Barany en Plancha", "Barani planxat", 2, "En Plancha", ".41", "DE PIE", "DE PIE"),
    (15, "Mortal Atrás Agrupado", "Mortal enrere agrupat", 2, "Agrupado", "40.", "DE PIE", "DE PIE"),
    (16, "Mortal Atrás en Carpa", "Mortal enrere carpat", 2, "En Carpa", "40.", "DE PIE", "DE PIE"),
    (17, "Mortal Atrás en Plancha", "Mortal enrere planxat", 2, "En Plancha", "40.", "DE PIE", "DE PIE"),
    (18, "Tres Cuartos Adelante", "Tres quarts endavant", 2, None, ".30", "DE PIE", "DE ESPALDAS"),
    (19, "Pirueta Adelante", "Pirueta endavant", 2, "En Plancha", ".42", "DE PIE", "DE PIE"),
    (20, "Tres Cuartos Atrás", "Tres quarts enrere", 2, None, "30.", "DE PIE", "DE PECHO"),
    (21, "Rudy", "Rudy", 3, "En Plancha", ".43", "DE PIE", "DE PIE"),
    (23, "Barany Ball Out Agrupado", "Barani ball out agrupat", 3, "Agrupado", ".501", "DE ESPALDAS", "DE PIE"),
    (24, "Barany Ball Out en Plancha", "Barani ball out planxat", 3, "En Plancha", ".501", "DE ESPALDAS", "DE PIE"),
    (25, "Cody", "Cody", 3, "Agrupado", "500.", "DE PECHO", "DE PIE"),
    (26, "Pirueta Atrás", "Pirueta enrere", 3, "En Plancha", "42.", "DE PIE", "DE PIE"),
    (27, "Mortal Tres Cuartos Agrupado", "Mortal tres quarts agrupat", 3, "Agrupado", "700.", "DE PIE", "DE ESPALDAS"),
    (28, "Mortal Tres Cuartos en Carpa", "Mortal tres quarts carpat", 3, "En Carpa", "700.", "DE PIE", "DE ESPALDAS"),
    (29, "Half Out Agrupado", "Half out agrupat", 4, "Agrupado", ".801", "DE PIE", "DE PIE"),
    (30, "Half Out en Carpa", "Half out carpat", 4, "En Carpa", ".801", "DE PIE", "DE PIE"),
    (31, "Doble Mortal Atrás Agrupado", "Doble mortal enrere agrupat", 4, "Agrupado", "800.", "DE PIE", "DE PIE"),
    (32, "Doble Mortal Atrás en Carpa", "Doble mortal enrere carpat", 4, "En Carpa", "800.", "DE PIE", "DE PIE"),
    (33, "Doble Mortal Atrás en Plancha", "Doble mortal enrere planxat", 4, "En Plancha", "800.", "DE PIE", "DE PIE"),
    (34, "Rudy Out Agrupado", "Rudy out agrupat", 4, "Agrupado", ".803", "DE PIE", "DE PIE"),
    (35, "Rudy Out en Carpa", "Rudy out carpat", 4, "En Carpa", ".803", "DE PIE", "DE PIE"),
    (36, "Half In Half Out Agrupado", "Half in half out agrupat", 4, "Agrupado", "811.", "DE PIE", "DE PIE"),
    (37, "Half In Half Out en Carpa", "Half in half out carpat", 4, "En Carpa", "811.", "DE PIE", "DE PIE"),
    (38, "Pirueta Barany Agrupada", "Pirueta barani agrupada", 4, "Agrupado", ".821", "DE PIE", "DE PIE"),
    (39, "Pirueta Barany en Carpa", "Pirueta barani carpada", 4, "En Carpa", ".821", "DE PIE", "DE PIE"),
    (40, "Pirueta Barany en Plancha", "Pirueta barani planxada", 4, "En Plancha", ".821", "DE PIE", "DE PIE"),
    (41, "Half In Rudy Out Agrupado", "Half in rudy out agrupat", 5, "Agrupado", "813.", "DE PIE", "DE PIE"),
    (42, "Half In Rudy Out en Carpa", "Half in rudy out carpat", 5, "En Carpa", "813.", "DE PIE", "DE PIE"),
    (43, "Full Full Agrupado", "Full full agrupat", 5, "Agrupado", "822.", "DE PIE", "DE PIE"),
    (44, "Full Full en Carpa", "Full full carpat", 5, "En Carpa", "822.", "DE PIE", "DE PIE"),
    (45, "Full Full en Plancha", "Full full planxat", 5, "En Plancha", "822.", "DE PIE", "DE PIE"),
    (46, "Pirueta Rudy Agrupada", "Pirueta rudy agrupada", 5, "Agrupado", ".823", "DE PIE", "DE PIE"),
    (47, "Pirueta Rudy en Carpa", "Pirueta rudy carpada", 5, "En Carpa", ".823", "DE PIE", "DE PIE"),
    (48, "Pirueta Rudy en Plancha", "Pirueta rudy planxada", 5, "En Plancha", ".823", "DE PIE", "DE PIE"),
)


BODY_SHAPES = {
    "Agrupado": "tuck",
    "En Carpa": "pike",
    "En Plancha": "straight",
}

CONTACT_POSITIONS = {
    "DE PIE": "feet",
    "SENTADO": "seat",
    "DE PECHO": "front",
    "DE ESPALDAS": "back",
    "DE 4 PATAS": "all_fours",
    "PLANO": "flat",
}


@dataclass(frozen=True)
class ImportSummary:
    created: int = 0
    updated: int = 0
    unchanged: int = 0


def _merged_attributes(concept, row, *, provenance_only=False):
    (
        legacy_id,
        legacy_name,
        canonical_name,
        legacy_level,
        legacy_position,
        legacy_notation,
        legacy_start,
        legacy_end,
    ) = row
    attributes = dict(concept.attributes or {})

    if not provenance_only:
        aliases = list(attributes.get("aliases") or [])
        if legacy_name.casefold() != canonical_name.casefold() and not any(
            alias.casefold() == legacy_name.casefold() for alias in aliases
        ):
            aliases.append(legacy_name)
        if aliases:
            attributes["aliases"] = aliases

        attributes.setdefault("legacy_level", legacy_level)
        attributes.setdefault("legacy_numeric_notation", legacy_notation)
        attributes.setdefault("start_position", CONTACT_POSITIONS[legacy_start])
        attributes.setdefault("end_position", CONTACT_POSITIONS[legacy_end])
        if legacy_position:
            attributes.setdefault("body_shape", BODY_SHAPES[legacy_position])
        attributes.setdefault("needs_review", True)

    source = {
        "project": LEGACY_PROJECT,
        "table": LEGACY_TABLE,
        "legacy_id": legacy_id,
        "original_name": legacy_name,
        "legacy_level": legacy_level,
        "legacy_position": legacy_position,
        "legacy_numeric_notation": legacy_notation,
        "legacy_start_position": legacy_start,
        "legacy_end_position": legacy_end,
    }
    sources = [
        existing
        for existing in list(attributes.get("legacy_sources") or [])
        if not (
            existing.get("project") == LEGACY_PROJECT
            and existing.get("table") == LEGACY_TABLE
            and existing.get("legacy_id") == legacy_id
        )
    ]
    sources.append(source)
    attributes["legacy_sources"] = sorted(sources, key=lambda item: item["legacy_id"])
    return attributes


@transaction.atomic
def import_main_elements(*, author):
    """Import the legacy main-element catalogue as attributable draft concepts."""
    created = 0
    updated = 0
    unchanged = 0

    for row in MAIN_ELEMENTS:
        legacy_name = row[1]
        canonical_name = row[2]
        concept = KnowledgeConcept.objects.filter(
            name__iexact=canonical_name,
            kind=KnowledgeConcept.Kind.SKILL,
            discipline__iexact="trampoline",
        ).first()

        if concept is None:
            concept = KnowledgeConcept(
                name=canonical_name,
                kind=KnowledgeConcept.Kind.SKILL,
                discipline="trampoline",
                editorial_status=KnowledgeConcept.EditorialStatus.DRAFT,
                authored_by=author,
                description=(
                    f"Element de trampolí importat del catàleg legacy «{legacy_name}»; "
                    "descripció tècnica pendent de revisió."
                ),
                attributes={},
            )
            concept.attributes = _merged_attributes(concept, row)
            concept.full_clean()
            concept.save()
            created += 1
            continue

        merged_attributes = _merged_attributes(
            concept,
            row,
            provenance_only=(
                concept.editorial_status == KnowledgeConcept.EditorialStatus.VALIDATED
            ),
        )
        if merged_attributes == concept.attributes:
            unchanged += 1
            continue
        concept.attributes = merged_attributes
        concept.full_clean()
        concept.save(update_fields=("attributes", "updated_at"))
        updated += 1

    return ImportSummary(created=created, updated=updated, unchanged=unchanged)
