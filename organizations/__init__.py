"""Shared organization domain.

Phase 1 keeps the Django models physically owned by ``core`` while exposing
the organization domain through this package.  Consumers should import from
``organizations`` so the models can move here in phase 2 without another
application-wide import rewrite.
"""

