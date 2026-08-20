import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field

from django.db import transaction

from iatrain_biomechanics.models import MuscleActionFunction, MuscleStabilizationFunction
from iatrain_motion.models import EditorialStatus, MotionConcept, normalize_label

from .catalog_data.v2 import BATCHES, CATALOG_VERSION, EQUIPMENT, SOURCES
from .checks import audit_exercise_catalog
from .completeness import refresh_revision_gaps
from .models import (
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


class CatalogDataError(ValueError):
    pass


class SemanticCollision(RuntimeError):
    pass


@dataclass
class ImportSummary:
    created: Counter = field(default_factory=Counter)
    updated: Counter = field(default_factory=Counter)
    skipped: Counter = field(default_factory=Counter)
    conflicts: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    batches: list = field(default_factory=list)

    def as_dict(self):
        return {
            "version": CATALOG_VERSION,
            "created": dict(self.created),
            "updated": dict(self.updated),
            "skipped": dict(self.skipped),
            "conflicts": self.conflicts,
            "gaps": self.gaps,
            "batches": self.batches,
        }


def _fingerprint(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_payload(source_refs):
    return [{"code": code, **SOURCES[code]} for code in source_refs]


def _provenance(*, batch_code, source_refs, payload_fingerprint, managed_fingerprint=""):
    return {
        "import_version": CATALOG_VERSION,
        "batch": batch_code,
        "scope": "personal_catalog_only",
        "review_status": "owner_review_required",
        "payload_fingerprint": payload_fingerprint,
        "managed_fingerprint": managed_fingerprint,
        "sources": _source_payload(source_refs),
    }


def validate_catalog_data(batches=BATCHES):
    errors = []
    variant_codes = set()
    variant_names = set()
    family_codes = set()
    family_names = set()
    equipment_codes = {row[0] for row in EQUIPMENT}
    choice_sets = {
        "modality": {row[0] for row in ExerciseRevision.Modality.choices},
        "execution_type": {row[0] for row in ExerciseRevision.ExecutionType.choices},
        "difficulty": {row[0] for row in ExerciseRevision.Difficulty.choices},
        "laterality": {row[0] for row in ExerciseRevision.Laterality.choices},
        "kinetic_chain": {row[0] for row in ExerciseRevision.KineticChain.choices},
        "movement_pattern": {row[0] for row in ExerciseRevision.MovementPattern.choices},
    }
    for batch in batches:
        if not 25 <= len(batch["variants"]) <= 50:
            errors.append(f"{batch['code']}: el lot ha de contenir entre 25 i 50 variants.")
        for item in batch["variants"]:
            code = item["variant"]["code"]
            family_codes.add(item["family"]["code"])
            family_names.add(normalize_label(item["family"]["name"]).casefold())
            normalized_name = normalize_label(item["variant"]["name"]).casefold()
            if code in variant_codes:
                errors.append(f"Codi de variant duplicat: {code}.")
            if normalized_name in variant_names:
                errors.append(f"Nom de variant duplicat: {item['variant']['name']}.")
            variant_codes.add(code)
            variant_names.add(normalized_name)
            for field_name, allowed in choice_sets.items():
                value = item["revision"][field_name]
                if value not in allowed:
                    errors.append(f"{code}: {field_name}={value} no és un valor controlat.")
            if not item["phases"] or not any(phase["key"] for phase in item["phases"]):
                errors.append(f"{code}: falta una fase clau.")
            if not item["objectives"] or not any(row["priority"] == "primary" for row in item["objectives"]):
                errors.append(f"{code}: falta un objectiu principal.")
            for row in item["equipment"]:
                if row["code"] not in equipment_codes:
                    errors.append(f"{code}: material desconegut {row['code']}.")
            for source_ref in item["source_refs"]:
                if source_ref not in SOURCES:
                    errors.append(f"{code}: font desconeguda {source_ref}.")
            for phase in item["phases"]:
                if phase["intent"] in {"produce", "assist", "control"} and not phase["actions"]:
                    errors.append(f"{code}.{phase['code']}: la fase motriu no té accions.")
                for role in phase["muscles"]:
                    if role["basis_type"] not in {"action", "stabilization"}:
                        errors.append(f"{code}.{phase['code']}: tipus de base desconegut.")
                    if role["role"] == "stabilizer" and role["basis_type"] != "stabilization":
                        errors.append(f"{code}.{phase['code']}: estabilitzador sense funció estabilitzadora.")
                    if role["role"] != "stabilizer" and role["basis_type"] != "action":
                        errors.append(f"{code}.{phase['code']}: contribuïdor sense funció d'acció.")
    for code in sorted(family_codes & variant_codes):
        errors.append(f"El codi {code} col·lideix entre família i variant.")
    for name in sorted(family_names & variant_names):
        errors.append(f"El nom normalitzat {name} col·lideix entre família i variant.")
    if errors:
        raise CatalogDataError("\n".join(errors))
    return {
        "batches": len(batches),
        "variants": len(variant_codes),
        "families": len({item["family"]["code"] for batch in batches for item in batch["variants"]}),
    }


def build_coverage_matrix(batches=BATCHES):
    rows = [item for batch in batches for item in batch["variants"]]

    def count(path):
        result = Counter()
        for item in rows:
            value = item
            for key in path:
                value = value[key]
            result[value] += 1
        return dict(sorted(result.items()))

    return {
        "variants": len(rows),
        "families": len({item["family"]["code"] for item in rows}),
        "patterns": count(("revision", "movement_pattern")),
        "modalities": count(("revision", "modality")),
        "difficulties": count(("revision", "difficulty")),
        "lateralities": count(("revision", "laterality")),
        "kinetic_chains": count(("revision", "kinetic_chain")),
        "execution_types": count(("revision", "execution_type")),
        "objectives": dict(sorted(Counter(row["code"] for item in rows for row in item["objectives"]).items())),
        "equipment": dict(sorted(Counter(row["code"] for item in rows for row in item["equipment"]).items())),
        "actions": dict(sorted(Counter(row["code"] for item in rows for phase in item["phases"] for row in phase["actions"]).items())),
        "muscles": dict(sorted(Counter(row["code"] for item in rows for phase in item["phases"] for row in phase["muscles"]).items())),
    }


def _revision_snapshot(revision):
    return {
        "revision": {
            field: getattr(revision, field)
            for field in (
                "modality", "execution_type", "difficulty", "laterality", "kinetic_chain",
                "movement_pattern", "description", "setup", "execution", "coaching_cues",
                "safety_notes", "requires_equipment",
            )
        },
        "equipment": sorted(
            ({"code": row.equipment.code, "requirement": row.requirement, "notes": row.notes} for row in revision.equipment_requirements.select_related("equipment")),
            key=lambda row: row["code"],
        ),
        "objectives": sorted(
            ({"code": row.objective, "priority": row.priority, "rationale": row.rationale} for row in revision.objectives.all()),
            key=lambda row: row["code"],
        ),
        "constraints": sorted(
            ({"code": row.code, "kind": row.kind, "severity": row.severity, "statement": row.statement, "rationale": row.rationale} for row in revision.constraints.all()),
            key=lambda row: row["code"],
        ),
        "phases": [
            {
                "code": phase.code,
                "name": phase.name,
                "type": phase.phase_type,
                "intent": phase.intent,
                "key": phase.is_key_phase,
                "description": phase.description,
                "actions": sorted(
                    (
                        {"code": row.action.code, "role": row.role, "laterality": row.laterality,
                         "verification_state": row.verification_state, "rationale": row.rationale}
                        for row in phase.actions.select_related("action")
                    ),
                    key=lambda row: (row["role"], row["code"]),
                ),
                "muscles": sorted(
                    (
                        {
                            "code": row.muscle.code,
                            "role": row.role,
                            "basis": (row.action_function or row.stabilization_function).code,
                            "basis_type": "action" if row.action_function_id else "stabilization",
                            "contraction": row.expected_contraction,
                            "verification_state": row.verification_state,
                            "rationale": row.rationale,
                        }
                        for row in phase.muscle_roles.select_related("muscle", "action_function", "stabilization_function")
                    ),
                    key=lambda row: (row["role"], row["code"]),
                ),
            }
            for phase in revision.phases.order_by("sequence_index")
        ],
    }


class PrivateCatalogImporter:
    def __init__(self, *, owner, batch_codes=()):
        self.owner = owner
        self.batches = tuple(
            batch for batch in BATCHES if not batch_codes or batch["code"] in set(batch_codes)
        )
        unknown = set(batch_codes) - {batch["code"] for batch in BATCHES}
        if unknown:
            raise CatalogDataError("Lots desconeguts: " + ", ".join(sorted(unknown)))
        validate_catalog_data(self.batches)
        self.summary = ImportSummary()
        self.catalog = None
        self.equipment = {}
        self.concepts = {}
        self.action_functions = {}
        self.stabilization_functions = {}

    def run(self):
        self._prepare_catalog_and_references()
        for batch in self.batches:
            for item in batch["variants"]:
                created_before = self.summary.created.copy()
                updated_before = self.summary.updated.copy()
                skipped_before = self.summary.skipped.copy()
                try:
                    with transaction.atomic():
                        self._sync_variant(batch["code"], item)
                except Exception as exc:  # a collision must not discard completed variants
                    self.summary.created = created_before
                    self.summary.updated = updated_before
                    self.summary.skipped = skipped_before
                    self.summary.conflicts.append(
                        {"batch": batch["code"], "variant": item["variant"]["code"], "reason": str(exc)}
                    )
            batch_codes = [item["variant"]["code"] for item in batch["variants"]]
            for revision in ExerciseRevision.objects.filter(
                exercise__catalog=self.catalog, exercise__code__in=batch_codes
            ):
                open_gaps = refresh_revision_gaps(revision)
                self.summary.gaps.extend(
                    {"variant": revision.exercise.code, "code": gap.requirement_code, "description": gap.description}
                    for gap in open_gaps
                )
            issues = audit_exercise_catalog(catalog=self.catalog, include_drafts=True)
            self.summary.batches.append(
                {
                    "code": batch["code"],
                    "requested": len(batch["variants"]),
                    "audit_issues": len(issues),
                    "conflicts_total": len(self.summary.conflicts),
                }
            )
            if issues:
                raise CatalogDataError(
                    f"L'auditoria del lot {batch['code']} ha fallat:\n- " + "\n- ".join(issues[:50])
                )
        return self.summary

    @transaction.atomic
    def _prepare_catalog_and_references(self):
        self.catalog, created = ExerciseCatalog.objects.get_or_create(
            owner=self.owner,
            code="private_exercise_examples",
            defaults={
                "name": "Catàleg privat d'exercicis",
                "description": "Base privada extensa i revisable d'exercicis d'IA Train.",
                "kind": ExerciseCatalog.Kind.PERSONAL,
            },
        )
        self.summary.created["catalogs"] += int(created)
        for code, name, category in EQUIPMENT:
            existing = Equipment.objects.filter(catalog=self.catalog, code=code).first()
            if existing:
                if normalize_label(existing.name).casefold() != normalize_label(name).casefold() or existing.category != category:
                    raise SemanticCollision(f"Col·lisió semàntica de material: {code}.")
                self.equipment[code] = existing
                continue
            name_collision = Equipment.objects.filter(catalog=self.catalog, name__iexact=name).first()
            if name_collision:
                raise SemanticCollision(f"El material {name} ja existeix amb el codi {name_collision.code}.")
            self.equipment[code] = Equipment.objects.create(
                catalog=self.catalog,
                code=code,
                name=name,
                category=category,
                description="Material del catàleg privat; pendent de revisió del propietari.",
            )
            self.summary.created["equipment"] += 1

        action_codes = set()
        muscle_codes = set()
        action_basis_codes = set()
        stabilization_basis_codes = set()
        for batch in self.batches:
            for item in batch["variants"]:
                for phase in item["phases"]:
                    action_codes.update(row["code"] for row in phase["actions"])
                    muscle_codes.update(row["code"] for row in phase["muscles"])
                    action_basis_codes.update(row["basis"] for row in phase["muscles"] if row["basis_type"] == "action")
                    stabilization_basis_codes.update(row["basis"] for row in phase["muscles"] if row["basis_type"] == "stabilization")
        self.concepts = MotionConcept.objects.in_bulk(action_codes | muscle_codes, field_name="code")
        self.action_functions = MuscleActionFunction.objects.in_bulk(action_basis_codes, field_name="code")
        self.stabilization_functions = MuscleStabilizationFunction.objects.in_bulk(stabilization_basis_codes, field_name="code")
        missing = sorted(
            (action_codes | muscle_codes) - set(self.concepts)
            | action_basis_codes - set(self.action_functions)
            | stabilization_basis_codes - set(self.stabilization_functions)
        )
        if missing:
            raise CatalogDataError("Referències professionals absents: " + ", ".join(missing))

    def _resolve_identity(self, item):
        family_data = item["family"]
        family = Exercise.objects.filter(catalog=self.catalog, code=family_data["code"]).first()
        if family:
            if family.kind != Exercise.Kind.FAMILY or normalize_label(family.name).casefold() != normalize_label(family_data["name"]).casefold():
                raise SemanticCollision(f"Col·lisió de família: {family_data['code']}.")
        else:
            collision = Exercise.objects.filter(catalog=self.catalog, name__iexact=family_data["name"]).first()
            if collision:
                raise SemanticCollision(f"La família {family_data['name']} ja usa el codi {collision.code}.")
            family = Exercise.objects.create(
                catalog=self.catalog, code=family_data["code"], name=family_data["name"],
                kind=Exercise.Kind.FAMILY, created_by=self.owner,
            )
            self.summary.created["families"] += 1

        variant_data = item["variant"]
        variant = Exercise.objects.filter(catalog=self.catalog, code=variant_data["code"]).first()
        if variant:
            if (
                variant.kind != Exercise.Kind.VARIANT
                or variant.parent_id != family.id
                or normalize_label(variant.name).casefold() != normalize_label(variant_data["name"]).casefold()
            ):
                raise SemanticCollision(f"Col·lisió de variant: {variant_data['code']}.")
        else:
            collision = Exercise.objects.filter(catalog=self.catalog, name__iexact=variant_data["name"]).first()
            if collision:
                raise SemanticCollision(f"La variant {variant_data['name']} ja usa el codi {collision.code}.")
            variant = Exercise.objects.create(
                catalog=self.catalog, code=variant_data["code"], name=variant_data["name"],
                kind=Exercise.Kind.VARIANT, parent=family, created_by=self.owner,
            )
            self.summary.created["variants"] += 1
        return variant

    def _sync_variant(self, batch_code, item):
        variant = self._resolve_identity(item)
        payload_fingerprint = _fingerprint({"item": item, "sources": _source_payload(item["source_refs"])})
        revision = ExerciseRevision.objects.filter(exercise=variant, revision_number=1).first()
        if revision:
            provenance = revision.provenance or {}
            if provenance.get("import_version") != CATALOG_VERSION:
                raise SemanticCollision("La revisió 1 existeix i no pertany a aquesta importació.")
            if revision.editorial_status != EditorialStatus.DRAFT:
                self.summary.skipped["protected_revisions"] += 1
                return
            current_fingerprint = _fingerprint(_revision_snapshot(revision))
            if current_fingerprint != provenance.get("managed_fingerprint"):
                raise SemanticCollision("La revisió ha estat modificada després de la importació.")
            if payload_fingerprint == provenance.get("payload_fingerprint"):
                self.summary.skipped["unchanged_variants"] += 1
                return
            for relation in (revision.phases, revision.equipment_requirements, revision.objectives, revision.constraints):
                relation.all().delete()
            for field_name, value in item["revision"].items():
                setattr(revision, field_name, value)
            revision.provenance = _provenance(
                batch_code=batch_code, source_refs=item["source_refs"], payload_fingerprint=payload_fingerprint
            )
            revision.save()
            self.summary.updated["revisions"] += 1
        else:
            revision = ExerciseRevision.objects.create(
                exercise=variant,
                revision_number=1,
                authored_by=self.owner,
                editorial_status=EditorialStatus.DRAFT,
                provenance=_provenance(
                    batch_code=batch_code, source_refs=item["source_refs"], payload_fingerprint=payload_fingerprint
                ),
                **item["revision"],
            )
            self.summary.created["revisions"] += 1

        child_provenance = _provenance(
            batch_code=batch_code, source_refs=item["source_refs"], payload_fingerprint=payload_fingerprint
        )
        for row in item["equipment"]:
            ExerciseEquipmentRequirement.objects.create(
                revision=revision, equipment=self.equipment[row["code"]], requirement=row["requirement"],
                notes="Classificació de material de la variant importada.",
            )
            self.summary.created["equipment_links"] += 1
        for row in item["objectives"]:
            ExerciseObjective.objects.create(
                revision=revision, objective=row["code"], priority=row["priority"],
                rationale="Objectiu funcional de la variant; no incorpora dosificació universal.",
            )
            self.summary.created["objectives"] += 1
        for row in item["constraints"]:
            ExerciseConstraint.objects.create(
                revision=revision, code=row["code"], kind=row["kind"], severity=row["severity"],
                statement=row["statement"], rationale="Condició d'execució pràctica i no clínica.",
            )
            self.summary.created["constraints"] += 1
        laterality = {
            "bilateral": ExercisePhaseAction.Laterality.BILATERAL,
            "alternating": ExercisePhaseAction.Laterality.ALTERNATING,
        }.get(revision.laterality, ExercisePhaseAction.Laterality.UNSPECIFIED)
        for index, phase_data in enumerate(item["phases"], start=1):
            phase = ExercisePhase.objects.create(
                revision=revision, sequence_index=index, code=phase_data["code"], name=phase_data["name"],
                phase_type=phase_data["type"], intent=phase_data["intent"], description=phase_data["description"],
                is_key_phase=phase_data["key"], authored_by=self.owner, provenance=child_provenance,
            )
            self.summary.created["phases"] += 1
            for row in phase_data["actions"]:
                ExercisePhaseAction.objects.create(
                    phase=phase, action=self.concepts[row["code"]], role=row["role"], laterality=laterality,
                    verification_state=ExercisePhaseAction.VerificationState.INFERRED,
                    rationale="Acció observable proposada per la fase; pendent de confirmació de l'entrenador.",
                    provenance=child_provenance,
                )
                self.summary.created["actions"] += 1
            for row in phase_data["muscles"]:
                basis = (
                    {"action_function": self.action_functions[row["basis"]]}
                    if row["basis_type"] == "action"
                    else {"stabilization_function": self.stabilization_functions[row["basis"]]}
                )
                ExercisePhaseMuscleRole.objects.create(
                    phase=phase, muscle=self.concepts[row["code"]], role=row["role"],
                    expected_contraction=row["contraction"],
                    verification_state=ExercisePhaseMuscleRole.VerificationState.INFERRED,
                    rationale="Rol derivat de la fase, la intenció i una única funció biomecànica tipada.",
                    provenance=child_provenance, **basis,
                )
                self.summary.created["muscle_roles"] += 1
        managed_fingerprint = _fingerprint(_revision_snapshot(revision))
        revision.provenance = _provenance(
            batch_code=batch_code,
            source_refs=item["source_refs"],
            payload_fingerprint=payload_fingerprint,
            managed_fingerprint=managed_fingerprint,
        )
        revision.save(update_fields=("provenance", "updated_at"))
        refresh_revision_gaps(revision)
