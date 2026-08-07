# Entrega 2: identitat reclamable i perfils d’IA Train

## Estat

Implementada el 4 d’agost de 2026 fins a la capa de domini dels punts 1–3. La creació d’entrenaments, el selector visual de mode i la retirada de `TrainingContext` queden fora d’aquesta iteració.

## Identitat

- Cada `User` nou rep automàticament una `Person` provisional.
- Un entrenador pot crear una `Person` sense compte per a un gimnasta.
- `PersonClaimInvitation` desa una invitació temporal mitjançant el resum segur d’un token.
- En acceptar-la, el compte reclama la identitat preexistent.
- Si el compte ja té una altra `Person`, `merge_people` consolida les identitats i `PersonMergeRecord` en conserva la traça.
- Diverses identitats creades per entrenadors diferents es poden fusionar successivament en una sola persona canònica.

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

## Límits d’aquesta iteració

- No hi ha encara pantalles per activar o alternar els modes Gimnasta i Entrenador.
- No s’envien correus d’invitació.
- No hi ha una pantalla pública d’acceptació del token.
- No es creen ni assignen entrenaments.
- `TrainingContext` continua al codi per compatibilitat, però no s’amplia.
