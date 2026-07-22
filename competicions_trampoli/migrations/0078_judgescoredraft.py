from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("competicions_trampoli", "0077_backfill_tot_score_values"),
    ]

    operations = [
        migrations.CreateModel(
            name="JudgeScoreDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject_kind", models.CharField(default="inscripcio", max_length=30)),
                ("subject_id", models.PositiveIntegerField()),
                ("exercici", models.PositiveSmallIntegerField(default=1)),
                ("field_code", models.CharField(max_length=80)),
                ("runtime_field_code", models.CharField(max_length=120)),
                ("judge_index", models.PositiveSmallIntegerField(default=1)),
                ("item_start", models.PositiveSmallIntegerField(default=1)),
                ("item_count", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("role", models.CharField(default="standard", max_length=20)),
                ("inputs_patch", models.JSONField(blank=True, default=dict)),
                ("normalized_inputs_patch", models.JSONField(blank=True, default=dict)),
                ("version", models.PositiveBigIntegerField(default=1)),
                ("client_sequence", models.PositiveBigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("comp_aparell", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="judge_score_drafts", to="competicions_trampoli.competicioaparell")),
                ("competicio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="judge_score_drafts", to="competicions_trampoli.competicio")),
                ("fase", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="judge_score_drafts", to="competicions_trampoli.competicioaparellfase")),
                ("submitted_by_assignment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="score_drafts", to="competicions_trampoli.judgeportalassignment")),
                ("submitted_by_token", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="score_drafts", to="competicions_trampoli.judgedevicetoken")),
            ],
            options={"ordering": ["updated_at", "id"]},
        ),
        migrations.AddIndex(model_name="judgescoredraft", index=models.Index(fields=["competicio", "comp_aparell", "fase", "updated_at"], name="judgedraft_scope_upd_idx")),
        migrations.AddIndex(model_name="judgescoredraft", index=models.Index(fields=["subject_kind", "subject_id", "exercici"], name="judgedraft_subject_ex_idx")),
        migrations.AddIndex(model_name="judgescoredraft", index=models.Index(fields=["submitted_by_token", "updated_at"], name="judgedraft_token_upd_idx")),
    ]
