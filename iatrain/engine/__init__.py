"""Training engine boundary.

The package owns engine-facing contracts and orchestration. HTTP views live in
``iatrain.views.engine`` and import from here, never the other way around.
"""

from .selection import TrainingSelection, build_training_selection

__all__ = ("TrainingSelection", "build_training_selection")
