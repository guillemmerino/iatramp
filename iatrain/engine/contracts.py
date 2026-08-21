"""LLM-agnostic contracts at the training block generation boundary.

These value objects deliberately do not persist anything. A future natural
language interpreter may build them, but the engine and adapter only consume
the validated, typed representation.
"""

from dataclasses import dataclass, field
from decimal import Decimal


TARGET_INTENSITIES = ("low", "moderate", "high", "very_high")
BLOCK_PARTICIPANT_MODES = ("shared", "personalized", "excluded")
ATHLETE_ADJUSTMENT_ACTIONS = ("modify", "replace", "skip")
PHYSICAL_BLOCK_HARD_CONSTRAINTS = (
    "validated_only",
    "bodyweight_only",
    "no_equipment",
    "no_jumps",
    "no_impact",
    "avoid_high_impact",
    "avoid_failure",
)


@dataclass(frozen=True, slots=True)
class BlockObjective:
    description: str
    primary_quality: str
    secondary_qualities: tuple[str, ...] = field(default_factory=tuple)
    movement_patterns: tuple[str, ...] = field(default_factory=tuple)
    body_region_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class BlockGenerationRequest:
    session_revision_id: int
    sequence_index: int
    name: str
    block_role: str
    planned_duration_minutes: int
    objective: BlockObjective
    participant_plan_ids: tuple[int, ...]
    excluded_participant_plan_ids: tuple[int, ...] = field(default_factory=tuple)
    execution_mode: str = "sequential"
    domain: str = "physical"
    target_intensity: str = "moderate"
    available_equipment_ids: tuple[int, ...] = field(default_factory=tuple)
    hard_constraints: tuple[str, ...] = field(default_factory=tuple)
    preferences: tuple[str, ...] = field(default_factory=tuple)
    instructions: str = ""
    rounds: int = 1
    rest_between_rounds_seconds: int = 0
    is_optional: bool = False
    contract_version: str = "1.0"


@dataclass(frozen=True, slots=True)
class ExerciseDoseProposal:
    exercise_revision_id: int
    dose_mode: str
    sets: int = 1
    repetitions: int | None = None
    duration_seconds: int | None = None
    distance: Decimal | None = None
    distance_unit: str = ""
    load_value: Decimal | None = None
    load_unit: str = ""
    intensity_metric: str = "none"
    intensity_value: Decimal | None = None
    tempo_eccentric_seconds: int | None = None
    tempo_pause_seconds: int | None = None
    tempo_concentric_seconds: int | None = None
    concentric_intent: str = "controlled"
    rest_between_sets_seconds: int = 0
    execution_notes: str = ""


@dataclass(frozen=True, slots=True)
class ExerciseAlternativeProposal:
    exercise_revision_id: int
    trigger: str
    rationale: str
    priority: int = 1


@dataclass(frozen=True, slots=True)
class AthleteAdjustmentProposal:
    participant_plan_id: int
    rationale: str
    action: str = "modify"
    replacement_exercise_revision_id: int | None = None
    sets: int | None = None
    repetitions: int | None = None
    duration_seconds: int | None = None
    load_value: Decimal | None = None
    load_unit: str = ""
    intensity_metric: str = ""
    intensity_value: Decimal | None = None
    rest_between_sets_seconds: int | None = None
    adaptation_notes: str = ""


@dataclass(frozen=True, slots=True)
class BlockItemProposal:
    sequence_index: int
    item_type: str
    title: str
    instructions: str = ""
    coaching_cues: str = ""
    planned_duration_seconds: int | None = None
    rest_after_seconds: int = 0
    selection_rationale: str = ""
    is_optional: bool = False
    dose: ExerciseDoseProposal | None = None
    alternatives: tuple[ExerciseAlternativeProposal, ...] = field(default_factory=tuple)
    athlete_adjustments: tuple[AthleteAdjustmentProposal, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True, slots=True)
class BlockLoadEstimate:
    mechanical_impact: Decimal
    neuromuscular: Decimal
    metabolic: Decimal
    coordinative: Decimal
    notes: str = ""


@dataclass(frozen=True, slots=True)
class BlockCoverage:
    physical_qualities: tuple[str, ...]
    movement_patterns: tuple[str, ...] = field(default_factory=tuple)
    body_region_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class BlockParticipantProposal:
    participant_plan_id: int
    mode: str
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class BlockGenerationProposal:
    request: BlockGenerationRequest
    items: tuple[BlockItemProposal, ...]
    estimated_duration_seconds: int
    estimated_load: BlockLoadEstimate
    coverage: BlockCoverage
    participants: tuple[BlockParticipantProposal, ...] = field(default_factory=tuple)
    satisfied_constraints: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    unmet_constraints: tuple[str, ...] = field(default_factory=tuple)
    confidence: Decimal | None = None
    generator_reference: str = ""
    contract_version: str = "1.0"
