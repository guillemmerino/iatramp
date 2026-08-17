from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Person
from iatrain.legacy_imports.contact_positions import import_contact_positions


class Command(BaseCommand):
    help = "Introdueix les posicions de contacte i les relacions legacy com a draft."

    def add_arguments(self, parser):
        parser.add_argument(
            "--author-person-id",
            type=int,
            required=True,
            help="Person curadora a qui s'atribueix la proposta editorial.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Calcula el resultat i desfà la transacció sense persistir canvis.",
        )

    def handle(self, *args, **options):
        try:
            author = Person.objects.get(pk=options["author_person_id"], is_active=True)
        except Person.DoesNotExist as exc:
            raise CommandError("No existeix una Person activa amb aquest identificador.") from exc

        with transaction.atomic():
            summary = import_contact_positions(author=author)
            if options["dry_run"]:
                transaction.set_rollback(True)

        mode = "Simulació" if options["dry_run"] else "Importació"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode} completada: {summary.positions_created} contactes creats, "
                f"{summary.positions_existing} ja existents; "
                f"inici {summary.start_relations_created} creats/"
                f"{summary.start_relations_existing} existents; "
                f"final {summary.end_relations_created} creats/"
                f"{summary.end_relations_existing} existents; "
                f"{summary.relations_skipped_conflict} conflictes i "
                f"{summary.unsupported_legacy_contacts} contactes no suportats."
            )
        )

