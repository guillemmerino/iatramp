from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Person
from iatrain_biomechanics.models import MuscleActionFunction, MuscleStabilizationFunction
from iatrain_motion.models import EditorialStatus, MotionConcept

from iatrain_exercises.checks import audit_exercise_catalog
from iatrain_exercises.models import (
    Equipment,
    Exercise,
    ExerciseCatalog,
    ExerciseConstraint,
    ExerciseEquipmentRequirement,
    ExerciseObjective,
    ExercisePhase,
    ExercisePhaseAction,
    ExercisePhaseMuscleRole,
    ExerciseRevision,
)
from iatrain_exercises.vocabulary import EQUIPMENT, EXERCISES, SEED_VERSION


class Command(BaseCommand):
    help = "Crea una mostra idempotent d'exercicis dins del catàleg privat d'un usuari."

    def add_arguments(self, parser):
        parser.add_argument("--owner-username", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.select_related("person").get(
                username=options["owner_username"]
            )
            owner = user.person
        except (get_user_model().DoesNotExist, Person.DoesNotExist):
            raise CommandError("No existeix l'usuari o no té una identitat Person.")
        if not owner.is_active:
            raise CommandError("El propietari necessita una identitat activa.")

        provenance = {
            "seed": SEED_VERSION,
            "review_status": "owner_review_required",
            "scope": "private_example_catalog",
        }
        counts = {"catalogs": 0, "equipment": 0, "families": 0, "variants": 0, "revisions": 0, "phases": 0, "links": 0}
        catalog, created = ExerciseCatalog.objects.get_or_create(
            owner=owner,
            code="private_exercise_examples",
            defaults={
                "name": "Mostra privada d'exercicis",
                "description": "Catàleg demostratiu privat i ampliable; no és una capa professional comuna.",
            },
        )
        counts["catalogs"] += int(created)

        equipment_by_code = {}
        for row in EQUIPMENT:
            equipment, created = Equipment.objects.get_or_create(
                catalog=catalog,
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "category": row["category"],
                    "description": "Material de la mostra privada d'exercicis.",
                },
            )
            equipment_by_code[row["code"]] = equipment
            counts["equipment"] += int(created)

        action_codes = {
            action_code
            for item in EXERCISES
            for phase in item["phases"]
            for action_code, _role in phase["actions"]
        }
        muscle_codes = {
            muscle_code
            for item in EXERCISES
            for phase in item["phases"]
            for muscle_code, _role, _basis, _basis_type, _contraction in phase["muscles"]
        }
        concepts = MotionConcept.objects.in_bulk(action_codes | muscle_codes, field_name="code")
        missing_concepts = sorted((action_codes | muscle_codes) - set(concepts))
        if missing_concepts:
            raise CommandError(
                "Falta el coneixement anatòmic-cinemàtic previ: " + ", ".join(missing_concepts)
            )

        action_basis_codes = {
            basis_code
            for item in EXERCISES
            for phase in item["phases"]
            for _muscle, _role, basis_code, basis_type, _contraction in phase["muscles"]
            if basis_type == "action"
        }
        stabilization_basis_codes = {
            basis_code
            for item in EXERCISES
            for phase in item["phases"]
            for _muscle, _role, basis_code, basis_type, _contraction in phase["muscles"]
            if basis_type == "stabilization"
        }
        action_functions = MuscleActionFunction.objects.in_bulk(action_basis_codes, field_name="code")
        stabilization_functions = MuscleStabilizationFunction.objects.in_bulk(
            stabilization_basis_codes, field_name="code"
        )
        missing_basis = sorted(
            (action_basis_codes - set(action_functions))
            | (stabilization_basis_codes - set(stabilization_functions))
        )
        if missing_basis:
            raise CommandError("Falta la base biomecànica prèvia: " + ", ".join(missing_basis))

        for item in EXERCISES:
            family_code, family_name = item["family"]
            family, created = Exercise.objects.get_or_create(
                catalog=catalog,
                code=family_code,
                defaults={
                    "name": family_name,
                    "kind": Exercise.Kind.FAMILY,
                    "created_by": owner,
                },
            )
            counts["families"] += int(created)
            variant_code, variant_name = item["variant"]
            variant, created = Exercise.objects.get_or_create(
                catalog=catalog,
                code=variant_code,
                defaults={
                    "name": variant_name,
                    "kind": Exercise.Kind.VARIANT,
                    "parent": family,
                    "created_by": owner,
                },
            )
            counts["variants"] += int(created)
            revision, created = ExerciseRevision.objects.get_or_create(
                exercise=variant,
                revision_number=1,
                defaults={
                    **item["revision"],
                    "authored_by": owner,
                    "editorial_status": EditorialStatus.DRAFT,
                    "provenance": provenance,
                },
            )
            if not created and (revision.provenance or {}).get("seed") != SEED_VERSION:
                raise CommandError(f"La revisió {revision} ja existeix i no pertany a la llavor.")
            if revision.editorial_status != EditorialStatus.DRAFT:
                raise CommandError(f"La revisió {revision} ja no és un esborrany.")
            counts["revisions"] += int(created)

            for equipment_code, requirement in item["equipment"]:
                _row, link_created = ExerciseEquipmentRequirement.objects.get_or_create(
                    revision=revision,
                    equipment=equipment_by_code[equipment_code],
                    defaults={"requirement": requirement},
                )
                counts["links"] += int(link_created)
            desired_objectives = {objective for objective, _priority in item["objectives"]}
            if (revision.provenance or {}).get("seed") == SEED_VERSION:
                revision.objectives.exclude(objective__in=desired_objectives).delete()
            for objective, priority in item["objectives"]:
                _row, link_created = ExerciseObjective.objects.get_or_create(
                    revision=revision,
                    objective=objective,
                    defaults={
                        "priority": priority,
                        "rationale": "Objectiu funcional declarat per a la mostra; pendent de revisió de l'entrenador.",
                    },
                )
                counts["links"] += int(link_created)
            for code, kind, severity, statement in item["constraints"]:
                _row, link_created = ExerciseConstraint.objects.get_or_create(
                    revision=revision,
                    code=code,
                    defaults={
                        "kind": kind,
                        "severity": severity,
                        "statement": statement,
                        "rationale": "Condició pràctica d'execució, no prescripció clínica.",
                    },
                )
                counts["links"] += int(link_created)

            for phase_data in item["phases"]:
                phase, phase_created = ExercisePhase.objects.get_or_create(
                    revision=revision,
                    code=phase_data["code"],
                    defaults={
                        "sequence_index": len(revision.phases.all()) + 1,
                        "name": phase_data["name"],
                        "phase_type": phase_data["type"],
                        "intent": phase_data["intent"],
                        "description": phase_data["description"],
                        "is_key_phase": phase_data["key"],
                        "authored_by": owner,
                        "provenance": provenance,
                    },
                )
                counts["phases"] += int(phase_created)
                for action_code, role in phase_data["actions"]:
                    action_laterality = (
                        ExercisePhaseAction.Laterality.UNSPECIFIED
                        if revision.laterality == ExerciseRevision.Laterality.UNILATERAL
                        else ExercisePhaseAction.Laterality.BILATERAL
                    )
                    _row, link_created = ExercisePhaseAction.objects.get_or_create(
                        phase=phase,
                        action=concepts[action_code],
                        laterality=action_laterality,
                        defaults={
                            "role": role,
                            "verification_state": ExercisePhaseAction.VerificationState.INFERRED,
                            "rationale": "Acció observada esperada en aquesta fase de la mostra.",
                            "provenance": provenance,
                        },
                    )
                    counts["links"] += int(link_created)
                for muscle_code, role, basis_code, basis_type, contraction in phase_data["muscles"]:
                    basis_defaults = (
                        {"action_function": action_functions[basis_code]}
                        if basis_type == "action"
                        else {"stabilization_function": stabilization_functions[basis_code]}
                    )
                    _row, link_created = ExercisePhaseMuscleRole.objects.get_or_create(
                        phase=phase,
                        muscle=concepts[muscle_code],
                        role=role,
                        defaults={
                            **basis_defaults,
                            "expected_contraction": contraction,
                            "verification_state": ExercisePhaseMuscleRole.VerificationState.INFERRED,
                            "rationale": "Rol proposat des de la fase, la intenció i la funció biomecànica enllaçada.",
                            "provenance": provenance,
                        },
                    )
                    counts["links"] += int(link_created)

        issues = audit_exercise_catalog(catalog=catalog, include_drafts=True)
        if issues:
            raise CommandError("La mostra d'exercicis no és coherent:\n- " + "\n- ".join(issues))
        self.stdout.write(
            self.style.SUCCESS(
                f"{SEED_VERSION}: "
                + ", ".join(f"{key}={value}" for key, value in counts.items())
                + "; catàleg privat coherent en draft."
            )
        )
