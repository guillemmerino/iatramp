from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("iatrain", "0019_trainingsessionitem_knowledge_support"),
    ]

    operations = [
        migrations.AddField(
            model_name="sessionitemathleteadjustment",
            name="professional_justification",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="sessionitemathleteadjustment",
            name="action",
            field=models.CharField(
                choices=[
                    ("monitor", "Monitorar sense canviar la dosi"),
                    ("modify", "Modificar dosi"),
                    ("replace", "Substituir exercici"),
                    ("skip", "No participa en l'ítem"),
                ],
                default="modify",
                max_length=20,
            ),
        ),
    ]
