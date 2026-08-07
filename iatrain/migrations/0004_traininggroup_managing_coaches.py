from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("iatrain", "0003_traininggroup_athleteprofile_extracted_facts_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="traininggroup",
            name="managing_coaches",
            field=models.ManyToManyField(
                blank=True,
                help_text="Entrenadors amb capacitat explícita per gestionar el grup.",
                related_name="managed_training_groups",
                to="iatrain.coachprofile",
            ),
        ),
    ]
