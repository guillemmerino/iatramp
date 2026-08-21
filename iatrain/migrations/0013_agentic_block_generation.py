from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("iatrain", "0012_personalized_block_generation")]

    operations = [
        migrations.AddField(
            model_name="blockgenerationrun",
            name="agent_trace",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="blockgenerationrun",
            name="response_ids",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="blockgenerationrun",
            name="usage_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="blockgenerationrun",
            name="validation_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
