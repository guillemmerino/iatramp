from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    """Adopt the existing core_* tables in Django state without touching SQL."""

    initial = True

    dependencies = [
        ("core", "0005_alter_person_last_name"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Membership",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("status", models.CharField(choices=[("active", "Activa"), ("suspended", "Suspesa"), ("left", "Finalitzada")], default="active", max_length=20)),
                        ("start_date", models.DateField(default=django.utils.timezone.localdate)),
                        ("end_date", models.DateField(blank=True, null=True)),
                        ("approved_at", models.DateTimeField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approved_organization_memberships", to="core.person")),
                    ],
                    options={
                        "db_table": "core_membership",
                        "ordering": ("organization_id", "person_id"),
                    },
                ),
                migrations.CreateModel(
                    name="Organization",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("name", models.CharField(max_length=255)),
                        ("slug", models.SlugField(max_length=255, unique=True)),
                        ("kind", models.CharField(choices=[("club", "Club"), ("federation", "Federació"), ("other", "Altres")], default="club", max_length=20)),
                        ("is_active", models.BooleanField(default=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_organizations", to="core.person")),
                    ],
                    options={
                        "db_table": "core_organization",
                        "ordering": ("name", "id"),
                    },
                ),
                migrations.CreateModel(
                    name="OrganizationMembershipRequest",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("message", models.TextField(blank=True, default="")),
                        ("status", models.CharField(choices=[("pending", "Pendent"), ("approved", "Aprovada"), ("rejected", "Rebutjada"), ("cancelled", "Cancel·lada")], default="pending", max_length=20)),
                        ("resolved_at", models.DateTimeField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="membership_requests", to="organizations.organization")),
                        ("person", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="organization_membership_requests", to="core.person")),
                        ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resolved_organization_membership_requests", to="core.person")),
                    ],
                    options={
                        "db_table": "core_organizationmembershiprequest",
                        "ordering": ("-created_at", "id"),
                    },
                ),
                migrations.CreateModel(
                    name="OrganizationMembershipRequestRole",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("role", models.CharField(choices=[("owner", "Responsable"), ("admin", "Administració"), ("coach", "Entrenador/a"), ("athlete", "Gimnasta"), ("judge", "Jutge/essa"), ("staff", "Personal"), ("member", "Membre")], max_length=20)),
                        ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="requested_roles", to="organizations.organizationmembershiprequest")),
                    ],
                    options={
                        "db_table": "core_organizationmembershiprequestrole",
                        "ordering": ("request_id", "role"),
                    },
                ),
                migrations.CreateModel(
                    name="MembershipRole",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("role", models.CharField(choices=[("owner", "Responsable"), ("admin", "Administració"), ("coach", "Entrenador/a"), ("athlete", "Gimnasta"), ("judge", "Jutge/essa"), ("staff", "Personal"), ("member", "Membre")], default="member", max_length=20)),
                        ("title", models.CharField(blank=True, default="", max_length=120)),
                        ("is_active", models.BooleanField(default=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("granted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="granted_organization_roles", to="core.person")),
                        ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="roles", to="organizations.membership")),
                    ],
                    options={
                        "db_table": "core_membershiprole",
                        "ordering": ("membership_id", "role"),
                    },
                ),
                migrations.CreateModel(
                    name="MembershipPermission",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("permission", models.CharField(choices=[("manage_organization", "Gestionar l'organització"), ("manage_members", "Gestionar membres"), ("review_requests", "Revisar sol·licituds"), ("manage_roles", "Gestionar rols i permisos")], max_length=40)),
                        ("is_allowed", models.BooleanField(default=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("granted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="granted_organization_permissions", to="core.person")),
                        ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="permission_overrides", to="organizations.membership")),
                    ],
                    options={
                        "db_table": "core_membershippermission",
                        "ordering": ("membership_id", "permission"),
                    },
                ),
                migrations.AddField(
                    model_name="membership",
                    name="organization",
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="organizations.organization"),
                ),
                migrations.AddField(
                    model_name="membership",
                    name="person",
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="core.person"),
                ),
                migrations.AddConstraint(
                    model_name="organizationmembershiprequestrole",
                    constraint=models.UniqueConstraint(fields=("request", "role"), name="core_membership_request_role_uniq"),
                ),
                migrations.AddIndex(
                    model_name="organizationmembershiprequest",
                    index=models.Index(fields=["organization", "status", "created_at"], name="core_memrequest_org_idx"),
                ),
                migrations.AddIndex(
                    model_name="organizationmembershiprequest",
                    index=models.Index(fields=["person", "status", "created_at"], name="core_memrequest_person_idx"),
                ),
                migrations.AddConstraint(
                    model_name="organizationmembershiprequest",
                    constraint=models.UniqueConstraint(condition=models.Q(("status", "pending")), fields=("person", "organization"), name="core_membership_request_one_pending"),
                ),
                migrations.AddIndex(
                    model_name="organization",
                    index=models.Index(fields=["kind", "is_active"], name="core_org_kind_active_idx"),
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
                    model_name="membershiprole",
                    constraint=models.UniqueConstraint(fields=("membership", "role"), name="core_membership_role_uniq"),
                ),
                migrations.AddConstraint(
                    model_name="membershippermission",
                    constraint=models.UniqueConstraint(fields=("membership", "permission"), name="core_membership_permission_uniq"),
                ),
                migrations.AddIndex(
                    model_name="membership",
                    index=models.Index(fields=["organization", "status"], name="core_member_org_status_idx"),
                ),
                migrations.AddIndex(
                    model_name="membership",
                    index=models.Index(fields=["person", "status"], name="core_member_person_idx"),
                ),
                migrations.AddConstraint(
                    model_name="membership",
                    constraint=models.UniqueConstraint(fields=("person", "organization"), name="core_membership_uniq_person_org"),
                ),
                migrations.AddConstraint(
                    model_name="membership",
                    constraint=models.CheckConstraint(check=models.Q(("end_date__isnull", True), ("end_date__gte", models.F("start_date")), _connector="OR"), name="core_membership_dates_valid"),
                ),
            ],
        ),
    ]

