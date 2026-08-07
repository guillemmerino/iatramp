from dataclasses import dataclass

from django.core.exceptions import ValidationError

from iatrain.models import GymEquipment, TrainingGroupMembership


@dataclass(frozen=True)
class TrainingSelection:
    """Validated, read-only input handed to the future generation pipeline."""

    organization: object
    training_group: object | None
    gym: object | None
    athletes: tuple
    equipment: tuple


def build_training_selection(
    *,
    organization,
    training_group=None,
    gym=None,
    additional_athletes=(),
):
    if training_group is not None and training_group.organization_id != organization.pk:
        raise ValidationError("El grup no pertany a l’organització seleccionada.")
    if gym is not None and not gym.organization_links.filter(
        organization=organization,
        is_active=True,
    ).exists():
        raise ValidationError("El gimnàs no està vinculat a l’organització seleccionada.")

    athlete_by_id = {athlete.pk: athlete for athlete in additional_athletes}
    if training_group is not None:
        memberships = TrainingGroupMembership.objects.filter(
            training_group=training_group,
            is_active=True,
            athlete_profile__is_active=True,
        ).select_related("athlete_profile__person")
        for membership in memberships:
            athlete_by_id[membership.athlete_profile_id] = membership.athlete_profile

    equipment = ()
    if gym is not None:
        equipment = tuple(
            GymEquipment.objects.filter(gym=gym)
            .exclude(availability=GymEquipment.Availability.UNAVAILABLE)
            .order_by("equipment_type", "name")
        )

    athletes = tuple(
        sorted(
            athlete_by_id.values(),
            key=lambda profile: (
                profile.person.last_name.lower(),
                profile.person.first_name.lower(),
                profile.pk,
            ),
        )
    )
    return TrainingSelection(
        organization=organization,
        training_group=training_group,
        gym=gym,
        athletes=athletes,
        equipment=equipment,
    )
