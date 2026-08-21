from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("iatrain", "0015_athletecondition_applicability_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingsessionitem",
            name="setup_seconds",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
