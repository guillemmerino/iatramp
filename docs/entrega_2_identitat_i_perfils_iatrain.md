# Entrega 2: identitat reclamable i perfils d’IA Train

## Estat

Implementada inicialment el 4 d’agost de 2026 i ampliada el 20 d’agost de 2026
amb la capa de **perfil viu del gimnasta**. La identitat, els perfils esportius,
les evidències temporals, les interpretacions revisables i el constructor de
context ja formen part del domini. La interfície específica i el motor de
selecció d’exercicis queden fora d’aquesta iteració.

## Identitat

- Cada `User` nou rep automàticament una `Person` provisional.
- Un entrenador pot crear una `Person` sense compte per a un gimnasta.
- `PersonClaimInvitation` desa una invitació temporal mitjançant el resum segur d’un token.
- En acceptar-la, el compte reclama la identitat preexistent.
- Si el compte ja té una altra `Person`, `merge_people` consolida les identitats i `PersonMergeRecord` en conserva la traça.
- Diverses identitats creades per entrenadors diferents es poden fusionar successivament en una sola persona canònica.
- La consolidació de dades és extensible per aplicació: Core executa els gestors registrats i IA Train és responsable de traslladar també autoria de rotacions i notacions, decisions editorials, gimnasos creats i gestió de grups.

## Perfils esportius

IA Train només defineix dos perfils, tots dos opcionals sobre la mateixa persona:

- `AthleteProfile`;
- `CoachProfile`.

Una persona pot tenir-ne un o tots dos. La configuració específica de cada mode queda encapsulada en el perfil corresponent.

## Relacions

`CoachAthleteRelation` pertany ara a `iatrain` i vincula un `CoachProfile` amb un `AthleteProfile`. Conserva vigència, organització opcional, funció i permisos per capacitat.

`create_unclaimed_athlete` crea de forma transaccional:

1. la persona sense compte;
2. el perfil de gimnasta;
3. la relació amb l’entrenador;
4. opcionalment, la invitació de reclamació.

La migració copia les relacions antigues de `core` als perfils nous abans de retirar el model anterior.

## Grups i informació extreta

- El cognom de `Person` és opcional per permetre altes conversacionals incompletes.
- `AthleteProfile.extracted_facts` conserva fets estructurats encara no confirmats, amb font, confiança i estat.
- `TrainingGroup` representa un grup estable dins d'una organització i pot conservar temporalment fets no formalitzats sobre horaris, material o objectius.
- `TrainingGroupMembership` manté l'historial temporal de pertinença dels perfils de gimnasta i impedeix duplicar una pertinença activa.
- Els noms dels grups són únics dins de cada organització sense distingir majúscules i minúscules.

`extracted_facts` és una safata flexible d’informació encara no formalitzada. No
forma part automàticament del context autoritatiu del selector. Un fet rellevant
s’ha de convertir en observació, mesura, condició o dada esportiva amb autoria,
data i regles pròpies.

## Perfil viu del gimnasta

El perfil no és una fitxa monolítica ni una fotografia que s’hagi de mantenir
manualment. És una projecció temporal construïda a partir de fonts independents:

```text
Person + AthleteProfile
├── AthleteSportProfile         context esportiu relativament estable
├── AthleteMeasurement          mesures objectives i sèrie temporal
├── AthleteObservation          criteri narratiu de l’entrenador
├── AthleteCondition            molèsties, restriccions i tolerància confirmades
├── TrainingItemResult          resposta real als entrenaments
└── AthleteInsight
    └── AthleteInsightEvidence  interpretació explicable sobre les fonts anteriors

                    ↓
          AthleteProfileContext
      fotografia calculada en un moment concret
```

La base de dades conserva esdeveniments i evidències. El context actual es
calcula quan es necessita i pot ser diferent segons la data, l’organització i
els permisos de qui el consulta.

### Context esportiu estable

`AthleteSportProfile` permet que una mateixa persona tingui context diferent per
disciplina. Conserva:

- disciplina;
- codi de nivell extensible, sense imposar una escala universal;
- data aproximada d’inici de la pràctica;
- lateralitat preferent;
- notes i vigència.

L’edat no es duplica: es calcula a partir de `Person.birth_date`. L’antropometria
no es tracta com una propietat permanent, sinó com mesures datades.

### Mesures objectives

`AthleteMeasurement` registra una dada numèrica amb:

- domini: antropometria, força, potència, mobilitat, control motor, resistència,
  recuperació, càrrega o altres;
- codi i nom de mètrica;
- valor, unitat i lateralitat;
- protocol utilitzat;
- font: valoració, dispositiu, resultat d’entrenament, informació del gimnasta o
  importació;
- incertesa opcional;
- data de mesura i vigència;
- organització, autoria i notes.

Les mesures formen una sèrie temporal. Una nova valoració no substitueix
l’anterior: permet estudiar progressió. Si una dada era incorrecta, es crea una
correcció amb `supersedes`; la fila original no es modifica ni s’elimina.

Les unitats són obligatòries. El sistema no pot comparar o agregar valors amb
unitats incompatibles només perquè comparteixin un nom semblant.

### Condicions temporals i informació sensible

`AthleteCondition` representa informació que pot alterar la selecció de treball:

- dolor o molèstia;
- lesió comunicada;
- restricció mèdica aportada;
- tolerància de càrrega;
- disponibilitat del moment;
- altres condicionants.

No és un model de diagnòstic clínic. Conserva la font i diferencia el relat del
gimnasta, l’observació de l’entrenador, la resposta en sessió i un document
clínic aportat.

Cada condició pot indicar regió anatòmica, lateralitat, severitat d’1 a 5,
evidència, dates i impacte sobre l’entrenament:

- `none`: sense impacte declarat;
- `monitor`: monitorar;
- `modify`: modificar la selecció o la dosi;
- `avoid`: evitar el treball afectat;
- `stop`: no entrenar.

Una condició nova sempre entra com a `proposed`. Només una confirmació humana la
converteix en `confirmed` i, per tant, en una restricció autoritativa per al
selector. Posteriorment es pot resoldre o substituir, però no reescriure.

### Observacions professionals

`AthleteObservation` continua sent l’espai narratiu de l’entrenador. És útil per
descriure competència, aprenentatge, fortaleses, dificultats, pors, limitacions i
notes que no encaixen honestament en una mètrica.

Ara també conserva l’organització que governa l’observació. Les observacions
antigues vinculades a `TrainingContext` hereten aquest abast durant la migració.
La narració, l’evidència, la confiança, la vigència, l’autoria i la cadena
`supersedes` continuen diferenciant una observació d’un fet objectiu.

### Resposta real a l’entrenament

No es copia l’historial de sessions dins del perfil. El constructor consulta
directament `TrainingItemResult` i incorpora, dins de la finestra temporal
demanada:

- exercici realment executat;
- finalització, substitució o aturada;
- sèries, repeticions, durada i càrrega reals;
- RPE i qualitat d’execució;
- resposta al dolor i retorns, només amb permís de salut.

Això fa que el perfil s’actualitzi automàticament després de registrar una sessió
sense crear una segona font que pugui quedar desincronitzada.

### Interpretacions del LLM

`AthleteInsight` conserva tendències, progrés, tolerància, preferències, senyals
de risc, hipòtesis o mancances d’informació. Una interpretació inclou afirmació,
raonament, confiança, finestra d’evidència, vigència, model utilitzat i persona
que n’ha provocat la generació.

Una interpretació sempre neix com a `proposed`. Per confirmar-la necessita com a
mínim un `AthleteInsightEvidence`, que apunta exactament a una font tipada:

- una observació;
- una mesura;
- una condició;
- un resultat d’ítem d’entrenament.

El text generat no es converteix silenciosament en fet. Les interpretacions
confirmades i les proposades sempre apareixen en seccions diferents del context.

| Capa | Exemple | Pot governar directament la selecció? |
|---|---|---|
| Dada estable | Disciplina i lateralitat preferent | Sí, amb vigència |
| Mesura | Salt amb contramoviment: 31,4 cm | Sí, dins del protocol i la data |
| Observació | Perd alineació quan augmenta la fatiga | Com a criteri professional contextual |
| Condició proposada | Possible molèstia al turmell | No, requereix revisió |
| Condició confirmada | Modificar impactes durant una setmana | Sí, com a restricció |
| Insight proposat | Sembla baixar la tolerància als impactes | No |
| Insight confirmat | Tendència sostinguda amb tres evidències | Sí, mantenint-ne la incertesa |

## Constructor de context

`build_athlete_profile_context` genera una estructura serialitzable per al futur
motor o per a una interfície. Rep gimnasta, organització, moment de tall i finestra
històrica. Retorna:

- identitat i edat calculada;
- perfils esportius actius;
- última mesura i historial recent per mètrica i lateralitat;
- condicions confirmades i vigents;
- observacions actuals;
- respostes recents a entrenaments;
- interpretacions confirmades;
- propostes encara no autoritatives;
- indicadors de seguretat per al selector.

No es desa com una veritat nova. Tornar-lo a construir després d’una sessió,
d’una mesura o d’una confirmació produeix una fotografia actualitzada.

Si l’usuari no té permís de salut, el context no interpreta l’absència de dades
com «el gimnasta no té restriccions». Retorna explícitament:

```text
health_data_available = false
requires_health_review = true
```

El futur motor haurà de tractar aquesta situació com informació desconeguda i no
com una autorització per prescriure sense precaucions.

## Actualització amb poca càrrega manual

El flux previst és:

```text
resultats de sessió ───────────────┐
mesures i dispositius ─────────────┤
notes breus o entrada per veu ─────┤
informació aportada pel gimnasta ──┤
                                   ↓
                         evidències amb font i data
                                   ↓
                    detecció de tendències pel LLM
                                   ↓
                  propostes agrupades per revisar
                                   ↓
                 confirmació només quan és necessària
```

Els resultats entren automàticament en el context. Una futura entrada per veu
podrà proposar observacions, mesures o condicions, però haurà de respectar el
tipus de dada i el nivell de confirmació. Les dades sensibles, les restriccions i
els senyals de risc no s’han de confirmar automàticament.

## Serveis disponibles

La capa `iatrain.athletes.services` centralitza permisos, autoria i transicions:

- `set_athlete_sport_profile`;
- `record_athlete_measurement`;
- `invalidate_athlete_measurement`;
- `propose_athlete_condition`;
- `review_athlete_condition`;
- `resolve_athlete_condition`;
- `propose_athlete_insight`;
- `attach_athlete_insight_evidence`;
- `review_athlete_insight`.

Les vistes, comandes, automatitzacions i eines del futur LLM han d’utilitzar
aquests serveis en lloc de reproduir transicions manualment.

## Permisos i organització

- Consultar el context requereix `can_view_training`.
- Modificar dades requereix `can_edit_training`.
- Condicions, senyals de risc i mesures sensibles requereixen també
  `can_view_health_data`.
- Per consultar un altre gimnasta s’ha d’indicar l’organització, excepte en el
  cas d’un superusuari.
- Mesures, condicions, observacions i interpretacions conserven el seu abast
  organitzatiu; les dades globals queden diferenciades amb organització buida.

La fusió d’identitats retargeta perfils esportius, mesures, condicions,
interpretacions i autoria. Si dues identitats tenen perfil per a la mateixa
disciplina, se’n preserva un de sol i es combinen les notes sense perdre les
evidències temporals.

## Límits d’aquesta iteració

- No hi ha encara pantalles per activar o alternar els modes Gimnasta i Entrenador.
- No s’envien correus d’invitació.
- No hi ha una pantalla pública d’acceptació del token.
- No hi ha encara una interfície específica per capturar mesures, revisar
  condicions o confirmar interpretacions en bloc.
- No s’executa encara cap procés periòdic que proposi tendències automàticament.
- El context prepara les dades per al selector, però encara no selecciona
  exercicis ni prescriu sessions.
- La captura per veu encara no transforma notes en propostes d’aquest domini.
- `TrainingContext` continua al codi per compatibilitat, però no s’amplia.
