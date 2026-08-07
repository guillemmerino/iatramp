# Iatramp: visió del projecte i base transversal

## Propòsit

Iatramp és una plataforma per donar suport al cicle complet de la gimnàstica de trampolí. El producte actual resol sobretot l'operativa de competicions; l'evolució prevista amplia aquest abast al treball quotidià de clubs, entrenadors i gimnastes amb **IA Train**.

L'objectiu no és convertir el domini de competicions en un mòdul d'entrenament, sinó compartir una base d'identitat i relacions estable sobre la qual puguin conviure mòduls independents.

## Estat actual: competicions

L'app `competicions_trampoli` és el mòdul productiu principal. Inclou, entre altres àrees:

- configuració de competicions, aparells, fases i unitats de programa;
- inscripcions individuals i per equips;
- planificació de rotacions i franges;
- entrada, revisió i publicació de puntuacions;
- classificacions i exportacions;
- portal de jutges, assignacions, comunicació i contingut multimèdia.

Aquest mòdul conserva els seus models i fluxos. La primera migració de `core` no mou, transforma ni enllaça automàticament dades existents de competicions.

## Evolució cap a IA Train

IA Train ha de facilitar la planificació, el seguiment i l'anàlisi de l'entrenament. Necessita identificar persones reals, els seus clubs i els vincles d'accés entre entrenadors i gimnastes, independentment de si aquestes persones ja participen en una competició o disposen d'un compte.

La primera versió de `core` estableix aquesta base; encara no implementa sessions, exercicis, plans, mètriques ni assistents d'IA.

## Model d'identitat i relacions

### Persona i compte

`Person` representa l'individu real. Pot existir sense credencials i sobreviu a la supressió del seu compte. Cada compte nou rep una `Person` provisional automàtica. El camp opcional 1:1 `Person.user` reutilitza `settings.AUTH_USER_MODEL`; no s'introdueix cap model d'usuari nou.

El compte respon **qui pot iniciar sessió**. La persona respon **qui és l'individu del domini**. Els rols no es desen al compte.

Una persona creada prèviament per un entrenador es pot reclamar mitjançant una invitació. Si el compte ja té una identitat, el servei fusiona les dues `Person`, trasllada les referències conegudes i conserva una traça de la fusió. Una mateixa persona humana no es duplica per entrenador.

### Organització i rols

`Organization` representa principalment un club o una federació. `Membership` vincula una persona amb una organització i hi assigna un rol contextual. Una mateixa persona pot tenir diversos rols dins d'una organització i membresies diferents en organitzacions diferents. Les dates i `is_active` permeten conservar historial sense haver d'esborrar vincles.

### Entrenadors i gimnastes

IA Train defineix `AthleteProfile` i `CoachProfile` com a perfils opcionals i compatibles sobre una mateixa `Person`. `CoachAthleteRelation` és un vincle explícit entre aquests perfils. Admet múltiples entrenadors per gimnasta, diverses funcions i un context d'organització opcional. Els permisos es concedeixen per capacitat:

- consulta de perfil;
- consulta d'entrenament;
- edició d'entrenament;
- consulta de dades de salut, desactivada per defecte per la seva sensibilitat.

L'accés requereix una relació activa i vigent. Els serveis també reconeixen l'accés de la persona al seu propi perfil i l'accés global de superusuari. Una membresia administrativa no concedeix automàticament accés a dades esportives o de salut.

## Modularitat

`core` és transversal i no depèn de `competicions_trampoli`. Els futurs mòduls poden dependre de `core`; cal evitar la dependència inversa si no hi ha una migració de dades explícita i planificada. La lògica d'altes, vinculació i permisos compartits viu en serveis petits, mentre que les regles estructurals es reforcen també amb restriccions de base de dades.

Una futura integració de competicions haurà de mapar explícitament les inscripcions i usuaris històrics a `Person` i `Organization`, amb previsualització, deduplicació i possibilitat de reversió.

## Objectiu del suport d'IA

La IA ha d'assistir, no substituir, el criteri tècnic ni concedir-se accés implícit. Els casos previstos inclouen resum de càrrega, suggeriments de planificació, detecció de patrons i preparació de feedback. Qualsevol ús ha de respectar els permisos de la relació, minimitzar dades personals, deixar traça de les recomanacions i mantenir una decisió humana final, especialment en dades de salut i menors.

## Decisions obertes

- verificació reforçada de reclamacions i resolució manual de conflictes de fusió;
- consentiment i representació legal de menors;
- granularitat futura dels permisos per equip, grup, temporada o pla;
- lliurament per correu i interfície pública del cicle d'invitacions;
- model territorial i jerarquia club–federació;
- migració o vinculació progressiva amb inscripcions i membresies de competició;
- política de conservació, auditoria i exportació de dades personals;
- límits exactes, explicabilitat i supervisió humana de les funcions d'IA.
