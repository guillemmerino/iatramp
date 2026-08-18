from dataclasses import dataclass

from django.db import transaction

from iatrain.models import ElementNotation, ElementRotation, ElementRotationSegment, KnowledgeConcept
from iatrain.rotation_notation import NotationParseError, parse_rotation_notation

from .main_elements import LEGACY_PROJECT, LEGACY_TABLE


@dataclass(frozen=True)
class RotationNotationImportSummary:
    profiles_created: int = 0
    profiles_existing: int = 0
    profile_conflicts: int = 0
    segments_created: int = 0
    notations_created: int = 0
    notations_existing: int = 0
    invalid_notations: int = 0


def _legacy_source(concept):
    for source in list((concept.attributes or {}).get("legacy_sources") or []):
        if source.get("project") == LEGACY_PROJECT and source.get("table") == LEGACY_TABLE:
            return source
    return None


def _profile_signature(profile):
    return (
        profile.transverse_quarters,
        profile.transverse_direction,
        tuple(
            profile.segments.order_by("sequence_index").values_list(
                "longitudinal_half_turns", flat=True
            )
        ),
    )


def _parsed_signature(parsed):
    return (
        parsed.transverse_quarters,
        parsed.transverse_direction,
        parsed.longitudinal_half_turns,
    )


def _notation_details(*, parsed=None, source=None, body_shape_hint=None, error=""):
    details = {
        "legacy_source": source or {},
        "legacy_body_shape_hint": body_shape_hint,
    }
    if parsed is not None:
        details.update(
            {
                "transverse_quarters": parsed.transverse_quarters,
                "transverse_direction": parsed.transverse_direction,
                "longitudinal_half_turns": list(parsed.longitudinal_half_turns),
                "position_code": parsed.position_code,
            }
        )
    if error:
        details["error"] = error
    return details


def _create_invalid_notation(*, element, raw_notation, source, author, error):
    notation = ElementNotation(
        element=element,
        scheme="fig_numeric",
        scheme_version="legacy",
        raw_notation=raw_notation,
        parse_status=ElementNotation.ParseStatus.INVALID,
        direction_source=ElementNotation.ResolutionSource.UNKNOWN,
        position_source=ElementNotation.ResolutionSource.UNKNOWN,
        parse_details=_notation_details(
            source=source,
            body_shape_hint=(element.attributes or {}).get("body_shape"),
            error=error,
        ),
        authored_by=author,
    )
    notation.full_clean()
    notation.save()
    return notation


@transaction.atomic
def import_rotation_notations(*, author):
    """Parse legacy notation into draft profiles without inferring omitted positions."""
    profiles_created = 0
    profiles_existing = 0
    profile_conflicts = 0
    segments_created = 0
    notations_created = 0
    notations_existing = 0
    invalid_notations = 0

    elements = KnowledgeConcept.objects.filter(
        kind=KnowledgeConcept.Kind.SKILL,
        discipline__iexact="trampoline",
    ).order_by("id")
    for element in elements:
        raw_notation = (element.attributes or {}).get("legacy_numeric_notation")
        source = _legacy_source(element)
        if not raw_notation or source is None:
            continue

        existing_notation = ElementNotation.objects.filter(
            element=element,
            scheme="fig_numeric",
            raw_notation=raw_notation,
        ).first()
        try:
            parsed = parse_rotation_notation(raw_notation)
        except NotationParseError as exc:
            if existing_notation is None:
                _create_invalid_notation(
                    element=element,
                    raw_notation=raw_notation,
                    source=source,
                    author=author,
                    error=str(exc),
                )
                notations_created += 1
            else:
                notations_existing += 1
            invalid_notations += 1
            continue

        try:
            profile = element.rotation_profile
        except ElementRotation.DoesNotExist:
            profile = ElementRotation(
                element=element,
                transverse_quarters=parsed.transverse_quarters,
                transverse_direction=parsed.transverse_direction,
                editorial_status=KnowledgeConcept.EditorialStatus.DRAFT,
                authored_by=author,
                provenance={
                    "project": LEGACY_PROJECT,
                    "table": LEGACY_TABLE,
                    "legacy_id": source.get("legacy_id"),
                    "raw_notation": raw_notation,
                },
            )
            profile.full_clean()
            profile.save()
            for index, half_turns in enumerate(parsed.longitudinal_half_turns, start=1):
                segment = ElementRotationSegment(
                    rotation=profile,
                    sequence_index=index,
                    longitudinal_half_turns=half_turns,
                )
                segment.full_clean()
                segment.save()
                segments_created += 1
            profiles_created += 1
            profile_is_compatible = True
        else:
            profile_is_compatible = _profile_signature(profile) == _parsed_signature(parsed)
            if profile_is_compatible:
                profiles_existing += 1
            else:
                profile_conflicts += 1

        if existing_notation is not None:
            notations_existing += 1
            continue

        notation = ElementNotation(
            element=element,
            rotation=profile if profile_is_compatible else None,
            scheme="fig_numeric",
            scheme_version="legacy",
            raw_notation=raw_notation,
            normalized_notation=parsed.normalized_notation,
            parse_status=(
                ElementNotation.ParseStatus.PARSED
                if profile_is_compatible
                else ElementNotation.ParseStatus.AMBIGUOUS
            ),
            is_abbreviated=parsed.is_abbreviated,
            direction_source=parsed.direction_source,
            position_source=parsed.position_source,
            position_symbol=parsed.position_symbol,
            parse_details=_notation_details(
                parsed=parsed,
                source=source,
                body_shape_hint=(element.attributes or {}).get("body_shape"),
                error=(
                    "La interpretació entra en conflicte amb el perfil de rotació existent."
                    if not profile_is_compatible
                    else ""
                ),
            ),
            authored_by=author,
        )
        notation.full_clean()
        notation.save()
        notations_created += 1

    return RotationNotationImportSummary(
        profiles_created=profiles_created,
        profiles_existing=profiles_existing,
        profile_conflicts=profile_conflicts,
        segments_created=segments_created,
        notations_created=notations_created,
        notations_existing=notations_existing,
        invalid_notations=invalid_notations,
    )

