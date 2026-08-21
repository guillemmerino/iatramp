from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("iatrain", "0016_trainingsessionitem_setup_seconds"),
    ]

    operations = [
        migrations.AddField(
            model_name="blockparticipantassignment",
            name="condition_decisions",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
