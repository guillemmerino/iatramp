from .common import batch, variant as V
from .templates import LATERAL_TRUNK_HOLD, TRUNK_EXTENSION, TRUNK_FLEXION, TRUNK_HOLD, TRUNK_ROTATION


ROWS = [
    V("abdominal_crunch", "Encongiment abdominal", "trunk_flexion", "Flexió del tronc", TRUNK_FLEXION, optional_equipment=("mat",), difficulty="beginner", kinetic_chain="open", modality="muscular_endurance"),
    V("stability_ball_crunch", "Encongiment abdominal sobre pilota", "trunk_flexion", "Flexió del tronc", TRUNK_FLEXION, equipment=("stability_ball",), difficulty="intermediate", kinetic_chain="open", modality="motor_control"),
    V("cable_kneeling_crunch", "Flexió de tronc agenollat amb politja", "trunk_flexion", "Flexió del tronc", TRUNK_FLEXION, equipment=("cable_machine", "mat"), difficulty="intermediate", kinetic_chain="open"),
    V("machine_abdominal_crunch", "Flexió de tronc en màquina", "trunk_flexion", "Flexió del tronc", TRUNK_FLEXION, equipment=("resistance_machine",), difficulty="beginner", kinetic_chain="open"),
    V("decline_bench_crunch", "Encongiment abdominal en banc declinat", "trunk_flexion", "Flexió del tronc", TRUNK_FLEXION, equipment=("bench",), difficulty="intermediate", kinetic_chain="open"),
    V("weighted_crunch", "Encongiment abdominal amb disc", "trunk_flexion", "Flexió del tronc", TRUNK_FLEXION, equipment=("weight_plate", "mat"), difficulty="intermediate", kinetic_chain="open"),
    V("roman_chair_back_extension", "Extensió de tronc en banc romà", "trunk_extension", "Extensió del tronc", TRUNK_EXTENSION, equipment=("roman_chair",), difficulty="beginner", kinetic_chain="open"),
    V("weighted_roman_chair_extension", "Extensió de tronc en banc romà amb disc", "trunk_extension", "Extensió del tronc", TRUNK_EXTENSION, equipment=("roman_chair", "weight_plate"), difficulty="intermediate", kinetic_chain="open"),
    V("stability_ball_back_extension", "Extensió de tronc sobre pilota", "trunk_extension", "Extensió del tronc", TRUNK_EXTENSION, equipment=("stability_ball",), difficulty="intermediate", kinetic_chain="open", modality="motor_control"),
    V("prone_floor_trunk_extension", "Extensió de tronc a terra", "trunk_extension", "Extensió del tronc", TRUNK_EXTENSION, optional_equipment=("mat",), difficulty="beginner", kinetic_chain="open", modality="motor_control"),
    V("cable_trunk_rotation", "Rotació de tronc amb politja", "trunk_rotation", "Rotació del tronc", TRUNK_ROTATION, equipment=("cable_machine",), difficulty="intermediate", laterality="unilateral", kinetic_chain="mixed"),
    V("band_trunk_rotation", "Rotació de tronc amb banda", "trunk_rotation", "Rotació del tronc", TRUNK_ROTATION, equipment=("elastic_band",), difficulty="beginner", laterality="unilateral", kinetic_chain="mixed"),
    V("medicine_ball_seated_rotation", "Rotació asseguda amb pilota medicinal", "trunk_rotation", "Rotació del tronc", TRUNK_ROTATION, equipment=("medicine_ball", "mat"), difficulty="intermediate", laterality="alternating", kinetic_chain="open"),
    V("landmine_trunk_rotation", "Rotació de tronc amb landmine", "trunk_rotation", "Rotació del tronc", TRUNK_ROTATION, equipment=("barbell", "landmine"), difficulty="advanced", laterality="alternating", kinetic_chain="mixed"),
    V("forearm_plank_knees", "Planxa d'avantbraços amb genolls", "front_plank", "Planxa frontal", TRUNK_HOLD, optional_equipment=("mat",), difficulty="beginner", execution_type="isometric", modality="motor_control"),
    V("high_plank", "Planxa alta", "front_plank", "Planxa frontal", TRUNK_HOLD, optional_equipment=("mat",), difficulty="beginner", execution_type="isometric", modality="motor_control"),
    V("feet_elevated_front_plank", "Planxa frontal amb peus elevats", "front_plank", "Planxa frontal", TRUNK_HOLD, equipment=("bench",), difficulty="advanced", execution_type="isometric", modality="muscular_endurance"),
    V("stability_ball_forearm_plank", "Planxa d'avantbraços sobre pilota", "front_plank", "Planxa frontal", TRUNK_HOLD, equipment=("stability_ball",), difficulty="advanced", execution_type="isometric", modality="motor_control"),
    V("suspension_front_plank", "Planxa frontal en suspensió", "front_plank", "Planxa frontal", TRUNK_HOLD, equipment=("suspension_trainer",), difficulty="advanced", execution_type="isometric", modality="motor_control"),
    V("kneeling_side_plank", "Planxa lateral amb genoll de suport", "side_plank", "Planxa lateral", LATERAL_TRUNK_HOLD, optional_equipment=("mat",), difficulty="beginner", laterality="unilateral", execution_type="isometric", modality="motor_control"),
    V("forearm_side_plank", "Planxa lateral sobre avantbraç", "side_plank", "Planxa lateral", LATERAL_TRUNK_HOLD, optional_equipment=("mat",), difficulty="intermediate", laterality="unilateral", execution_type="isometric", modality="muscular_endurance"),
    V("feet_elevated_side_plank", "Planxa lateral amb peus elevats", "side_plank", "Planxa lateral", LATERAL_TRUNK_HOLD, equipment=("bench",), difficulty="advanced", laterality="unilateral", execution_type="isometric", modality="muscular_endurance"),
    V("copenhagen_side_hold_short_lever", "Manteniment lateral Copenhagen de palanca curta", "copenhagen_hold", "Manteniment lateral Copenhagen", LATERAL_TRUNK_HOLD, equipment=("bench", "mat"), difficulty="intermediate", laterality="unilateral", execution_type="isometric", modality="motor_control"),
    V("copenhagen_side_hold_long_lever", "Manteniment lateral Copenhagen de palanca llarga", "copenhagen_hold", "Manteniment lateral Copenhagen", LATERAL_TRUNK_HOLD, equipment=("bench", "mat"), difficulty="advanced", laterality="unilateral", execution_type="isometric", modality="muscular_endurance"),
    V("dead_bug_hold", "Manteniment dead bug", "dead_bug", "Dead bug", TRUNK_HOLD, optional_equipment=("mat",), difficulty="beginner", execution_type="isometric", modality="motor_control"),
    V("dead_bug_alternating", "Dead bug alternant", "dead_bug", "Dead bug", TRUNK_HOLD, optional_equipment=("mat",), difficulty="intermediate", laterality="alternating", execution_type="mixed", modality="motor_control"),
    V("bird_dog_hold", "Manteniment bird dog", "bird_dog", "Bird dog", TRUNK_HOLD, optional_equipment=("mat",), difficulty="beginner", laterality="unilateral", execution_type="isometric", modality="motor_control"),
    V("bird_dog_alternating", "Bird dog alternant", "bird_dog", "Bird dog", TRUNK_HOLD, optional_equipment=("mat",), difficulty="intermediate", laterality="alternating", execution_type="mixed", modality="motor_control"),
    V("hollow_body_hold", "Manteniment hollow body", "hollow_hold", "Manteniment hollow", TRUNK_HOLD, optional_equipment=("mat",), difficulty="advanced", execution_type="isometric", modality="muscular_endurance"),
    V("stability_ball_stir_hold", "Manteniment de planxa amb cercles sobre pilota", "front_plank", "Planxa frontal", TRUNK_HOLD, equipment=("stability_ball",), difficulty="advanced", execution_type="mixed", modality="motor_control"),
]

BATCH = batch("09_trunk", "Tronc dinàmic i estabilitzador", ROWS)

