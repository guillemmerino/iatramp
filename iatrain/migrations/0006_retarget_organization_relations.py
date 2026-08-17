from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Retarget ORM state while preserving the existing FK columns and tables."""

    dependencies = [
        ("organizations", "0001_adopt_core_organization_models"),
        ("iatrain", "0005_gym_gymorganization_gymequipment_gym_organizations_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="coachathleterelation",
                    name="organization",
                    field=models.ForeignKey(
                        blank=True,
                        help_text="Organització en què s'aplica la relació; buit si és global.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="training_relationships",
                        to="organizations.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="gym",
                    name="organizations",
                    field=models.ManyToManyField(
                        blank=True,
                        related_name="training_gyms",
                        through="iatrain.GymOrganization",
                        to="organizations.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="gymorganization",
                    name="organization",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gym_links",
                        to="organizations.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="trainingcontext",
                    name="organization",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="training_contexts",
                        to="organizations.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="traininggroup",
                    name="organization",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="training_groups",
                        to="organizations.organization",
                    ),
                ),
            ],
        ),
    ]

