from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("iatrain", "0018_sessionitemathleteadjustment_station_remainder_action_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingsessionitem",
            name="knowledge_support",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
