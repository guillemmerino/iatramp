import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.models import Person
from iatrain_exercises.catalog_importer import (
    CatalogDataError,
    PrivateCatalogImporter,
    build_coverage_matrix,
    validate_catalog_data,
)


class Command(BaseCommand):
    help = "Importa el catàleg privat versionat, idempotent i revisable d'exercicis."

    def add_arguments(self, parser):
        parser.add_argument("--owner-username", required=True)
        parser.add_argument("--batch", action="append", dest="batches", default=[])
        parser.add_argument("--coverage-only", action="store_true")

    def handle(self, *args, **options):
        try:
            validation = validate_catalog_data()
        except CatalogDataError as exc:
            raise CommandError(str(exc))
        if options["coverage_only"]:
            self.stdout.write(json.dumps({"validation": validation, "coverage": build_coverage_matrix()}, ensure_ascii=False, indent=2, sort_keys=True))
            return
        try:
            user = get_user_model().objects.select_related("person").get(username=options["owner_username"])
            owner = user.person
        except (get_user_model().DoesNotExist, Person.DoesNotExist):
            raise CommandError("No existeix l'usuari o no té una identitat Person.")
        if not owner.is_active:
            raise CommandError("El propietari necessita una identitat activa.")
        try:
            summary = PrivateCatalogImporter(owner=owner, batch_codes=options["batches"]).run()
        except CatalogDataError as exc:
            raise CommandError(str(exc))
        payload = summary.as_dict()
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        if payload["conflicts"]:
            self.stderr.write(self.style.WARNING(f"Importació completada amb {len(payload['conflicts'])} conflictes protegits."))
        else:
            self.stdout.write(self.style.SUCCESS("Importació privada coherent completada en draft."))

