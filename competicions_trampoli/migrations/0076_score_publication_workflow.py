from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_published_scores(apps, schema_editor):
    ScoreEntry = apps.get_model("competicions_trampoli", "ScoreEntry")
    TeamScoreEntry = apps.get_model("competicions_trampoli", "TeamScoreEntry")
    ScoreRevision = apps.get_model("competicions_trampoli", "ScoreRevision")
    ScorePublicationState = apps.get_model("competicions_trampoli", "ScorePublicationState")
    PublishedScoreEntry = apps.get_model("competicions_trampoli", "PublishedScoreEntry")
    PublishedTeamScoreEntry = apps.get_model("competicions_trampoli", "PublishedTeamScoreEntry")

    for entry in ScoreEntry.objects.all().iterator(chunk_size=500):
        revision = ScoreRevision.objects.create(
            competicio_id=entry.competicio_id,
            comp_aparell_id=entry.comp_aparell_id,
            fase_id=entry.fase_id,
            score_entry_id=entry.id,
            subject_kind="inscripcio",
            subject_id=entry.inscripcio_id,
            exercici=entry.exercici,
            inputs=entry.inputs or {},
            outputs=entry.outputs or {},
            total=entry.total,
            source="system",
            publication_status="published",
            reviewed_at=entry.updated_at,
        )
        ScorePublicationState.objects.create(
            score_entry_id=entry.id,
            current_revision_id=revision.id,
            published_revision_id=revision.id,
        )
        PublishedScoreEntry.objects.create(
            source_entry_id=entry.id,
            competicio_id=entry.competicio_id,
            inscripcio_id=entry.inscripcio_id,
            exercici=entry.exercici,
            comp_aparell_id=entry.comp_aparell_id,
            fase_id=entry.fase_id,
            inputs=entry.inputs or {},
            outputs=entry.outputs or {},
            total=entry.total,
        )

    for entry in TeamScoreEntry.objects.all().iterator(chunk_size=500):
        revision = ScoreRevision.objects.create(
            competicio_id=entry.competicio_id,
            comp_aparell_id=entry.comp_aparell_id,
            fase_id=entry.fase_id,
            team_score_entry_id=entry.id,
            subject_kind="team_unit",
            subject_id=entry.team_subject_id,
            exercici=entry.exercici,
            inputs=entry.inputs or {},
            outputs=entry.outputs or {},
            total=entry.total,
            source="system",
            publication_status="published",
            reviewed_at=entry.updated_at,
        )
        ScorePublicationState.objects.create(
            team_score_entry_id=entry.id,
            current_revision_id=revision.id,
            published_revision_id=revision.id,
        )
        PublishedTeamScoreEntry.objects.create(
            source_entry_id=entry.id,
            competicio_id=entry.competicio_id,
            team_subject_id=entry.team_subject_id,
            exercici=entry.exercici,
            comp_aparell_id=entry.comp_aparell_id,
            fase_id=entry.fase_id,
            inputs=entry.inputs or {},
            outputs=entry.outputs or {},
            total=entry.total,
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("competicions_trampoli", "0075_judgescoresubmission"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScorePublicationPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(choices=[("auto", "Publicacio automatica"), ("organization_review", "Validacio de l'organitzacio")], default="auto", max_length=30)),
                ("changed_at", models.DateTimeField(auto_now=True)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="score_publication_policy_changes", to=settings.AUTH_USER_MODEL)),
                ("competicio", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="score_publication_policy", to="competicions_trampoli.competicio")),
            ],
        ),
        migrations.CreateModel(
            name="PublishedScoreEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("exercici", models.PositiveSmallIntegerField(default=1)),
                ("inputs", models.JSONField(blank=True, default=dict)),
                ("outputs", models.JSONField(blank=True, default=dict)),
                ("total", models.DecimalField(decimal_places=3, default=0, max_digits=10)),
                ("published_at", models.DateTimeField(auto_now=True)),
                ("comp_aparell", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="published_scores", to="competicions_trampoli.competicioaparell")),
                ("competicio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="published_scores", to="competicions_trampoli.competicio")),
                ("fase", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="published_scores", to="competicions_trampoli.competicioaparellfase")),
                ("inscripcio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="published_scores", to="competicions_trampoli.inscripcio")),
                ("source_entry", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="published_snapshot", to="competicions_trampoli.scoreentry")),
            ],
        ),
        migrations.CreateModel(
            name="PublishedTeamScoreEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("exercici", models.PositiveSmallIntegerField(default=1)),
                ("inputs", models.JSONField(blank=True, default=dict)),
                ("outputs", models.JSONField(blank=True, default=dict)),
                ("total", models.DecimalField(decimal_places=3, default=0, max_digits=10)),
                ("published_at", models.DateTimeField(auto_now=True)),
                ("comp_aparell", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="published_team_scores", to="competicions_trampoli.competicioaparell")),
                ("competicio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="published_team_scores", to="competicions_trampoli.competicio")),
                ("fase", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="published_team_scores", to="competicions_trampoli.competicioaparellfase")),
                ("source_entry", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="published_snapshot", to="competicions_trampoli.teamscoreentry")),
                ("team_subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="published_scores", to="competicions_trampoli.teamcompetitivesubject")),
            ],
        ),
        migrations.CreateModel(
            name="ScoreRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject_kind", models.CharField(max_length=30)),
                ("subject_id", models.PositiveIntegerField()),
                ("exercici", models.PositiveSmallIntegerField(default=1)),
                ("inputs", models.JSONField(blank=True, default=dict)),
                ("outputs", models.JSONField(blank=True, default=dict)),
                ("total", models.DecimalField(decimal_places=3, default=0, max_digits=10)),
                ("source", models.CharField(choices=[("judge", "Jutge"), ("supervisor", "Supervisor"), ("organization", "Organitzacio"), ("import", "Importacio"), ("system", "Sistema")], default="system", max_length=20)),
                ("publication_status", models.CharField(choices=[("pending", "Pendent d'organitzacio"), ("published", "Publicada"), ("rejected", "Rebutjada"), ("superseded", "Substituida")], default="pending", max_length=20)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_note", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor_judge_token", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="score_revisions", to="competicions_trampoli.judgedevicetoken")),
                ("actor_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="score_revisions", to=settings.AUTH_USER_MODEL)),
                ("comp_aparell", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="score_revisions", to="competicions_trampoli.competicioaparell")),
                ("competicio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="score_revisions", to="competicions_trampoli.competicio")),
                ("fase", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="score_revisions", to="competicions_trampoli.competicioaparellfase")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_score_revisions", to=settings.AUTH_USER_MODEL)),
                ("score_entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="revisions", to="competicions_trampoli.scoreentry")),
                ("team_score_entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="revisions", to="competicions_trampoli.teamscoreentry")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="scorerevision",
            constraint=models.CheckConstraint(check=models.Q(models.Q(("score_entry__isnull", False), ("team_score_entry__isnull", True)), models.Q(("score_entry__isnull", True), ("team_score_entry__isnull", False)), _connector="OR"), name="score_revision_exactly_one_entry"),
        ),
        migrations.AddIndex(model_name="scorerevision", index=models.Index(fields=["competicio", "publication_status", "created_at"], name="score_rev_comp_status_at_idx")),
        migrations.AddIndex(model_name="scorerevision", index=models.Index(fields=["competicio", "source", "created_at"], name="score_rev_comp_source_at_idx")),
        migrations.AddIndex(model_name="scorerevision", index=models.Index(fields=["subject_kind", "subject_id", "exercici"], name="score_rev_subject_ex_idx")),
        migrations.CreateModel(
            name="ScorePublicationState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("current_revision", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="current_for_states", to="competicions_trampoli.scorerevision")),
                ("published_revision", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="published_for_states", to="competicions_trampoli.scorerevision")),
                ("score_entry", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="publication_state", to="competicions_trampoli.scoreentry")),
                ("team_score_entry", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="publication_state", to="competicions_trampoli.teamscoreentry")),
            ],
        ),
        migrations.AddConstraint(
            model_name="scorepublicationstate",
            constraint=models.CheckConstraint(check=models.Q(models.Q(("score_entry__isnull", False), ("team_score_entry__isnull", True)), models.Q(("score_entry__isnull", True), ("team_score_entry__isnull", False)), _connector="OR"), name="score_publication_state_one_entry"),
        ),
        migrations.RunPython(backfill_published_scores, migrations.RunPython.noop),
    ]
