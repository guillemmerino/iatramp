from .common import action_phase, hold_template, pair_template


A = "action"
S = "stabilization"

SQUAT = pair_template(
    summary="patró multiarticular de flexió i extensió coordinades de maluc, genoll i turmell",
    setup="Organitza els peus sobre una base estable i ajusta la posició inicial a la variant.",
    execution="Descendeix amb flexió coordinada de les extremitats inferiors i torna dempeus estenent maluc i genolls.",
    cues="Mantén el contacte del peu, acompanya la direcció dels genolls i conserva el tronc organitzat.",
    outbound_actions=("hip_extension", "knee_extension", "ankle_plantarflexion"),
    return_actions=("hip_flexion", "knee_flexion", "ankle_dorsiflexion"),
    muscles=(("gluteus_maximus", "primary", "gluteus_maximus__hip_extension__general", A), ("vastus_lateralis", "primary", "vastus_lateralis__knee_extension__general", A)),
    source_refs=("squat_review_2024", "ace_applied_science"), pattern="squat",
)

SQUAT_HOLD = hold_template(
    summary="manteniment d'una posició d'esquat sota tensió continuada",
    setup="Situa els peus estables i adopta l'angle de maluc i genoll definit per la variant.",
    execution="Mantén la posició acordada sense desplaçament deliberat del tronc ni de les extremitats.",
    cues="Distribueix la pressió als peus, mantén els genolls orientats i respira de forma regular.",
    muscles=(("gluteus_maximus", "primary", "gluteus_maximus__hip_extension__general", A), ("vastus_lateralis", "primary", "vastus_lateralis__knee_extension__general", A)),
    source_refs=("squat_review_2024",), pattern="squat",
)

HINGE = pair_template(
    summary="frontissa de maluc amb tronc estable i moviment predominant al maluc",
    setup="Estableix una base ferma, una columna organitzada i la càrrega prop del cos quan n'hi hagi.",
    execution="Desplaça el maluc enrere fins al rang controlat i estén-lo per recuperar la posició inicial.",
    cues="Porta el maluc enrere, conserva la càrrega a prop i acaba amb extensió de maluc sense exagerar l'extensió lumbar.",
    outbound_actions=("hip_extension",), return_actions=("hip_flexion",),
    muscles=(("gluteus_maximus", "primary", "gluteus_maximus__hip_extension__general", A), ("semitendinosus", "secondary", "semitendinosus__hip_extension__general", A)),
    source_refs=("deadlift_emg_review", "acsm_resistance_2026"), pattern="hinge",
)

HIP_BRIDGE = pair_template(
    summary="extensió de maluc des d'un suport supí o amb l'esquena recolzada",
    setup="Col·loca el suport posterior estable, els peus plantats i la pelvis preparada per moure's.",
    execution="Eleva la pelvis mitjançant extensió de maluc i baixa-la de forma controlada.",
    cues="Empeny el terra, mantén les costelles controlades i evita convertir el final en hiperextensió lumbar.",
    outbound_actions=("hip_extension",), return_actions=("hip_flexion",),
    muscles=(("gluteus_maximus", "primary", "gluteus_maximus__hip_extension__general", A),),
    source_refs=("deadlift_emg_review", "ace_applied_science"), pattern="hinge",
)

UNILATERAL_SQUAT = pair_template(
    summary="patró unilateral de flexió i extensió de maluc i genoll amb control frontal de la pelvis",
    setup="Estableix el peu de treball i el suport indicat, amb la pelvis orientada i estable.",
    execution="Flexiona maluc i genoll sobre la cama de treball i torna estenent-los sense perdre l'equilibri.",
    cues="Mantén el peu complet, controla la pelvis i dirigeix el genoll de manera coherent amb el peu.",
    outbound_actions=("hip_extension", "knee_extension"), return_actions=("hip_flexion", "knee_flexion"),
    muscles=(("gluteus_maximus", "primary", "gluteus_maximus__hip_extension__general", A), ("vastus_lateralis", "primary", "vastus_lateralis__knee_extension__general", A), ("gluteus_medius", "stabilizer", "gluteus_medius_pelvis_control", S)),
    source_refs=("unilateral_meta_analysis", "squat_review_2024"), pattern="squat",
)

KNEE_EXTENSION = pair_template(
    summary="extensió de genoll en cadena oberta amb moviment aïllat i controlat",
    setup="Alinea el genoll amb l'eix o el punt de resistència i estabilitza la resta del cos.",
    execution="Estén el genoll fins al rang definit i retorna lentament a flexió.",
    cues="Mou només el genoll, evita l'impuls i mantén una trajectòria constant.",
    outbound_actions=("knee_extension",), return_actions=("knee_flexion",),
    muscles=(("vastus_lateralis", "primary", "vastus_lateralis__knee_extension__general", A),),
    source_refs=("acsm_resistance_2026", "ace_applied_science"), pattern="other",
)

KNEE_FLEXION = pair_template(
    summary="flexió de genoll en cadena oberta amb control del retorn",
    setup="Alinea el genoll i el punt de resistència, mantenint la pelvis estable.",
    execution="Flexiona el genoll contra la resistència i torna fins al rang inicial sense deixar caure la càrrega.",
    cues="Mantén la pelvis quieta i evita accelerar el retorn.",
    outbound_actions=("knee_flexion",), return_actions=("knee_extension",),
    muscles=(("semitendinosus", "primary", "semitendinosus__knee_flexion__general", A),),
    source_refs=("acsm_resistance_2026", "ace_applied_science"), pattern="other",
)

HIP_ABDUCTION = pair_template(
    summary="abducció de maluc en cadena oberta amb pelvis controlada",
    setup="Estabilitza el tronc i la pelvis abans de separar la cama de la línia mitjana.",
    execution="Abdueix el maluc fins al rang controlat i retorna cap a adducció lentament.",
    cues="Evita inclinar el tronc o girar la pelvis per guanyar rang.",
    outbound_actions=("hip_abduction",), return_actions=("hip_adduction",),
    muscles=(("gluteus_medius", "primary", "gluteus_medius__hip_abduction__general", A),),
    source_refs=("ace_applied_science", "openstax_lower_limb"), pattern="other",
)

HIP_ADDUCTION = pair_template(
    summary="adducció de maluc en cadena oberta amb trajectòria definida",
    setup="Estabilitza el tronc i situa la resistència perquè la cama pugui acostar-se a la línia mitjana.",
    execution="Adduïx el maluc contra la resistència i retorna en abducció de manera controlada.",
    cues="Mantén la pelvis quieta i evita utilitzar impuls.",
    outbound_actions=("hip_adduction",), return_actions=("hip_abduction",),
    muscles=(("adductor_magnus", "primary", "adductor_magnus__hip_adduction__general", A),),
    source_refs=("ace_applied_science", "openstax_lower_limb"), pattern="other",
)

CALF_RAISE = pair_template(
    summary="flexió plantar del turmell amb control de la baixada",
    setup="Situa l'avantpeu estable i prepara un suport d'equilibri si la variant ho requereix.",
    execution="Eleva el taló mitjançant flexió plantar i baixa'l cap a dorsiflexió de manera controlada.",
    cues="Mantén la pressió repartida sobre l'avantpeu i evita oscil·lacions laterals.",
    outbound_actions=("ankle_plantarflexion",), return_actions=("ankle_dorsiflexion",),
    muscles=(("gastrocnemius", "primary", "gastrocnemius__ankle_plantarflexion__general", A), ("soleus", "primary", "soleus__ankle_plantarflexion__general", A)),
    source_refs=("ace_applied_science", "openstax_lower_limb"), pattern="ankle_dominant",
)

DORSIFLEXION = pair_template(
    summary="dorsiflexió activa del turmell contra resistència o gravetat",
    setup="Estabilitza el taló i situa el peu perquè es pugui elevar l'avantpeu.",
    execution="Porta l'avantpeu cap a la tíbia i retorna lentament cap a flexió plantar.",
    cues="Mou el turmell sense balancejar el cos ni accelerar el retorn.",
    outbound_actions=("ankle_dorsiflexion",), return_actions=("ankle_plantarflexion",),
    muscles=(("tibialis_anterior", "primary", "tibialis_anterior__ankle_dorsiflexion__general", A),),
    source_refs=("ace_applied_science", "openstax_lower_limb"), pattern="ankle_dominant",
)

HORIZONTAL_PRESS = pair_template(
    summary="empenta horitzontal coordinant espatlla i colze",
    setup="Organitza els punts de suport, la cintura escapular i la presa pròpia de la variant.",
    execution="Allunya la resistència amb adducció horitzontal d'espatlla i extensió de colze; retorna sense perdre el control.",
    cues="Mantén canells i colzes organitzats, controla les escàpules i evita l'impuls.",
    outbound_actions=("shoulder_horizontal_adduction", "elbow_extension"), return_actions=("shoulder_horizontal_abduction", "elbow_flexion"),
    muscles=(("pectoralis_major", "primary", "pectoralis_major__shoulder_horizontal_adduction__general", A), ("triceps_brachii", "secondary", "triceps_brachii__elbow_extension__general", A), ("serratus_anterior", "stabilizer", "serratus_anterior_scapular_control", S)),
    source_refs=("bench_press_review", "chest_kinematics"), pattern="horizontal_push",
)

VERTICAL_PRESS = pair_template(
    summary="empenta per sobre del cap amb flexió d'espatlla i extensió de colze",
    setup="Estableix la base o el suport assegut i situa la resistència a l'alçada inicial prevista.",
    execution="Eleva la resistència amb flexió d'espatlla i extensió de colze; retorna de forma controlada.",
    cues="Mantén el tronc estable, deixa una trajectòria lliure per als braços i evita compensar amb la zona lumbar.",
    outbound_actions=("shoulder_flexion", "elbow_extension"), return_actions=("shoulder_extension", "elbow_flexion"),
    muscles=(("deltoid_anterior", "primary", "deltoid_anterior__shoulder_flexion__general", A), ("triceps_brachii", "secondary", "triceps_brachii__elbow_extension__general", A), ("trapezius_lower", "stabilizer", "trapezius_lower_scapular_control", S)),
    source_refs=("overhead_press_review", "openstax_upper_limb"), pattern="vertical_push",
)

HORIZONTAL_ROW = pair_template(
    summary="tracció horitzontal amb extensió d'espatlla i flexió de colze",
    setup="Estabilitza els suports i comença amb els braços orientats cap a la resistència.",
    execution="Acosta la resistència estenent l'espatlla i flexionant el colze; retorna fins a la posició inicial.",
    cues="Inicia des de l'espatlla, mantén el tronc estable i evita elevar les espatlles.",
    outbound_actions=("shoulder_extension", "elbow_flexion"), return_actions=("shoulder_flexion", "elbow_extension"),
    muscles=(("latissimus_dorsi", "primary", "latissimus_dorsi__shoulder_extension__general", A), ("biceps_brachii", "secondary", "biceps_brachii__elbow_flexion__general", A), ("trapezius_middle", "stabilizer", "trapezius_middle_scapular_control", S)),
    source_refs=("ace_cable_exercises", "openstax_upper_limb"), pattern="horizontal_pull",
)

REAR_PULL = pair_template(
    summary="tracció orientada a l'abducció horitzontal de l'espatlla i al control escapular",
    setup="Estabilitza el tronc i situa els braços davant del cos amb la resistència alineada.",
    execution="Separa els braços en abducció horitzontal i retorna cap a adducció horitzontal lentament.",
    cues="Conserva el coll relaxat i evita convertir el gest en una extensió del tronc.",
    outbound_actions=("shoulder_horizontal_abduction",), return_actions=("shoulder_horizontal_adduction",),
    muscles=(("deltoid_posterior", "primary", "deltoid_posterior__shoulder_horizontal_abduction__general", A), ("trapezius_middle", "stabilizer", "trapezius_middle_scapular_control", S)),
    source_refs=("ace_shoulder_study", "openstax_upper_limb"), pattern="horizontal_pull",
)

VERTICAL_PULL = pair_template(
    summary="tracció vertical amb adducció d'espatlla i flexió de colze",
    setup="Assegura la presa i organitza el tronc sota o davant del punt de resistència.",
    execution="Acosta el cos o la resistència mitjançant adducció d'espatlla i flexió de colze; retorna controladament.",
    cues="Inicia el moviment des de l'espatlla, evita balancejar el tronc i conserva una presa estable.",
    outbound_actions=("shoulder_adduction", "elbow_flexion"), return_actions=("shoulder_abduction", "elbow_extension"),
    muscles=(("latissimus_dorsi", "primary", "latissimus_dorsi__shoulder_adduction__general", A), ("biceps_brachii", "secondary", "biceps_brachii__elbow_flexion__general", A), ("trapezius_lower", "stabilizer", "trapezius_lower_scapular_control", S)),
    source_refs=("ace_cable_exercises", "openstax_upper_limb"), pattern="vertical_pull",
)

ELBOW_FLEXION = pair_template(
    summary="flexió de colze en cadena oberta amb control del retorn",
    setup="Estabilitza el braç i alinea la resistència amb el moviment del colze.",
    execution="Flexiona el colze sense desplaçar el tronc i torna a l'extensió de forma controlada.",
    cues="Evita l'impuls i mantén el canell en una posició estable.",
    outbound_actions=("elbow_flexion",), return_actions=("elbow_extension",),
    muscles=(("biceps_brachii", "primary", "biceps_brachii__elbow_flexion__general", A),),
    source_refs=("acsm_resistance_2026", "openstax_upper_limb"), pattern="other",
)

ELBOW_EXTENSION = pair_template(
    summary="extensió de colze en cadena oberta amb braç estabilitzat",
    setup="Situa el braç i la resistència perquè el colze es pugui estendre sense moviment del tronc.",
    execution="Estén el colze contra la resistència i retorna a flexió lentament.",
    cues="Mantén el braç quiet i evita accelerar el retorn.",
    outbound_actions=("elbow_extension",), return_actions=("elbow_flexion",),
    muscles=(("triceps_brachii", "primary", "triceps_brachii__elbow_extension__general", A),),
    source_refs=("acsm_resistance_2026", "openstax_upper_limb"), pattern="other",
)

SHOULDER_ABDUCTION = pair_template(
    summary="abducció d'espatlla en cadena oberta amb trajectòria controlada",
    setup="Estabilitza el tronc i situa la resistència al costat del cos.",
    execution="Eleva el braç en abducció fins al rang controlat i baixa'l en adducció.",
    cues="Evita inclinar el tronc o encongir les espatlles per guanyar rang.",
    outbound_actions=("shoulder_abduction",), return_actions=("shoulder_adduction",),
    muscles=(("deltoid_middle", "primary", "deltoid_middle__shoulder_abduction__general", A), ("supraspinatus", "stabilizer", "supraspinatus_shoulder_centering", S)),
    source_refs=("ace_shoulder_study", "openstax_upper_limb"), pattern="other",
)

SHOULDER_EXTERNAL_ROTATION = pair_template(
    summary="rotació externa d'espatlla amb colze i tronc estabilitzats",
    setup="Alinea la resistència, mantén el colze en la posició definida i controla l'escàpula.",
    execution="Rota externament l'espatlla i torna cap a rotació interna de manera lenta.",
    cues="No separis el colze ni giris el tronc per ampliar el recorregut.",
    outbound_actions=("shoulder_external_rotation",), return_actions=("shoulder_internal_rotation",),
    muscles=(("infraspinatus", "primary", "infraspinatus__shoulder_external_rotation__general", A),),
    source_refs=("ace_applied_science", "openstax_upper_limb"), pattern="other",
)

TRUNK_FLEXION = pair_template(
    summary="flexió del tronc amb pelvis i extremitats estabilitzades segons la variant",
    setup="Organitza els punts de suport i defineix la posició inicial del tronc.",
    execution="Flexiona el tronc fins al rang controlat i retorna cap a extensió sense impuls.",
    cues="Inicia el moviment al tronc, mantén la respiració fluida i evita estirar del coll.",
    outbound_actions=("trunk_flexion",), return_actions=("trunk_extension",),
    muscles=(("rectus_abdominis", "primary", "rectus_abdominis__trunk_flexion__general", A),),
    source_refs=("core_prescription_review", "openstax_axial"), pattern="trunk_control",
)

TRUNK_EXTENSION = pair_template(
    summary="extensió del tronc amb control de la tornada a flexió",
    setup="Estabilitza la pelvis i col·loca el tronc amb espai per moure's en el rang definit.",
    execution="Estén el tronc fins a la posició acordada i retorna cap a flexió de forma controlada.",
    cues="Allarga la columna i evita buscar rang amb un moviment brusc.",
    outbound_actions=("trunk_extension",), return_actions=("trunk_flexion",),
    muscles=(("erector_spinae", "primary", "erector_spinae__trunk_extension__general", A),),
    source_refs=("core_prescription_review", "openstax_axial"), pattern="trunk_control",
)

TRUNK_ROTATION = pair_template(
    summary="rotació axial del tronc contra una resistència o desplaçament controlat",
    setup="Estabilitza la pelvis i orienta el punt de resistència respecte del tronc.",
    execution="Rota el tronc cap al costat de treball i torna a la posició inicial sense accelerar.",
    cues="Mantén la pelvis estable i reparteix el moviment pel tronc sense estirar amb els braços.",
    outbound_actions=("trunk_axial_rotation",), return_actions=("trunk_axial_rotation",),
    muscles=(("external_oblique", "primary", "external_oblique__trunk_axial_rotation__general", A),),
    source_refs=("core_prescription_review", "openstax_axial"), pattern="trunk_control",
)
TRUNK_ROTATION["phases"][1]["intent"] = "produce"
TRUNK_ROTATION["phases"][1]["phase_type"] = "active"
TRUNK_ROTATION["phases"][1]["description"] = "Es produeix una rotació axial controlada en el sentit de retorn."
for _role in TRUNK_ROTATION["phases"][1]["muscles"]:
    _role["contraction"] = "concentric"

TRUNK_HOLD = hold_template(
    summary="control isomètric del tronc davant d'una demanda postural",
    setup="Organitza els punts de suport i situa tronc i pelvis en la posició definida.",
    execution="Mantén la posició sense perdre l'alineació ni bloquejar la respiració.",
    cues="Respira, conserva la pelvis i finalitza quan la posició deixi de ser estable.",
    muscles=(("transversus_abdominis", "stabilizer", "transversus_abdominis_trunk_postural", S), ("multifidus", "stabilizer", "multifidus_spine_centering", S)),
    source_refs=("core_prescription_review", "core_stability_critical_review"),
)

LATERAL_TRUNK_HOLD = hold_template(
    summary="manteniment lateral del tronc amb control lumbopèlvic",
    setup="Alinea els punts de suport i situa el cos en el pla lateral definit.",
    execution="Mantén el tronc estable sense deixar caure ni girar la pelvis.",
    cues="Allarga el cos, respira i conserva l'espatlla de suport organitzada.",
    muscles=(("quadratus_lumborum", "primary", "quadratus_lumborum__trunk_lateral_flexion__general", A), ("transversus_abdominis", "stabilizer", "transversus_abdominis_trunk_postural", S)),
    source_refs=("core_prescription_review", "openstax_axial"),
)

JUMP = {
    "summary": "salt amb producció ràpida de força i recepció controlada",
    "setup": "Organitza els peus, l'espai de caiguda i qualsevol obstacle abans d'iniciar el salt.",
    "execution": "Carrega les extremitats inferiors, impulsa't amb rapidesa i rep la caiguda flexionant maluc, genolls i turmells.",
    "cues": "Salta amb intenció, aterra en silenci i estabilitza abans de repetir.",
    "movement_pattern": "locomotion",
    "source_refs": ["weightlifting_meta_analysis", "unilateral_meta_analysis"],
    "phases": [
        action_phase("propulsion", "Propulsió", "produce", "El cos s'impulsa mitjançant extensió ràpida de maluc i genoll i flexió plantar.", ("hip_extension", "knee_extension", "ankle_plantarflexion"), (("gluteus_maximus", "primary", "gluteus_maximus__hip_extension__general", A, "concentric"), ("vastus_lateralis", "primary", "vastus_lateralis__knee_extension__general", A, "concentric"), ("gastrocnemius", "secondary", "gastrocnemius__ankle_plantarflexion__general", A, "concentric"))),
        action_phase("landing", "Recepció", "control", "La recepció es frena amb flexió coordinada de maluc i genoll i dorsiflexió.", ("hip_flexion", "knee_flexion", "ankle_dorsiflexion"), (("gluteus_maximus", "primary", "gluteus_maximus__hip_extension__general", A, "eccentric"), ("vastus_lateralis", "primary", "vastus_lateralis__knee_extension__general", A, "eccentric"), ("gastrocnemius", "secondary", "gastrocnemius__ankle_plantarflexion__general", A, "eccentric")), "recovery"),
    ],
}
