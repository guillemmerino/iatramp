from django.core.exceptions import ValidationError
from django.db import models

from .base import CleanOnSaveModel


class BlockGenerationRun(CleanOnSaveModel):
    """Auditable, non-authoritative record of an automated block proposal."""

    class Status(models.TextChoices):
        PROCESSING = "processing", "Generant"
        AWAITING_DECISION = "awaiting_decision", "Esperant decisió"
        PROPOSED = "proposed", "Proposta preparada"
        REVIEW_REQUIRED = "review_required", "Requereix revisió"
        APPLIED = "applied", "Afegida a la sessió"
        DISCARDED = "discarded", "Descartada"
        FAILED = "failed", "No completada"

    session_revision = models.ForeignKey(
        "iatrain.TrainingSessionRevision",
        on_delete=models.PROTECT,
        related_name="block_generation_runs",
    )
    created_by = models.ForeignKey(
        "core.Person",
        on_delete=models.PROTECT,
        related_name="created_block_generation_runs",
    )
    parent_run = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="refinements",
    )
    applied_block = models.OneToOneField(
        "iatrain.TrainingBlock",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="generation_run",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PROCESSING,
    )
    prompt = models.TextField()
    refinement_instruction = models.TextField(blank=True, default="")
    interpretation_payload = models.JSONField(blank=True, default=dict)
    planning_payload = models.JSONField(blank=True, default=dict)
    request_payload = models.JSONField(blank=True, default=dict)
    proposal_payload = models.JSONField(blank=True, default=dict)
    decision_payload = models.JSONField(blank=True, default=dict)
    coach_decisions = models.JSONField(blank=True, default=dict)
    source_references = models.JSONField(blank=True, default=list)
    agent_trace = models.JSONField(blank=True, default=list)
    response_ids = models.JSONField(blank=True, default=list)
    usage_payload = models.JSONField(blank=True, default=dict)
    validation_payload = models.JSONField(blank=True, default=dict)
    progress_payload = models.JSONField(blank=True, default=dict)
    model_name = models.CharField(max_length=120, blank=True, default="")
    prompt_version = models.CharField(max_length=40, default="1.0")
    engine_version = models.CharField(max_length=40, default="1.0")
    contract_version = models.CharField(max_length=40, default="1.0")
    error_code = models.CharField(max_length=80, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("session_revision", "status", "created_at"),
                name="iatrain_block_gen_status_idx",
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        if not self.prompt.strip():
            errors["prompt"] = "La generació necessita la petició original."
        if self.parent_run_id and self.parent_run.session_revision_id != self.session_revision_id:
            errors["parent_run"] = "La reformulació ha de pertànyer a la mateixa versió."
        if self.applied_block_id:
            if self.applied_block.session_revision_id != self.session_revision_id:
                errors["applied_block"] = "El bloc aplicat ha de pertànyer a la mateixa versió."
            if self.status != self.Status.APPLIED:
                errors["status"] = "Una proposta amb bloc aplicat ha d'estar marcada com aplicada."
        for field_name in (
            "interpretation_payload",
            "planning_payload",
            "request_payload",
            "proposal_payload",
            "decision_payload",
            "coach_decisions",
            "usage_payload",
            "validation_payload",
            "progress_payload",
        ):
            if not isinstance(getattr(self, field_name), dict):
                errors[field_name] = "Aquest camp ha de ser un objecte JSON."
        if not isinstance(self.source_references, list):
            errors["source_references"] = "Les fonts han de ser una llista."
        if not isinstance(self.agent_trace, list):
            errors["agent_trace"] = "La traça de l'agent ha de ser una llista."
        if not isinstance(self.response_ids, list):
            errors["response_ids"] = "Els identificadors de resposta han de ser una llista."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Generació {self.pk or 'nova'} · {self.get_status_display()}"
