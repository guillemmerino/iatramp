# IA Train: arquitectura del primer MVP

Aquest document és la font principal de context per continuar el desenvolupament d'`iatrain`. Descriu què existeix, quines regles protegeixen el domini i com fer créixer el model sense confondre identitat, coneixement expert, observacions i futures funcions d'IA.

## 1. Propòsit i abast actual

IA Train prepara una base professional per registrar contextos d'entrenament, observacions de gimnastes i coneixement tècnic de trampolí en forma de graf dirigit. El primer MVP és deliberadament sobri:

- ofereix models relacionals i una migració additiva;
- reutilitza identitat i permisos de `core`;
- permet representar nodes i relacions de coneixement amb estat editorial;
- permet observacions narratives lliures o vinculades al graf;
- conserva revisions d'observacions sense sobreescriure la traça anterior;
- exposa una entrada web de consulta amb estats buits coherents;
- ofereix administració Django per mantenir dades inicials.

No genera entrenaments, no consulta cap LLM, no conté encara un catàleg ampli i no necessita una base de dades grafal externa.

## 2. Frontera entre Core i IA Train

### Core és propietari de la identitat

`core` continua sent l'únic propietari de:

- `Person`: individu real, amb compte opcional;
- `Organization`: club, federació o altra organització;
- `Membership`: rol contextual dins d'una organització;
- `CoachAthleteRelation`: relació explícita entrenador–gimnasta, vigència i permisos.

`iatrain` referencia aquests models; no els replica i no dedueix permisos a partir del nom d'un rol. Ser entrenador en una `Membership` no concedeix automàticament accés a cap gimnasta.

### IA Train és propietari del domini d'entrenament

`iatrain` és propietari de:

- `TrainingContext`: marc temporal i organitzatiu de treball;
- `KnowledgeConcept`: node del coneixement professional;
- `KnowledgeRelation`: aresta dirigida entre nodes;
- `AthleteObservation`: afirmació narrativa, datada i versionable sobre un gimnasta.

La dependència permesa és `iatrain -> core`. No s'ha d'introduir la dependència inversa. `competicions_trampoli` tampoc no s'ha de convertir en font d'identitat o de permisos d'entrenament sense un projecte de vinculació de dades explícit.

## 3. Autorització

La capa de serveis d'`iatrain.services` reutilitza `CoachAthleteRelation` i les capacitats de Core:

- consultar observacions requereix `can_view_training=True`;
- registrar o revisar observacions requereix `can_edit_training=True`;
- la relació ha d'estar activa i dins de les dates de vigència;
- si el context té organització, la relació autoritzadora ha de tenir el mateix context organitzatiu segons la semàntica actual de Core;
- un compte sense `Person` activa no pot crear observacions, perquè no hi ha autoria professional traçable;
- una persona no obté permís d'escriptura sobre si mateixa pel simple fet de ser el mateix subjecte;
- el superusuari conserva l'excepció global de Core, però per crear observacions també necessita una `Person` activa com a autora.

Les funcions clau són:

- `accessible_athletes(user, permission=...)`;
- `can_consult_observations(user, athlete, ...)`;
- `can_record_observations(user, athlete, ...)`;
- `record_athlete_observation(...)`;
- `revise_athlete_observation(...)`.

Les vistes han d'aplicar aquests serveis o consultes equivalents centralitzades; no han d'inventar dreceres basades en membresies.

## 4. Contextos d'entrenament

`TrainingContext` delimita un espai de treball. Conté:

- nom i propòsit;
- disciplina o àmbit;
- organització opcional;
- entrenador responsable (`Person`);
- període de vigència;
- estat (`draft`, `active`, `closed`, `archived`);
- gimnastes associats amb una relació M2M;
- `metadata` per a extensions petites i documentades.

La M2M permet un context individual amb un sol gimnasta o un context compartit amb diversos gimnastes. Aquest MVP no crea un model de grup esportiu: encara no hi ha regles de composició, rols dins del grup ni cicle de vida que ho justifiquin. Si aquestes regles apareixen, cal introduir un model explícit o un `through` model en una migració posterior, no codificar grups opacs dins de `metadata`.

Una observació amb context només és coherent si el gimnasta està associat al context.

## 5. Graf de coneixement professional

### Nodes: KnowledgeConcept

Cada `KnowledgeConcept` és una unitat de significat professional. Exemples inicials de `kind`:

- `skill`: habilitat o element;
- `technical_component`: component tècnic;
- `error`: error observable;
- `exercise`: exercici o tasca;
- `quality`: qualitat o fortalesa;
- `risk`: risc;
- `goal`: objectiu.

`kind` és text extensible, no una enumeració tancada a base de dades. Els valors coneguts viuen com a constants de conveniència, però es poden afegir tipus nous sense redissenyar el graf. Cada node també té nom, descripció, disciplina, autoria, dates, estat editorial i `attributes` JSON.

`attributes` només serveix per propietats petites que no mereixen encara una columna estable. No s'hi han de guardar arestes, llistes d'identificadors ni informació essencial per autoritzar accés.

La combinació de nom sense distingir majúscules/minúscules, tipus i disciplina és única. Per representar matisos diferents cal usar noms o àmbits realment diferenciats, no duplicar el mateix node.

### Arestes: KnowledgeRelation

Cada `KnowledgeRelation` connecta un `source` amb un `target` i té direcció. Tipus inicials:

- `requires`: el node origen requereix el node destí;
- `progresses_to`: l'origen progressa cap al destí;
- `corrects`: l'origen ajuda a corregir el destí;
- `conditions`: l'origen condiciona el destí;
- `trains`: l'origen treballa o entrena el destí.

La frase exacta s'ha de llegir sempre amb la direcció `source --relation_type--> target`. Abans d'afegir una relació cal comprovar que aquesta lectura sigui clara.

No es permet:

- una aresta d'un node cap a si mateix;
- repetir exactament origen, destí i tipus;
- validar una relació si algun extrem està retirat.

`rationale` explica el criteri tècnic o la justificació. No substitueix evidència formal, però evita arestes opaques.

## 6. Estat editorial

Nodes i relacions tenen un cicle editorial:

- `draft`: proposta encara no acceptada com a coneixement compartit;
- `validated`: revisada i acceptada segons el procés professional vigent;
- `retired`: ja no s'ha d'usar per a registres nous, però es conserva per història.

Retirar és preferible a esborrar. Una observació antiga pot continuar apuntant a un concepte que després es retira. La UI futura haurà d'indicar aquesta situació sense reescriure el passat.

Encara no existeix un workflow de revisors, votacions ni publicació. No s'ha d'interpretar `validated` com una certificació científica automàtica: és una decisió editorial humana que haurà de tenir una política organitzativa explícita.

## 7. Observacions, evidència i incertesa

`AthleteObservation` registra una afirmació professional en un moment concret. Inclou:

- gimnasta;
- context opcional;
- concepte opcional;
- categoria;
- narració obligatòria;
- evidència textual opcional;
- estat de l'observació;
- confiança entre 0 i 1, opcional;
- intensitat entre 1 i 5, opcional;
- data observada;
- autoria;
- enllaç opcional `supersedes` a la versió anterior.

### Nota lliure i vinculació al graf

Una observació pot existir sense `KnowledgeConcept`. Això és important: el vocabulari no ha de créixer precipitadament per forçar cada frase dins d'un node.

Quan hi ha concepte i context, les disciplines han de coincidir, excepte quan un dels dos àmbits és `general`. El concepte aporta semàntica reutilitzable; la narració conserva el detall particular del gimnasta.

### Evidència

`evidence` descriu fets observables: repeticions, vídeo, condicions de la sessió o indicadors mesurats. No ha de contenir una justificació inventada per un model ni dades sensibles innecessàries.

### Incertesa

`confidence` és opcional. Només s'ha d'omplir si l'autor pot explicar què significa el valor. No és una probabilitat clínica ni una puntuació generada automàticament. `intensity` serveix quan una escala ordinal de 1 a 5 té sentit; no s'ha d'usar com a falsa precisió.

## 8. Versionat

Les revisions no modifiquen la fila anterior. `revise_athlete_observation` crea una observació nova i enllaça `supersedes` amb l'anterior. Això conserva autoria, data i text de cada versió.

Regles actuals:

- una revisió no pot canviar de gimnasta;
- la nova data no pot ser anterior a la versió substituïda;
- una observació només pot tenir una successora directa, perquè `supersedes` és 1:1;
- l'original no es marca automàticament com a `no_longer_current`: aquesta decisió de domini ha de ser explícita si es necessita.

Si en el futur calen branques, fusió de revisions o moderació editorial, cal un model de versions més ric. No s'ha de trencar silenciosament la cadena actual.

## 9. Normes per fer créixer el vocabulari

Abans de crear un node o tipus nou:

1. Buscar conceptes equivalents per nom, disciplina i significat.
2. Decidir si és una observació particular o coneixement reutilitzable.
3. Preferir una observació lliure quan encara no hi ha consens terminològic.
4. Donar al node un nom atòmic; evitar frases que combinin diverses idees.
5. Definir la disciplina com un valor curt i estable (`trampoline`, `dmt`, `tumbling`, `general`).
6. Explicar els nous `kind` i `relation_type` en aquest document o en un registre de vocabulari futur.
7. Crear relacions només quan la direcció i la justificació siguin explícites.
8. Mantenir en `draft` qualsevol proposta no revisada.
9. Retirar termes obsolets en lloc d'esborrar-los.
10. Convertir un atribut JSON en camp o model quan es consulta sovint, participa en permisos o necessita restriccions.

## 10. Què no s'ha de fer encara

- No afegir prompts, crides a LLM ni generació automàtica de plans.
- No afirmar que el graf és complet o validat professionalment.
- No desplegar Neo4j, RDF, vectors ni una infraestructura grafal externa.
- No importar massivament taxonomies sense procés editorial i deduplicació.
- No crear plans, sessions, càrregues o prescripcions dins de JSON genèric.
- No usar observacions com a diagnòstics mèdics.
- No concedir accés per `Membership` quan falta `CoachAthleteRelation`.
- No vincular automàticament participants de competicions a `Person`.
- No esborrar observacions per actualitzar-ne el contingut; cal versionar-les.
- No tractar confiança o intensitat com una mesura objectiva si no hi ha protocol.

## 11. Flux d'exemple complet

Descripció inicial de l'entrenador:

> «L'Aina completa el mortal endavant, però obre massa aviat i perd l'eix. Amb salts agrupats de control millora al cap de tres repeticions.»

Flux recomanat:

1. Comprovar que l'entrenador i l'Aina són `Person` i que existeix una `CoachAthleteRelation` activa amb `can_edit_training=True`.
2. Associar l'Aina a un `TrainingContext` actiu, per exemple «Preparació tècnica de tardor», disciplina `trampoline`.
3. Registrar primer una observació narrativa de categoria `difficulty`, amb el text complet i evidència «observació directa, tres repeticions». Pot quedar sense node mentre es revisa el vocabulari.
4. Si el vocabulari ja és estable, crear en `draft`:
   - concepte `Mortal endavant`, `kind=skill`;
   - concepte `Obertura prematura`, `kind=error`;
   - concepte `Salt agrupat de control`, `kind=exercise`.
5. Crear arestes dirigides justificades:
   - `Salt agrupat de control --corrects--> Obertura prematura`;
   - `Obertura prematura --conditions--> Mortal endavant`.
6. Vincular l'observació a `Obertura prematura` si aquest és el focus principal. La narració continua conservant que també es perd l'eix i que hi ha millora.
7. En una sessió posterior, crear una revisió amb `revise_athlete_observation`, estat `in_progress` o `stable`, nova evidència i `supersedes` apuntant a l'observació anterior.
8. Només després d'una revisió humana del vocabulari, moure nodes i arestes de `draft` a `validated`.

Aquest flux separa quatre fets: qui té permís, què s'ha observat, quin coneixement és reutilitzable i quin grau de validació editorial té.

## 12. Punts d'extensió futurs

Quan hi hagi requisits reals es poden afegir, mitjançant migracions explícites:

- grups amb membresia i rols propis;
- sessions i plans d'entrenament;
- adjunts o referències d'evidència;
- revisors i historial editorial del graf;
- sinònims, traduccions i identificadors de taxonomies externes;
- permisos més granulars per context;
- consultes grafals materialitzades o un motor extern, si el volum ho justifica;
- assistència d'IA amb traça, explicabilitat i aprovació humana.

Cap d'aquests punts és una funcionalitat implícita del MVP actual.
