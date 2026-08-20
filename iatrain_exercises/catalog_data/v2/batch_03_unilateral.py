from .common import batch, variant as V
from .templates import HIP_BRIDGE, HINGE, UNILATERAL_SQUAT


ROWS = [
    V("bodyweight_split_squat", "Esquat dividit amb pes corporal", "split_squat", "Esquat dividit", UNILATERAL_SQUAT, difficulty="beginner", laterality="unilateral"),
    V("dumbbell_split_squat", "Esquat dividit amb manuelles", "split_squat", "Esquat dividit", UNILATERAL_SQUAT, equipment=("dumbbell",), laterality="unilateral"),
    V("barbell_split_squat", "Esquat dividit amb barra", "split_squat", "Esquat dividit", UNILATERAL_SQUAT, equipment=("barbell",), difficulty="advanced", laterality="unilateral", objective="max_strength"),
    V("front_foot_elevated_split_squat", "Esquat dividit amb peu davanter elevat", "split_squat", "Esquat dividit", UNILATERAL_SQUAT, equipment=("step_platform",), difficulty="intermediate", laterality="unilateral", secondary_objective="mobility"),
    V("rear_foot_elevated_split_squat", "Esquat búlgar amb pes corporal", "bulgarian_split_squat", "Esquat búlgar", UNILATERAL_SQUAT, equipment=("bench",), difficulty="intermediate", laterality="unilateral"),
    V("dumbbell_bulgarian_split_squat", "Esquat búlgar amb manuelles", "bulgarian_split_squat", "Esquat búlgar", UNILATERAL_SQUAT, equipment=("bench", "dumbbell"), difficulty="advanced", laterality="unilateral"),
    V("barbell_bulgarian_split_squat", "Esquat búlgar amb barra", "bulgarian_split_squat", "Esquat búlgar", UNILATERAL_SQUAT, equipment=("bench", "barbell"), difficulty="advanced", laterality="unilateral", objective="max_strength"),
    V("forward_lunge", "Gambada endavant", "lunge", "Gambada", UNILATERAL_SQUAT, difficulty="beginner", laterality="alternating"),
    V("reverse_lunge", "Gambada enrere", "lunge", "Gambada", UNILATERAL_SQUAT, difficulty="beginner", laterality="alternating"),
    V("walking_lunge", "Gambada caminant", "lunge", "Gambada", UNILATERAL_SQUAT, difficulty="intermediate", laterality="alternating"),
    V("dumbbell_forward_lunge", "Gambada endavant amb manuelles", "lunge", "Gambada", UNILATERAL_SQUAT, equipment=("dumbbell",), difficulty="intermediate", laterality="alternating"),
    V("dumbbell_reverse_lunge", "Gambada enrere amb manuelles", "lunge", "Gambada", UNILATERAL_SQUAT, equipment=("dumbbell",), difficulty="intermediate", laterality="alternating"),
    V("barbell_reverse_lunge", "Gambada enrere amb barra", "lunge", "Gambada", UNILATERAL_SQUAT, equipment=("barbell",), difficulty="advanced", laterality="alternating"),
    V("lateral_lunge", "Gambada lateral amb pes corporal", "lateral_lunge_family", "Gambada lateral", UNILATERAL_SQUAT, difficulty="intermediate", laterality="alternating", modality="motor_control"),
    V("goblet_lateral_lunge", "Gambada lateral goblet", "lateral_lunge_family", "Gambada lateral", UNILATERAL_SQUAT, equipment=("kettlebell",), difficulty="intermediate", laterality="alternating"),
    V("bodyweight_step_up", "Pujada a esglaó amb pes corporal", "step_up", "Pujada a esglaó", UNILATERAL_SQUAT, equipment=("step_platform",), difficulty="beginner", laterality="unilateral"),
    V("dumbbell_step_up", "Pujada a esglaó amb manuelles", "step_up", "Pujada a esglaó", UNILATERAL_SQUAT, equipment=("step_platform", "dumbbell"), difficulty="intermediate", laterality="unilateral"),
    V("lateral_step_up", "Pujada lateral a esglaó", "step_up", "Pujada a esglaó", UNILATERAL_SQUAT, equipment=("step_platform",), difficulty="intermediate", laterality="unilateral", modality="motor_control"),
    V("controlled_step_down", "Baixada controlada d'esglaó", "step_down", "Baixada d'esglaó", UNILATERAL_SQUAT, equipment=("step_platform",), difficulty="intermediate", laterality="unilateral", modality="motor_control"),
    V("assisted_single_leg_squat", "Esquat a una cama assistit", "single_leg_squat", "Esquat a una cama", UNILATERAL_SQUAT, equipment=("suspension_trainer",), difficulty="intermediate", laterality="unilateral", modality="motor_control"),
    V("box_single_leg_squat", "Esquat a una cama fins a caixa", "single_leg_squat", "Esquat a una cama", UNILATERAL_SQUAT, equipment=("box",), difficulty="advanced", laterality="unilateral"),
    V("pistol_squat", "Esquat pistola", "single_leg_squat", "Esquat a una cama", UNILATERAL_SQUAT, difficulty="advanced", laterality="unilateral", secondary_objective="mobility"),
    V("single_leg_romanian_deadlift", "Pes mort romanès a una cama", "single_leg_hinge", "Frontissa a una cama", HINGE, difficulty="intermediate", laterality="unilateral", kinetic_chain="closed", modality="motor_control"),
    V("dumbbell_single_leg_romanian_deadlift", "Pes mort romanès a una cama amb mancuerna", "single_leg_hinge", "Frontissa a una cama", HINGE, equipment=("dumbbell",), difficulty="intermediate", laterality="unilateral"),
    V("kettlebell_single_leg_romanian_deadlift", "Pes mort romanès a una cama amb kettlebell", "single_leg_hinge", "Frontissa a una cama", HINGE, equipment=("kettlebell",), difficulty="intermediate", laterality="unilateral"),
    V("supported_single_leg_romanian_deadlift", "Frontissa a una cama amb suport", "single_leg_hinge", "Frontissa a una cama", HINGE, equipment=("wall",), difficulty="beginner", laterality="unilateral", modality="motor_control"),
    V("single_leg_glute_bridge", "Pont de glutis a una cama amb pes corporal", "single_leg_glute_bridge_family", "Pont de glutis a una cama", HIP_BRIDGE, optional_equipment=("mat",), difficulty="intermediate", laterality="unilateral"),
    V("single_leg_hip_thrust", "Hip thrust a una cama amb pes corporal", "single_leg_hip_thrust_family", "Hip thrust a una cama", HIP_BRIDGE, equipment=("bench",), difficulty="advanced", laterality="unilateral"),
]

BATCH = batch("03_unilateral", "Força unilateral d'extremitat inferior", ROWS)
