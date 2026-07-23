from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competicions_trampoli", "0080_judge_guided_scoring_flow"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="judgescoringwindow",
            name="uniq_active_judge_window_per_lane",
        ),
        migrations.AddConstraint(
            model_name="judgescoringwindow",
            constraint=models.UniqueConstraint(
                fields=("lane",),
                condition=models.Q(status="open"),
                name="uniq_active_judge_window_per_lane",
            ),
        ),
    ]
