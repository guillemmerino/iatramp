from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Person
from iatrain.athletes.services import (
    propose_athlete_condition,
    record_athlete_measurement,
    review_athlete_condition,
    set_athlete_sport_profile,
)
from iatrain.models import AthleteMeasurement, AthleteObservation, CoachProfile
from iatrain_motion.models import MotionConcept
from iatrain.services import (
    activate_athlete_profile,
    record_athlete_observation,
    set_coach_athlete_relation,
)
from organizations.models import MembershipRole, Organization


MARKER = "Dades simulades per a proves d'IA Train."


ATHLETES = (
    {
        "first_name": "Laia",
        "last_name": "Vidal Simulada",
        "birth_date": date(2017, 4, 12),
        "discipline": "trampoline",
        "level": "iniciacio_2",
        "laterality": "right",
        "started_on": date(2024, 9, 1),
        "condition": ("injury", "Apofisitis calcània comunicada", "Dolor de taló després de salts repetits; restricció aportada per la família.", "bilateral", 2, "modify", "ankle"),
        "measurements": (("power", "salt_vertical", "Salt vertical", "18.5", "cm", "not_applicable"), ("mobility", "dorsiflexio_turmell", "Dorsiflexió de turmell", "28", "graus", "bilateral")),
        "observation": ("learning", "Aprèn ràpidament patrons nous, però perd alineació quan acumula recepcions."),
    },
    {
        "first_name": "Nil",
        "last_name": "Soler Simulat",
        "birth_date": date(2016, 10, 3),
        "discipline": "dmt",
        "level": "base_3",
        "laterality": "left",
        "started_on": date(2023, 9, 1),
        "condition": ("medical_restriction", "Osgood-Schlatter comunicat", "Molèstia anterior de genoll amb flexions profundes i volum elevat de salts.", "left", 2, "monitor", "knee"),
        "measurements": (("power", "salt_vertical", "Salt vertical", "22", "cm", "not_applicable"), ("mobility", "flexio_genoll", "Flexió de genoll sense molèstia", "105", "graus", "left")),
        "observation": ("strength", "Bona orientació espacial i control del ritme en aproximacions curtes."),
    },
    {
        "first_name": "Emma",
        "last_name": "Roca Simulada",
        "birth_date": date(2014, 2, 21),
        "discipline": "trampoline",
        "level": "competicio_4",
        "laterality": "right",
        "started_on": date(2021, 9, 1),
        "condition": ("injury", "Inestabilitat recurrent de turmell", "Antecedents d'esquinços; inseguretat en recepcions amb desviació lateral.", "right", 3, "modify", "ankle"),
        "measurements": (("power", "salt_vertical", "Salt vertical", "27.5", "cm", "not_applicable"), ("motor_control", "equilibri_unipodal", "Equilibri unipodal", "24", "s", "right")),
        "observation": ("difficulty", "En recepcions laterals descarrega pes de manera precoç sobre la cama esquerra."),
    },
    {
        "first_name": "Biel",
        "last_name": "Puig Simulat",
        "birth_date": date(2013, 7, 8),
        "discipline": "tumbling",
        "level": "competicio_5",
        "laterality": "mixed",
        "started_on": date(2020, 9, 1),
        "condition": ("pain", "Tendinopatia rotuliana comunicada", "Dolor anterior de genoll després de sèries explosives i recepcions rígides.", "right", 3, "avoid", "knee"),
        "measurements": (("power", "salt_vertical", "Salt vertical", "31", "cm", "not_applicable"), ("strength", "isometric_quadriceps", "Força isomètrica de quàdriceps", "182", "n", "right")),
        "observation": ("limitation", "Augmenta la rigidesa de genoll quan busca més velocitat en la diagonal."),
    },
    {
        "first_name": "Júlia",
        "last_name": "Martí Simulada",
        "birth_date": date(2012, 11, 16),
        "discipline": "trampoline",
        "level": "tecnificacio_6",
        "laterality": "left",
        "started_on": date(2019, 9, 1),
        "condition": ("medical_restriction", "Espondilòlisi lumbar en retorn progressiu", "Restricció mèdica aportada: evitar hiperextensions i impactes màxims de moment.", "not_applicable", 4, "avoid", "lumbar"),
        "measurements": (("motor_control", "control_lumbopelvic", "Control lumbopèlvic", "3", "nivell", "not_applicable"), ("mobility", "flexio_maluc", "Flexió de maluc", "118", "graus", "bilateral")),
        "observation": ("competency", "Manté molt bon control tècnic en tasques submàximes i amb volum reduït."),
    },
    {
        "first_name": "Pol",
        "last_name": "Serra Simulat",
        "birth_date": date(2011, 1, 27),
        "discipline": "dmt",
        "level": "tecnificacio_7",
        "laterality": "right",
        "started_on": date(2018, 9, 1),
        "condition": ("discomfort", "Tendinopatia extensora de canell comunicada", "Molèstia amb suport prolongat de mans i recepcions de mans repetides.", "left", 2, "modify", "wrist"),
        "measurements": (("power", "salt_vertical", "Salt vertical", "35", "cm", "not_applicable"), ("mobility", "extensio_canell", "Extensió de canell", "61", "graus", "left")),
        "observation": ("strength", "Bona capacitat de producció de força i estabilitat en impulsos bilaterals."),
    },
    {
        "first_name": "Ivet",
        "last_name": "Costa Simulada",
        "birth_date": date(2010, 6, 14),
        "discipline": "tumbling",
        "level": "alt_rendiment_8",
        "laterality": "right",
        "started_on": date(2017, 9, 1),
        "condition": ("injury", "Inestabilitat anterior d'espatlla", "Episodis comunicats d'inestabilitat; limitar palanques llargues per sobre del cap.", "right", 3, "avoid", "shoulder"),
        "measurements": (("strength", "rotacio_externa_espatlla", "Força de rotació externa", "8.4", "kg", "right"), ("mobility", "flexio_espatlla", "Flexió d'espatlla", "162", "graus", "right")),
        "observation": ("difficulty", "Perd control escapular en les últimes repeticions de les sèries de força."),
    },
    {
        "first_name": "Jan",
        "last_name": "Ferrer Simulat",
        "birth_date": date(2009, 9, 30),
        "discipline": "dmt",
        "level": "alt_rendiment_9",
        "laterality": "left",
        "started_on": date(2016, 9, 1),
        "condition": ("load_tolerance", "Tendinopatia aquíl·lia comunicada", "Tolera càrrega moderada, però apareix rigidesa l'endemà de sessions explosives.", "left", 2, "monitor", "ankle"),
        "measurements": (("power", "salt_vertical", "Salt vertical", "39.5", "cm", "not_applicable"), ("workload", "salts_setmanals", "Salts setmanals", "245", "repeticions", "not_applicable")),
        "observation": ("competency", "Regula bé la intensitat quan rep objectius clars de volum i RPE."),
    },
    {
        "first_name": "Clàudia",
        "last_name": "Pons Simulada",
        "birth_date": date(2007, 12, 5),
        "discipline": "trampoline",
        "level": "retorn_competicio",
        "laterality": "right",
        "started_on": date(2014, 9, 1),
        "condition": ("medical_restriction", "Retorn després de reconstrucció de LCA", "Fase de readaptació comunicada; encara no autoritzada per a recepcions màximes.", "left", 4, "modify", "knee"),
        "measurements": (("strength", "single_leg_press", "Força unilateral de cama", "72", "kg", "left"), ("motor_control", "hop_test_simetria", "Simetria en hop test", "84", "%", "not_applicable")),
        "observation": ("learning", "Executa bé les correccions, però anticipa la protecció de la cama esquerra."),
    },
    {
        "first_name": "Arnau",
        "last_name": "Mas Simulat",
        "birth_date": date(2004, 3, 19),
        "discipline": "trampoline",
        "level": "senior_10",
        "laterality": "mixed",
        "started_on": date(2010, 9, 1),
        "condition": ("medical_restriction", "Protocol de retorn després de commoció", "Restricció mèdica temporal: sense entrenament fins a nova autorització.", "not_applicable", 5, "stop", None),
        "measurements": (("recovery", "benestar_percebut", "Benestar percebut", "4", "sobre_10", "not_applicable"), ("motor_control", "equilibri_tandem", "Equilibri tàndem", "18", "s", "not_applicable")),
        "observation": ("limitation", "S'ha aturat tota exposició física i tècnica fins a completar el protocol mèdic."),
    },
)


class Command(BaseCommand):
    help = "Crea deu gimnastes simulats amb perfils vius i condicions variades."

    def add_arguments(self, parser):
        parser.add_argument("--coach-username", required=True)
        parser.add_argument("--organization-id", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.select_related("person").get(
                username=options["coach_username"]
            )
            CoachProfile.objects.get(person=user.person, is_active=True)
        except (get_user_model().DoesNotExist, CoachProfile.DoesNotExist) as exc:
            raise CommandError("L'usuari necessita un perfil d'entrenador actiu.") from exc
        try:
            organization = Organization.objects.get(pk=options["organization_id"])
        except Organization.DoesNotExist as exc:
            raise CommandError("L'organització indicada no existeix.") from exc
        if not MembershipRole.objects.filter(
            membership__person=user.person,
            membership__organization=organization,
            role=MembershipRole.Role.COACH,
        ).exists() and not user.is_superuser:
            raise CommandError("L'usuari no és entrenador de l'organització indicada.")

        created_people = 0
        with transaction.atomic():
            for index, data in enumerate(ATHLETES, start=1):
                email = f"iatrain.simulat.{index:02d}@example.invalid"
                person, created = Person.objects.get_or_create(
                    email=email,
                    defaults={
                        "first_name": data["first_name"],
                        "last_name": data["last_name"],
                        "birth_date": data["birth_date"],
                        "is_provisional": False,
                    },
                )
                created_people += int(created)
                person.first_name = data["first_name"]
                person.last_name = data["last_name"]
                person.birth_date = data["birth_date"]
                person.is_provisional = False
                person.is_active = True
                person.save()
                athlete = activate_athlete_profile(person=person)
                set_coach_athlete_relation(
                    coach=user.person,
                    athlete=athlete,
                    organization=organization,
                    can_view_profile=True,
                    can_view_training=True,
                    can_edit_training=True,
                    can_view_health_data=True,
                    notes=MARKER,
                )
                set_athlete_sport_profile(
                    user=user,
                    athlete=athlete,
                    organization=organization,
                    discipline=data["discipline"],
                    level_code=data["level"],
                    training_started_on=data["started_on"],
                    preferred_laterality=data["laterality"],
                    notes=MARKER,
                )
                for offset, measurement in enumerate(data["measurements"]):
                    domain, code, label, value, unit, side = measurement
                    if not AthleteMeasurement.objects.filter(
                        athlete_profile=athlete,
                        organization=organization,
                        metric_code=code,
                        notes=MARKER,
                    ).exists():
                        record_athlete_measurement(
                            user=user,
                            athlete=athlete,
                            organization=organization,
                            domain=domain,
                            metric_code=code,
                            metric_label=label,
                            value=Decimal(value),
                            unit=unit,
                            side=side,
                            source="assessment",
                            measured_at=timezone.now() - timedelta(days=index + offset),
                            notes=MARKER,
                        )
                category, narrative = data["observation"]
                if not AthleteObservation.objects.filter(
                    athlete=person,
                    organization=organization,
                    evidence=MARKER,
                ).exists():
                    record_athlete_observation(
                        user=user,
                        athlete=person,
                        organization=organization,
                        category=category,
                        narrative=narrative,
                        evidence=MARKER,
                        confidence=Decimal("0.85"),
                        observed_at=timezone.now() - timedelta(days=index),
                    )
                condition_data = data["condition"]
                title = condition_data[1]
                region = (
                    MotionConcept.objects.filter(code=condition_data[6]).first()
                    if condition_data[6]
                    else None
                )
                if not athlete.conditions.filter(
                    organization=organization,
                    title=title,
                    evidence=MARKER,
                ).exists():
                    condition = propose_athlete_condition(
                        user=user,
                        athlete=athlete,
                        organization=organization,
                        category=condition_data[0],
                        title=title,
                        narrative=condition_data[2],
                        evidence=MARKER,
                        body_region=region,
                        applicability_scope=(
                            "regional"
                            if region
                            else "global"
                            if condition_data[5] == "stop"
                            else "unknown"
                        ),
                        laterality=condition_data[3],
                        severity=condition_data[4],
                        training_impact=condition_data[5],
                        source="clinical_document",
                        started_at=timezone.now() - timedelta(days=10 + index),
                    )
                    review_athlete_condition(user=user, condition=condition, accept=True)
            if options["dry_run"]:
                transaction.set_rollback(True)

        mode = "Simulació" if options["dry_run"] else "Creació"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode} completada: {len(ATHLETES)} perfils processats, "
                f"{created_people} persones noves."
            )
        )
