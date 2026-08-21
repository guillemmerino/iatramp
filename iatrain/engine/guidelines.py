"""Versioned professional baselines and exercise-specific guideline resolution."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from iatrain_exercises.models import (
    ExerciseObjective,
    ExercisePrescriptionGuideline,
    ExerciseRevision,
)


GUIDELINE_VERSION = "professional-baselines-1.1"
PROFESSIONAL_SOURCES = (
    {
        "title": "NSCA Youth Resistance Training Position Statement",
        "url": "https://www.nsca.com/globalassets/about/position-statements/position_stand_youth_resistance_training---2009.pdf",
        "scope": "youth_strength_power",
    },
    {
        "title": "ACSM Resistance Training Prescription Position Stand (2026)",
        "url": "https://acsm.org/resistance-training-guidelines-update-2026/",
        "scope": "adult_resistance_training",
    },
    {
        "title": "IOC Consensus Statement on Youth Athletic Development",
        "url": "https://bjsm.bmj.com/content/49/13/843",
        "scope": "individualization_youth_health",
    },
)


@dataclass(frozen=True, slots=True)
class AthletePrescriptionProfile:
    population_stage: str
    experience_level: str
    age_years: int | None
    training_years: Decimal | None


@dataclass(frozen=True, slots=True)
class ResolvedGuideline:
    dose_mode: str
    min_sets: int
    default_sets: int
    max_sets: int
    min_repetitions: int | None
    default_repetitions: int | None
    max_repetitions: int | None
    min_duration_seconds: int | None
    default_duration_seconds: int | None
    max_duration_seconds: int | None
    min_rest_seconds: int
    default_rest_seconds: int
    max_rest_seconds: int
    min_rpe: Decimal | None
    max_rpe: Decimal | None
    setup_duration_seconds: int
    seconds_per_repetition: Decimal | None
    mechanical_impact: Decimal
    neuromuscular_load: Decimal
    metabolic_load: Decimal
    coordinative_load: Decimal
    quality_stop_rule: str
    source: str
    source_url: str
    is_exercise_specific: bool


def _age_on(birth_date, on_date):
    if not birth_date:
        return None
    return on_date.year - birth_date.year - (
        (on_date.month, on_date.day) < (birth_date.month, birth_date.day)
    )


def athlete_prescription_profile(athlete_payload, *, on_date=None):
    on_date = on_date or date.today()
    athlete = athlete_payload.get("athlete", {})
    age = athlete.get("age_years")
    if age is None and athlete.get("birth_date"):
        try:
            age = _age_on(date.fromisoformat(athlete["birth_date"]), on_date)
        except (TypeError, ValueError):
            age = None
    if age is None:
        stage = ExercisePrescriptionGuideline.PopulationStage.ALL
    elif age < 12:
        stage = ExercisePrescriptionGuideline.PopulationStage.CHILD
    elif age < 18:
        stage = ExercisePrescriptionGuideline.PopulationStage.ADOLESCENT
    elif age < 65:
        stage = ExercisePrescriptionGuideline.PopulationStage.ADULT
    else:
        stage = ExercisePrescriptionGuideline.PopulationStage.OLDER_ADULT

    earliest = None
    level_tokens = []
    for sport in athlete_payload.get("sport_profiles", []):
        level_tokens.append(str(sport.get("level_code", "")).casefold())
        started = sport.get("training_started_on")
        if started:
            try:
                parsed = date.fromisoformat(started)
            except (TypeError, ValueError):
                continue
            earliest = parsed if earliest is None or parsed < earliest else earliest
    training_years = None
    if earliest:
        training_years = Decimal(str(max((on_date - earliest).days / 365.25, 0))).quantize(
            Decimal("0.1")
        )
    joined_levels = " ".join(level_tokens)
    if any(token in joined_levels for token in ("elit", "alt_rendiment", "advanced", "avanç")):
        experience = ExercisePrescriptionGuideline.ExperienceLevel.ADVANCED
    elif any(token in joined_levels for token in ("intermedi", "intermediate", "competic")):
        experience = ExercisePrescriptionGuideline.ExperienceLevel.INTERMEDIATE
    elif training_years is None or training_years < 1:
        experience = ExercisePrescriptionGuideline.ExperienceLevel.NOVICE
    elif training_years < 3:
        experience = ExercisePrescriptionGuideline.ExperienceLevel.INTERMEDIATE
    else:
        experience = ExercisePrescriptionGuideline.ExperienceLevel.ADVANCED
    return AthletePrescriptionProfile(stage, experience, age, training_years)


def _baseline(objective, experience, population_stage, execution_type, modality):
    novice = experience == ExercisePrescriptionGuideline.ExperienceLevel.NOVICE
    advanced = experience == ExercisePrescriptionGuideline.ExperienceLevel.ADVANCED
    mode = "repetitions"
    sets = (1, 2, 3)
    reps = (8, 10, 15)
    duration = (None, None, None)
    rest = (45, 60, 120)
    rpe = (Decimal("4"), Decimal("7"))
    loads = [Decimal("2"), Decimal("2"), Decimal("2"), Decimal("2")]
    stop_rule = "Atura la sèrie quan es perdi la tècnica prevista o aparegui dolor."

    if objective == ExerciseObjective.Objective.POWER:
        sets = (1, 2 if novice else 3, 4)
        reps = (3, 4, 6)
        rest = (75, 120, 240)
        rpe = (Decimal("4"), Decimal("7"))
        loads = [Decimal("3.5"), Decimal("4"), Decimal("1.5"), Decimal("4")]
        stop_rule = "Atura quan disminueixi clarament la velocitat, la qualitat o la recepció."
    elif objective == ExerciseObjective.Objective.MAX_STRENGTH:
        sets = (2, 3, 4)
        reps = (3 if advanced else 5, 5 if advanced else 8, 10)
        rest = (90, 150, 300)
        rpe = (Decimal("6"), Decimal("8.5"))
        loads = [Decimal("3"), Decimal("4"), Decimal("2"), Decimal("2.5")]
    elif objective == ExerciseObjective.Objective.HYPERTROPHY:
        sets = (2, 3, 4)
        reps = (6, 10, 15)
        rest = (60, 90, 180)
        rpe = (Decimal("6"), Decimal("9"))
        loads = [Decimal("2.5"), Decimal("3"), Decimal("3"), Decimal("2")]
    elif objective == ExerciseObjective.Objective.MUSCULAR_ENDURANCE:
        sets = (1, 2, 3)
        reps = (12, 15, 25)
        rest = (20, 45, 90)
        rpe = (Decimal("4"), Decimal("8"))
        loads = [Decimal("2"), Decimal("2"), Decimal("4"), Decimal("2")]
    elif objective == ExerciseObjective.Objective.MOTOR_CONTROL:
        sets = (1, 2, 3)
        reps = (5, 8, 12)
        rest = (30, 60, 120)
        rpe = (Decimal("3"), Decimal("6"))
        loads = [Decimal("1.5"), Decimal("2"), Decimal("1.5"), Decimal("4")]
    elif objective == ExerciseObjective.Objective.MOBILITY:
        mode = "duration"
        sets = (1, 1, 2)
        reps = (None, None, None)
        duration = (20, 30, 45)
        rest = (10, 20, 45)
        rpe = (Decimal("2"), Decimal("5"))
        loads = [Decimal("1"), Decimal("1"), Decimal("1"), Decimal("2.5")]
    elif objective == ExerciseObjective.Objective.PREPARATION:
        sets = (1, 1, 2)
        reps = (5, 8, 12)
        rest = (10, 30, 60)
        rpe = (Decimal("2"), Decimal("5"))
        loads = [Decimal("1.5"), Decimal("1.5"), Decimal("1.5"), Decimal("2.5")]
    elif novice:
        sets = (1, 1, 2)
        reps = (10, 12, 15)
        rest = (45, 60, 90)
        rpe = (Decimal("3"), Decimal("6"))
    elif advanced:
        sets = (2, 3, 4)
        reps = (6, 8, 12)
        rest = (60, 120, 240)
        rpe = (Decimal("5"), Decimal("8.5"))

    # Stage and experience remain separate axes. These envelopes preserve an
    # advanced youth athlete's training age while avoiding adult-only defaults.
    if population_stage == ExercisePrescriptionGuideline.PopulationStage.CHILD:
        sets = (sets[0], min(sets[1], 2), min(sets[2], 3))
        rpe = (min(rpe[0], Decimal("5")), min(rpe[1], Decimal("7.5")))
        if reps[1] is not None and objective == ExerciseObjective.Objective.MAX_STRENGTH:
            reps = (max(reps[0], 5), max(reps[1], 6), max(reps[2], 10))
        stop_rule = (
            "En població infantil prioritza domini tècnic, supervisió i progressió gradual. "
            + stop_rule
        )
    elif population_stage == ExercisePrescriptionGuideline.PopulationStage.ADOLESCENT:
        sets = (sets[0], sets[1], min(sets[2], 4))
        rpe = (rpe[0], min(rpe[1], Decimal("8")))
        stop_rule = "En adolescents progressa segons competència tècnica i maduració. " + stop_rule
    elif population_stage == ExercisePrescriptionGuideline.PopulationStage.OLDER_ADULT:
        sets = (sets[0], min(sets[1], 2), min(sets[2], 3))
        rpe = (min(rpe[0], Decimal("5")), min(rpe[1], Decimal("7.5")))
        if reps[1] is not None and objective != ExerciseObjective.Objective.POWER:
            reps = (max(reps[0], 6), max(reps[1], 8), max(reps[2], 12))
        stop_rule = (
            "En adults grans inicia amb familiarització, estabilitat i progressió gradual. "
            + stop_rule
        )

    if execution_type == ExerciseRevision.ExecutionType.ISOMETRIC:
        mode = "hold"
        reps = (None, None, None)
        duration = (10, 20 if novice else 30, 45)
    if modality == ExerciseRevision.Modality.WARM_UP:
        sets = (1, 1, min(2, sets[2]))
        rest = (0, min(rest[1], 30), min(rest[2], 60))
        rpe = (Decimal("2"), Decimal("5"))
    return mode, sets, reps, duration, rest, rpe, loads, stop_rule


def _specific_guideline(revision, *, profile, objective, block_role):
    rows = [row for row in revision.prescription_guidelines.all() if row.is_active]
    eligible = []
    for row in rows:
        if row.objective != objective:
            continue
        if row.population_stage not in {profile.population_stage, "all"}:
            continue
        if row.experience_level not in {profile.experience_level, "all"}:
            continue
        if row.block_role not in {block_role, "all"}:
            continue
        specificity = sum(
            (
                row.population_stage != "all",
                row.experience_level != "all",
                row.block_role != "all",
            )
        )
        eligible.append((specificity, row))
    return max(eligible, key=lambda pair: (pair[0], pair[1].pk))[1] if eligible else None


def resolve_guideline(revision, *, profile, objective, block_role):
    specific = _specific_guideline(
        revision, profile=profile, objective=objective, block_role=block_role
    )
    if specific:
        return ResolvedGuideline(
            dose_mode=specific.dose_mode,
            min_sets=specific.min_sets,
            default_sets=specific.default_sets,
            max_sets=specific.max_sets,
            min_repetitions=specific.min_repetitions,
            default_repetitions=specific.default_repetitions,
            max_repetitions=specific.max_repetitions,
            min_duration_seconds=specific.min_duration_seconds,
            default_duration_seconds=specific.default_duration_seconds,
            max_duration_seconds=specific.max_duration_seconds,
            min_rest_seconds=specific.min_rest_seconds,
            default_rest_seconds=specific.default_rest_seconds,
            max_rest_seconds=specific.max_rest_seconds,
            min_rpe=specific.min_rpe,
            max_rpe=specific.max_rpe,
            setup_duration_seconds=specific.setup_duration_seconds,
            seconds_per_repetition=specific.seconds_per_repetition,
            mechanical_impact=specific.mechanical_impact,
            neuromuscular_load=specific.neuromuscular_load,
            metabolic_load=specific.metabolic_load,
            coordinative_load=specific.coordinative_load,
            quality_stop_rule=specific.quality_stop_rule,
            source=specific.source_title,
            source_url=specific.source_url,
            is_exercise_specific=True,
        )
    mode, sets, reps, duration, rest, rpe, loads, stop_rule = _baseline(
        objective,
        profile.experience_level,
        profile.population_stage,
        revision.execution_type,
        revision.modality,
    )
    return ResolvedGuideline(
        dose_mode=mode,
        min_sets=sets[0],
        default_sets=sets[1],
        max_sets=sets[2],
        min_repetitions=reps[0],
        default_repetitions=reps[1],
        max_repetitions=reps[2],
        min_duration_seconds=duration[0],
        default_duration_seconds=duration[1],
        max_duration_seconds=duration[2],
        min_rest_seconds=rest[0],
        default_rest_seconds=rest[1],
        max_rest_seconds=rest[2],
        min_rpe=rpe[0],
        max_rpe=rpe[1],
        setup_duration_seconds=20,
        seconds_per_repetition=Decimal("4") if reps[1] else None,
        mechanical_impact=loads[0],
        neuromuscular_load=loads[1],
        metabolic_load=loads[2],
        coordinative_load=loads[3],
        quality_stop_rule=stop_rule,
        source=(
            f"{GUIDELINE_VERSION} · baseline professional · "
            f"{profile.population_stage}/{profile.experience_level}"
        ),
        source_url="",
        is_exercise_specific=False,
    )
