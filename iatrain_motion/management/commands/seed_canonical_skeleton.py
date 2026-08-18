from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Person
from iatrain_motion.checks import audit_skeleton_schema
from iatrain_motion.models import (
    CanonicalJoint,
    CanonicalLandmark,
    CanonicalSegment,
    EditorialStatus,
    JointAngleDefinition,
    MotionConcept,
    SkeletonSchema,
)
from iatrain_motion.skeleton_vocabulary import (
    ANGLES,
    JOINTS,
    LANDMARKS,
    SCHEMA,
    SEED_ID,
    SEGMENTS,
)


class Command(BaseCommand):
    help = "Crea idempotentment l'esquelet funcional canònic com a esborrany."

    def add_arguments(self, parser):
        parser.add_argument("--author-username", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        def sync_seed_owned(instance, defaults, was_created):
            if was_created:
                return False
            if (instance.provenance or {}).get("seed") != SEED_ID:
                raise CommandError(
                    f"{instance} ja existeix però no està gestionat per la llavor {SEED_ID}."
                )
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
                instance.save(update_fields=(*changed_fields, "updated_at"))
                return True
            return False

        try:
            user = get_user_model().objects.select_related("person").get(
                username=options["author_username"]
            )
            author = user.person
        except (get_user_model().DoesNotExist, Person.DoesNotExist):
            raise CommandError("No existeix l'usuari o no té una identitat Person.")
        if not author.is_active:
            raise CommandError("L'autor necessita una identitat activa.")

        schema, schema_created = SkeletonSchema.objects.get_or_create(
            code=SCHEMA["code"],
            version=SCHEMA["version"],
            defaults={**SCHEMA, "authored_by": author, "editorial_status": EditorialStatus.DRAFT},
        )
        if schema.editorial_status != EditorialStatus.DRAFT:
            raise CommandError("La llavor només es pot completar mentre l'esquema sigui esborrany.")
        schema_updated = False
        if not schema_created:
            schema_defaults = {key: value for key, value in SCHEMA.items() if key not in {"code", "version"}}
            schema_updated = sync_seed_owned(schema, schema_defaults, False)

        required_codes = {
            data["concept_code"] for data in (*SEGMENTS, *JOINTS)
        } | {
            code
            for data in ANGLES
            for code in (
                data["positive_action_code"], data["negative_action_code"],
                data["plane_code"], data["axis_code"],
            )
        }
        concepts = MotionConcept.objects.in_bulk(required_codes, field_name="code")
        missing = sorted(required_codes - set(concepts))
        if missing:
            raise CommandError("Falten conceptes anatòmics previs: " + ", ".join(missing))

        created = {"landmarks": 0, "segments": 0, "joints": 0, "angles": 0}
        updated = {"landmarks": 0, "segments": 0, "joints": 0, "angles": 0}
        landmarks = {}
        for data in LANDMARKS:
            landmark, was_created = CanonicalLandmark.objects.get_or_create(
                schema=schema,
                code=data["code"],
                defaults={**data, "authored_by": author},
            )
            if not was_created and (
                landmark.side != data["side"]
                or landmark.landmark_type != data["landmark_type"]
                or landmark.measurement_source != data["measurement_source"]
            ):
                raise CommandError(f"El punt existent {landmark.code} no coincideix amb {SEED_ID}.")
            landmarks[landmark.code] = landmark
            created["landmarks"] += was_created
            updated["landmarks"] += sync_seed_owned(
                landmark,
                {key: value for key, value in data.items() if key != "code"},
                was_created,
            )

        segments = {}
        for data in SEGMENTS:
            defaults = {
                "concept": concepts[data["concept_code"]],
                "side": data["side"],
                "axis_start_landmark": landmarks[data["axis_start"]],
                "axis_end_landmark": landmarks[data["axis_end"]],
                "plane_landmark": landmarks.get(data["plane_landmark"]),
                "orientation_capability": data["orientation_capability"],
                "primary_axis": data["primary_axis"],
                "frame_notes": data["frame_notes"],
                "provenance": data["provenance"],
                "authored_by": author,
            }
            segment, was_created = CanonicalSegment.objects.get_or_create(
                schema=schema,
                code=data["code"],
                defaults=defaults,
            )
            if not was_created and (
                segment.concept_id != defaults["concept"].pk or segment.side != defaults["side"]
            ):
                raise CommandError(f"El segment existent {segment.code} no coincideix amb {SEED_ID}.")
            segments[segment.code] = segment
            created["segments"] += was_created
            updated["segments"] += sync_seed_owned(segment, defaults, was_created)

        joints = {}
        for data in JOINTS:
            defaults = {
                "concept": concepts[data["concept_code"]],
                "side": data["side"],
                "center_landmark": landmarks[data["center_landmark"]],
                "proximal_segment": segments[data["proximal_segment"]],
                "distal_segment": segments[data["distal_segment"]],
                "provenance": data["provenance"],
                "authored_by": author,
            }
            joint, was_created = CanonicalJoint.objects.get_or_create(
                schema=schema,
                code=data["code"],
                defaults=defaults,
            )
            if not was_created and (
                joint.concept_id != defaults["concept"].pk or joint.side != defaults["side"]
            ):
                raise CommandError(f"L'articulació existent {joint.code} no coincideix amb {SEED_ID}.")
            joints[joint.code] = joint
            created["joints"] += was_created
            updated["joints"] += sync_seed_owned(joint, defaults, was_created)

        for data in ANGLES:
            defaults = {
                "joint": joints[data["joint_code"]],
                "component": data["component"],
                "sequence_index": data["sequence_index"],
                "positive_action": concepts[data["positive_action_code"]],
                "negative_action": concepts[data["negative_action_code"]],
                "plane": concepts[data["plane_code"]],
                "axis": concepts[data["axis_code"]],
                "calculation_method": data["calculation_method"],
                "sign_convention": data["sign_convention"],
                "provenance": data["provenance"],
                "authored_by": author,
            }
            angle, was_created = JointAngleDefinition.objects.get_or_create(
                schema=schema,
                code=data["code"],
                defaults=defaults,
            )
            if not was_created and angle.joint_id != defaults["joint"].pk:
                raise CommandError(f"L'angle existent {angle.code} no coincideix amb {SEED_ID}.")
            created["angles"] += was_created
            updated["angles"] += sync_seed_owned(angle, defaults, was_created)

        issues = audit_skeleton_schema(schema)
        if issues:
            raise CommandError("L'esquelet creat no és coherent:\n- " + "\n- ".join(issues))
        self.stdout.write(
            self.style.SUCCESS(
                f"{SEED_ID}: schema={int(schema_created)}, "
                f"landmarks={created['landmarks']}, segments={created['segments']}, "
                f"joints={created['joints']}, angles={created['angles']}; "
                f"updated={int(schema_updated) + sum(updated.values())}; auditoria correcta."
            )
        )
