from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Person
from iatrain.legacy_imports.rotation_notations import import_rotation_notations


class Command(BaseCommand):
    help = "Interpreta les notacions legacy i crea perfils estructurats de rotació draft."

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
            summary = import_rotation_notations(author=author)
            if options["dry_run"]:
                transaction.set_rollback(True)

        mode = "Simulació" if options["dry_run"] else "Importació"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode} completada: {summary.profiles_created} perfils creats, "
                f"{summary.profiles_existing} ja existents, "
                f"{summary.profile_conflicts} conflictes; "
                f"{summary.segments_created} segments i "
                f"{summary.notations_created} notacions creades/"
                f"{summary.notations_existing} existents; "
                f"{summary.invalid_notations} no vàlides."
            )
        )

