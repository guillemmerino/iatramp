"""Manifest visual de la Biblioteca.

Protocol de generació i integració:
``docs/generacio_imatges_biblioteca_iatrain.md``.
"""

from django.templatetags.static import static


EXERCISE_IMAGE_VERSIONS = {
    "band_resisted_squat": 2,
    "barbell_box_squat": 2,
    "barbell_front_squat": 1,
    "barbell_high_bar_back_squat": 1,
    "barbell_low_bar_back_squat": 1,
    "barbell_overhead_squat": 1,
    "bench_sit_to_stand": 1,
    "bodyweight_box_squat": 1,
    "bodyweight_squat": 2,
    "bodyweight_wall_sit": 1,
    "cyclist_squat_dumbbell": 2,
    "double_dumbbell_front_squat": 1,
    "double_kettlebell_front_squat": 1,
    "dumbbell_box_squat": 1,
    "dumbbell_goblet_squat": 1,
    "goblet_squat": 1,
    "goblet_squat_hold": 1,
    "hack_squat_machine": 1,
    "heel_elevated_goblet_squat": 3,
    "landmine_squat": 1,
    "leg_press_bilateral": 1,
    "leg_press_narrow_stance": 1,
    "leg_press_wide_stance": 1,
    "narrow_stance_bodyweight_squat": 1,
    "smith_machine_squat": 1,
    "suspension_assisted_squat": 1,
    "wall_sit_with_ball": 1,
    "weighted_bench_sit_to_stand": 1,
    "wide_stance_goblet_squat": 1,
}

FAMILY_IMAGE_VERSIONS = {
    "squat": 1,
    "box_squat": 2,
    "sit_to_stand": 2,
    "wall_sit": 1,
    "hack_squat": 1,
    "squat_hold": 1,
    "leg_press": 1,
}

LOWER_BODY_GROUP_IMAGE = "iatrain/library/groups/lower_body-v1-256.webp"


def _movement_labels(code):
    if "sit_to_stand" in code:
        return "Assegut", "Dempeus"
    if "wall_sit" in code or code == "goblet_squat_hold":
        return "Inici", "Manteniment"
    if "box_squat" in code:
        return "Inici", "Contacte"
    if code.startswith("leg_press") or code == "hack_squat_machine":
        return "Extensió", "Flexió"
    return "Inici", "Descens"


def exercise_illustration(code, name=None):
    version = EXERCISE_IMAGE_VERSIONS.get(code)
    if version is None:
        return None
    base = f"iatrain/library/exercises/{code}-v{version}"
    start_label, end_label = _movement_labels(code)
    exercise_name = name or "l’exercici"
    return {
        "large": f"{base}-960.webp",
        "small": f"{base}-480.webp",
        "large_url": static(f"{base}-960.webp"),
        "small_url": static(f"{base}-480.webp"),
        "alt": (
            f"Avatar d’IA Train mostrant l’inici i la posició clau de {exercise_name}."
        ),
        "start_label": start_label,
        "end_label": end_label,
    }


def family_illustration(code, name=None):
    version = FAMILY_IMAGE_VERSIONS.get(code)
    if version is None:
        return None
    cover = f"iatrain/library/families/{code}-v{version}-480.webp"
    family_name = name or "la família d’exercicis"
    return {
        "cover": cover,
        "cover_url": static(cover),
        "cover_alt": f"Avatar d’IA Train executant {family_name}.",
        "group": LOWER_BODY_GROUP_IMAGE,
        "group_url": static(LOWER_BODY_GROUP_IMAGE),
        "group_alt": "Cames i glutis",
    }
