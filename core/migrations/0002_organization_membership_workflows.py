from django.db import migrations, models
import django.db.models.deletion


ROLE_CHOICES = [
    ("owner", "Responsable"),
    ("admin", "Administració"),
    ("coach", "Entrenador/a"),
    ("athlete", "Gimnasta"),
    ("judge", "Jutge/essa"),
    ("staff", "Personal"),
    ("member", "Membre"),
]


def migrate_memberships_forward(apps, schema_editor):
    Membership = apps.get_model("core", "Membership")
    MembershipRole = apps.get_model("core", "MembershipRole")

    pairs = list(
        Membership.objects.order_by("person_id", "organization_id", "id")
        .values_list("person_id", "organization_id")
        .distinct()
    )
    for person_id, organization_id in pairs:
        memberships = list(
            Membership.objects.filter(
                person_id=person_id,
                organization_id=organization_id,
            ).order_by("id")
        )
        primary = memberships[0]
        active_memberships = [item for item in memberships if item.is_active]
        primary.status = "active" if active_memberships else "suspended"
        primary.start_date = min(item.start_date for item in memberships)
        if any(item.end_date is None for item in memberships):
            primary.end_date = None
        else:
            primary.end_date = max(item.end_date for item in memberships)
        primary.save(update_fields=("status", "start_date", "end_date"))

        for item in memberships:
            MembershipRole.objects.update_or_create(
                membership_id=primary.pk,
                role=item.role,
                defaults={
                    "title": item.title,
                    "is_active": item.is_active,
                },
            )
        for duplicate in memberships[1:]:
            duplicate.delete()


def migrate_memberships_reverse(apps, schema_editor):
    Membership = apps.get_model("core", "Membership")
    MembershipRole = apps.get_model("core", "MembershipRole")

    for membership in list(Membership.objects.order_by("id")):
        roles = list(
            MembershipRole.objects.filter(membership_id=membership.pk).order_by("id")
        )
        if not roles:
            roles = [None]
        first = roles[0]
        membership.role = first.role if first else "member"
        membership.title = first.title if first else ""
        membership.is_active = first.is_active if first else membership.status == "active"
        membership.save(update_fields=("role", "title", "is_active"))

        for role in roles[1:]:
            Membership.objects.create(
                person_id=membership.person_id,
                organization_id=membership.organization_id,
                role=role.role,
                title=role.title,
                start_date=membership.start_date,
                end_date=membership.end_date,
                is_active=role.is_active,
                status=membership.status,
                approved_at=membership.approved_at,
                approved_by_id=membership.approved_by_id,
            )


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_organizations",
                to="core.person",
            ),
        ),
        migrations.AddField(
            model_name="membership",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="membership",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_organization_memberships",
                to="core.person",
            ),
        ),
        migrations.AddField(
            model_name="membership",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Activa"),
                    ("suspended", "Suspesa"),
                    ("left", "Finalitzada"),
                ],
                default="active",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="MembershipRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=ROLE_CHOICES, default="member", max_length=20)),
                ("title", models.CharField(blank=True, default="", max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="granted_organization_roles",
                        to="core.person",
                    ),
                ),
                (
                    "membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="roles",
                        to="core.membership",
                    ),
                ),
            ],
            options={"ordering": ("membership_id", "role")},
        ),
        migrations.CreateModel(
            name="MembershipPermission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "permission",
                    models.CharField(
                        choices=[
                            ("manage_organization", "Gestionar l'organització"),
                            ("manage_members", "Gestionar membres"),
                            ("review_requests", "Revisar sol·licituds"),
                            ("manage_roles", "Gestionar rols i permisos"),
                        ],
                        max_length=40,
                    ),
                ),
                ("is_allowed", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="granted_organization_permissions",
                        to="core.person",
                    ),
                ),
                (
                    "membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="permission_overrides",
                        to="core.membership",
                    ),
                ),
            ],
            options={"ordering": ("membership_id", "permission")},
        ),
        migrations.CreateModel(
            name="OrganizationMembershipRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pendent"),
                            ("approved", "Aprovada"),
                            ("rejected", "Rebutjada"),
                            ("cancelled", "Cancel·lada"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="membership_requests",
                        to="core.organization",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organization_membership_requests",
                        to="core.person",
                    ),
                ),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resolved_organization_membership_requests",
                        to="core.person",
                    ),
                ),
            ],
            options={"ordering": ("-created_at", "id")},
        ),
        migrations.CreateModel(
            name="OrganizationMembershipRequestRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=ROLE_CHOICES, max_length=20)),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="requested_roles",
                        to="core.organizationmembershiprequest",
                    ),
                ),
            ],
            options={"ordering": ("request_id", "role")},
        ),
        migrations.AddConstraint(
            model_name="membershiprole",
            constraint=models.UniqueConstraint(fields=("membership", "role"), name="core_membership_role_uniq"),
        ),
        migrations.AddIndex(
            model_name="membershiprole",
            index=models.Index(fields=["membership", "is_active"], name="core_memrole_active_idx"),
        ),
        migrations.AddIndex(
            model_name="membershiprole",
            index=models.Index(fields=["role", "is_active"], name="core_memrole_role_idx"),
        ),
        migrations.AddConstraint(
            model_name="membershippermission",
            constraint=models.UniqueConstraint(
                fields=("membership", "permission"),
                name="core_membership_permission_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationmembershiprequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "pending")),
                fields=("person", "organization"),
                name="core_membership_request_one_pending",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationmembershiprequest",
            index=models.Index(
                fields=["organization", "status", "created_at"],
                name="core_memrequest_org_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationmembershiprequest",
            index=models.Index(
                fields=["person", "status", "created_at"],
                name="core_memrequest_person_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationmembershiprequestrole",
            constraint=models.UniqueConstraint(
                fields=("request", "role"),
                name="core_membership_request_role_uniq",
            ),
        ),
        migrations.RunPython(migrate_memberships_forward, migrate_memberships_reverse),
        migrations.RemoveConstraint(
            model_name="membership",
            name="core_membership_uniq_role",
        ),
        migrations.RemoveIndex(
            model_name="membership",
            name="core_member_org_role_idx",
        ),
        migrations.RemoveIndex(
            model_name="membership",
            name="core_member_person_idx",
        ),
        migrations.RemoveField(model_name="membership", name="role"),
        migrations.RemoveField(model_name="membership", name="title"),
        migrations.RemoveField(model_name="membership", name="is_active"),
        migrations.AlterModelOptions(
            name="membership",
            options={"ordering": ("organization_id", "person_id")},
        ),
        migrations.AddConstraint(
            model_name="membership",
            constraint=models.UniqueConstraint(
                fields=("person", "organization"),
                name="core_membership_uniq_person_org",
            ),
        ),
        migrations.AddIndex(
            model_name="membership",
            index=models.Index(fields=["organization", "status"], name="core_member_org_status_idx"),
        ),
        migrations.AddIndex(
            model_name="membership",
            index=models.Index(fields=["person", "status"], name="core_member_person_idx"),
        ),
    ]
