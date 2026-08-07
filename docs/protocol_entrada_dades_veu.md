# Protocol d'entrada de dades per veu

## Propòsit

Aquest document és la font de continuïtat per a la tasca d'introduir dades reals a la base de dades relacional d'Iatramp mitjançant conversa de veu. Qualsevol agent que reprengui la feina ha de llegir-lo abans de crear o modificar registres.

L'objectiu és convertir informació dictada en registres relacionals consistents, revisables i traçables, sense perdre el context operatiu de la conversa.

Iatramp ha de permetre que les persones usuàries interactuïn amb el sistema en llenguatge natural. L'agent fa de capa d'interpretació: transforma una descripció conversacional en propostes de registres i relacions de domini, però no converteix una interpretació en dades persistides sense que la persona usuària l'hagi validada.

## Mètode de treball

1. La persona usuària dicta la informació amb llenguatge natural.
2. L'agent identifica els registres, les relacions i les dades que falten.
3. Abans d'escriure a la base de dades, l'agent presenta un resum estructurat i demana confirmació explícita.
4. Només després de la confirmació, l'agent crea o actualitza els registres.
5. L'agent informa del resultat i actualitza aquest document quan s'acordi un protocol nou o canviï l'estat de la tasca.

Durant el procés, l'agent ha de fer explícit el que troba: si una entitat ja existeix, si manca una dada necessària, si apareix una possible duplicació o si el model actual no representa amb precisió el que s'ha dictat. Pot interrompre amb preguntes breus quan això eviti una interpretació incorrecta.

## Protocol de resolució de dades dictades

Per cada fragment dictat, resoldre les dependències de més estable a més específica:

1. Identificar l'organització esmentada i cercar-la abans de crear-ne una de nova.
2. Dins de l'organització, cercar o crear el grup d'entrenament.
3. Cercar la persona; si no existeix, proposar-ne la creació amb les dades disponibles i marcar com a pendents les que faltin.
4. Comprovar que la persona tingui el perfil requerit i que estigui vinculada al grup; proposar només les relacions que no existeixin.
5. Per habilitats, elements i coneixement tècnic, cercar primer el `KnowledgeConcept` equivalent. Si no existeix, proposar el concepte, el seu tipus, la disciplina i les relacions tècniques que calguin abans d'associar-lo a una observació del gimnasta.
6. Resumir en una sola proposta els registres nous, les actualitzacions i les dades pendents, i demanar confirmació abans de desar res.

Mai no s'ha d'assumir que un nom similar correspon a la mateixa persona, grup o element tècnic. Si el context no ho resol, cal demanar confirmació.

Quan una descripció atribueixi una habilitat a un gimnasta:

- «Ho ha fet» o «sap fer-ho» no implica automàticament domini estable; cal aclarir el nivell de certesa si el context no el determina.
- «Ho domina» es proposa com una observació de competència amb estat `stable`.
- `stable` no significa execució tècnicament perfecta. Significa que la competència està adquirida amb prou autonomia i consistència per continuar progressant cap a altres aprenentatges.
- El marge de refinament tècnic s'ha de descriure separadament a la narrativa o, quan hi hagi evidència concreta, en observacions específiques de dificultat o aprenentatge. No s'ha de rebaixar automàticament una competència a `in_progress` només perquè l'execució sigui millorable.
- `in_progress` s'ha de reservar per a habilitats que encara no estan prou adquirides per considerar-les disponibles de manera funcional o per avançar amb seguretat en la progressió indicada.
- Si el concepte esmentat no existeix o l'agent no en coneix prou la definició, l'agent ho ha de dir, demanar-ne una descripció i proposar explícitament si es vol incorporar com a nou `KnowledgeConcept`.
- El concepte nou s'ha de confirmar i crear abans de registrar-hi l'observació del gimnasta.

## Exemple de flux: gimnasta i habilitats

Una descripció com «Jaume, al grup d'adults de Marbella, d'uns trenta anys, ha començat fa poc i ja fa l'agrupat, la carpa oberta i la carpa tancada» s'ha de tractar com una proposta, no com una ordre directa de crear dades:

1. Cercar l'organització Marbella.
2. Cercar el grup Adults dins de Marbella.
3. Cercar Jaume, desambiguant-lo abans de crear una persona nova.
4. Proposar la vinculació de Jaume al grup si encara no hi és.
5. Cercar els tres elements al catàleg de coneixement. Per a cada element absent, proposar-ne la modelització abans de registrar que Jaume el domina o l'ha realitzat.
6. Aclarir quin significat té «ja fa»: per defecte pot ser una observació de competència, però cal confirmar el nivell, l'evidència, la data i, si és necessari, qui ho ha observat.

## Ordre inicial de construcció

La seqüència normal és:

1. Organitzacions.
2. Persones.
3. Membresies i rols dins de cada organització.
4. Perfils de gimnasta i d'entrenador/a.
5. Relacions entrenador/a-gimnasta i grups d'entrenament.
6. Contextos d'entrenament, conceptes tècnics i observacions.

No s'ha de forçar aquest ordre si la informació dictada exigeix crear una dependència anterior; en aquest cas, s'ha d'explicar i validar amb la persona usuària.

## Principis obligatoris

- No crear, fusionar ni eliminar identitats sense confirmació explícita.
- No inventar dades, dates, rols o relacions no dictades.
- Marcar la incertesa i fer una sola pregunta concreta quan calgui una dada imprescindible.
- Evitar duplicats: cercar sempre una organització o persona existent abans de crear-la.
- Tractar les dades de salut i altres dades sensibles amb especial prudència i només amb autorització clara.
- Mantenir les observacions com a fets atribuïbles, amb autoria i data, sense presentar inferències com si fossin dades confirmades.

## Estat actual

El protocol està actiu. Els canvis persistits mitjançant aquest flux s'han de resumir a continuació perquè una conversa futura pugui reprendre el context.

### Registres confirmats durant la sessió

- S'ha creat el `KnowledgeConcept` «Bot» com a `skill` de trampolí, nivell inicial i estat `draft`, amb la descripció tècnica dictada sobre la posició estirada, l'impuls de la malla i el recorregut dels braços.
- S'ha creat la relació `Agrupat —requires→ Bot`, també en estat `draft`, perquè el Bot és la base tècnica prèvia a l'Agrupat.
- S'ha creat el `KnowledgeConcept` «Carpa oberta» com a `skill` bàsica de trampolí, en estat `draft`, amb inici i recepció dempeus, obertura de cames, contacte de les mans amb les puntes dels peus i sense rotacions.
- S'ha creat la relació `Carpa oberta —requires→ Bot`, en estat `draft`.
- S'ha refinat «Carpa oberta» per indicar explícitament que les cames es mantenen estirades i separades; aquests trets també s'han desat com a propietats estructurades per permetre comparacions derivades.
- S'ha creat el `KnowledgeConcept` «Carpa tancada» com a `skill` inicial de trampolí, en estat `draft`, amb inici i recepció dempeus, sense rotacions i amb les cames estirades i juntes; aquests trets s'han desat també com a propietats estructurades.
- S'ha creat la relació `Carpa tancada —requires→ Bot`, en estat `draft`.
- S'ha registrat una `AthleteObservation` per a Jaume sobre «Agrupat», amb categoria `competency` i estat `stable`: l'element està funcionalment adquirit i permet continuar progressant, encara que l'execució admeti refinament tècnic.

## Protocols pendents de definir

Les instruccions següents es dictaran progressivament i s'han d'afegir aquí amb exemples i criteris de confirmació:

- Alta d'organitzacions.
- Alta i desambiguació de persones.
- Assignació de membresies, rols i permisos.
- Alta de perfils d'entrenador/a i gimnasta.
- Registre d'observacions, habilitats, dificultats i evolució.
- Correccions, actualitzacions i desactivacions de dades existents.
