from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.models import Person
from iatrain.engine.context import build_block_engine_context
from iatrain.evaluation.block_benchmark import (
    build_context_snapshot,
    context_fingerprint,
    process_metrics,
    quality_score,
    selected_cases,
    summarize_records,
    usage_cost,
)
from iatrain.models import AthleteProfile, CoachProfile, SessionParticipantPlan, TrainingSession
from iatrain.training.services import create_session_revision, create_training_session
from organizations.models import Organization


class BlockBenchmarkUnitTests(TestCase):
    def test_cases_are_fixed_and_selectable(self):
        self.assertEqual(len(selected_cases()), 8)
        self.assertEqual(selected_cases(("base",))[0]["duration_minutes"], 12)
        with self.assertRaises(ValueError):
            selected_cases(("inexistent",))

    def test_cost_uses_explicit_cached_and_uncached_rates(self):
        pricing = {
            "models": {
                "model-a": {
                    "input_per_million": 2,
                    "cached_input_per_million": 1,
                    "output_per_million": 4,
                }
            }
        }
        cost = usage_cost(
            {
                "input_tokens": 1_000_000,
                "cached_tokens": 250_000,
                "output_tokens": 500_000,
            },
            "model-a",
            pricing,
        )
        self.assertEqual(cost, 3.75)
        self.assertIsNone(usage_cost({}, "model-without-price", pricing))

    def test_critical_or_inappropriate_judgement_is_capped(self):
        judgement = {
            "outcome_assessment": {"appropriate": False},
            "critical_failure": False,
            "dimensions": {
                name: {"score": 95, "rationale": ""}
                for name in (
                    "safety", "personalization", "selection_coherence",
                    "dose_and_timing", "clarity_and_usability"
                )
            },
        }
        self.assertEqual(quality_score(judgement), 39.0)
        judgement["outcome_assessment"]["appropriate"] = True
        judgement["critical_failure"] = True
        self.assertEqual(quality_score(judgement), 39.0)

    def test_process_metrics_expose_search_depth_repairs_and_split_usage(self):
        run = SimpleNamespace(
            agent_trace=[
                {
                    "tool": "search_exercises", "status": "ok",
                    "total_matches": 20, "exercise_revision_ids": [1, 2, 3],
                },
                {
                    "tool": "get_exercise_details", "status": "ok",
                    "exercise_revision_ids": [1, 2],
                },
                {
                    "tool": "find_compatible_alternatives", "status": "ok",
                    "total_matches": 4, "exercise_revision_ids": [2, 4],
                },
            ],
            response_ids=["one", "two"],
            validation_payload={
                "attempts": [{"valid": False}, {"valid": True}],
                "review_attempts": [{"verdict": "revise"}, {"verdict": "pass"}],
            },
            usage_payload={
                "input_tokens": 100, "output_tokens": 20,
                "total_tokens": 120, "cached_tokens": 10,
                "planner": {"total_tokens": 90},
                "reviewer": {"total_tokens": 30},
            },
        )
        metrics = process_metrics(run)
        self.assertEqual(metrics["unique_candidates_returned"], 4)
        self.assertEqual(metrics["unique_candidates_inspected"], 2)
        self.assertEqual(metrics["server_repairs"], 1)
        self.assertEqual(metrics["review_revisions"], 1)

    def test_summary_keeps_quality_reliability_cost_and_value_separate(self):
        records = [
            {
                "model_requested": "model-a", "case_id": "base",
                "status": "proposed", "hard_gate_pass": True,
                "quality_score": 80, "elapsed_seconds": 10,
                "production_cost": 0.02, "judge_cost": 0.01,
                "process": {"tool_calls": 5, "server_repairs": 0,
                            "review_revisions": 0, "total_tokens": 1000},
            },
            {
                "model_requested": "model-a", "case_id": "base",
                "status": "failed", "hard_gate_pass": False,
                "quality_score": 0, "elapsed_seconds": 8,
                "production_cost": 0.01, "judge_cost": 0.0,
                "process": {"tool_calls": 2, "server_repairs": 1,
                            "review_revisions": 0, "total_tokens": 400},
            },
        ]
        summary = summarize_records(records)["by_model"]["model-a"]
        self.assertEqual(summary["hard_gate_rate"], 0.5)
        self.assertEqual(summary["quality_effective_mean"], 40.0)
        self.assertEqual(summary["production_cost_mean"], 0.015)
        self.assertEqual(summary["cost_per_hard_pass"], 0.03)


class BlockBenchmarkCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="benchmark-coach")
        CoachProfile.objects.create(person=self.user.person)
        organization = Organization.objects.create(name="Benchmark", slug="benchmark")
        athlete = AthleteProfile.objects.create(
            person=Person.objects.create(first_name="Aina", last_name="Benchmark")
        )
        session = create_training_session(
            user=self.user,
            organization=organization,
            scheduled_start=timezone.now(),
            expected_duration_minutes=60,
            discipline=TrainingSession.Discipline.TRAMPOLINE,
            session_scope=TrainingSession.Scope.INDIVIDUAL,
        )
        self.revision = create_session_revision(
            user=self.user,
            session=session,
            title="Benchmark models",
            general_objective="Preparació física",
            planned_duration_minutes=60,
        )
        SessionParticipantPlan.objects.create(
            session_revision=self.revision,
            athlete_profile=athlete,
        )

    def test_context_fingerprint_ignores_generation_timestamp(self):
        first = build_context_snapshot(
            build_block_engine_context(user=self.user, revision=self.revision)
        )
        second = build_context_snapshot(
            build_block_engine_context(user=self.user, revision=self.revision)
        )
        self.assertEqual(context_fingerprint(first), context_fingerprint(second))

    @patch("iatrain.engine.agent._post_responses_api")
    def test_dry_run_preflights_matrix_without_calling_openai(self, post_api):
        stdout = StringIO()
        call_command(
            "benchmark_training_models",
            "--coach-username", self.user.username,
            "--session-revision-id", str(self.revision.pk),
            "--models", "model-a", "model-b",
            "--case", "base",
            "--repetitions", "2",
            "--dry-run",
            stdout=stdout,
        )
        self.assertIn("4 generacions", stdout.getvalue())
        self.assertIn("No s’ha cridat cap LLM", stdout.getvalue())
        post_api.assert_not_called()

    def test_command_persists_partial_results_even_when_generation_fails(self):
        def fail_generation(*, user, run, context=None):
            run.status = run.Status.FAILED
            run.model_name = "model-a"
            run.error_code = "synthetic_failure"
            run.error_message = "Fallada simulada"
            run.usage_payload = {
                "input_tokens": 100,
                "output_tokens": 10,
                "total_tokens": 110,
                "cached_tokens": 0,
                "planner": {
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "total_tokens": 110,
                    "cached_tokens": 0,
                },
                "reviewer": {},
            }
            run.save()
            return run

        with TemporaryDirectory() as directory, patch(
            "iatrain.management.commands.benchmark_training_models."
            "execute_block_generation_run",
            side_effect=fail_generation,
        ):
            call_command(
                "benchmark_training_models",
                "--coach-username", self.user.username,
                "--session-revision-id", str(self.revision.pk),
                "--models", "model-a",
                "--case", "base",
                "--repetitions", "1",
                "--no-review",
                "--no-judge",
                "--output-dir", directory,
                "--run-name", "failure-test",
                stdout=StringIO(),
            )
            result_dir = Path(directory) / "failure-test"
            self.assertTrue((result_dir / "runs.jsonl").exists())
            summary = json.loads(
                (result_dir / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["by_model"]["model-a"]["failed"], 1)
            self.assertTrue((result_dir / "human_scores.csv").exists())
            self.assertTrue((result_dir / "blind_context.json").exists())
