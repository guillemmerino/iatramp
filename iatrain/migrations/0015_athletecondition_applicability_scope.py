from django.db import migrations, models


def classify_existing_conditions(apps, schema_editor):
    AthleteCondition = apps.get_model("iatrain", "AthleteCondition")
    AthleteCondition.objects.filter(body_region__isnull=False).update(
        applicability_scope="regional"
    )
    AthleteCondition.objects.filter(training_impact="stop").update(
        applicability_scope="global"
    )


class Migration(migrations.Migration):
    dependencies = [("iatrain", "0014_blockgenerationrun_progress_payload")]

    operations = [
        migrations.AddField(
            model_name="athletecondition",
            name="applicability_scope",
            field=models.CharField(
                choices=[
                    ("unknown", "Abast pendent de concretar"),
                    ("regional", "Regió corporal concreta"),
                    ("global", "Afecta globalment l’entrenament"),
                ],
                default="unknown",
                max_length=20,
            ),
        ),
        migrations.RunPython(classify_existing_conditions, migrations.RunPython.noop),
    ]
