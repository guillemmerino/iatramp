from .common import batch, variant as V
from .templates import CALF_RAISE, DORSIFLEXION, HIP_ABDUCTION, HIP_ADDUCTION, KNEE_EXTENSION, KNEE_FLEXION


ROWS = [
    V("seated_leg_extension", "Extensió de genoll en màquina", "knee_extension", "Extensió de genoll", KNEE_EXTENSION, equipment=("leg_extension_machine",), difficulty="beginner", kinetic_chain="open"),
    V("single_leg_extension_machine", "Extensió unilateral de genoll en màquina", "knee_extension", "Extensió de genoll", KNEE_EXTENSION, equipment=("leg_extension_machine",), difficulty="beginner", laterality="unilateral", kinetic_chain="open"),
    V("band_knee_extension", "Extensió de genoll amb banda", "knee_extension", "Extensió de genoll", KNEE_EXTENSION, equipment=("elastic_band",), difficulty="beginner", laterality="unilateral", kinetic_chain="open"),
    V("cable_knee_extension", "Extensió de genoll amb politja", "knee_extension", "Extensió de genoll", KNEE_EXTENSION, equipment=("cable_machine",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
    V("lying_leg_curl_machine", "Flexió de genoll estirat en màquina", "knee_flexion", "Flexió de genoll", KNEE_FLEXION, equipment=("leg_curl_machine",), difficulty="beginner", kinetic_chain="open"),
    V("seated_leg_curl_machine", "Flexió de genoll assegut en màquina", "knee_flexion", "Flexió de genoll", KNEE_FLEXION, equipment=("leg_curl_machine",), difficulty="beginner", kinetic_chain="open"),
    V("standing_single_leg_curl_machine", "Flexió unilateral de genoll dempeus", "knee_flexion", "Flexió de genoll", KNEE_FLEXION, equipment=("leg_curl_machine",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
    V("band_standing_leg_curl", "Flexió de genoll dempeus amb banda", "knee_flexion", "Flexió de genoll", KNEE_FLEXION, equipment=("elastic_band",), difficulty="beginner", laterality="unilateral", kinetic_chain="open"),
    V("slider_leg_curl", "Flexió de genolls amb discs lliscants", "knee_flexion", "Flexió de genoll", KNEE_FLEXION, equipment=("slider",), difficulty="advanced", kinetic_chain="mixed"),
    V("stability_ball_leg_curl", "Flexió de genolls sobre pilota", "knee_flexion", "Flexió de genoll", KNEE_FLEXION, equipment=("stability_ball",), difficulty="advanced", kinetic_chain="mixed", modality="motor_control"),
    V("machine_hip_abduction", "Abducció de maluc en màquina", "hip_abduction", "Abducció de maluc", HIP_ABDUCTION, equipment=("resistance_machine",), difficulty="beginner", kinetic_chain="open"),
    V("cable_standing_hip_abduction", "Abducció de maluc dempeus amb politja", "hip_abduction", "Abducció de maluc", HIP_ABDUCTION, equipment=("cable_machine",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
    V("band_standing_hip_abduction", "Abducció de maluc dempeus amb banda", "hip_abduction", "Abducció de maluc", HIP_ABDUCTION, equipment=("elastic_band",), difficulty="beginner", laterality="unilateral", kinetic_chain="open"),
    V("side_lying_hip_abduction", "Abducció de maluc en decúbit lateral", "hip_abduction", "Abducció de maluc", HIP_ABDUCTION, optional_equipment=("mat",), difficulty="beginner", laterality="unilateral", kinetic_chain="open"),
    V("machine_hip_adduction", "Adducció de maluc en màquina", "hip_adduction", "Adducció de maluc", HIP_ADDUCTION, equipment=("resistance_machine",), difficulty="beginner", kinetic_chain="open"),
    V("cable_standing_hip_adduction", "Adducció de maluc dempeus amb politja", "hip_adduction", "Adducció de maluc", HIP_ADDUCTION, equipment=("cable_machine",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
    V("band_standing_hip_adduction", "Adducció de maluc dempeus amb banda", "hip_adduction", "Adducció de maluc", HIP_ADDUCTION, equipment=("elastic_band",), difficulty="beginner", laterality="unilateral", kinetic_chain="open"),
    V("standing_bodyweight_calf_raise", "Elevació de talons dempeus", "calf_raise", "Elevació de talons", CALF_RAISE, optional_equipment=("wall",), difficulty="beginner"),
    V("single_leg_calf_raise", "Elevació de taló a una cama", "calf_raise", "Elevació de talons", CALF_RAISE, optional_equipment=("wall",), difficulty="intermediate", laterality="unilateral"),
    V("dumbbell_single_leg_calf_raise", "Elevació de taló a una cama amb mancuerna", "calf_raise", "Elevació de talons", CALF_RAISE, equipment=("dumbbell",), optional_equipment=("wall",), difficulty="intermediate", laterality="unilateral"),
    V("seated_calf_raise_machine", "Elevació de talons assegut en màquina", "seated_calf_raise", "Elevació de talons assegut", CALF_RAISE, equipment=("resistance_machine",), difficulty="beginner", kinetic_chain="closed"),
    V("seated_dumbbell_calf_raise", "Elevació de talons assegut amb manuelles", "seated_calf_raise", "Elevació de talons assegut", CALF_RAISE, equipment=("dumbbell", "bench"), difficulty="beginner"),
    V("smith_machine_calf_raise", "Elevació de talons a màquina Smith", "calf_raise", "Elevació de talons", CALF_RAISE, equipment=("smith_machine",), difficulty="intermediate", objective="max_strength"),
    V("leg_press_calf_raise", "Flexió plantar a la premsa de cames", "calf_raise", "Elevació de talons", CALF_RAISE, equipment=("leg_press_machine",), difficulty="intermediate", kinetic_chain="closed"),
    V("step_calf_raise", "Elevació de talons sobre esglaó", "calf_raise", "Elevació de talons", CALF_RAISE, equipment=("step_platform",), difficulty="intermediate", secondary_objective="mobility"),
    V("wall_tibialis_raise", "Elevació de l'avantpeu recolzat a la paret", "tibialis_raise", "Elevació de l'avantpeu", DORSIFLEXION, equipment=("wall",), difficulty="beginner", kinetic_chain="open"),
    V("band_ankle_dorsiflexion", "Dorsiflexió de turmell amb banda", "tibialis_raise", "Elevació de l'avantpeu", DORSIFLEXION, equipment=("elastic_band",), difficulty="beginner", laterality="unilateral", kinetic_chain="open"),
    V("cable_ankle_dorsiflexion", "Dorsiflexió de turmell amb politja", "tibialis_raise", "Elevació de l'avantpeu", DORSIFLEXION, equipment=("cable_machine",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
]

BATCH = batch("04_lower_accessory", "Genoll, maluc i turmell monoarticulars", ROWS)

