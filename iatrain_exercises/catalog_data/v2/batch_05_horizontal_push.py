from .common import batch, variant as V
from .templates import HORIZONTAL_PRESS


ROWS = [
    V("barbell_flat_bench_press", "Press de banca pla amb barra", "bench_press", "Press de banca", HORIZONTAL_PRESS, equipment=("barbell", "bench"), difficulty="advanced", kinetic_chain="open", objective="max_strength"),
    V("dumbbell_flat_bench_press", "Press de banca pla amb manuelles", "bench_press", "Press de banca", HORIZONTAL_PRESS, equipment=("dumbbell", "bench"), difficulty="intermediate", kinetic_chain="open"),
    V("barbell_incline_bench_press", "Press de banca inclinat amb barra", "incline_press", "Press inclinat", HORIZONTAL_PRESS, equipment=("barbell", "bench"), difficulty="advanced", kinetic_chain="open", objective="max_strength"),
    V("dumbbell_incline_bench_press", "Press de banca inclinat amb manuelles", "incline_press", "Press inclinat", HORIZONTAL_PRESS, equipment=("dumbbell", "bench"), difficulty="intermediate", kinetic_chain="open"),
    V("dumbbell_decline_bench_press", "Press declinat amb manuelles", "decline_press", "Press declinat", HORIZONTAL_PRESS, equipment=("dumbbell", "bench"), difficulty="advanced", kinetic_chain="open"),
    V("close_grip_barbell_bench_press", "Press de banca amb presa estreta", "bench_press", "Press de banca", HORIZONTAL_PRESS, equipment=("barbell", "bench"), difficulty="advanced", kinetic_chain="open"),
    V("neutral_grip_dumbbell_bench_press", "Press de banca amb presa neutra", "bench_press", "Press de banca", HORIZONTAL_PRESS, equipment=("dumbbell", "bench"), difficulty="intermediate", kinetic_chain="open"),
    V("alternating_dumbbell_bench_press", "Press de banca alternant amb manuelles", "bench_press", "Press de banca", HORIZONTAL_PRESS, equipment=("dumbbell", "bench"), difficulty="advanced", laterality="alternating", kinetic_chain="open", modality="motor_control"),
    V("single_arm_dumbbell_bench_press", "Press de banca unilateral amb mancuerna", "bench_press", "Press de banca", HORIZONTAL_PRESS, equipment=("dumbbell", "bench"), difficulty="advanced", laterality="unilateral", kinetic_chain="open", modality="motor_control"),
    V("dumbbell_floor_press", "Press a terra amb manuelles", "floor_press", "Press a terra", HORIZONTAL_PRESS, equipment=("dumbbell",), optional_equipment=("mat",), difficulty="beginner", kinetic_chain="open"),
    V("barbell_floor_press", "Press a terra amb barra", "floor_press", "Press a terra", HORIZONTAL_PRESS, equipment=("barbell",), difficulty="advanced", kinetic_chain="open", objective="max_strength"),
    V("kettlebell_floor_press", "Press a terra amb kettlebells", "floor_press", "Press a terra", HORIZONTAL_PRESS, equipment=("kettlebell",), difficulty="intermediate", kinetic_chain="open"),
    V("machine_chest_press", "Press bilateral de pit en màquina", "machine_chest_press_family", "Press de pit en màquina", HORIZONTAL_PRESS, equipment=("resistance_machine",), difficulty="beginner", kinetic_chain="open"),
    V("single_arm_machine_chest_press", "Press de pit unilateral en màquina", "machine_chest_press_family", "Press de pit en màquina", HORIZONTAL_PRESS, equipment=("resistance_machine",), difficulty="intermediate", laterality="unilateral", kinetic_chain="open"),
    V("standing_cable_chest_press", "Press de pit dempeus amb politja", "cable_chest_press", "Press de pit amb politja", HORIZONTAL_PRESS, equipment=("cable_machine",), difficulty="intermediate", kinetic_chain="mixed", modality="motor_control"),
    V("single_arm_cable_chest_press", "Press de pit unilateral amb politja", "cable_chest_press", "Press de pit amb politja", HORIZONTAL_PRESS, equipment=("cable_machine",), difficulty="advanced", laterality="unilateral", kinetic_chain="mixed", modality="motor_control"),
    V("band_standing_chest_press", "Press de pit dempeus amb banda", "band_chest_press", "Press de pit amb banda", HORIZONTAL_PRESS, equipment=("elastic_band",), difficulty="beginner", kinetic_chain="mixed"),
    V("incline_push_up_bench", "Flexió de braços inclinada sobre banc", "push_up", "Flexió de braços", HORIZONTAL_PRESS, equipment=("bench",), difficulty="beginner", kinetic_chain="closed"),
    V("knee_push_up", "Flexió de braços amb suport de genolls", "push_up", "Flexió de braços", HORIZONTAL_PRESS, optional_equipment=("mat",), difficulty="beginner", kinetic_chain="closed"),
    V("decline_push_up", "Flexió de braços declinada", "push_up", "Flexió de braços", HORIZONTAL_PRESS, equipment=("bench",), difficulty="advanced", kinetic_chain="closed"),
    V("close_grip_push_up", "Flexió de braços amb mans juntes", "push_up", "Flexió de braços", HORIZONTAL_PRESS, optional_equipment=("mat",), difficulty="advanced", kinetic_chain="closed"),
    V("wide_hand_push_up", "Flexió de braços amb mans amples", "push_up", "Flexió de braços", HORIZONTAL_PRESS, optional_equipment=("mat",), difficulty="intermediate", kinetic_chain="closed"),
    V("suspension_push_up", "Flexió de braços en suspensió", "push_up", "Flexió de braços", HORIZONTAL_PRESS, equipment=("suspension_trainer",), difficulty="advanced", kinetic_chain="closed", modality="motor_control"),
    V("stability_ball_push_up", "Flexió de braços amb mans sobre pilota", "push_up", "Flexió de braços", HORIZONTAL_PRESS, equipment=("stability_ball",), difficulty="advanced", kinetic_chain="closed", modality="motor_control"),
    V("medicine_ball_offset_push_up", "Flexió de braços amb una mà sobre pilota medicinal", "push_up", "Flexió de braços", HORIZONTAL_PRESS, equipment=("medicine_ball",), difficulty="advanced", laterality="alternating", kinetic_chain="closed", modality="motor_control"),
    V("wall_push_up", "Flexió de braços a la paret", "push_up", "Flexió de braços", HORIZONTAL_PRESS, equipment=("wall",), difficulty="beginner", kinetic_chain="closed", modality="warm_up", objective="preparation"),
    V("smith_bar_incline_push_up", "Flexió inclinada sobre barra Smith", "push_up", "Flexió de braços", HORIZONTAL_PRESS, equipment=("smith_machine",), difficulty="beginner", kinetic_chain="closed"),
    V("weighted_push_up", "Flexió de braços amb disc", "push_up", "Flexió de braços", HORIZONTAL_PRESS, equipment=("weight_plate",), difficulty="advanced", kinetic_chain="closed", objective="max_strength"),
]

BATCH = batch("05_horizontal_push", "Empentes horitzontals", ROWS)
