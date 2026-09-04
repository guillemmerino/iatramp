import csv
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings

from iatrain.engine.context import build_block_engine_context
from iatrain.engine.eligibility import analyze_participant_eligibility
from iatrain.engine.services import (
    create_block_generation_run,
    execute_block_generation_run,
)
from iatrain.evaluation.block_benchmark import (
    BENCHMARK_VERSION,
    QUALITY_DIMENSIONS,
    build_catalog_snapshot,
    build_context_snapshot,
    context_fingerprint,
    evaluate_run_with_judge,
    outcome_name,
    process_metrics,
    selected_exercise_evidence,
    selected_cases,
    summarize_records,
    usage_cost,
)
from iatrain.models import BlockGenerationRun, TrainingSessionRevision


class Command(BaseCommand):
    help = (
        "Compara models de planificació física amb casos fixos, jutge cec, "
        "mètriques de procés i cost explícit."
    )

    def add_arguments(self, parser):
        parser.add_argument("--coach-username", required=True)
        parser.add_argument("--session-revision-id", required=True, type=int)
        parser.add_argument("--models", required=True, nargs="+")
        parser.add_argument("--case", dest="case_ids", action="append", default=[])
        parser.add_argument("--repetitions", type=int, default=3)
        parser.add_argument("--seed", type=int, default=20260822)
        parser.add_argument("--run-name", default="")
        parser.add_argument("--output-dir", default="var/benchmarks")
        parser.add_argument("--resume", default="")
        parser.add_argument(
            "--reasoning-effort",
            choices=("low", "medium", "high", "xhigh"),
            default="medium",
        )
        parser.add_argument(
            "--review-model",
            default=getattr(settings, "OPENAI_TRAINING_REVIEW_MODEL", "gpt-5.6-luna"),
        )
        parser.add_argument(
            "--review-reasoning-effort",
            choices=("low", "medium", "high", "xhigh"),
            default="medium",
        )
        parser.add_argument("--no-review", action="store_true")
        parser.add_argument(
            "--judge-model",
            default=getattr(settings, "OPENAI_TRAINING_REVIEW_MODEL", "gpt-5.6-luna"),
        )
        parser.add_argument(
            "--judge-reasoning-effort",
            choices=("low", "medium", "high", "xhigh"),
            default="high",
        )
        parser.add_argument("--no-judge", action="store_true")
        parser.add_argument("--pricing-file", default="")
        parser.add_argument("--reuse-decisions-from-run", type=int)
        parser.add_argument(
            "--coach-decision",
            action="append",
            default=[],
            metavar="CLAU=VALOR",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--fail-fast", action="store_true")

    def handle(self, *args, **options):
        if options["repetitions"] < 1:
            raise CommandError("--repetitions ha de ser com a mínim 1.")
        models = list(dict.fromkeys(options["models"]))
        try:
            cases = selected_cases(options["case_ids"])
        except ValueError as error:
            raise CommandError(str(error)) from error
        try:
            user = get_user_model().objects.get(username=options["coach_username"])
        except get_user_model().DoesNotExist as error:
            raise CommandError("L’usuari entrenador no existeix.") from error
        try:
            revision = TrainingSessionRevision.objects.select_related("session").get(
                pk=options["session_revision_id"]
            )
        except TrainingSessionRevision.DoesNotExist as error:
            raise CommandError("La versió de sessió no existeix.") from error

        remaining = revision.planned_duration_minutes - sum(
            revision.blocks.values_list("planned_duration_minutes", flat=True)
        )
        required = max(row["duration_minutes"] for row in cases)
        if remaining < required:
            raise CommandError(
                f"La versió només té {remaining} minuts lliures i el benchmark en necessita "
                f"{required}. Usa una versió clonada sense blocs aplicats."
            )

        decisions = self._decisions(options)
        context = build_block_engine_context(user=user, revision=revision)
        snapshot = build_context_snapshot(context)
        fingerprint = context_fingerprint(snapshot)
        catalog_snapshot = build_catalog_snapshot(context.owner)
        catalog_fingerprint = context_fingerprint(catalog_snapshot)
        eligibility = analyze_participant_eligibility(
            context=context, decisions=decisions
        )
        if eligibility.needs_decision:
            choices = []
            for issue in eligibility.payload().get("issues", []):
                key = issue.get("decision_key", issue.get("participant_plan_id"))
                values = ", ".join(
                    row.get("value", "") for row in issue.get("choices", [])
                )
                choices.append(f"{key}=[{values}]")
            raise CommandError(
                "Falten decisions prèvies i no convé comparar models amb contextos "
                "diferents. Usa --coach-decision CLAU=VALOR o "
                "--reuse-decisions-from-run ID. Decisions: " + "; ".join(choices)
            )

        pricing = self._load_pricing(options["pricing_file"])
        jobs = self._jobs(
            cases=cases,
            models=models,
            repetitions=options["repetitions"],
            seed=options["seed"],
        )
        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Preflight correcte: {len(jobs)} generacions, "
                    f"{len(cases)} casos, {len(models)} models, "
                    f"context {fingerprint[:12]}, catàleg {catalog_fingerprint[:12]}. "
                    "No s’ha cridat cap LLM."
                )
            )
            for case in cases:
                self.stdout.write(
                    f"- {case['id']}: {case['duration_minutes']} min · "
                    f"{case['title']}"
                )
            return

        output_dir, records, manifest = self._prepare_output(
            options=options,
            models=models,
            cases=cases,
            fingerprint=fingerprint,
            snapshot=snapshot,
            catalog_fingerprint=catalog_fingerprint,
            catalog_snapshot=catalog_snapshot,
            decisions=decisions,
            pricing=pricing,
        )
        completed = {
            (row["case_id"], row["model_requested"], int(row["repetition"]))
            for row in records
        }
        pending = [
            row for row in jobs
            if (row["case"]["id"], row["model"], row["repetition"]) not in completed
        ]
        self.stdout.write(
            f"Benchmark {manifest['run_name']}: {len(pending)} pendents de "
            f"{len(jobs)}; resultats a {output_dir}."
        )

        for index, job in enumerate(pending, start=1):
            current_context = build_block_engine_context(user=user, revision=revision)
            current_snapshot = build_context_snapshot(current_context)
            if context_fingerprint(current_snapshot) != fingerprint:
                raise CommandError(
                    "El context de la sessió ha canviat durant el benchmark. "
                    "S’atura per no barrejar condicions."
                )
            if context_fingerprint(build_catalog_snapshot(context.owner)) != catalog_fingerprint:
                raise CommandError(
                    "El catàleg professional ha canviat durant el benchmark. "
                    "S’atura per no comparar models amb candidats diferents."
                )
            case = job["case"]
            model = job["model"]
            self.stdout.write(
                f"[{index}/{len(pending)}] {case['id']} · {model} · "
                f"repetició {job['repetition']}"
            )
            started = time.monotonic()
            run = create_block_generation_run(
                user=user,
                revision=revision,
                prompt=case["prompt"],
                duration_minutes=case["duration_minutes"],
                block_role=case["block_role"],
            )
            run.coach_decisions = decisions
            run.save(update_fields=("coach_decisions", "updated_at"))
            generation_error = ""
            try:
                with override_settings(
                    OPENAI_TRAINING_MODEL=model,
                    OPENAI_TRAINING_REASONING_EFFORT=options["reasoning_effort"],
                    OPENAI_TRAINING_REVIEW_ENABLED=not options["no_review"],
                    OPENAI_TRAINING_REVIEW_MODEL=options["review_model"],
                    OPENAI_TRAINING_REVIEW_REASONING_EFFORT=options[
                        "review_reasoning_effort"
                    ],
                ):
                    execute_block_generation_run(user=user, run=run, context=context)
            except Exception as error:  # The failed run remains audited in the database.
                generation_error = str(error)[:1000]
                if options["fail_fast"]:
                    raise
            elapsed = round(time.monotonic() - started, 3)
            run.refresh_from_db()
            judge = None
            judge_error = ""
            exercise_evidence = selected_exercise_evidence(run.proposal_payload)
            if not options["no_judge"]:
                try:
                    judge = evaluate_run_with_judge(
                        run=run,
                        case=case,
                        context_snapshot=current_snapshot,
                        judge_model=options["judge_model"],
                        reasoning_effort=options["judge_reasoning_effort"],
                        exercise_evidence=exercise_evidence,
                    )
                except Exception as error:
                    judge_error = str(error)[:1000]
                    if options["fail_fast"]:
                        raise
            record = self._record(
                run=run,
                job=job,
                elapsed=elapsed,
                generation_error=generation_error,
                judge=judge,
                judge_error=judge_error,
                review_model=options["review_model"],
                review_enabled=not options["no_review"],
                pricing=pricing,
                seed=options["seed"],
                exercise_evidence=exercise_evidence,
            )
            records.append(record)
            self._write_outputs(output_dir, manifest, records)
            label = "PASS" if record["hard_gate_pass"] else "NO PASS"
            self.stdout.write(
                f"  {label} · estat {run.status} · qualitat "
                f"{record['quality_score']} · {elapsed}s · run DB {run.pk}"
            )

        summary = summarize_records(records)
        self.stdout.write(self.style.SUCCESS("Benchmark complet."))
        for model, row in summary["by_model"].items():
            gate_label = (
                f"{row['hard_gate_rate']:.0%}"
                if row["hard_gate_rate"] is not None else "n/d"
            )
            self.stdout.write(
                f"- {model}: qualitat efectiva {row['quality_effective_mean']}, "
                f"pass {gate_label}, cost mitjà "
                f"{row['production_cost_mean']}, valor/cent "
                f"{row['value_points_per_cent']}"
            )
        self.stdout.write(f"Resum: {output_dir / 'summary.json'}")

    def _decisions(self, options):
        decisions = {}
        source_id = options.get("reuse_decisions_from_run")
        if source_id:
            try:
                source = BlockGenerationRun.objects.get(pk=source_id)
            except BlockGenerationRun.DoesNotExist as error:
                raise CommandError("La run indicada per reutilitzar decisions no existeix.") from error
            decisions.update(source.coach_decisions or {})
        for raw in options.get("coach_decision", []):
            if "=" not in raw:
                raise CommandError("--coach-decision ha de tenir format CLAU=VALOR.")
            key, value = raw.split("=", 1)
            key, value = key.strip(), value.strip()
            if not key or not value:
                raise CommandError("--coach-decision ha de tenir format CLAU=VALOR.")
            decisions[key] = value
        return decisions

    def _load_pricing(self, filename):
        if not filename:
            return {"currency": "EUR", "models": {}}
        path = Path(filename)
        if not path.exists():
            raise CommandError(f"No existeix el fitxer de preus: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CommandError("El fitxer de preus no és JSON vàlid.") from error
        if not isinstance(payload.get("models"), dict):
            raise CommandError("El fitxer de preus necessita un objecte 'models'.")
        return payload

    def _jobs(self, *, cases, models, repetitions, seed):
        rng = random.Random(seed)
        jobs = []
        for repetition in range(1, repetitions + 1):
            for case in cases:
                ordered_models = list(models)
                rng.shuffle(ordered_models)
                for model in ordered_models:
                    jobs.append(
                        {"case": case, "model": model, "repetition": repetition}
                    )
        return jobs

    def _prepare_output(
        self, *, options, models, cases, fingerprint, snapshot,
        catalog_fingerprint, catalog_snapshot, decisions, pricing
    ):
        if options["resume"]:
            output_dir = Path(options["resume"])
            manifest_path = output_dir / "manifest.json"
            if not manifest_path.exists():
                raise CommandError("El directori de represa no conté manifest.json.")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("context_fingerprint") != fingerprint:
                raise CommandError("El context actual no coincideix amb el benchmark reprès.")
            if manifest.get("catalog_fingerprint") != catalog_fingerprint:
                raise CommandError("El catàleg actual no coincideix amb el benchmark reprès.")
            if manifest.get("models") != models:
                raise CommandError("Els models no coincideixen amb el benchmark reprès.")
            if manifest.get("cases", []) != list(cases):
                raise CommandError("Els casos no coincideixen amb el benchmark reprès.")
            if manifest.get("coach_decisions", {}) != decisions:
                raise CommandError("Les decisions no coincideixen amb el benchmark reprès.")
            if manifest.get("pricing", {}) != pricing:
                raise CommandError("Les tarifes no coincideixen amb el benchmark reprès.")
            expected_options = {
                "review_model": options["review_model"],
                "review_enabled": not options["no_review"],
                "judge_model": options["judge_model"],
                "judge_enabled": not options["no_judge"],
                "repetitions": options["repetitions"],
                "seed": options["seed"],
                "reasoning_effort": options["reasoning_effort"],
                "review_reasoning_effort": options["review_reasoning_effort"],
                "judge_reasoning_effort": options["judge_reasoning_effort"],
            }
            mismatched = [
                key for key, value in expected_options.items()
                if manifest.get(key) != value
            ]
            if mismatched:
                raise CommandError(
                    "La configuració no coincideix amb el benchmark reprès: "
                    + ", ".join(mismatched)
                )
            records = self._read_jsonl(output_dir / "runs.jsonl")
            return output_dir, records, manifest

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_name = options["run_name"].strip() or f"training-models-{stamp}"
        output_dir = Path(options["output_dir"]) / run_name
        if output_dir.exists():
            raise CommandError(
                "El directori del benchmark ja existeix; usa un altre --run-name o --resume."
            )
        output_dir.mkdir(parents=True)
        manifest = {
            "benchmark_version": BENCHMARK_VERSION,
            "run_name": run_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "session_revision_id": options["session_revision_id"],
            "coach_username": options["coach_username"],
            "models": models,
            "review_model": options["review_model"],
            "review_enabled": not options["no_review"],
            "judge_model": options["judge_model"],
            "judge_enabled": not options["no_judge"],
            "repetitions": options["repetitions"],
            "seed": options["seed"],
            "reasoning_effort": options["reasoning_effort"],
            "review_reasoning_effort": options["review_reasoning_effort"],
            "judge_reasoning_effort": options["judge_reasoning_effort"],
            "cases": cases,
            "context_fingerprint": fingerprint,
            "context_snapshot": snapshot,
            "catalog_fingerprint": catalog_fingerprint,
            "catalog_snapshot": catalog_snapshot,
            "coach_decisions": decisions,
            "pricing": pricing,
            "quality_weights": QUALITY_DIMENSIONS,
        }
        self._atomic_json(output_dir / "manifest.json", manifest)
        return output_dir, [], manifest

    def _record(
        self, *, run, job, elapsed, generation_error, judge, judge_error,
        review_model, review_enabled, pricing, seed, exercise_evidence
    ):
        case = job["case"]
        process = process_metrics(run)
        usage = run.usage_payload or {}
        planner_usage = usage.get("planner") or (
            usage if "planner" not in usage else {}
        )
        reviewer_usage = usage.get("reviewer") or {}
        planner_model = run.model_name or job["model"]
        planner_cost = usage_cost(planner_usage, planner_model, pricing)
        actual_reviewer_model = usage.get("reviewer_model") or review_model
        reviewer_cost = (
            usage_cost(reviewer_usage, actual_reviewer_model, pricing)
            if review_enabled else 0.0
        )
        production_cost = (
            round(planner_cost + reviewer_cost, 8)
            if planner_cost is not None and reviewer_cost is not None else None
        )
        judge_cost = None
        if judge:
            judge_cost = usage_cost(
                judge.get("usage") or {}, judge.get("model", ""), pricing
            )
        judgement = (judge or {}).get("judgement")
        expected = outcome_name(run.status) in case["expected_outcomes"]
        judged_appropriate = (
            judgement.get("outcome_assessment", {}).get("appropriate", False)
            if judgement else (judge is None and not judge_error)
        )
        critical = bool(judgement and judgement.get("critical_failure"))
        final_review = (run.validation_payload or {}).get("independent_review") or {}
        material_review_issues = [
            row for row in final_review.get("issues", [])
            if row.get("severity") in {"critical", "error"}
        ]
        review_pass = not (
            run.status == run.Status.REVIEW_REQUIRED
            or bool((run.validation_payload or {}).get("review_required"))
            or material_review_issues
            or final_review.get("verdict") == "needs_clarification"
        )
        hard_gate = bool(expected and judged_appropriate and not critical and review_pass)
        run_key = f"{case['id']}::{job['model']}::{job['repetition']}"
        blind_id = __import__("hashlib").sha256(
            f"{seed}:{run_key}".encode("utf-8")
        ).hexdigest()[:12]
        return {
            "benchmark_version": BENCHMARK_VERSION,
            "run_key": run_key,
            "blind_id": blind_id,
            "case_id": case["id"],
            "case_title": case["title"],
            "prompt": case["prompt"],
            "repetition": job["repetition"],
            "model_requested": job["model"],
            "model_actual": planner_model,
            "database_run_id": run.pk,
            "status": run.status,
            "expected_outcomes": case["expected_outcomes"],
            "hard_gate_pass": hard_gate,
            "quality_score": (judge or {}).get("quality_score"),
            "elapsed_seconds": elapsed,
            "process": process,
            "usage": usage,
            "cost_currency": pricing.get("currency", "EUR"),
            "planner_cost": planner_cost,
            "reviewer_cost": reviewer_cost,
            "production_cost": production_cost,
            "judge_cost": judge_cost,
            "judge": judge,
            "generation_error": generation_error or run.error_message,
            "judge_error": judge_error,
            "proposal": run.proposal_payload,
            "decision": run.decision_payload,
            "interpretation": run.interpretation_payload,
            "planning": run.planning_payload,
            "validation": run.validation_payload,
            "exercise_evidence": exercise_evidence,
        }

    def _write_outputs(self, output_dir, manifest, records):
        runs_path = output_dir / "runs.jsonl"
        runs_path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, default=str) + "\n"
                for row in records
            ),
            encoding="utf-8",
        )
        summary = summarize_records(records)
        summary["run_name"] = manifest["run_name"]
        summary["context_fingerprint"] = manifest["context_fingerprint"]
        self._atomic_json(output_dir / "summary.json", summary)
        self._write_summary_csv(output_dir / "summary.csv", summary)
        self._write_blind_files(output_dir, records, manifest)

    def _write_summary_csv(self, path, summary):
        rows = []
        for model, values in summary["by_model"].items():
            rows.append({"model": model, **values})
        fields = list(rows[0]) if rows else ["model"]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def _write_blind_files(self, output_dir, records, manifest):
        (output_dir / "blind_review.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        "blind_id": row["blind_id"],
                        "case_id": row["case_id"],
                        "case_title": row["case_title"],
                        "prompt": row["prompt"],
                        "status": row["status"],
                        "proposal": row["proposal"],
                        "decision": row["decision"],
                        "exercise_evidence": row["exercise_evidence"],
                    },
                    ensure_ascii=False,
                    default=str,
                ) + "\n"
                for row in records
            ),
            encoding="utf-8",
        )
        key = {
            row["blind_id"]: {
                "model": row["model_requested"],
                "case_id": row["case_id"],
                "repetition": row["repetition"],
                "database_run_id": row["database_run_id"],
            }
            for row in records
        }
        self._atomic_json(output_dir / "blind_key.json", key)
        self._atomic_json(
            output_dir / "blind_context.json",
            {
                "cases": manifest["cases"],
                "context_snapshot": manifest["context_snapshot"],
                "quality_weights": manifest["quality_weights"],
            },
        )
        human_path = output_dir / "human_scores.csv"
        fields = [
            "blind_id", "case_id", *QUALITY_DIMENSIONS,
            "critical_failure", "notes"
        ]
        previous = {}
        if human_path.exists():
            with human_path.open("r", encoding="utf-8", newline="") as handle:
                previous = {
                    row["blind_id"]: row for row in csv.DictReader(handle)
                    if row.get("blind_id")
                }
        with human_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in records:
                saved = previous.get(row["blind_id"], {})
                writer.writerow(
                    {
                        **{field: saved.get(field, "") for field in fields},
                        "blind_id": row["blind_id"],
                        "case_id": row["case_id"],
                    }
                )

    def _read_jsonl(self, path):
        if not path.exists():
            return []
        return [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _atomic_json(self, path, payload):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
