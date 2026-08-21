import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("iatrain", "0011_blockgenerationrun_equipment_codes"),
    ]

    operations = [
        migrations.AddField(
            model_name="blockgenerationrun",
            name="coach_decisions",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="blockgenerationrun",
            name="decision_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="blockgenerationrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("processing", "Generant"),
                    ("awaiting_decision", "Esperant decisió"),
                    ("proposed", "Proposta preparada"),
                    ("applied", "Afegida a la sessió"),
                    ("discarded", "Descartada"),
                    ("failed", "No completada"),
                ],
                default="processing",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sessionitemathleteadjustment",
            name="action",
            field=models.CharField(
                choices=[
                    ("modify", "Modificar dosi"),
                    ("replace", "Substituir exercici"),
                    ("skip", "No participa en l'ítem"),
                ],
                default="modify",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="BlockParticipantAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("shared", "Prescripció compartida"),
                            ("personalized", "Prescripció personalitzada"),
                            ("excluded", "Exclosa del bloc"),
                        ],
                        max_length=20,
                    ),
                ),
                ("rationale", models.TextField(blank=True, default="")),
                (
                    "block",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participant_assignments",
                        to="iatrain.trainingblock",
                    ),
                ),
                (
                    "participant_plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="block_assignments",
                        to="iatrain.sessionparticipantplan",
                    ),
                ),
            ],
            options={"ordering": ("block_id", "participant_plan_id")},
        ),
        migrations.AddConstraint(
            model_name="blockparticipantassignment",
            constraint=models.UniqueConstraint(
                fields=("block", "participant_plan"),
                name="iatrain_block_participant_uniq",
            ),
        ),
    ]
