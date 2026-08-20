"""Reviewable seed contract for IA Train's first measurable canonical skeleton."""

from .models import (
    CanonicalLandmark,
    CanonicalSegment,
    JointAngleDefinition,
    SkeletonSide,
)


SKELETON_CODE = "iatrain_functional_skeleton"
SKELETON_VERSION = "1.0.0-draft"
SEED_ID = f"{SKELETON_CODE}_{SKELETON_VERSION}"

SCHEMA = {
    "code": SKELETON_CODE,
    "version": SKELETON_VERSION,
    "name": "Esquelet funcional canònic d'IA Train",
    "description": (
        "Esquema corporal tridimensional, independent del tracker, per descriure segments, "
        "centres articulars i angles funcionals rellevants per al moviment de trampolí."
    ),
    "spatial_dimensions": 3,
    "length_unit": "metre",
    "angle_unit": "radian",
    "coordinate_convention": {
        "handedness": "right_handed",
        "axes": {
            "+x": "direcció horitzontal de referència definida en el calibratge de la instal·lació",
            "+y": "vertical ascendent, oposada a la gravetat",
            "+z": "completa el triedre dretà en el pla horitzontal",
        },
        "segment_frames": {
            "primary_axis": "vector d'axis_start_landmark cap a axis_end_landmark",
            "plane_reference": "tercer punt projectat ortogonalment respecte de l'eix principal",
            "orthonormalization": "gram_schmidt",
            "long_axis_only": "no permet inferir rotació axial del segment",
        },
    },
    "neutral_pose": {
        "name": "posició anatòmica funcional",
        "description": (
            "Cos erecte, pelvis i tronc neutres, extremitats inferiors esteses, "
            "braços al costat del cos i mirada endavant."
        ),
        "joint_angle_zero": "zero funcional definit per cada JointAngleDefinition",
    },
    "provenance": {
        "seed": SEED_ID,
        "standards": [
            "ISB global kinematic reporting recommendations",
            "ISB joint coordinate system recommendations",
        ],
        "review_status": "professional_review_required",
    },
}


def _landmark(code, name, landmark_type, source, side, definition, derivation=None):
    return {
        "code": code,
        "name": name,
        "definition": definition,
        "landmark_type": landmark_type,
        "measurement_source": source,
        "side": side,
        "derivation": derivation or {},
        "provenance": {"seed": SEED_ID},
    }


LT = CanonicalLandmark.LandmarkType
MS = CanonicalLandmark.MeasurementSource
S = SkeletonSide

LANDMARKS = [
    _landmark(
        "pelvis_center", "Centre de pelvis", LT.VIRTUAL, MS.DERIVED, S.MIDLINE,
        "Punt mig funcional entre els centres dels dos malucs.",
        {"method": "midpoint", "inputs": ["left_hip_center", "right_hip_center"]},
    ),
    _landmark(
        "thorax_center", "Centre toràcic", LT.VIRTUAL, MS.DERIVED, S.MIDLINE,
        "Punt mig funcional entre els centres de les dues espatlles.",
        {"method": "midpoint", "inputs": ["left_shoulder_center", "right_shoulder_center"]},
    ),
    _landmark(
        "head_center", "Centre del cap", LT.ANATOMICAL, MS.OBSERVED, S.MIDLINE,
        "Punt representatiu del centre del cap, mapable o derivable segons el tracker.",
    ),
    _landmark(
        "head_top", "Vèrtex cranial", LT.TERMINAL, MS.OBSERVED, S.MIDLINE,
        "Punt superior del cap utilitzat quan el tracker el proporciona de manera fiable.",
    ),
    _landmark(
        "sacrum_center", "Centre sacre posterior", LT.VIRTUAL, MS.DERIVED, S.MIDLINE,
        "Punt mig funcional entre les espines ilíaques posterosuperiors.",
        {"method": "midpoint", "inputs": ["left_psis", "right_psis"]},
    ),
    _landmark(
        "neck_base", "Base funcional cervical", LT.JOINT_CENTER, MS.ESTIMATED, S.MIDLINE,
        "Centre funcional estimat de la transició entre el tronc i el complex cap-coll.",
    ),
]

for side, label in ((S.LEFT, "esquerre"), (S.RIGHT, "dret")):
    prefix = side
    LANDMARKS.extend(
        (
            _landmark(f"{prefix}_shoulder_center", f"Centre d'espatlla {label}", LT.JOINT_CENTER, MS.ESTIMATED, side, "Centre funcional del complex de l'espatlla."),
            _landmark(f"{prefix}_elbow_center", f"Centre de colze {label}", LT.JOINT_CENTER, MS.ESTIMATED, side, "Centre funcional del complex del colze."),
            _landmark(f"{prefix}_wrist_center", f"Centre de canell {label}", LT.JOINT_CENTER, MS.ESTIMATED, side, "Centre funcional del canell."),
            _landmark(f"{prefix}_hand_center", f"Centre de mà {label}", LT.TERMINAL, MS.OBSERVED, side, "Punt distal representatiu de la mà."),
            _landmark(f"{prefix}_hip_center", f"Centre de maluc {label}", LT.JOINT_CENTER, MS.ESTIMATED, side, "Centre funcional de l'articulació coxofemoral."),
            _landmark(f"{prefix}_asis", f"Espina ilíaca anterosuperior {label}", LT.ANATOMICAL, MS.ESTIMATED, side, "Punt pèlvic anterior utilitzat per definir el marc local de la pelvis."),
            _landmark(f"{prefix}_psis", f"Espina ilíaca posterosuperior {label}", LT.ANATOMICAL, MS.ESTIMATED, side, "Punt pèlvic posterior utilitzat per definir el marc local de la pelvis."),
            _landmark(f"{prefix}_knee_center", f"Centre de genoll {label}", LT.JOINT_CENTER, MS.ESTIMATED, side, "Centre funcional del complex del genoll."),
            _landmark(f"{prefix}_ankle_center", f"Centre de turmell {label}", LT.JOINT_CENTER, MS.ESTIMATED, side, "Centre funcional del complex del turmell."),
            _landmark(f"{prefix}_heel", f"Taló {label}", LT.ANATOMICAL, MS.OBSERVED, side, "Punt posterior representatiu del calcani."),
            _landmark(f"{prefix}_forefoot_center", f"Centre d'avantpeu {label}", LT.TERMINAL, MS.OBSERVED, side, "Punt distal representatiu de l'avantpeu."),
            _landmark(f"{prefix}_scapula_center", f"Centre escapular {label}", LT.JOINT_CENTER, MS.ESTIMATED, side, "Punt funcional estimat per representar la interfície escapulotoràcica."),
        )
    )

LANDMARKS = tuple(LANDMARKS)


def _segment(code, concept, side, start, end, capability, plane=None, primary_axis="longitudinal", notes=""):
    return {
        "code": code,
        "concept_code": concept,
        "side": side,
        "axis_start": start,
        "axis_end": end,
        "plane_landmark": plane,
        "orientation_capability": capability,
        "primary_axis": primary_axis,
        "frame_notes": notes,
        "provenance": {"seed": SEED_ID},
    }


OC = CanonicalSegment.OrientationCapability
PA = CanonicalSegment.PrimaryAxis

SEGMENTS = [
    _segment("pelvis", "pelvis", S.MIDLINE, "left_asis", "right_asis", OC.FULL_3D, "sacrum_center", PA.MEDIOLATERAL, "Marc pèlvic definit exclusivament amb punts fixats a la pelvis."),
    _segment("trunk", "trunk", S.MIDLINE, "pelvis_center", "thorax_center", OC.FULL_3D, "left_shoulder_center"),
    _segment("head_neck", "head_neck", S.MIDLINE, "thorax_center", "head_center", OC.LONG_AXIS_ONLY),
]

for side in (S.LEFT, S.RIGHT):
    SEGMENTS.extend(
        (
            _segment(f"{side}_shoulder_girdle", "shoulder_girdle", side, "thorax_center", f"{side}_shoulder_center", OC.LONG_AXIS_ONLY, primary_axis=PA.MEDIOLATERAL),
            _segment(f"{side}_upper_arm", "upper_arm", side, f"{side}_shoulder_center", f"{side}_elbow_center", OC.LONG_AXIS_ONLY),
            _segment(f"{side}_forearm", "forearm", side, f"{side}_elbow_center", f"{side}_wrist_center", OC.LONG_AXIS_ONLY),
            _segment(f"{side}_hand", "hand", side, f"{side}_wrist_center", f"{side}_hand_center", OC.LONG_AXIS_ONLY),
            _segment(f"{side}_thigh", "thigh", side, f"{side}_hip_center", f"{side}_knee_center", OC.LONG_AXIS_ONLY),
            _segment(f"{side}_lower_leg", "lower_leg", side, f"{side}_knee_center", f"{side}_ankle_center", OC.LONG_AXIS_ONLY),
            _segment(f"{side}_foot", "foot", side, f"{side}_heel", f"{side}_forefoot_center", OC.FULL_3D, f"{side}_ankle_center"),
        )
    )

SEGMENTS = tuple(SEGMENTS)


def _joint(code, concept, side, center, proximal, distal):
    return {
        "code": code,
        "concept_code": concept,
        "side": side,
        "center_landmark": center,
        "proximal_segment": proximal,
        "distal_segment": distal,
        "provenance": {"seed": SEED_ID},
    }


JOINTS = [
    _joint("thoracolumbar_spine_complex", "thoracolumbar_spine_complex", S.MIDLINE, "pelvis_center", "pelvis", "trunk"),
    _joint("cervical_spine_complex", "cervical_spine_complex", S.MIDLINE, "neck_base", "trunk", "head_neck"),
]
for side in (S.LEFT, S.RIGHT):
    JOINTS.extend(
        (
            _joint(f"{side}_scapulothoracic_joint", "scapulothoracic_joint", side, f"{side}_scapula_center", "trunk", f"{side}_shoulder_girdle"),
            _joint(f"{side}_shoulder_joint", "shoulder_joint", side, f"{side}_shoulder_center", f"{side}_shoulder_girdle", f"{side}_upper_arm"),
            _joint(f"{side}_elbow_joint", "elbow_joint", side, f"{side}_elbow_center", f"{side}_upper_arm", f"{side}_forearm"),
            _joint(f"{side}_wrist_joint", "wrist_joint", side, f"{side}_wrist_center", f"{side}_forearm", f"{side}_hand"),
            _joint(f"{side}_hip_joint", "hip_joint", side, f"{side}_hip_center", "pelvis", f"{side}_thigh"),
            _joint(f"{side}_knee_joint", "knee_joint", side, f"{side}_knee_center", f"{side}_thigh", f"{side}_lower_leg"),
            _joint(f"{side}_ankle_joint", "ankle_joint", side, f"{side}_ankle_center", f"{side}_lower_leg", f"{side}_foot"),
        )
    )

JOINTS = tuple(JOINTS)


def _angle(
    code,
    joint,
    positive,
    negative,
    plane,
    axis,
    component="flexion_extension",
    sequence_index=1,
):
    return {
        "code": code,
        "joint_code": joint,
        "component": component,
        "sequence_index": sequence_index,
        "positive_action_code": positive,
        "negative_action_code": negative,
        "plane_code": plane,
        "axis_code": axis,
        "calculation_method": JointAngleDefinition.CalculationMethod.PROJECTED_PLANAR,
        "sign_convention": (
            f"Valors positius representen {positive}; valors negatius representen {negative}. "
            "Zero segons la posició neutra de l'esquema."
        ),
        "provenance": {"seed": SEED_ID},
    }


ANGLES = [
    _angle("trunk_flexion_extension", "thoracolumbar_spine_complex", "trunk_flexion", "trunk_extension", "sagittal_plane", "mediolateral_axis"),
    _angle("cervical_flexion_extension", "cervical_spine_complex", "neck_flexion", "neck_extension", "sagittal_plane", "mediolateral_axis"),
]
for side in (S.LEFT, S.RIGHT):
    ANGLES.extend(
        (
            _angle(f"{side}_shoulder_flexion_extension", f"{side}_shoulder_joint", "shoulder_flexion", "shoulder_extension", "sagittal_plane", "mediolateral_axis"),
            _angle(f"{side}_shoulder_abduction_adduction", f"{side}_shoulder_joint", "shoulder_abduction", "shoulder_adduction", "frontal_plane", "anteroposterior_axis", JointAngleDefinition.Component.ABDUCTION_ADDUCTION, 2),
            _angle(f"{side}_shoulder_horizontal_abduction_adduction", f"{side}_shoulder_joint", "shoulder_horizontal_abduction", "shoulder_horizontal_adduction", "transverse_plane", "longitudinal_axis", JointAngleDefinition.Component.HORIZONTAL_ABDUCTION_ADDUCTION, 3),
            _angle(f"{side}_elbow_flexion_extension", f"{side}_elbow_joint", "elbow_flexion", "elbow_extension", "sagittal_plane", "mediolateral_axis"),
            _angle(f"{side}_wrist_flexion_extension", f"{side}_wrist_joint", "wrist_flexion", "wrist_extension", "sagittal_plane", "mediolateral_axis"),
            _angle(f"{side}_wrist_radial_ulnar_deviation", f"{side}_wrist_joint", "wrist_radial_deviation", "wrist_ulnar_deviation", "frontal_plane", "anteroposterior_axis", JointAngleDefinition.Component.RADIAL_ULNAR_DEVIATION, 2),
            _angle(f"{side}_hip_flexion_extension", f"{side}_hip_joint", "hip_flexion", "hip_extension", "sagittal_plane", "mediolateral_axis"),
            _angle(f"{side}_hip_abduction_adduction", f"{side}_hip_joint", "hip_abduction", "hip_adduction", "frontal_plane", "anteroposterior_axis", JointAngleDefinition.Component.ABDUCTION_ADDUCTION, 2),
            _angle(f"{side}_knee_flexion_extension", f"{side}_knee_joint", "knee_flexion", "knee_extension", "sagittal_plane", "mediolateral_axis"),
            _angle(f"{side}_ankle_flexion_extension", f"{side}_ankle_joint", "ankle_dorsiflexion", "ankle_plantarflexion", "sagittal_plane", "mediolateral_axis"),
            _angle(f"{side}_ankle_inversion_eversion", f"{side}_ankle_joint", "foot_inversion", "foot_eversion", "frontal_plane", "anteroposterior_axis", JointAngleDefinition.Component.INVERSION_EVERSION, 2),
        )
    )

ANGLES = tuple(ANGLES)
