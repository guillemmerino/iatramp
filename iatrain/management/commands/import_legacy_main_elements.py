from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Person
from iatrain.legacy_imports.main_elements import import_main_elements


class Command(BaseCommand):
    help = "Importa els 47 elements principals de tramponline com a conceptes draft."

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
            summary = import_main_elements(author=author)
            if options["dry_run"]:
                transaction.set_rollback(True)

        mode = "Simulació" if options["dry_run"] else "Importació"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode} completada: {summary.created} creats, "
                f"{summary.updated} actualitzats i {summary.unchanged} sense canvis."
            )
        )

