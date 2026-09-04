from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("iatrain", "0020_sessionitemathleteadjustment_professional_justification")]

    operations = [
        migrations.AddField(
            model_name="blockgenerationrun",
            name="planning_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
