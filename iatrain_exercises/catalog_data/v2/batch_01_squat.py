from .common import batch, variant as V
from .templates import SQUAT, SQUAT_HOLD


ROWS = [
    V("goblet_squat", "Esquat goblet", "squat", "Esquat", SQUAT, equipment=("kettlebell",), difficulty="beginner"),
    V("dumbbell_goblet_squat", "Esquat goblet amb mancuerna", "squat", "Esquat", SQUAT, equipment=("dumbbell",), difficulty="beginner"),
    V("barbell_high_bar_back_squat", "Esquat posterior amb barra alta", "squat", "Esquat", SQUAT, equipment=("barbell",), difficulty="advanced", objective="max_strength"),
    V("barbell_low_bar_back_squat", "Esquat posterior amb barra baixa", "squat", "Esquat", SQUAT, equipment=("barbell",), difficulty="advanced", objective="max_strength"),
    V("barbell_front_squat", "Esquat frontal amb barra", "squat", "Esquat", SQUAT, equipment=("barbell",), difficulty="advanced", objective="max_strength"),
    V("barbell_overhead_squat", "Esquat amb barra sobre el cap", "squat", "Esquat", SQUAT, equipment=("barbell",), difficulty="advanced", objective="motor_control", secondary_objective="mobility"),
    V("double_dumbbell_front_squat", "Esquat frontal amb dues manuelles", "squat", "Esquat", SQUAT, equipment=("dumbbell",), difficulty="intermediate"),
    V("double_kettlebell_front_squat", "Esquat frontal amb dues kettlebells", "squat", "Esquat", SQUAT, equipment=("kettlebell",), difficulty="intermediate"),
    V("landmine_squat", "Esquat amb landmine", "squat", "Esquat", SQUAT, equipment=("barbell", "landmine"), difficulty="beginner"),
    V("smith_machine_squat", "Esquat a màquina Smith", "squat", "Esquat", SQUAT, equipment=("smith_machine",), difficulty="beginner", kinetic_chain="closed"),
    V("barbell_box_squat", "Esquat a caixa amb barra", "box_squat", "Esquat a caixa", SQUAT, equipment=("barbell", "box"), difficulty="intermediate"),
    V("bodyweight_box_squat", "Esquat a caixa amb pes corporal", "box_squat", "Esquat a caixa", SQUAT, equipment=("box",), difficulty="beginner", modality="motor_control"),
    V("dumbbell_box_squat", "Esquat a caixa amb manuelles", "box_squat", "Esquat a caixa", SQUAT, equipment=("dumbbell", "box"), difficulty="intermediate"),
    V("bench_sit_to_stand", "Asseure's i aixecar-se del banc", "sit_to_stand", "Asseure's i aixecar-se", SQUAT, equipment=("bench",), difficulty="beginner", modality="motor_control"),
    V("weighted_bench_sit_to_stand", "Asseure's i aixecar-se amb càrrega frontal", "sit_to_stand", "Asseure's i aixecar-se", SQUAT, equipment=("bench", "dumbbell"), difficulty="intermediate"),
    V("band_resisted_squat", "Esquat amb banda sobre els genolls", "squat", "Esquat", SQUAT, equipment=("elastic_band",), difficulty="beginner", modality="motor_control"),
    V("suspension_assisted_squat", "Esquat assistit amb suspensió", "squat", "Esquat", SQUAT, equipment=("suspension_trainer",), difficulty="beginner", modality="motor_control"),
    V("heel_elevated_goblet_squat", "Esquat goblet amb talons elevats", "squat", "Esquat", SQUAT, equipment=("kettlebell", "weight_plate"), difficulty="intermediate", secondary_objective="mobility"),
    V("cyclist_squat_dumbbell", "Esquat ciclista amb mancuerna", "squat", "Esquat", SQUAT, equipment=("dumbbell", "weight_plate"), difficulty="intermediate"),
    V("wide_stance_goblet_squat", "Esquat goblet amb base ampla", "squat", "Esquat", SQUAT, equipment=("kettlebell",), difficulty="intermediate"),
    V("narrow_stance_bodyweight_squat", "Esquat amb base estreta", "squat", "Esquat", SQUAT, difficulty="intermediate", modality="mobility", objective="mobility"),
    V("hack_squat_machine", "Hack squat en màquina", "hack_squat", "Hack squat", SQUAT, equipment=("hack_squat_machine",), difficulty="intermediate", objective="max_strength"),
    V("leg_press_bilateral", "Premsa bilateral de cames", "leg_press", "Premsa de cames", SQUAT, equipment=("leg_press_machine",), difficulty="beginner", kinetic_chain="closed"),
    V("leg_press_narrow_stance", "Premsa de cames amb base estreta", "leg_press", "Premsa de cames", SQUAT, equipment=("leg_press_machine",), difficulty="intermediate"),
    V("leg_press_wide_stance", "Premsa de cames amb base ampla", "leg_press", "Premsa de cames", SQUAT, equipment=("leg_press_machine",), difficulty="intermediate"),
    V("bodyweight_wall_sit", "Cadira isomètrica a la paret", "wall_sit", "Cadira isomètrica", SQUAT_HOLD, equipment=("wall",), modality="muscular_endurance", execution_type="isometric", difficulty="beginner"),
    V("wall_sit_with_ball", "Cadira isomètrica amb pilota a la paret", "wall_sit", "Cadira isomètrica", SQUAT_HOLD, equipment=("wall", "stability_ball"), modality="motor_control", execution_type="isometric", difficulty="beginner"),
    V("goblet_squat_hold", "Manteniment d'esquat goblet", "squat_hold", "Manteniment d'esquat", SQUAT_HOLD, equipment=("kettlebell",), modality="muscular_endurance", execution_type="isometric", difficulty="intermediate"),
]

BATCH = batch("01_squat", "Esquats bilaterals i manteniments", ROWS)
