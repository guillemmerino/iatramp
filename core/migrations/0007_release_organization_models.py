from django.db import migrations


class Migration(migrations.Migration):
    """Finish releasing organization model state after IA Train retargets FKs."""

    dependencies = [
        ("iatrain", "0006_retarget_organization_relations"),
        ("core", "0006_release_organization_relations"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="Organization"),
                migrations.DeleteModel(name="OrganizationMembershipRequest"),
                migrations.DeleteModel(name="OrganizationMembershipRequestRole"),
            ],
        ),
    ]

