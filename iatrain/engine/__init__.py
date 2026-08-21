"""Training engine boundary.

The package owns engine-facing contracts and orchestration. HTTP views live in
``iatrain.views.engine`` and import from here, never the other way around.
"""

from .adapter import apply_block_generation_proposal
from .contracts import (
    AthleteAdjustmentProposal,
    BlockCoverage,
    BlockGenerationProposal,
    BlockGenerationRequest,
    BlockItemProposal,
    BlockLoadEstimate,
    BlockObjective,
    BlockParticipantProposal,
    ParticipantConditionDecision,
    ExerciseAlternativeProposal,
    ExerciseDoseProposal,
)
from .selection import TrainingSelection, build_training_selection
from .context import BlockEngineContext, build_block_engine_context
from .generation import ENGINE_VERSION, generate_block_proposal
from .serialization import contract_to_payload, proposal_from_payload, request_from_payload
from .services import (
    apply_generation_run,
    discard_generation_run,
    generate_block_run,
    resume_generation_run,
)
from .validation import (
    validate_block_generation_proposal,
    validate_block_generation_request,
)

__all__ = (
    "AthleteAdjustmentProposal",
    "BlockCoverage",
    "BlockEngineContext",
    "BlockGenerationProposal",
    "BlockGenerationRequest",
    "BlockItemProposal",
    "BlockLoadEstimate",
    "BlockObjective",
    "BlockParticipantProposal",
    "ParticipantConditionDecision",
    "ExerciseAlternativeProposal",
    "ExerciseDoseProposal",
    "TrainingSelection",
    "apply_block_generation_proposal",
    "build_training_selection",
    "build_block_engine_context",
    "contract_to_payload",
    "discard_generation_run",
    "ENGINE_VERSION",
    "generate_block_proposal",
    "generate_block_run",
    "apply_generation_run",
    "proposal_from_payload",
    "request_from_payload",
    "resume_generation_run",
    "validate_block_generation_proposal",
    "validate_block_generation_request",
)
