# Catàleg privat i explicable d'exercicis d'IA Train

> **Estat:** base privada extensa implementada, importada i revisable en `draft`
> **Actualitzat:** 20 d'agost de 2026
> **Mòdul:** `iatrain_exercises`
> **Abast actual:** exercicis de preparació física propietat d'una persona, connectats al coneixement anatòmic, cinemàtic i biomecànic.
> **Fora d'abast actual:** catàleg professional comú, compartició entre entrenadors, prescripció de sèries i càrregues, planificació de rutines, observacions del tracker i connexió amb elements tècnics.

## 1. Objectiu

La capa permet que cada entrenador construeixi un catàleg propi, consultable i ampliable sense copiar el graf professional. Un exercici privat pot referenciar accions articulars, músculs i funcions biomecàniques compartides i conservar una explicació del perquè de cada connexió.

L'arquitectura separa quatre responsabilitats:

```text
Coneixement professional comú (només lectura des del catàleg)
├── iatrain_motion: anatomia i cinemàtica
└── iatrain_biomechanics: funcions musculars i estabilització
             ↓
Catàleg privat de cada entrenador
└── iatrain_exercises: exercicis, revisions, fases i connexions
             ↓ futur
Prescripció i planificació
└── rutines, sessions, dosificació i adaptació a l'esportista
```

`iatrain_exercises` és un mòdul intern del domini IA Train. Comparteix projecte i PostgreSQL amb la resta; la separació en app existeix per mantenir fronteres de models, govern, migracions i proves.

## 2. Decisió de propietat

La versió inicial admet exclusivament `ExerciseCatalog.Kind.PERSONAL`:

- cada catàleg té exactament una `Person` propietària;
- exercicis, revisions, fases i propostes pertanyen a aquest abast;
- les consultes del motor exigeixen el propietari i mai barregen catàlegs;
- encara no existeixen catàlegs d'organització ni un catàleg professional compartit;
- la futura capa comuna s'haurà d'afegir com un origen explícit que el catàleg privat pugui estendre, no convertint registres privats en globals silenciosament.

La fusió d'identitats trasllada els catàlegs i l'autoria. Si dues identitats tenen catàlegs amb el mateix codi o nom, es preserven tots dos amb una identitat desambiguada.

## 3. Model d'informació

### 3.1. Identitat i versió

- `ExerciseCatalog`: frontera privada i propietari.
- `Exercise`: identitat estable dins del catàleg.
- `Exercise.Kind.FAMILY`: família conceptual, per exemple `hip_thrust`.
- `Exercise.Kind.VARIANT`: forma executable, per exemple `barbell_hip_thrust`; sempre depèn d'una família del mateix catàleg.
- `ExerciseRevision`: descripció versionada de la variant. Inclou modalitat, patró motriu, tipus d'execució, dificultat, lateralitat, cadena cinètica, preparació, execució, consignes, seguretat, material, autoria i procedència.

Només una revisió per exercici pot estar validada alhora. Una revisió validada no es modifica: una correcció crea una revisió superior amb `supersedes`.

### 3.2. Fases i cinemàtica

`ExercisePhase` conserva ordre, tipus, intenció i descripció observable. Les intencions són:

- `produce`: produir el moviment;
- `assist`: assistir-lo;
- `control`: frenar o controlar el moviment;
- `hold`: mantenir una posició;
- `reposition`: tornar o reorganitzar la posició sense atribuir-hi un estímul principal.

`ExercisePhaseAction` connecta una fase amb un `MotionConcept(kind=joint_action)`. Conserva rol principal o de suport, lateralitat aplicada, justificació, procedència i estat de verificació (`confirmed`, `inferred` o `pending`).

Les fases no són nodes del graf professional. Són components ordenats d'una revisió privada.

### 3.3. Biomecànica explicable

`ExercisePhaseMuscleRole` connecta una fase amb un múscul i exigeix exactament una base:

- `MuscleActionFunction`, per a contribució a una acció;
- `MuscleStabilizationFunction`, per a control o estabilització.

El rol pot ser `primary`, `secondary` o `stabilizer`. La contracció esperada pot ser concèntrica, excèntrica, isomètrica, variable o indeterminada. No es tracta com una propietat fixa del múscul: queda lligada a la fase, la intenció i la funció biomecànica.

Camí explicatiu mínim:

```text
exercici → fase → intenció → acció observada
                        ↘ múscul → funció biomecànica → contracció esperada
```

La base declara una expectativa funcional, no activació muscular observada ni magnitud de força.

### 3.4. Informació pràctica

- `Equipment`: vocabulari de material dins del catàleg privat.
- `ExerciseEquipmentRequirement`: material necessari, opcional o substitutiu.
- `ExerciseObjective`: objectiu principal o secundari.
- `ExerciseConstraint`: requisit, precaució o limitació pràctica. No és una prescripció clínica.

Les sèries, repeticions, descans, intensitat i tempo no formen part de la identitat de l'exercici. S'afegiran a una capa posterior de prescripció.

## 4. Flux editorial i del LLM

El LLM no escriu directament dades validades. El flux previst i sostingut pels models és:

```text
petició de l'entrenador
→ resolució de família i variant / cerca de duplicats
→ creació o selecció d'una revisió draft
→ validador determinista de completesa
→ ExerciseGap per cada buit
→ ExerciseChangeProposal + ExerciseProposalItem
→ revisió humana
→ aplicació sobre models tipats
→ nova comprovació de completesa
→ validació editorial
```

`ExerciseGap` registra el requisit absent, la ubicació estructurada, la gravetat, qui l'ha detectat i si continua obert, té proposta o s'ha resolt.

`ExerciseChangeProposal` agrupa una proposta humana, del sistema o d'un LLM. `ExerciseProposalItem` conserva operació, destí, valor proposat, confiança, evidència i el buit que pretén resoldre. El JSON només és una zona de preparació: després d'aprovar-lo, la dada ha d'entrar al model tipat corresponent.

`refresh_revision_gaps()` executa l'esquema `exercise_completeness_v1`. Actualment comprova com a mínim:

- descripció, preparació, execució i consignes;
- almenys un objectiu;
- coherència del material necessari;
- almenys una fase clau;
- accions per a fases que produeixen, assisteixen o controlen moviment;
- base biomecànica de cada rol muscular;
- tipus correctes dels conceptes;
- estat validat de totes les dependències quan es vol validar la revisió.

## 5. Govern i dependències

Les revisions utilitzen `draft`, `validated` i `retired`.

- una revisió nova entra sempre en `draft`;
- el propietari —o un superusuari— governa el seu catàleg;
- validar exigeix completesa i dependències professionals validades;
- la transició crea un `KnowledgeEditorialEvent` amb snapshot;
- el detall d'una revisió validada queda bloquejat;
- un exercici o catàleg es desactiva o es retira, no s'esborra;
- una revisió d'exercici validada bloqueja la reobertura de les accions, músculs i funcions biomecàniques que la sostenen.

La mostra continua en `draft` perquè la base anatòmica i biomecànica prèvia també està pendent de revisió professional.

## 6. Mostra implementada

La llavor `private_exercise_examples_v1` crea per al propietari indicat:

| Component | Quantitat |
|---|---:|
| Catàlegs personals | 1 |
| Materials | 4 |
| Famílies | 6 |
| Variants executables | 6 |
| Revisions | 6 |
| Fases | 12 |
| Connexions i classificacions | 60 |

Les variants són:

| Variant | Cobertura representativa | Connexions principals |
|---|---|---|
| Hip thrust amb barra | càrrega externa, patró de frontissa, fases concèntrica/isomètrica/excèntrica | extensió/flexió de maluc, gluti major |
| Esquat amb pes corporal | multiarticular, cadena tancada, control excèntric i ascens | maluc, genoll, turmell, gluti major i vast lateral |
| Flexió de braços a terra | empenta superior en cadena tancada i estabilització escapular | colze, espatlla, tríceps, pectoral major i serrat anterior |
| Elevació bilateral de talons | patró dominant de turmell | flexió plantar/dorsal, gastrocnemi i soli |
| Planxa frontal sobre avantbraços | exercici isomètric sense acció angular principal | transvers abdominal i serrat anterior com a estabilitzadors |
| Rotació externa d'espatlla amb banda | cadena oberta, unilateral i resistència elàstica | rotació externa/interna i infraespinós |

La varietat és deliberada: mostra com representar exercicis dinàmics i isomètrics, amb i sense material, unilaterals i bilaterals, monoarticulars i multiarticulars, i rols de moviment i estabilització.

La llavor és idempotent i específica d'un usuari:

```powershell
python manage.py seed_private_exercise_examples --owner-username <usuari>
```

No s'ha d'executar sense haver sembrat abans `seed_motion_vocabulary` i `seed_functional_biomechanics`.

## 7. Recuperació per al motor de suggeriments

`build_exercise_context()` exigeix un propietari i, per defecte, només retorna revisions validades. Permet filtrar per accions, músculs i objectius i retorna una projecció amb:

- exercici, família, versió i classificació;
- fases, accions i intencions;
- rols musculars i base biomecànica;
- material, objectius i restriccions;
- `explanation_paths` preparats per justificar una selecció;
- política explícita de privacitat, estat editorial i inferència muscular.

En treball editorial es pot usar `include_drafts=True`. Un motor productiu no ho ha de fer.

## 8. Protocol obligatori per ampliar el catàleg

Aquest apartat és la referència principal per a un agent futur que hagi de crear una bateria gran d'exercicis.

1. **Treballar sempre dins d'un propietari.** No crear dades sense `ExerciseCatalog` personal ni inventar un catàleg professional comú.
2. **Buscar família i variant abans de crear.** Mateix patró no significa mateixa variant; canvi de material, suport o lateralitat pot justificar una variant.
3. **No posar contingut descriptiu a `Exercise`.** La identitat és estable; la descripció executable viu a `ExerciseRevision`.
4. **Crear tot en `draft`.** Usar procedència amb llavor, importació, autor i estat de revisió.
5. **Descriure fases observables i ordenades.** Una fase ha d'explicar què passa, no només dir «fase concèntrica».
6. **Connectar accions existents.** Cercar primer `MotionConcept`; no crear anatomia des del mòdul d'exercicis.
7. **Justificar cada múscul.** Enllaçar exactament una `MuscleActionFunction` o `MuscleStabilizationFunction`; no afegir músculs perquè siguin habituals en una llista informal.
8. **Derivar la contracció des de la fase.** `produce` sobre l'acció funcional pot sostenir concèntrica; `control` sobre l'acció oposada pot sostenir excèntrica; `hold` pot sostenir isomètrica. Si no és clar, usar `indeterminate`.
9. **Distingir material necessari i opcional.** `requires_equipment=True` exigeix almenys un enllaç `required`.
10. **Separar exercici i dosificació.** No fixar sèries o repeticions com a propietats universals.
11. **Registrar restriccions amb prudència.** Descriure condicions d'execució i limitacions del registre; no inventar diagnòstics ni contraindicacions clíniques.
12. **Executar completesa i auditoria.** No declarar la bateria coherent mentre hi hagi buits obligatoris.
13. **Provar idempotència i aïllament.** Repetir la llavor no ha de duplicar registres i un altre propietari no ha de recuperar-los.
14. **No validar automàticament.** La revisió professional i la confirmació del propietari són externes a la importació.

### Plantilla mínima per a cada variant

```text
família + variant
revision:
  modalitat, patró, dificultat, lateralitat, cadena i tipus d'execució
  descripció, setup, execució, cues i notes de seguretat
  material explícit
  objectiu principal i opcionals secundaris
  requisits o limitacions pràctiques
phases[]:
  ordre, codi, nom, tipus, intenció, descripció i fase clau
  actions[]: MotionConcept + rol + lateralitat + justificació
  muscles[]: MotionConcept + rol + funció biomecànica + contracció esperada + justificació
provenance:
  origen, versió de llavor/importació i revisió requerida
```

### Criteri per afegir coneixement que falta

Si un exercici necessita una acció, múscul o funció biomecànica que no existeix:

1. registrar el buit;
2. no crear un substitut aproximat;
3. proposar l'ampliació a `iatrain_motion` o `iatrain_biomechanics`;
4. revisar i sembrar aquella capa amb les seves pròpies regles;
5. tornar a connectar l'exercici quan la dependència existeixi.

## 9. Passos futurs

Ordre recomanat:

1. revisar professionalment les sis mostres i les dependències en `draft`;
2. construir una interfície privada de consulta, alta i revisió de buits/propostes;
3. implementar resolució de duplicats i aplicació transaccional de propostes del LLM;
4. ampliar gradualment el catàleg privat seguint la plantilla, amb proves de cobertura per patrons i articulacions;
5. crear la capa de prescripció i rutines separada;
6. afegir perfil, objectius i restriccions de l'esportista per filtrar candidats;
7. implementar el catàleg professional comú només quan se'n defineixin autoria, distribució, herència, conflictes i versions;
8. connectar preparació física i tècnica mitjançant especificacions explícites, no arestes vagues.

## 10. Mapa del codi

- `iatrain_exercises/models.py`: catàleg, identitat, revisions, fases, connexions, buits i propostes.
- `iatrain_exercises/checks.py`: esquema i auditoria de completesa.
- `iatrain_exercises/completeness.py`: sincronització durable dels buits.
- `iatrain_exercises/editorial.py`: transicions, permisos i snapshots.
- `iatrain_exercises/reasoning.py`: projecció privada i explicable per al motor.
- `iatrain_exercises/dependencies.py`: protecció del coneixement professional consumit.
- `iatrain_exercises/identity.py`: fusió segura de propietaris i autoria.
- `iatrain_exercises/vocabulary.py`: sis exemples canònics per copiar com a patró estructural.
- `iatrain_exercises/management/commands/seed_private_exercise_examples.py`: llavor privada idempotent.
- `iatrain_exercises/admin.py`: gestió inicial consultable des de Django admin.
- `iatrain_exercises/tests/`: privacitat, coherència, propostes, identitat, raonament i idempotència.

## 11. Estat honest

La capa està preparada per registrar i consultar exercicis explicables de manera coherent. No és encara un motor de rutines ni un catàleg professional validat. Les sis mostres són exemples privats en `draft`, dissenyats perquè una persona o agent pugui ampliar la bateria sense perdre propietat, traçabilitat ni connexió amb el coneixement base.

## 12. Ampliació privada `private_exercise_catalog_v2_2026_08_20`

El 20 d'agost de 2026 s'ha afegit una ampliació declarativa de **292 variants noves** en deu lots. S'ha importat al mateix catàleg personal de `guillemmerino`, conservant les sis mostres anteriors. El resultat a PostgreSQL és:

| Component | Quantitat |
|---|---:|
| Catàlegs personals del propietari | 1 |
| Famílies | 92 |
| Variants executables | 298 |
| Revisions | 298 |
| Revisions en `draft` | 298 |
| Fases temporals | 577 |
| Accions articulars de fase | 928 |
| Rols musculars amb una base exacta | 1.207 |
| Buits obligatoris oberts | 0 |
| Conflictes en l'execució final | 0 |

No s'ha creat cap catàleg d'organització, compartit o professional. Tampoc s'ha canviat cap model ni vocabulari controlat: els tipus existents ja representaven la cobertura requerida i, per tant, no ha calgut cap migració nova.

### 12.1. Matriu de cobertura final

Els recomptes inclouen les sis mostres compatibles. Una variant pot tenir més d'un objectiu i més d'un material; per això aquestes columnes no sumen 298.

| Dimensió | Recompte |
|---|---|
| Patró | `squat` 57; `hinge` 36; `horizontal_push` 33; `vertical_push` 17; `horizontal_pull` 22; `vertical_pull` 8; `ankle_dominant` 16; `trunk_control` 34; `locomotion` 14; `other` 61 |
| Modalitat | força 199; control motor 46; potència 18; mobilitat 15; escalfament 11; resistència muscular 9 |
| Dificultat | inicial 128; intermèdia 105; avançada 65 |
| Lateralitat de les 292 noves | bilateral 194; unilateral 74; alternant 24 |
| Cadena de les 292 noves | tancada 161; oberta 114; mixta 17 |
| Execució de les 292 noves | dinàmica 273; isomètrica 16; mixta 3 |
| Objectiu | força general 175; força màxima potencial 23; hipertròfia 1; potència 18; resistència muscular 24; control motor 292; mobilitat 21; preparació 11 |

L'objectiu de control motor és secundari en moltes variants: indica que la descripció exigeix trajectòria observable, no que totes siguin exercicis primaris de control motor. Igualment, «força màxima» descriu potencial funcional de la variant, no prescriu càrrega, repeticions ni intensitat.

Materials enllaçats: `barbell` 32; `dumbbell` 45; `kettlebell` 12; `weight_plate` 6; `trap_bar` 1; `bench` 47; `box` 9; `step_platform` 6; `wall` 14; `mat` 33; `elastic_band` 25; `cable_machine` 28; `smith_machine` 8; `leg_press_machine` 4; `hack_squat_machine` 1; `leg_extension_machine` 2; `leg_curl_machine` 3; `resistance_machine` 14; `roman_chair` 2; `suspension_trainer` 8; `pull_up_bar` 4; `landmine` 5; `stability_ball` 8; `medicine_ball` 4; `slider` 1.

Quantitats per família:

```text
ankle_mobility=3; ankle_warm_up=1; band_chest_press=1; band_overhead_press_family=1
band_row=2; bench_dip=2; bench_press=6; bird_dog=2; box_jump_family=3; box_squat=3
bulgarian_split_squat=3; cable_chest_press=2; cable_overhead_press_family=1; cable_row=3
calf_raise=7; copenhagen_hold=2; dead_bug=2; deadlift=6; decline_press=1; dip=2
dynamic_warm_up=3; elbow_curl=11; explosive_push_up=2; face_pull=2; floor_press=3
front_plank=7; glute_bridge=5; good_morning=3; hack_squat=1; handstand_push_up=1
hip_abduction=4; hip_adduction=3; hip_hinge_drill=2; hip_mobility=4; hip_thrust=6
hip_warm_up=1; hollow_hold=1; horizontal_jump=1; incline_press=2; inverted_row=3
knee_extension=4; knee_flexion=6; landmine_press=2; lateral_jump=1; lateral_lunge_family=2
lateral_raise=6; lat_pulldown=3; leg_press=3; lunge=6; lying_triceps_extension=2
machine_chest_press_family=2; machine_shoulder_press_family=1; medicine_ball_press=2
overhead_press=9; overhead_triceps_extension=3; pike_push_up_family=2; pogo_jump=2
preacher_curl=1; pull_up=5; push_up=12; rack_pull=2; rear_fly=3; romanian_deadlift=5
row=5; seated_calf_raise=2; shoulder_external_rotation=6; shoulder_mobility=2
shoulder_warm_up=2; side_plank=3; single_leg_glute_bridge_family=1; single_leg_hinge=4
single_leg_hip_thrust_family=1; single_leg_jump=3; single_leg_squat=3; sit_to_stand=2
split_jump=1; split_squat=4; squat=17; squat_hold=1; squat_mobility=2; step_down=1
step_up=3; supported_row=2; suspension_row=2; tibialis_raise=3; triceps_extension=4
trunk_extension=4; trunk_flexion=6; trunk_mobility=3; trunk_rotation=4; vertical_jump=3
wall_sit=2
```

### 12.2. Criteris d'inclusió i exclusió

S'han inclòs variants quan almenys una diferència executable és observable: material o direcció de resistència, suport, lateralitat, cadena, orientació corporal, demanda d'estabilització o fase temporal pròpia. Un simple canvi de sèries, repeticions, descans, tempo o càrrega no crea una variant. Les regressions i progressions només s'han separat quan canvia realment el suport o l'execució, com flexió a la paret, sobre banc, a terra o en suspensió.

Cada variant inclosa té descripció pròpia, preparació, execució, consignes, nota pràctica de seguretat, objectiu principal, fases, accions i almenys un rol muscular. Els rols només utilitzen funcions professionals existents; els estabilitzadors s'han mantingut isomètrics o indeterminats i cap múscul s'ha descrit com a concèntric o excèntric de manera fixa.

S'han exclòs:

- sinònims, marques comercials i duplicats semàntics;
- canvis que són només dosificació;
- exercicis que requerien inventar accions, músculs o funcions;
- afirmacions d'activació quantitativa no observada;
- diagnòstics, tractaments, contraindicacions o promeses de prevenció;
- variants en què la base professional no permetia una explicació mínima segura.

### 12.3. Fonts i procedència

Cada revisió, fase, acció i rol importat conserva a `provenance` la versió, lot, URL, tipus de font, data de consulta (`2026-08-20`), justificació i estat `owner_review_required`. El registre complet és a `iatrain_exercises/catalog_data/v2/metadata.py`.

| Grup | Fonts principals |
|---|---|
| Selecció i objectius de força | [ACSM 2026](https://pubmed.ncbi.nlm.nih.gov/41843416/), [ACSM 2002](https://pubmed.ncbi.nlm.nih.gov/11828249/), [WHO 2020](https://iris.who.int/bitstream/handle/10665/336656/9789240015128-eng.pdf) |
| Esquat i unilateral | [revisió biomecànica d'esquat](https://pmc.ncbi.nlm.nih.gov/articles/PMC10987311/), [metanàlisi unilateral/bilateral](https://pmc.ncbi.nlm.nih.gov/articles/PMC9331349/) |
| Frontissa i pes mort | [revisió sistemàtica del pes mort](https://pmc.ncbi.nlm.nih.gov/articles/PMC7046193/) |
| Empenta horitzontal | [revisió de press de banca](https://pmc.ncbi.nlm.nih.gov/articles/PMC5295722/), [cinemàtica de pit i politja](https://pmc.ncbi.nlm.nih.gov/articles/PMC8877248/) |
| Empenta vertical i potència | [derivats de press d'halterofília](https://pubmed.ncbi.nlm.nih.gov/30924081/), [derivats de tracció](https://pubmed.ncbi.nlm.nih.gov/25689955/), [metanàlisi d'halterofília i pliometria](https://pubmed.ncbi.nlm.nih.gov/35025093/) |
| Tronc | [prescripció de control del tronc](https://pmc.ncbi.nlm.nih.gov/articles/PMC3806181/), [revisió crítica d'estabilitat](https://pmc.ncbi.nlm.nih.gov/articles/PMC4647147/) |
| Mobilitat i escalfament | [metanàlisi de força i rang](https://pubmed.ncbi.nlm.nih.gov/36622555/), [consens d'estiraments](https://pmc.ncbi.nlm.nih.gov/articles/PMC12305623/) |
| Recurs professional contrastat | [ACE Applied Exercise Science](https://www.acefitness.org/academy/AcademyElitePDFs/ESS-AES_Download_Final.pdf), [ACE cable exercises](https://www.acefitness.org/cp/pdfs/CertifiedNews/AugSept09Cert.pdf), [ACE shoulder study](https://www.acefitness.org/certifiednews/images/article/pdfs/ACEShoulderStudy.pdf) |
| Anatomia governada existent | [OpenStax extremitat inferior](https://openstax.org/books/anatomy-and-physiology-2e/pages/11-6-appendicular-muscles-of-the-pelvic-girdle-and-lower-limbs), [extremitat superior](https://openstax.org/books/anatomy-and-physiology-2e/pages/11-5-muscles-of-the-pectoral-girdle-and-upper-limbs), [tronc](https://openstax.org/books/anatomy-and-physiology-2e/pages/11-4-axial-muscles-of-the-abdominal-wall-and-thorax) |

Les fonts orienten selecció, classificació i prudència interpretativa. Les descripcions del catàleg són originals i breus; no reprodueixen manuals ni biblioteques d'exercicis.

### 12.4. Cobertura anatòmica i biomecànica

La bateria enllaça 21 accions: maluc (flexió, extensió, abducció i adducció), genoll (flexió i extensió), turmell (flexió plantar i dorsal), espatlla (flexió, extensió, abducció, adducció, rotació interna/externa i adducció/abducció horitzontal), colze (flexió i extensió) i tronc (flexió, extensió i rotació axial).

Utilitza 26 músculs amb funcions professionals tipades. La cobertura principal inclou glutis, quàdriceps, isquiotibials, adductors, tríceps sural, tibial anterior, pectoral, dorsal ample, deltoides, manegot, bíceps, tríceps, trapezis, serrat i musculatura global/local del tronc. La repetició d'un múscul a moltes variants no és una afirmació d'activació mesurada: és un camí explicatiu privat `fase → intenció → funció`.

### 12.5. Buits professionals registrats

`PROFESSIONAL_GAPS` enregistra sis buits `pending` sense ampliar silenciosament les capes comunes:

1. pronació i supinació de l'avantbraç, i les funcions musculars associades;
2. accions dels dits i musculatura intrínseca del peu;
3. funcions estabilitzadores tipades per a tots els músculs escapulars disponibles;
4. funcions estabilitzadores cervicals;
5. model complet de presa, dits, canell i avantbraç;
6. accions suficients per explicar fases de marxa i exercicis de transport carregat.

Aquests buits bloquegen, entre altres, `pronation_curl`, `short_foot`, una sèrie isomètrica cervical completa, `wrist_roller`, `farmers_carry` i `suitcase_carry`. No s'han substituït per conceptes aproximats.

### 12.6. Importador idempotent i protecció editorial

La comanda és:

```powershell
python manage.py import_private_exercise_catalog --owner-username guillemmerino
```

També accepta `--batch 04_lower_accessory` repetible i `--coverage-only`. Abans de crear valida vocabularis, referències, duplicats exactes, col·lisions de codi i col·lisions de nom normalitzat. Cada variant s'importa en una transacció independent, de manera que la comanda es pot reprendre després d'un error.

L'empremta `managed_fingerprint` cobreix revisió, material, objectius, restriccions, fases, accions, rols, justificacions i estats de verificació. Només se sincronitza una revisió si:

- pertany exactament a `private_exercise_catalog_v2_2026_08_20`;
- continua en `draft`;
- el contingut actual coincideix amb l'última empremta importada.

Una revisió validada s'omet. Una revisió editada per l'entrenador es registra com a conflicte i no es toca. L'execució completa repetida ha informat `unchanged_variants=292`, `created=0`, `updated=0`, `conflicts=0` i `gaps=0`.

### 12.7. Procediment exacte per continuar

1. Llegir aquest document i `catalog_data/v2/common.py`, `templates.py`, `metadata.py` i el lot del patró que es vol ampliar.
2. Executar `import_private_exercise_catalog --owner-username guillemmerino --coverage-only` i triar la dimensió infrarepresentada.
3. Afegir una font al registre si el grup no queda cobert; conservar URL, tipus, data i justificació.
4. Afegir entre 25 i 50 variants a un lot nou o a una versió nova. No reutilitzar codis o noms, ni crear una variant per un canvi de dosificació.
5. Utilitzar només plantilles amb accions i funcions existents. Si falta coneixement professional, afegir-lo a `PROFESSIONAL_GAPS`, excloure la variant i obrir el treball editorial a la capa corresponent.
6. Executar primer el lot concret i comprovar `gaps=0`, `conflicts=0` i `audit_issues=0`.
7. Repetir el mateix lot: totes les variants han d'aparèixer a `skipped.unchanged_variants`.
8. Executar la importació completa, les auditories amb esborranys i les proves dels tres mòduls.
9. Actualitzar els recomptes d'aquest document des de PostgreSQL; no declarar mai validació professional automàtica.

### 12.8. Limitacions actuals

- Les connexions musculars són inferències funcionals revisables, no EMG ni magnituds de força.
- La lateralitat professional no diferencia encara totes les direccions de rotació del tronc.
- Les variants de potència descriuen fases, però la qualitat de recepció i la velocitat requereixen observació externa.
- La modalitat és una classificació funcional; la dosificació que determina l'adaptació continua fora del catàleg.
- No hi ha encara una interfície de revisió massiva, resolució de conflictes o comparació de versions.
- La base és extensa però no exhaustiva i continua pendent de revisió de `guillemmerino` i de validació professional de les dependències.

### 12.9. Verificació executada

| Comprovació | Resultat |
|---|---|
| `python manage.py migrate` | cap migració pendent |
| `python manage.py makemigrations --check --dry-run` | cap canvi de model detectat |
| `python manage.py check` | 0 incidències |
| `audit_motion_graph(include_drafts=True)` | 0 incidències |
| `audit_biomechanics(include_drafts=True)` | 0 incidències |
| `audit_exercise_catalog(..., include_drafts=True)` | 0 incidències |
| `refresh_revision_gaps()` sobre 298 revisions | 0 buits oberts |
| proves específiques de l'importador | 2/2 correctes |
| regressió conjunta `iatrain_exercises`, `iatrain_motion`, `iatrain_biomechanics`, `iatrain` | 128/128 correctes |

La regressió conjunta inclou compatibilitat amb la llavor de sis mostres, privacitat, identitat, editorial, raonament, esquelet i vocabularis professionals.

## 13. Mapa de l'ampliació

- `iatrain_exercises/catalog_data/v2/metadata.py`: versió, 21 fonts, 26 materials i sis buits professionals.
- `iatrain_exercises/catalog_data/v2/templates.py`: plantilles de fases, accions i bases musculars.
- `iatrain_exercises/catalog_data/v2/batch_*.py`: deu lots per patró.
- `iatrain_exercises/catalog_importer.py`: validació, matriu, col·lisions, sincronització i auditoria.
- `iatrain_exercises/management/commands/import_private_exercise_catalog.py`: interfície de comanda.
- `iatrain_exercises/tests/test_catalog_importer.py`: cobertura, idempotència, privacitat i protecció d'edicions.

## 14. Conclusió editorial

El resultat és una base privada extensa, coherent i consultable en `draft`. **No és un catàleg professionalment validat**, no és una prescripció i no s'ha de presentar com a tal. La publicació o validació de cada revisió continua requerint revisió humana i dependències professionals validades.
