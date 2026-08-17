from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import Person


class Organization(models.Model):
    class Kind(models.TextChoices):
        CLUB = "club", "Club"
        FEDERATION = "federation", "Federació"
        OTHER = "other", "Altres"

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CLUB)
    created_by = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_organizations",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_organization"
        ordering = ("name", "id")
        indexes = [models.Index(fields=("kind", "is_active"), name="core_org_kind_active_idx")]

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        SUSPENDED = "suspended", "Suspesa"
        LEFT = "left", "Finalitzada"

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_organization_memberships",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_membership"
        ordering = ("organization_id", "person_id")
        constraints = [
            models.UniqueConstraint(
                fields=("person", "organization"),
                name="core_membership_uniq_person_org",
            ),
            models.CheckConstraint(
                check=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="core_membership_dates_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("organization", "status"),
                name="core_member_org_status_idx",
            ),
            models.Index(fields=("person", "status"), name="core_member_person_idx"),
        ]

    def clean(self):
        super().clean()
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La data de fi no pot ser anterior a la d'inici."})

    def is_current(self, on_date=None):
        on_date = on_date or timezone.localdate()
        return (
            self.status == self.Status.ACTIVE
            and self.start_date <= on_date
            and (self.end_date is None or self.end_date >= on_date)
            and self.organization.is_active
        )

    @property
    def role_labels(self):
        return [role.get_role_display() for role in self.roles.filter(is_active=True)]

    @property
    def role_summary(self):
        return ", ".join(self.role_labels) or "Sense rol"

    def __str__(self):
        return f"{self.person} · {self.organization}"


class MembershipRole(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Responsable"
        ADMIN = "admin", "Administració"
        COACH = "coach", "Entrenador/a"
        ATHLETE = "athlete", "Gimnasta"
        JUDGE = "judge", "Jutge/essa"
        STAFF = "staff", "Personal"
        MEMBER = "member", "Membre"

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="roles")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    title = models.CharField(max_length=120, blank=True, default="")
    is_active = models.BooleanField(default=True)
    granted_by = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_organization_roles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_membershiprole"
        ordering = ("membership_id", "role")
        constraints = [
            models.UniqueConstraint(
                fields=("membership", "role"),
                name="core_membership_role_uniq",
            )
        ]
        indexes = [
            models.Index(fields=("membership", "is_active"), name="core_memrole_active_idx"),
            models.Index(fields=("role", "is_active"), name="core_memrole_role_idx"),
        ]

    def __str__(self):
        return f"{self.membership} · {self.get_role_display()}"


class MembershipPermission(models.Model):
    class Permission(models.TextChoices):
        MANAGE_ORGANIZATION = "manage_organization", "Gestionar l'organització"
        MANAGE_MEMBERS = "manage_members", "Gestionar membres"
        REVIEW_REQUESTS = "review_requests", "Revisar sol·licituds"
        MANAGE_ROLES = "manage_roles", "Gestionar rols i permisos"

    membership = models.ForeignKey(
        Membership,
        on_delete=models.CASCADE,
        related_name="permission_overrides",
    )
    permission = models.CharField(max_length=40, choices=Permission.choices)
    is_allowed = models.BooleanField(default=True)
    granted_by = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_organization_permissions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_membershippermission"
        ordering = ("membership_id", "permission")
        constraints = [
            models.UniqueConstraint(
                fields=("membership", "permission"),
                name="core_membership_permission_uniq",
            )
        ]

    def __str__(self):
        decision = "permès" if self.is_allowed else "denegat"
        return f"{self.membership} · {self.get_permission_display()} ({decision})"


class OrganizationMembershipRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendent"
        APPROVED = "approved", "Aprovada"
        REJECTED = "rejected", "Rebutjada"
        CANCELLED = "cancelled", "Cancel·lada"

    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="organization_membership_requests",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="membership_requests",
    )
    message = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    resolved_by = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_organization_membership_requests",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_organizationmembershiprequest"
        ordering = ("-created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("person", "organization"),
                condition=Q(status="pending"),
                name="core_membership_request_one_pending",
            )
        ]
        indexes = [
            models.Index(
                fields=("organization", "status", "created_at"),
                name="core_memrequest_org_idx",
            ),
            models.Index(
                fields=("person", "status", "created_at"),
                name="core_memrequest_person_idx",
            ),
        ]

    @property
    def requested_role_labels(self):
        return [role.get_role_display() for role in self.requested_roles.all()]

    @property
    def requested_role_summary(self):
        return ", ".join(self.requested_role_labels) or "Membre"

    def __str__(self):
        return f"{self.person} → {self.organization} ({self.get_status_display()})"


class OrganizationMembershipRequestRole(models.Model):
    request = models.ForeignKey(
        OrganizationMembershipRequest,
        on_delete=models.CASCADE,
        related_name="requested_roles",
    )
    role = models.CharField(max_length=20, choices=MembershipRole.Role.choices)

    class Meta:
        db_table = "core_organizationmembershiprequestrole"
        ordering = ("request_id", "role")
        constraints = [
            models.UniqueConstraint(
                fields=("request", "role"),
                name="core_membership_request_role_uniq",
            )
        ]

    def __str__(self):
        return f"{self.request} · {self.get_role_display()}"

