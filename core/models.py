from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Person(models.Model):
    """A real person, independently of whether they can sign in to Iatramp."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person",
    )
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=200, blank=True, default="")
    preferred_name = models.CharField(max_length=150, blank=True, default="")
    birth_date = models.DateField(null=True, blank=True)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=40, blank=True, default="")
    is_provisional = models.BooleanField(
        default=False,
        help_text="Identitat creada automàticament amb el compte i encara no confirmada.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("last_name", "first_name", "id")
        indexes = [
            models.Index(fields=("last_name", "first_name"), name="core_person_name_idx"),
            models.Index(fields=("is_active",), name="core_person_active_idx"),
        ]

    @property
    def display_name(self):
        return self.preferred_name or f"{self.first_name} {self.last_name}".strip()

    def clean(self):
        super().clean()
        if self.birth_date and self.birth_date > timezone.localdate():
            raise ValidationError({"birth_date": "La data de naixement no pot ser futura."})

    def __str__(self):
        return self.display_name


class PersonClaimInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendent"
        CLAIMED = "claimed", "Reclamada"
        CANCELLED = "cancelled", "Cancel·lada"
        EXPIRED = "expired", "Caducada"

    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="claim_invitations",
    )
    email = models.EmailField()
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_by = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_person_claim_invitations",
    )
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_person_invitations",
    )
    expires_at = models.DateTimeField()
    claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "id")
        indexes = [
            models.Index(fields=("person", "status"), name="core_claim_person_idx"),
            models.Index(fields=("email", "status"), name="core_claim_email_idx"),
        ]

    def __str__(self):
        return f"{self.person} · {self.email} ({self.get_status_display()})"


class PersonMergeRecord(models.Model):
    canonical_person = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="absorbed_identity_records",
    )
    duplicate_person_id = models.PositiveBigIntegerField(unique=True)
    duplicate_snapshot = models.JSONField(default=dict)
    merged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person_merge_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "id")

    def __str__(self):
        return f"Identitat {self.duplicate_person_id} → {self.canonical_person}"
