from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competicions_trampoli", "0078_judgescoredraft"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="judgescoredraft",
            constraint=models.UniqueConstraint(
                condition=models.Q(("submitted_by_assignment__isnull", False)),
                fields=(
                    "submitted_by_token",
                    "submitted_by_assignment",
                    "subject_kind",
                    "subject_id",
                    "exercici",
                    "runtime_field_code",
                ),
                name="uniq_judgedraft_assignment_subject_field",
            ),
        ),
    ]
