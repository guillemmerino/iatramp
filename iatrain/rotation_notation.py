from dataclasses import dataclass


POSITION_SYMBOLS = {
    "o": "tuck",
    "<": "pike",
    "/": "straight",
}


class NotationParseError(ValueError):
    pass


class AmbiguousNotationError(NotationParseError):
    pass


@dataclass(frozen=True)
class ParsedRotationNotation:
    raw_notation: str
    normalized_notation: str
    transverse_quarters: int
    transverse_direction: str
    longitudinal_half_turns: tuple[int, ...]
    position_symbol: str = ""
    position_code: str | None = None
    direction_source: str = "unknown"
    position_source: str = "unknown"
    is_abbreviated: bool = False

    @property
    def segment_count(self):
        return len(self.longitudinal_half_turns)


@dataclass(frozen=True)
class _NumericCandidate:
    quarters: int
    half_turns: tuple[int, ...]
    shorthand: bool


def expected_segment_count(transverse_quarters):
    return max(1, (transverse_quarters + 3) // 4)


def _numeric_candidates(numeric_code):
    prefix_digit_count = 0
    for character in numeric_code:
        if not character.isdigit():
            break
        prefix_digit_count += 1

    candidates = []
    for prefix_length in range(1, prefix_digit_count + 1):
        quarter_token = numeric_code[:prefix_length]
        if len(quarter_token) > 1 and quarter_token.startswith("0"):
            continue
        twist_tokens = numeric_code[prefix_length:]
        if not twist_tokens or any(not (token.isdigit() or token == "-") for token in twist_tokens):
            continue

        quarters = int(quarter_token)
        segment_count = expected_segment_count(quarters)
        if len(twist_tokens) == segment_count:
            candidates.append(
                _NumericCandidate(
                    quarters=quarters,
                    half_turns=tuple(0 if token == "-" else int(token) for token in twist_tokens),
                    shorthand=False,
                )
            )
        elif len(twist_tokens) == 1 and twist_tokens in {"0", "-"} and segment_count > 1:
            candidates.append(
                _NumericCandidate(
                    quarters=quarters,
                    half_turns=(0,) * segment_count,
                    shorthand=True,
                )
            )
    return candidates


def parse_rotation_notation(raw_notation):
    """Parse trampoline notation into an unambiguous canonical rotation structure."""
    if not isinstance(raw_notation, str) or not raw_notation.strip():
        raise NotationParseError("La notació no pot quedar buida.")

    compact = "".join(raw_notation.strip().split()).lower()
    position_symbol = compact[-1] if compact[-1] in POSITION_SYMBOLS else ""
    position_code = POSITION_SYMBOLS.get(position_symbol)
    if position_symbol:
        compact = compact[:-1]

    has_forward_dot = compact.startswith(".")
    has_backward_dot = compact.endswith(".")
    if has_forward_dot and has_backward_dot:
        raise NotationParseError("La notació no pot indicar alhora rotació endavant i enrere.")
    if has_forward_dot:
        numeric_code = compact[1:]
        explicit_direction = "forward"
    elif has_backward_dot:
        numeric_code = compact[:-1]
        explicit_direction = "backward"
    else:
        numeric_code = compact
        explicit_direction = None
    if "." in numeric_code:
        raise NotationParseError("El punt de direcció està en una posició no vàlida.")
    if not numeric_code:
        raise NotationParseError("Falta el component numèric de la notació.")

    candidates = _numeric_candidates(numeric_code)
    exact_candidates = [candidate for candidate in candidates if not candidate.shorthand]
    preferred = exact_candidates or candidates
    if not preferred:
        raise NotationParseError(
            "No es pot separar de manera vàlida el nombre de quarts i els mig girs."
        )
    unique_candidates = {
        (candidate.quarters, candidate.half_turns, candidate.shorthand): candidate
        for candidate in preferred
    }
    if len(unique_candidates) != 1:
        raise AmbiguousNotationError("La notació admet més d'una interpretació estructural.")
    candidate = next(iter(unique_candidates.values()))

    if candidate.quarters == 0:
        if explicit_direction is not None:
            raise NotationParseError(
                "Un element sense rotació transversal no pot portar punt de direcció."
            )
        direction = "none"
        direction_source = "inferred"
    elif explicit_direction is None:
        direction = "unknown"
        direction_source = "unknown"
    else:
        direction = explicit_direction
        direction_source = "explicit"

    normalized_numeric = str(candidate.quarters) + "".join(
        str(half_turns) for half_turns in candidate.half_turns
    )
    if direction == "forward":
        normalized = "." + normalized_numeric
    elif direction == "backward":
        normalized = normalized_numeric + "."
    else:
        normalized = normalized_numeric
    normalized += position_symbol

    input_was_abbreviated = (
        candidate.shorthand
        or "-" in numeric_code
        or normalized != "".join(raw_notation.strip().split()).lower()
    )
    return ParsedRotationNotation(
        raw_notation=raw_notation.strip(),
        normalized_notation=normalized,
        transverse_quarters=candidate.quarters,
        transverse_direction=direction,
        longitudinal_half_turns=candidate.half_turns,
        position_symbol=position_symbol,
        position_code=position_code,
        direction_source=direction_source,
        position_source="explicit" if position_symbol else "unknown",
        is_abbreviated=input_was_abbreviated,
    )

