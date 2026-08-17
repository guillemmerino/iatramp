from django.db import migrations


class Migration(migrations.Migration):
    """Release organization relations from Core's state without altering SQL."""

    dependencies = [
        ("organizations", "0001_adopt_core_organization_models"),
        ("core", "0005_alter_person_last_name"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveField(
                    model_name="membershippermission",
                    name="granted_by",
                ),
                migrations.RemoveField(
                    model_name="membershippermission",
                    name="membership",
                ),
                migrations.RemoveField(
                    model_name="membershiprole",
                    name="granted_by",
                ),
                migrations.RemoveField(
                    model_name="membershiprole",
                    name="membership",
                ),
                migrations.RemoveField(
                    model_name="organization",
                    name="created_by",
                ),
                migrations.RemoveField(
                    model_name="organizationmembershiprequest",
                    name="organization",
                ),
                migrations.RemoveField(
                    model_name="organizationmembershiprequest",
                    name="person",
                ),
                migrations.RemoveField(
                    model_name="organizationmembershiprequest",
                    name="resolved_by",
                ),
                migrations.RemoveField(
                    model_name="organizationmembershiprequestrole",
                    name="request",
                ),
                migrations.DeleteModel(name="Membership"),
                migrations.DeleteModel(name="MembershipPermission"),
                migrations.DeleteModel(name="MembershipRole"),
            ],
        ),
    ]

