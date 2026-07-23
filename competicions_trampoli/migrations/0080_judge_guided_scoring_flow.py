import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competicions_trampoli", "0079_judgescoredraft_unique"),
    ]

    operations = [
        migrations.CreateModel(
            name="JudgeScoringLane",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(blank=True, default="", max_length=160)),
                ("is_enabled", models.BooleanField(default=False)),
                ("version", models.PositiveBigIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "comp_aparell",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="judge_scoring_lanes",
                        to="competicions_trampoli.competicioaparell",
                    ),
                ),
                (
                    "competicio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="judge_scoring_lanes",
                        to="competicions_trampoli.competicio",
                    ),
                ),
                (
                    "controller_assignment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="controlled_scoring_lanes",
                        to="competicions_trampoli.judgeportalassignment",
                    ),
                ),
                (
                    "fase",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="judge_scoring_lanes",
                        to="competicions_trampoli.competicioaparellfase",
                    ),
                ),
            ],
            options={
                "ordering": ["competicio_id", "comp_aparell_id", "fase_id", "id"],
                "indexes": [
                    models.Index(fields=["competicio", "is_enabled"], name="judgelane_comp_enabled_idx"),
                    models.Index(fields=["comp_aparell", "fase"], name="judgelane_app_phase_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("fase__isnull", True)),
                        fields=("competicio", "comp_aparell"),
                        name="uniq_judgelane_preliminary",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("fase__isnull", False)),
                        fields=("competicio", "comp_aparell", "fase"),
                        name="uniq_judgelane_phase",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="JudgeScoringWindow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveBigIntegerField(default=1)),
                ("subject_kind", models.CharField(default="inscripcio", max_length=30)),
                ("subject_id", models.PositiveIntegerField()),
                ("exercici", models.PositiveSmallIntegerField(default=1)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Oberta"),
                            ("closing", "Tancant"),
                            ("locked", "Bloquejada"),
                            ("finalized", "Finalitzada"),
                            ("cancelled", "Cancel·lada"),
                        ],
                        default="open",
                        max_length=20,
                    ),
                ),
                ("configuration_snapshot", models.JSONField(blank=True, default=dict)),
                ("final_inputs", models.JSONField(blank=True, default=dict)),
                ("final_outputs", models.JSONField(blank=True, default=dict)),
                ("final_total", models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ("error_message", models.CharField(blank=True, default="", max_length=500)),
                ("opened_at", models.DateTimeField(auto_now_add=True)),
                ("closing_at", models.DateTimeField(blank=True, null=True)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("finalized_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "closed_by_assignment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="closed_scoring_windows",
                        to="competicions_trampoli.judgeportalassignment",
                    ),
                ),
                (
                    "finalized_by_assignment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="finalized_scoring_windows",
                        to="competicions_trampoli.judgeportalassignment",
                    ),
                ),
                (
                    "lane",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scoring_windows",
                        to="competicions_trampoli.judgescoringlane",
                    ),
                ),
                (
                    "opened_by_assignment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="opened_scoring_windows",
                        to="competicions_trampoli.judgeportalassignment",
                    ),
                ),
            ],
            options={
                "ordering": ["-sequence", "-id"],
                "indexes": [
                    models.Index(fields=["lane", "status"], name="judgewindow_lane_status_idx"),
                    models.Index(fields=["subject_kind", "subject_id", "exercici"], name="judgewindow_subject_ex_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("status__in", ["open", "closing", "locked"])),
                        fields=("lane",),
                        name="uniq_active_judge_window_per_lane",
                    ),
                    models.UniqueConstraint(
                        fields=("lane", "sequence"),
                        name="uniq_judge_window_lane_sequence",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="judgescoredraft",
            name="scoring_window",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="score_drafts",
                to="competicions_trampoli.judgescoringwindow",
            ),
        ),
    ]
