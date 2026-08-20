from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Person
from iatrain_motion.models import EditorialStatus, MotionConcept, MotionRelation

from iatrain_biomechanics.checks import audit_biomechanics
from iatrain_biomechanics.models import (
    BiomechanicalContext,
    EvidenceReference,
    MuscleActionFunction,
    MuscleActionFunctionEvidence,
    MuscleStabilizationEvidence,
    MuscleStabilizationFunction,
)
from iatrain_biomechanics.vocabulary import (
    CONTEXTS,
    FUNCTIONS_BY_MUSCLE,
    GROUPS,
    MUSCLES,
    SEED_VERSION,
    SOURCES,
    STABILIZATIONS,
    source_for_muscle,
)


class Command(BaseCommand):
    help = "Crea idempotentment la base anatòmica muscular i biomecànica funcional en draft."

    def add_arguments(self, parser):
        parser.add_argument("--author-username", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.select_related("person").get(
                username=options["author_username"]
            )
            author = user.person
        except (get_user_model().DoesNotExist, Person.DoesNotExist):
            raise CommandError("No existeix l'usuari o no té una identitat Person.")
        if not author.is_active:
            raise CommandError("L'autor necessita una identitat activa.")

        provenance = {
            "seed": SEED_VERSION,
            "review_status": "professional_review_required",
        }
        counts = {
            "concepts": 0,
            "relations": 0,
            "sources": 0,
            "contexts": 0,
            "action_functions": 0,
            "stabilizations": 0,
            "evidence_links": 0,
            "updated": 0,
        }

        def sync_seed_owned(instance, defaults, created):
            if created:
                return False
            if (instance.provenance or {}).get("seed") != SEED_VERSION:
                return False
            if hasattr(instance, "editorial_status") and instance.editorial_status != EditorialStatus.DRAFT:
                raise CommandError(f"{instance} està governat i ja no és draft.")
            changed_fields = []
            for field_name, value in defaults.items():
                if field_name == "authored_by":
                    continue
                current = getattr(instance, field_name)
                current_value = current.pk if hasattr(current, "pk") else current
                expected_value = value.pk if hasattr(value, "pk") else value
                if current_value != expected_value:
                    setattr(instance, field_name, value)
                    changed_fields.append(field_name)
            if changed_fields:
                update_fields = list(changed_fields)
                if hasattr(instance, "updated_at"):
                    update_fields.append("updated_at")
                instance.save(update_fields=tuple(update_fields))
                counts["updated"] += 1
                return True
            return False

        required_codes = {
            code
            for muscle in MUSCLES
            for code in muscle["joints"]
        } | {
            action_code
            for functions in FUNCTIONS_BY_MUSCLE.values()
            for action_code, _contribution in functions
        } | {
            target_code
            for _code, _muscle, _kind, target_code, _stype, _statement in STABILIZATIONS
        }
        existing_required = MotionConcept.objects.in_bulk(required_codes, field_name="code")
        missing = sorted(required_codes - set(existing_required))
        if missing:
            raise CommandError(
                "Falta el vocabulari anatòmic-cinemàtic previ. Executa primer "
                "seed_motion_vocabulary. Falten: " + ", ".join(missing)
            )

        concepts = dict(existing_required)
        for data in (*GROUPS, *MUSCLES):
            defaults = {
                "name": data["name"],
                "definition": data["definition"],
                "kind": data["kind"],
                "laterality": data["laterality"],
                "authored_by": author,
                "editorial_status": EditorialStatus.DRAFT,
                "provenance": {
                    **provenance,
                    **({"source": data["source"]} if "source" in data else {}),
                },
            }
            concept, created = MotionConcept.objects.get_or_create(
                code=data["code"],
                defaults=defaults,
            )
            if concept.kind != data["kind"] or concept.laterality != data["laterality"]:
                raise CommandError(f"El concepte existent {concept.code} no coincideix amb la llavor.")
            sync_seed_owned(concept, defaults, created)
            concepts[concept.code] = concept
            counts["concepts"] += int(created)

        for muscle_data in MUSCLES:
            source = concepts[muscle_data["code"]]
            relation_targets = (
                (
                    MotionRelation.RelationType.MEMBER_OF_MUSCLE_GROUP,
                    muscle_data["groups"],
                ),
                (MotionRelation.RelationType.SPANS_JOINT, muscle_data["joints"]),
            )
            for relation_type, target_codes in relation_targets:
                for target_code in target_codes:
                    relation, created = MotionRelation.objects.get_or_create(
                        source=source,
                        target=concepts[target_code],
                        relation_type=relation_type,
                        defaults={
                            "rationale": (
                                "Relació anatòmica funcional de la llavor biomecànica; "
                                "requereix revisió professional abans de validar."
                            ),
                            "authored_by": author,
                            "editorial_status": EditorialStatus.DRAFT,
                            "provenance": provenance,
                        },
                    )
                    if not created and relation.editorial_status == EditorialStatus.RETIRED:
                        raise CommandError(f"La relació requerida està retirada: {relation}.")
                    counts["relations"] += int(created)

        sources = {}
        for data in SOURCES:
            defaults = {
                **{key: value for key, value in data.items() if key != "code"},
                "citation": data["title"],
                "authored_by": author,
                "provenance": provenance,
            }
            source, created = EvidenceReference.objects.get_or_create(
                code=data["code"],
                defaults=defaults,
            )
            sync_seed_owned(source, defaults, created)
            sources[source.code] = source
            counts["sources"] += int(created)

        contexts = {}
        for data in CONTEXTS:
            defaults = {
                **{key: value for key, value in data.items() if key != "code"},
                "authored_by": author,
                "editorial_status": EditorialStatus.DRAFT,
                "provenance": provenance,
            }
            context, created = BiomechanicalContext.objects.get_or_create(
                code=data["code"],
                defaults=defaults,
            )
            sync_seed_owned(context, defaults, created)
            contexts[context.code] = context
            counts["contexts"] += int(created)

        general_context = contexts["general_functional_context"]
        for muscle_code, functions in FUNCTIONS_BY_MUSCLE.items():
            muscle = concepts[muscle_code]
            source = sources[source_for_muscle(muscle_code)]
            for action_code, contribution_class in functions:
                action = concepts[action_code]
                code = f"{muscle_code}__{action_code}__general"
                defaults = {
                    "muscle": muscle,
                    "action": action,
                    "context": general_context,
                    "contribution_class": contribution_class,
                    "statement": (
                        f"{muscle.name} pot contribuir mecànicament a {action.name.lower()}; "
                        "el rol concret depèn de la postura, la càrrega i la tasca."
                    ),
                    "conditions": {
                        "scope": "qualitative_general",
                        "activation_inferred": False,
                        "contraction_mode": "phase_dependent",
                    },
                    "limitations": (
                        "No quantifica activació, força ni braç de moment i no substitueix "
                        "una anàlisi específica de postura o exercici."
                    ),
                    "authored_by": author,
                    "editorial_status": EditorialStatus.DRAFT,
                    "provenance": {**provenance, "source": source.code},
                }
                function, created = MuscleActionFunction.objects.get_or_create(
                    code=code,
                    defaults=defaults,
                )
                sync_seed_owned(function, defaults, created)
                counts["action_functions"] += int(created)
                _link, link_created = MuscleActionFunctionEvidence.objects.get_or_create(
                    function=function,
                    evidence=source,
                    defaults={"relationship": "supports"},
                )
                counts["evidence_links"] += int(link_created)

        for code, muscle_code, target_kind, target_code, stabilization_type, statement in STABILIZATIONS:
            muscle = concepts[muscle_code]
            source = sources[source_for_muscle(muscle_code)]
            defaults = {
                "muscle": muscle,
                "target_joint": concepts[target_code] if target_kind == "joint" else None,
                "target_segment": concepts[target_code] if target_kind == "segment" else None,
                "context": general_context,
                "stabilization_type": stabilization_type,
                "statement": statement,
                "conditions": {
                    "scope": "qualitative_general",
                    "activation_inferred": False,
                },
                "limitations": (
                    "La contribució estabilitzadora real depèn de la tasca, la càrrega i la coordinació."
                ),
                "authored_by": author,
                "editorial_status": EditorialStatus.DRAFT,
                "provenance": {**provenance, "source": source.code},
            }
            function, created = MuscleStabilizationFunction.objects.get_or_create(
                code=code,
                defaults=defaults,
            )
            sync_seed_owned(function, defaults, created)
            counts["stabilizations"] += int(created)
            _link, link_created = MuscleStabilizationEvidence.objects.get_or_create(
                function=function,
                evidence=source,
                defaults={"relationship": "supports"},
            )
            counts["evidence_links"] += int(link_created)

        issues = audit_biomechanics(include_drafts=True)
        if issues:
            raise CommandError("La base biomecànica no és coherent:\n- " + "\n- ".join(issues))

        self.stdout.write(
            self.style.SUCCESS(
                f"{SEED_VERSION}: "
                + ", ".join(f"{key}={value}" for key, value in counts.items())
                + "; auditoria correcta."
            )
        )
