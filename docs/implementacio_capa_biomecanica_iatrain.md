# Implementació de la capa biomecànica funcional d'IA Train

> **Estat:** implementació funcional completa en `draft`, pendent de revisió professional
> **Actualitzat:** 20 d'agost de 2026
> **Abast:** musculatura anatòmica, funcions musculars qualitatives, estabilització, context, evidència, raonament de contracció i projecció visual.
> **No inclou:** activació muscular observada, EMG, forces internes, braços de moment quantitatius ni simulació musculoesquelètica. La capa privada d'exercicis ja està implementada separadament a [`implementacio_cataleg_privat_exercicis_iatrain.md`](implementacio_cataleg_privat_exercicis_iatrain.md).

## 1. Objectiu

La capa biomecànica permet passar de «quina acció articular existeix?» a «quines estructures musculars hi poden contribuir, en quin context i amb quines limitacions?». Està preparada perquè les futures capes privades d'exercicis dels entrenadors puguin referenciar coneixement professional compartit sense copiar-lo ni modificar-lo.

La divisió implementada és:

```text
iatrain_motion
├── anatomia: segments, articulacions, músculs i grups musculars
├── cinemàtica: accions, plans, eixos i angles canònics
└── esquelet canònic: instàncies mesurables versionades

iatrain_biomechanics
├── contextos biomecànics
├── funcions múscul → acció
├── funcions estabilitzadores
├── evidència i procedència
└── recuperació i inferència funcional

iatrain_exercises
└── exercicis i fases privats que referencien les capes professionals
```

Les dues apps viuen al mateix projecte i a la mateixa base PostgreSQL. La separació és de responsabilitat, govern, migracions i proves; no és un microservei ni una base física diferent.

## 2. Canvis anatòmics i cinemàtics

### 2.1. Nous tipus de node

`MotionConcept.Kind` incorpora:

- `muscle`;
- `muscle_group`.

Els músculs són conceptes anatòmics genèrics i parells quan correspon. No es creen ontologies duplicades esquerra/dreta; el costat concret s'aplicarà a l'esquelet, a una fase o a un exercici.

### 2.2. Noves relacions anatòmiques

`MotionRelation` incorpora:

- `member_of_muscle_group`: múscul → grup muscular;
- `spans_joint`: múscul → articulació que travessa funcionalment.

Les dues relacions tenen domini i rang validats. Una funció biomecànica no es pot validar si el múscul no pertany a cap grup o no declara que travessa l'articulació de l'acció.

### 2.3. Ampliació cinemàtica

El vocabulari `functional_anatomy_v2` afegeix els complexos cervical i escapulotoràcic i accions necessàries per descriure millor la preparació física:

- flexió, extensió, flexió lateral i rotació cervical;
- elevació, depressió, protracció, retracció i rotacions escapulars;
- abducció i adducció horitzontal d'espatlla;
- desviacions radial i cubital del canell.

No s'han introduït conceptes de contracció com si fossin accions articulars. `concentric`, `eccentric` i `isometric` són interpretacions d'una fase, no moviments anatòmics.

### 2.4. Esquelet canònic ampliat

L'esquema `iatrain_functional_skeleton / 1.0.0-draft` conté ara:

- 30 landmarks;
- 17 segments;
- 16 articulacions canòniques;
- 24 definicions angulars.

S'hi han incorporat el complex cervical i les dues interfícies escapulotoràciques, més components mesurables d'abducció-adducció d'espatlla i maluc, abducció-adducció horitzontal, desviació de canell i inversió-eversió.

No s'han definit rotacions axials de segments que continuen sent `long_axis_only`. Aquesta absència és intencionada: evita inventar graus de llibertat que l'esquelet actual no sosté.

## 3. Models biomecànics

### 3.1. `EvidenceReference`

Font bibliogràfica o ontològica reutilitzable. Conserva tipus, identificador, citació, URL, autoria i procedència. Les afirmacions validades necessiten evidència de suport o qualificació.

### 3.2. `BiomechanicalContext`

Descriu l'abast d'una afirmació:

- cadena oberta, tancada, ambdues o no especificada;
- condicions de càrrega estructurades;
- descripció i estat editorial;
- restriccions angulars opcionals en radians mitjançant `ContextAngleConstraint`.

La llavor crea context general, cadena oberta i cadena tancada. El context general no converteix una contribució qualitativa en una afirmació universal.

### 3.3. `MuscleActionFunction`

Uneix un múscul amb una acció articular i un context. Inclou:

- classe de contribució: `major`, `supporting`, `variable` o `unspecified`;
- afirmació textual explícita;
- condicions estructurades;
- limitacions;
- evidència;
- autoria, estat editorial, procedència i possible `supersedes`.

No desa `agonist` o `antagonist` com una propietat permanent. Aquest paper depèn de la tasca, la direcció, la càrrega i la fase.

### 3.4. `MuscleStabilizationFunction`

Representa contribucions que no són una acció angular simple:

- centratge articular;
- control segmentari;
- cocontracció;
- transferència de força;
- control postural.

Cada registre apunta exactament a una articulació o un segment i conserva les mateixes garanties editorials i d'evidència.

## 4. Contingut inicial

Després d'executar les llavors, el domini professional conté:

| Component | Quantitat |
|---|---:|
| Conceptes anatòmics-cinemàtics totals | 169 |
| Relacions anatòmiques-cinemàtiques totals | 360 |
| Músculs | 70 |
| Grups musculars | 31 |
| Accions articulars | 40 |
| Contextos biomecànics | 3 |
| Fonts estructurades | 4 |
| Funcions múscul → acció | 129 |
| Funcions estabilitzadores | 16 |

La cobertura funcional inclou extremitat inferior, tronc i coll, cintura escapular, espatlla, colze i canell. Es diferencien estructures que seria incorrecte agrupar, com els caps llarg i curt del bíceps femoral o les porcions del deltoide i del trapezi.

Tots els músculs sembrats:

- pertanyen almenys a un grup;
- declaren almenys una articulació travessada;
- tenen almenys una funció d'acció o estabilització;
- conserven font, procedència i limitacions;
- romanen en `draft` fins a revisió professional.

Les fonts inicials són Uberon com a correspondència ontològica i seccions anatòmiques d'OpenStax per extremitat inferior, extremitat superior i musculatura axial. Són punt de partida documental, no una validació automàtica de cada jerarquia funcional.

## 5. Govern i coherència

La nova app reutilitza els estats `draft`, `validated` i `retired`, però disposa de serveis editorials propis.

Per validar una funció:

1. múscul, acció i context han d'estar validats;
2. l'acció ha de tenir una única articulació validada;
3. el múscul ha de tenir una pertinença de grup validada;
4. el múscul ha de declarar que travessa l'articulació;
5. ha d'existir evidència de suport o qualificació;
6. la transició crea un `KnowledgeEditorialEvent` amb snapshot.

Les dependències es registren des de `iatrain_biomechanics` sense introduir imports inversos a `iatrain_motion`. Una funció validada bloqueja la reobertura dels conceptes i relacions professionals que la sostenen. La fusió de `Person` trasllada autoria i validació del domini biomecànic.

Les llavors són idempotents i només sincronitzen dades pròpies que continuen en `draft`:

```powershell
python manage.py seed_motion_vocabulary --author-username <usuari>
python manage.py seed_canonical_skeleton --author-username <usuari>
python manage.py seed_functional_biomechanics --author-username <usuari>
```

## 6. Raonament i recuperació

`build_biomechanics_context()` produeix un paquet estructurat per a l'LLM. Per defecte només retorna coneixement validat i declara explícitament que la base no observa activació muscular.

`infer_contraction_mode()` classifica una contracció funcional prevista com:

- `concentric`;
- `eccentric`;
- `isometric`;
- `indeterminate`.

La inferència exigeix una funció muscular, una acció de fase, una intenció —produir, assistir, controlar o mantenir— i que el múscul estigui declarat com a objectiu o actiu. Si falta aquesta informació, retorna `indeterminate`. Sempre adjunta limitacions sobre activació no observada, biarticularitat i canvis de braç de moment.

## 7. Visualització

El visor 3D disposa ara de tres dominis:

1. graf tècnic;
2. graf anatòmic-cinemàtic, que ja mostra músculs, grups i articulacions travessades;
3. graf biomecànic, que projecta contribucions a accions i estabilitzacions.

La projecció biomecànica és de consulta. El govern detallat d'afirmacions, contextos i evidència es fa des de l'administració Django, on es poden revisar totes les propietats sense simplificar-les a una aresta visual.

## 8. Límits professionals actuals

La base és funcionalment completa per començar a estructurar preparació física, però no s'ha de presentar encara com a coneixement professional validat. Falta:

- revisió per professionals d'anatomia, biomecànica i preparació física;
- fonts específiques per a afirmacions dependents de postura o qualificades com `variable`;
- rangs angulars contextuals revisats;
- mapatge del tracker i validació de les mesures reals;
- informació quantitativa de moment articular, potència, braç de moment i relació força-longitud-velocitat;
- observacions EMG quan siguin necessàries i legalment adequades;
- revisió professional de les connexions creades per la primera mostra privada d'exercicis;

Una base musculoesquelètica quantitativa futura necessitaria una `MusculoskeletalModelSchema` versionada amb insercions, trajectòries, paràmetres i convencions pròpies. No s'ha barrejat amb aquesta capa qualitativa.

## 9. Connexió implementada amb exercicis

La capa privada depèn de la professional, mai al revés. La implementació actual expressa:

```text
ExerciseRevision
└── ExercisePhase
    ├── acció articular professional
    ├── múscul o funció biomecànica professional
    ├── intenció: produir, controlar o mantenir
    ├── contracció prevista
    ├── prioritat i costat
    └── càrrega, material i indicacions privades
```

Això ja permet consultar exercicis privats per moviment o musculatura i explicar el perquè. Les mostres i el protocol d'ampliació es documenten a [`implementacio_cataleg_privat_exercicis_iatrain.md`](implementacio_cataleg_privat_exercicis_iatrain.md).

## 10. Mapa del codi

- `iatrain_biomechanics/models.py`: contextos, evidència i funcions musculars.
- `iatrain_biomechanics/checks.py`: auditories i invariants entre capes.
- `iatrain_biomechanics/editorial.py`: transicions i snapshots editorials.
- `iatrain_biomechanics/dependencies.py`: protecció de dependències d'anatomia i cinemàtica.
- `iatrain_biomechanics/identity.py`: fusió d'autoria i validació.
- `iatrain_biomechanics/reasoning.py`: recuperació i inferència de contracció.
- `iatrain_biomechanics/vocabulary.py`: llavor funcional revisable.
- `iatrain_biomechanics/management/commands/seed_functional_biomechanics.py`: importació idempotent.
- `iatrain_biomechanics/admin.py`: supervisió editorial.
- `iatrain_biomechanics/tests/`: contractes de dades, govern, identitat, llavor i raonament.
- `iatrain_motion/dependencies.py`: registre desacoblat de consumidors validats.
