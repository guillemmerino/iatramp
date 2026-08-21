from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("iatrain", "0013_agentic_block_generation")]

    operations = [
        migrations.AddField(
            model_name="blockgenerationrun",
            name="progress_payload",
            field=models.JSONField(blank=True, default=dict),
        )
    ]
