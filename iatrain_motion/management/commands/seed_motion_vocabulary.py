from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Person
from iatrain_motion.checks import audit_motion_graph
from iatrain_motion.models import EditorialStatus, MotionConcept, MotionRelation
from iatrain_motion.vocabulary import CONCEPTS, RELATIONS, SEED_VERSION


class Command(BaseCommand):
    help = "Crea idempotentment el vocabulari anatòmic-cinemàtic inicial com a esborrany."

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

        nodes = {}
        created_nodes = 0
        for data in CONCEPTS:
            node, created = MotionConcept.objects.get_or_create(
                code=data["code"],
                defaults={**data, "authored_by": author, "editorial_status": EditorialStatus.DRAFT},
            )
            if not created and (node.kind != data["kind"] or node.laterality != data["laterality"]):
                raise CommandError(f"El node existent {node.code} no coincideix amb el contracte de {SEED_VERSION}.")
            nodes[node.code] = node
            created_nodes += created

        created_relations = 0
        for source_code, relation_type, target_code in RELATIONS:
            source, target = nodes[source_code], nodes[target_code]
            if relation_type == MotionRelation.RelationType.OPPOSITE_OF and source.pk > target.pk:
                source, target = target, source
            existing = MotionRelation.objects.filter(
                source=source,
                relation_type=relation_type,
            )
            if relation_type in {
                MotionRelation.RelationType.PROXIMAL_SEGMENT,
                MotionRelation.RelationType.DISTAL_SEGMENT,
                MotionRelation.RelationType.ACTION_AT_JOINT,
                MotionRelation.RelationType.PRIMARY_PLANE,
                MotionRelation.RelationType.PRIMARY_AXIS,
            }:
                conflict = existing.exclude(target=target).first()
                if conflict:
                    raise CommandError(f"La relació funcional de {source.code} entra en conflicte amb {conflict}.")
            _, created = MotionRelation.objects.get_or_create(
                source=source,
                target=target,
                relation_type=relation_type,
                defaults={
                    "authored_by": author,
                    "editorial_status": EditorialStatus.DRAFT,
                    "provenance": {"seed": SEED_VERSION},
                },
            )
            created_relations += created

        issues = audit_motion_graph(include_drafts=True)
        if issues:
            raise CommandError("El vocabulari creat no és coherent:\n- " + "\n- ".join(issues))
        self.stdout.write(
            self.style.SUCCESS(
                f"{SEED_VERSION}: {created_nodes} nodes i {created_relations} relacions noves; auditoria correcta."
            )
        )
