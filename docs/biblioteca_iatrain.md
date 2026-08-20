# Biblioteca d’IA Train

> **Estat:** primera versió funcional implementada
> **Actualitzat:** 20 d’agost de 2026
> **Ruta d’usuari:** `/iatrain/biblioteca/`
> **Abast actual:** consulta de preparació física privada i coneixement tècnic professional de trampolí

## 1. Propòsit

La Biblioteca és el punt únic d’IA Train per descobrir, consultar i entendre contingut aplicable a l’entrenament. No és un editor ni una representació gràfica del coneixement: transforma dades estructurades i connexions internes en una experiència de cerca quotidiana per a l’entrenador.

La secció neix amb dos dominis:

- **Preparació física:** famílies, variants executables, revisions, classificacions, instruccions, fases i connexions biomecàniques.
- **Tècnica de trampolí:** elements i, en el futur, exercicis tècnics, amb les seves posicions, contactes, prerequisits, progressions i altres relacions professionals.

El nom «Biblioteca» és deliberadament més ampli que «Exercicis». Permet incorporar nous tipus de contingut sense fragmentar la navegació ni fer passar una habilitat tècnica per un exercici físic.

## 2. Encaix dins d’IA Train

La Biblioteca és una destinació principal del mode entrenador i apareix després de **Resum** a la navegació:

```text
Resum · Biblioteca · Organitzacions · Grups · Gimnastes · Gimnasos
```

Es manté separada del **Graf 3D** perquè tenen funcions diferents:

- la Biblioteca serveix per cercar, comparar i aplicar contingut;
- el Graf 3D serveix per inspeccionar i governar l’estructura professional;
- la Biblioteca és per a qualsevol entrenador actiu;
- el Graf 3D continua sent una eina editorial de superusuari.

El resum de l’entrenador també incorpora l’acció ràpida **Explorar Biblioteca** al costat de l’inici d’entrenament. La navegació ofereix accés persistent i el resum en facilita el descobriment inicial.

L’accés exigeix autenticació i un perfil d’entrenador actiu. El mode gimnasta no mostra la navegació d’entrenador ni permet entrar a la Biblioteca.

## 3. Funcionament de la interfície

### 3.1. Capçalera i recompte

La capçalera explica l’objectiu de la secció i mostra el volum accessible de cada domini:

- variants físiques del catàleg privat de la persona;
- elements tècnics professionals visibles per a l’usuari.

Els recomptes respecten permisos i estat editorial. No són recomptes globals de dades privades d’altres persones.

### 3.2. Cerca unificada

La cerca accepta un únic terme i consulta camps diferents segons el domini.

En preparació física cerca per:

- nom de variant i família;
- descripció, preparació, execució i consignes;
- objectius;
- material;
- accions articulars;
- músculs connectats.

En tècnica de trampolí cerca per:

- nom i descripció del concepte;
- noms dels conceptes connectats;
- contactes inicials o finals;
- posicions, prerequisits i altres relacions tipades.

Això permet trobar un element encara que el terme cercat no aparegui al seu nom. Per exemple, cercar una posició de contacte pot recuperar tots els elements que hi comencen o hi acaben.

### 3.3. Filtres

La primera versió implementa:

- **Àmbit:** tots, preparació física o tècnica de trampolí.
- **Origen:** tots, el meu catàleg o base professional.
- **Estat:** actius, esborrany, validat o retirat.
- **Dificultat física.**
- **Patró motriu.**

Els valors viuen a la URL. Per tant, una cerca es pot conservar als favorits del navegador, recarregar o compartir sense perdre el context.

Els filtres físics no s’apliquen artificialment a la tècnica. Si se selecciona dificultat o patró motriu, els resultats queden restringits al domini físic encara que l’àmbit indiqui «Tots».

### 3.4. Famílies i variants

Les variants físiques no apareixen com una llista plana. La pantalla les agrupa per família:

```text
Esquat
├── Esquat amb pes corporal
├── Esquat amb barra
├── Esquat goblet
└── ...
```

La família es pot desplegar per consultar-ne les variants coincidents. Quan una cerca només coincideix amb algunes variants, l’agrupació mostra únicament aquestes coincidències.

Els elements tècnics són resultats individuals perquè actualment el model professional no defineix una jerarquia equivalent a família/variant.

Les famílies amb direccions anatòmiques inequívoces incorporen una etiqueta breu per facilitar-ne la diferenciació visual: `AB`, `AD`, `ROT EXT`, `ROT INT`, `ROT`, `FLEX` o `EXT`. El nom complet es conserva i l’etiqueta exposa el significat desenvolupat com a ajuda accessible. La regla utilitza el codi semàntic estable de la família i evita falsos positius com «Flexió de braços», que no representa necessàriament una flexió articular.

El primer lot visual cobreix les set famílies d’esquat (`squat`, `box_squat`, `sit_to_stand`, `wall_sit`, `hack_squat`, `squat_hold` i `leg_press`) i les seves 29 variants visibles. Cada targeta combina una portada de família amb la miniatura muscular general **Cames i glutis**; aquesta miniatura substitueix `PF` només quan la categoria visual està disponible. `TT` es manté sense canvis.

### 3.5. Fitxa de preparació física

La fitxa lateral mostra:

- origen, estat editorial, autoria i número de revisió;
- descripció i classificació;
- preparació, execució, consignes i seguretat;
- objectius i material;
- fases ordenades;
- accions articulars de cada fase;
- rols musculars i base biomecànica;
- contracció esperada;
- requisits, precaucions i limitacions.

Les 29 variants del primer lot d’esquat incorporen una composició de l’avatar en posició inicial i en posició clau, amb etiquetes i direcció superposades per HTML/CSS. Cada asset es distribueix en WebP de `960×640` i `480×320`; la miniatura usa càrrega diferida i la fitxa selecciona la mida segons l’amplada de pantalla. Les portades de les set famílies es distribueixen a `480×320` i la miniatura de grup muscular a `256×256`. Les variants sense il·lustració mantenen el fallback textual i no mostren cap imatge genèrica enganyosa.

La identitat facial de totes aquestes peces deriva exclusivament de `core/static/core/avatar/explaining`. Les expressions varien entre atenció, concentració i esforç contingut segons el moviment. Els textos, les fletxes i les etiquetes no formen part del bitmap: són UI, de manera que es poden traduir, adaptar i mantenir accessibles.

El procediment complet per ampliar aquest sistema està recollit al [protocol de generació d’imatges per lots](generacio_imatges_biblioteca_iatrain.md).

Cada connexió física mostra el seu estat de verificació:

- **Confirmada:** afirmació confirmada per l’autor.
- **Inferida:** relació derivada del model però no confirmada com a observació.
- **Pendent:** connexió que encara necessita revisió.

La Biblioteca presenta un camí explicatiu, no una afirmació d’activació muscular mesurada:

```text
variant → fase → intenció → acció articular
                           ↘ múscul → base biomecànica → contracció esperada
```

### 3.6. Fitxa tècnica

La fitxa tècnica mostra la descripció, característiques simples i connexions llegibles. Les relacions sortints i entrants es diferencien amb direcció i poden incloure justificació i estat editorial.

Exemple conceptual:

```text
Barani agrupat
→ Comença des de: peus
→ Posició característica: agrupat
→ Acaba en: peus
← És prerequisit de: Barani ball out agrupat
```

La UI no necessita exposar un graf per comunicar aquestes connexions.

### 3.7. Paginació i responsive

La consulta pagina famílies i elements per evitar una pantalla excessivament llarga. En escriptori utilitza una composició de resultats i fitxa lateral. En tauleta o mòbil, la fitxa baixa sota els resultats i deixa de ser fixa.

## 4. Fonts de dades i permisos

La Biblioteca no fusiona els models de domini. Construeix una projecció de lectura comuna sobre dues fonts.

### 4.1. Catàleg físic personal

Font: `iatrain_exercises.ExerciseRevision`.

Regles:

- només recupera catàlegs actius propietat de la persona autenticada;
- només recupera variants actives;
- mostra l’última revisió de cada variant;
- el propietari pot consultar els seus esborranys;
- no barreja mai catàlegs privats de persones diferents;
- els registres retirats queden fora de la vista activa per defecte.

### 4.2. Coneixement tècnic professional

Font: `iatrain.KnowledgeConcept` i `iatrain.KnowledgeRelation`.

Regles:

- limita l’àmbit a `trampoline`;
- mostra conceptes `skill` i els futurs conceptes `exercise`;
- un entrenador normal només veu conceptes i relacions validats;
- un superusuari també pot filtrar i revisar esborranys;
- el contingut retirat queda ocult per defecte.

Actualment la base conté elements tècnics però encara no exercicis tècnics diferenciats. Quan apareguin conceptes `kind=exercise`, la Biblioteca ja els podrà identificar com a **Exercici tècnic**.

## 5. Decisions d’arquitectura

### 5.1. Projecció comuna, models separats

Un exercici físic i un element tècnic comparteixen informació útil per cercar —nom, domini, origen, estat o descripció— però no comparteixen tota la seva estructura. La Biblioteca normalitza només la targeta de resultat i delega el detall a una projecció específica per domini.

No s’han creat claus genèriques ni s’han forçat les dades tècniques dins de `iatrain_exercises`.

### 5.2. Consulta diferent del context del motor

`build_exercise_context()` continua sent una projecció privada, explicable i orientada al futur motor de suggeriments. La Biblioteca té necessitats diferents:

- text lliure;
- agrupació per famílies;
- múltiples orígens;
- estat de filtres a la URL;
- paginació;
- fitxes de consulta humana;
- dades físiques i tècniques.

Per això la Biblioteca no reutilitza directament la resposta del motor.

### 5.3. Sense escriptures en la primera versió

La primera entrega és deliberadament de només lectura. No permet:

- crear o editar exercicis;
- validar contingut;
- publicar contingut;
- copiar exercicis d’altres persones;
- afegir directament contingut a una sessió;
- marcar favorits o prioritats.

Aquest límit evita barrejar descoberta, govern editorial i planificació abans que cada operació tingui permisos i traçabilitat propis.

## 6. Integració futura amb el motor d’entrenament

La Biblioteca ha de convertir-se en un component reutilitzable del pipeline, no en un cercador duplicat.

Flux previst:

```text
Pas 1 · Context
organització + grup/gimnastes + gimnàs + material disponible
                         ↓
Pas 2 · Biblioteca en mode selecció
candidats prefiltrats + cerca manual + favorits + prioritats
                         ↓
Pas 3 · Prescripció
sèries + repeticions + càrrega + descans + adaptacions
```

El mode selecció haurà de conservar la mateixa cerca i fitxa, però afegirà:

- selecció múltiple;
- compatibilitat amb el material real del gimnàs;
- indicació de per què un candidat és pertinent;
- detecció de restriccions del context;
- incorporació a un bloc o sessió sense modificar la identitat de l’exercici.

La dosificació continuarà fora de la Biblioteca: una variant defineix què és l’exercici; la prescripció defineix com s’aplica en un entrenament concret.

## 7. Orígens i comunitat

La UI ja diferencia dos orígens:

- **El meu catàleg.**
- **Base professional.**

El tercer origen previst és **Comunitat**, per a publicacions públiques d’altres persones. Abans d’implementar-lo cal separar explícitament:

- origen;
- propietari actual;
- autoria;
- visibilitat;
- revisió publicada;
- llinatge o contingut de procedència.

Una possible presentació futura és:

```text
Meu · privat · derivat de Base professional v3
Comunitat · públic · publicat per Anna Puig · v2
```

### 7.1. Publicacions versionades

La comunitat no ha de llegir directament els esborranys vius d’una altra persona. Publicar hauria de crear una versió estable i consultable.

Això permet:

- conservar exactament què s’ha incorporat a un entrenament;
- actualitzar una publicació sense reescriure sessions històriques;
- retirar una versió sense eliminar-ne l’evidència;
- bifurcar o copiar contingut respectant autoria i procedència;
- revisar canvis abans d’adoptar una nova versió.

Visibilitats candidates:

- privada;
- compartida amb una organització;
- no llistada mitjançant enllaç;
- pública.

## 8. Favorits i prioritats de planificació

No s’han d’unificar en un sol camp.

### 8.1. Favorit

Un favorit és un marcador personal i privat. Serveix per recuperar contingut ràpidament i no hauria d’alterar automàticament les decisions del motor.

Característiques previstes:

- disponible sobre contingut propi, professional o comunitari;
- privat per defecte;
- visible com a filtre i col·lecció;
- independent de la versió, amb avís quan existeixi una revisió nova.

### 8.2. Prioritat per planificar

Una prioritat és una regla de planificació. Indica al motor que valori més aquell contingut dins d’un context, però no obliga a seleccionar-lo si és incompatible.

Pot necessitar abast:

- global de l’entrenador;
- organització;
- grup;
- gimnasta;
- objectiu o període concret.

També ha de permetre una justificació, dates de vigència i un pes o ordre. Per això no s’ha d’implementar com un simple booleà `preferred=True` sobre l’exercici.

## 9. Aspiracions de la secció

### Fase 1 — Consulta, implementada

- navegació principal;
- cerca física i tècnica;
- filtres inicials;
- famílies i variants;
- fitxes de detall;
- connexions explicables;
- permisos privats i professionals;
- paginació i adaptació responsive.

### Fase 2 — Personalització

- favorits;
- cerques desades;
- historial recent;
- col·leccions personals;
- comparació de variants.

### Fase 3 — Edició privada

- alta de famílies i variants;
- noves revisions;
- revisió de buits i propostes;
- detecció de duplicats;
- assistència de l’LLM sota validació humana.

### Fase 4 — Biblioteca professional i comunitària

- catàlegs professionals físics;
- publicació versionada;
- visibilitat d’organització i pública;
- atribució i llinatge;
- bifurcació i adopció de revisions;
- moderació i retirada.

### Fase 5 — Planificació contextual

- mode selecció dins del pipeline;
- material disponible;
- objectius del grup o gimnasta;
- prioritats contextuals;
- justificacions del motor;
- registres d’ús en sessions.

### Fase 6 — Aprenentatge responsable

- freqüència d’ús privada;
- efectivitat observada amb criteris definits;
- retroalimentació de l’entrenador;
- recomanacions sense convertir popularitat en qualitat;
- protecció de dades d’esportistes i organitzacions.

## 10. Limitacions actuals

- Totes les 298 revisions físiques importades continuen en `draft`.
- El coneixement tècnic professional només mostra contingut validat als entrenadors normals.
- No existeix encara una capa professional comuna d’exercicis físics.
- No existeix publicació entre persones.
- No existeixen favorits, prioritats ni col·leccions.
- La cerca usa PostgreSQL i relacions Django; si el volum creix molt, convindrà una projecció indexada o motor de cerca específic.
- Els resultats no disposen encara d’ordenació per rellevància ponderada.
- La Biblioteca no és una eina de prescripció clínica ni presenta inferències biomecàniques com a mesures observades.

## 11. Mapa del codi

- `iatrain/library.py`: projecció, cerca, filtres, agrupació, permisos editorials i detall.
- `iatrain/library_visuals.py`: manifest versionat d’il·lustracions de variants, famílies i grup muscular.
- `docs/generacio_imatges_biblioteca_iatrain.md`: protocol reproduïble per inventariar, generar, revisar, convertir i integrar nous lots visuals.
- `iatrain/views/library.py`: frontera HTTP i exigència de perfil d’entrenador.
- `iatrain/templates/iatrain/library/index.html`: interfície de resultats i fitxes.
- `iatrain/static/iatrain/library.css`: disseny responsive de la secció.
- `iatrain/urls.py`: ruta `/iatrain/biblioteca/`.
- `iatrain/templates/iatrain/components/header.html`: accés des de la navegació principal.
- `iatrain/tests/test_library.py`: permisos, aïllament privat, cerca relacional i visibilitat editorial.

## 12. Criteris de verificació

La primera versió es considera correcta quan:

1. un usuari sense perfil d’entrenador rep un `403`;
2. un entrenador mai recupera variants privades d’una altra persona;
3. un entrenador pot cercar dins del seu catàleg encara que les revisions siguin esborranys;
4. els conceptes professionals no validats només són visibles per a superusuaris;
5. una cerca per concepte connectat recupera l’element tècnic corresponent;
6. les famílies agrupen variants i la fitxa conserva la revisió seleccionada;
7. els filtres es mantenen a la URL;
8. la pantalla continua sent utilitzable en escriptori i mòbil.
9. les 29 variants i les set famílies del primer lot resolen a assets WebP existents.
