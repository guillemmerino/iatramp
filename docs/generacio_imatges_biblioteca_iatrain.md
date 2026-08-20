# Generació d’imatges per lots de la Biblioteca d’IA Train

> **Estat:** protocol operatiu vigent
> **Actualitzat:** 20 d’agost de 2026
> **Àmbit:** il·lustracions d’exercicis físics, variants, famílies i grups musculars
> **Manifest de producció:** `iatrain/library_visuals.py`

## 1. Objectiu del protocol

Aquest document permet que un agent nou ampliï el catàleg visual sense haver de reconstruir les decisions preses durant el primer lot. Defineix com inventariar un lot, preparar les referències de l’avatar, generar cada tipus d’asset, revisar-lo, convertir-lo a WebP, integrar-lo a la UI i validar el resultat.

La generació no es considera acabada quan existeix una imatge atractiva. Es considera acabada quan:

- representa l’exercici i el material declarats al catàleg;
- diferencia la variant de les variants veïnes;
- manté la identitat visual d’IA Train;
- funciona com a miniatura i en la fitxa de detall;
- està versionada, optimitzada i registrada al manifest;
- supera la revisió visual i els tests.

## 2. Estat actual i límit d’abast

El lot visual completat és `01_squat`:

- font principal: `iatrain_exercises/catalog_data/v2/batch_01_squat.py`;
- 28 variants definides al lot;
- `bodyweight_squat`, procedent del vocabulari inicial, inclòs com a variant relacionada;
- 29 il·lustracions de variant en total;
- set portades de família;
- un grup muscular general: `lower_body`, mostrat com a **Cames i glutis**.

El lot `02_hinge` està ajornat. No s’ha de generar ni integrar fins que l’usuari ho demani de nou de manera explícita.

## 3. Fonts de veritat

Abans d’escriure prompts, l’agent ha de llegir les dades del repositori. El nom de l’exercici, la intuïció o una imatge semblant no són suficients.

Fonts que cal consultar:

1. `iatrain_exercises/catalog_data/v2/batch_XX_*.py`
   Defineix el codi, el nom, la família, el patró, el material i part de la classificació.
2. `iatrain_exercises/catalog_data/v2/templates.py`
   Defineix la preparació i l’execució compartides pel patró.
3. `iatrain_exercises/vocabulary.py`
   Pot contenir variants inicials relacionades que no formen part de `ROWS`, com `bodyweight_squat`.
4. `iatrain/library_visuals.py`
   Indica quins assets estan actius i quina versió serveix la UI.
5. `core/static/core/avatar/explaining/`
   És l’única font autoritzada per a la cara i les expressions de l’avatar.

Per cada variant s’ha de preparar una fitxa de generació amb:

- codi estable;
- nom visible;
- família;
- material obligatori;
- posició inicial;
- posició final o posició clau;
- diferència visual respecte de variants semblants;
- riscos de confusió que el prompt ha d’excloure.

Exemple:

```text
code: band_resisted_squat
material: elastic_band
inici: dempeus, peus a l’amplada de les espatlles
final: esquat bilateral
diferenciador: minibanda tancada immediatament sobre els genolls
exclusions: cap banda sota els peus, a les mans o als turmells
```

## 4. Unitat de treball i planificació del lot

Un lot de catàleg és la unitat màxima de treball. No s’han de barrejar dos fitxers `batch_XX` en una mateixa entrega si l’usuari no ho ha autoritzat.

L’inventari previ ha de separar:

| Tipus | Quantitat esperada | Ús |
|---|---:|---|
| Variant | una per codi executable | Llista de variants i fitxa detallada |
| Família | una per codi de família | Portada de la targeta familiar |
| Grup muscular | una per categoria nova | Substitució visual de `PF` |

Cada variant és un asset independent. No s’ha de generar una làmina amb diverses variants i retallar-la: això redueix la precisió del material, de la postura i de la identitat facial.

Ordre recomanat:

1. inventari i fitxes de generació;
2. grup muscular;
3. portades de família;
4. primera mostra de tres o quatre variants;
5. revisió de la mostra;
6. resta de variants en onades petites;
7. revisió conjunta contra el catàleg;
8. conversió i integració;
9. tests i revisió de la pàgina.

## 5. Referències i identitat de l’avatar

### 5.1. Regla obligatòria per a la cara

La cara i les expressions s’han de basar exclusivament en imatges de:

```text
core/static/core/avatar/explaining/
```

No s’ha d’utilitzar `standard` ni cap altra carpeta com a referència facial. Per mantenir consistència entre crides independents, cal fixar el mateix subconjunt de dues o tres imatges durant tot el lot. El primer lot va utilitzar:

```text
explaining_5.png
explaining_6.png
explaining_7.png
```

Abans de començar un lot nou es poden inspeccionar totes les imatges d’`explaining` i escollir un altre subconjunt, però no s’ha de canviar a mig lot.

### 5.2. Expressió

L’avatar no ha de somriure sempre. Cal escollir l’expressió segons la funció:

- atenta o pedagògica en exercicis d’aprenentatge;
- neutra i concentrada en posicions de control;
- d’esforç contingut en variants carregades;
- mai exagerada, dolorosa o caricaturesca.

### 5.3. Estil comú

El primer lot estableix aquesta base:

- il·lustració esportiva polida i realista;
- fons d’estudi gris càlid i clar;
- ombres suaus;
- roba esportiva en turquesa i coral;
- cos complet, anatomia clara i marges generosos;
- cap logotip, text, etiqueta, fletxa, marca d’aigua o decoració innecessària.

Els textos `Inici`, `Descens`, `Contacte`, `Flexió` o equivalents són HTML/CSS. No s’han d’incrustar al bitmap.

## 6. Plantilles de prompt

Les plantilles són una base. La part biomecànica i el material s’han d’adaptar a cada fitxa de generació.

### 6.1. Variant executable

Format: horitzontal `3:2`, amb exactament dues representacions del mateix avatar.

```text
Use the supplied IA Train avatar references as the exclusive facial identity
and expression reference. Create a polished landscape 3:2 exercise-library
illustration with exactly two full-body depictions of the same avatar side by
side: the start position on the left and the end or key position on the right.
Keep both figures fully visible, clearly separated and anatomically precise.
Use a focused natural expression, teal and coral athletic clothing, a pale warm
gray studio background and soft shadows. No text, arrows, logos, labels,
watermarks, borders, extra people or extra limbs.

Exercise: {name}.
LEFT: {start_position}.
RIGHT: {end_position}.
Equipment in BOTH positions: {equipment_and_placement}.
Critical differentiator: {variant_specific_detail}.
Never show: {known_confusions}.
```

El prompt ha de descriure la ubicació del material, no només el seu nom. Exemples:

- barra frontal: sobre clavícules i espatlles, colzes alts;
- barra baixa: sobre deltoides posteriors, per sota de la cresta de l’espatlla;
- caixa: directament darrere del cos, mai sota els peus ni al costat;
- landmine: un extrem de la barra ancorat visiblement al terra;
- minibanda: al voltant de les cuixes i immediatament sobre els genolls;
- talons elevats: talons sobre falca o discos, dits en contacte amb el terra;
- premsa: esquena recolzada, peus a la plataforma i màquina completa visible.

### 6.2. Portada de família

Format final `3:2`, una sola figura en la posició més recognoscible.

```text
Create a polished exercise-library family cover for “{family_name}”. Use the
supplied IA Train avatar references as the exclusive facial identity and
expression reference. Show one full-body avatar in the most recognizable key
position of the family. Make {essential_support_or_equipment} unmistakable.
Use a concentrated natural expression, teal and coral athletic clothing, a
pale warm gray studio background and soft shadows. No text, arrows, logos,
labels, watermarks, split panels or extra people. Keep the complete body and
all essential equipment visible.
```

La portada representa la família, no una variant excessivament específica. Per exemple, `box_squat` necessita una caixa darrere del cos, però no una marca concreta de barra o manuella.

### 6.3. Grup muscular

Format final quadrat. Ha de funcionar a `30×30 px` i no pot dependre de text.

```text
Create a clean square IA Train library category illustration for “{group}”.
Use the supplied IA Train avatar references as the exclusive facial identity
and expression reference. Show one centered full-body avatar in a simple pose
that emphasizes {body_regions}, without anatomical labels or highlighted pain.
Use the established teal, coral and pale studio visual language. No text,
logos, arrows, watermarks, extra people or complex equipment.
```

Categories previstes, a crear només quan el lot les necessiti:

- `lower_body`: Cames i glutis;
- `upper_body`: Braços i tren superior;
- `core`: Core i tronc;
- `full_body`: Cos complet;
- `mobility`: Mobilitat i control.

La categoria s’ha de deduir del conjunt de famílies, no d’una sola fase muscular secundària.

## 7. Generació i versions

### 7.1. Eina

S’ha d’utilitzar una eina de generació d’imatges que admeti les referències locals. Si l’agent disposa d’una habilitat o protocol propi d’ImageGen, l’ha de llegir completament abans de generar.

Cada crida ha de crear un únic asset final. Es poden executar diverses crides independents en paral·lel si l’eina ho permet, però cada prompt i cada resultat han de conservar el seu codi.

### 7.2. Noms de treball

```text
iatrain/static/iatrain/library/exercises/{code}-v{N}-source.png
iatrain/static/iatrain/library/families/{family_code}-v{N}-source.png
iatrain/static/iatrain/library/groups/{group_code}-v{N}-source.png
```

Els PNG `source` són originals de treball i estan ignorats per Git. Els originals retornats per l’eina de generació també s’han de conservar a la ubicació pròpia de l’eina si aquesta en proporciona una.

### 7.3. Política de versions

- Un asset acceptat no s’ha de sobreescriure.
- La primera versió és `v1`.
- Qualsevol regeneració posterior és `v2`, `v3`, etc.
- Només la versió seleccionada s’afegeix a `iatrain/library_visuals.py`.
- Les versions rebutjades no s’han d’afegir al manifest ni al control de versions.
- No s’han d’esborrar originals o versions de manera massiva. Qualsevol neteja ha de tenir objectius exactes i autorització adequada.

Exemples actuals:

```text
bodyweight_squat-v2
band_resisted_squat-v2
barbell_box_squat-v2
heel_elevated_goblet_squat-v3
```

El número superior indica que una revisió visual o semàntica va substituir una proposta anterior.

## 8. Revisió visual

### 8.1. Revisió per onades

Després de cada tres a deu assets, cal crear una làmina temporal de contacte i inspeccionar-la. La làmina no forma part del producte i està ignorada per Git.

Cal revisar:

- identitat facial coherent;
- cos complet i sense extremitats duplicades;
- diferència clara entre esquerra i dreta;
- ordre correcte: inici a l’esquerra, posició clau a la dreta;
- material correcte, amb quantitat i ubicació correctes;
- màquines recognoscibles i punts de suport visibles;
- base de peus, lateralitat i amplitud coherents;
- absència de text, marques i artefactes;
- llegibilitat quan la imatge es redueix a miniatura.

### 8.2. Revisió contra dades

La revisió final s’ha de repetir amb el fitxer `batch_XX` obert. Aquest pas és obligatori perquè una imatge pot semblar biomecànicament plausible i, tot i així, contradir el catàleg.

Errors reals detectats al primer lot:

- una banda elàstica sota els peus quan el catàleg indicava banda sobre els genolls;
- una manuella en una variant que requeria kettlebell;
- una gambada en lloc d’un esquat ciclista bilateral;
- una caixa situada al costat del cos en lloc de directament darrere;
- una elevació de talons massa petita per ser visible.

Si el material o el diferenciador principal és incorrecte, l’asset s’ha de regenerar. No s’ha de corregir només el text alternatiu o el nom.

## 9. Conversió a WebP

Els PNG de treball no se serveixen a la UI.

Sortides de variant:

```text
iatrain/static/iatrain/library/exercises/{code}-v{N}-960.webp
iatrain/static/iatrain/library/exercises/{code}-v{N}-480.webp
```

Mides:

- detall: `960×640`;
- miniatura responsive: `480×320`;
- portada de família: `480×320`;
- grup muscular: `256×256`.

Configuració de referència amb Pillow:

```python
from PIL import Image, ImageOps

with Image.open(source) as image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    for width, height in ((960, 640), (480, 320)):
        result = ImageOps.fit(image, (width, height), Image.Resampling.LANCZOS)
        result.save(output, "WEBP", quality=84, method=6)
```

Abans d’utilitzar `ImageOps.fit`, cal comprovar que el retall no elimina peus, discos, ancoratges o parts de la màquina. Quan la composició necessita tots els marges, s’ha d’utilitzar `ImageOps.contain` sobre un llenç del mateix color que el fons.

## 10. Integració al programa

### 10.1. Manifest

Cal actualitzar `iatrain/library_visuals.py`:

```python
EXERCISE_IMAGE_VERSIONS["exercise_code"] = version
FAMILY_IMAGE_VERSIONS["family_code"] = version
```

No s’han d’escriure rutes d’asset directament a la plantilla. Les funcions `exercise_illustration()` i `family_illustration()` construeixen les rutes i les metadades.

També cal revisar `_movement_labels()` perquè les etiquetes HTML coincideixin amb la composició:

- `Inici → Descens`;
- `Assegut → Dempeus`;
- `Inici → Contacte`;
- `Extensió → Flexió`;
- `Inici → Manteniment`.

### 10.2. Grups musculars futurs

La implementació actual només té `LOWER_BODY_GROUP_IMAGE` perquè el primer lot és íntegrament de cames i glutis. Quan aparegui el primer lot d’una altra categoria, l’agent ha de generalitzar el manifest abans d’integrar-lo:

```python
GROUP_IMAGES = {
    "lower_body": ".../lower_body-v1-256.webp",
    "upper_body": ".../upper_body-v1-256.webp",
}

FAMILY_GROUPS = {
    "squat": "lower_body",
    "horizontal_push": "upper_body",
}
```

No s’ha de reutilitzar la miniatura de cames per a braços, tronc o cos complet.

### 10.3. UI

La plantilla activa és `iatrain/templates/iatrain/library/index.html` i els estils viuen a `iatrain/static/iatrain/library.css`.

Comportament esperat:

- portada de família a la targeta física;
- grup muscular superposat en lloc de `PF` quan existeix;
- `TT` sense canvis fins que es defineixi el seu sistema visual;
- miniatura de variant a la llista;
- imatge gran limitada a `720 px` dins de la fitxa;
- etiquetes i fletxa superposades amb HTML/CSS;
- fallback textual quan una variant encara no té imatge.

## 11. Tests i validació final

El test principal és `iatrain/tests/test_library.py`. Ha de comprovar:

- nombre d’exercicis i famílies registrats al lot;
- existència física de totes les rutes del manifest amb `django.contrib.staticfiles.finders`;
- mides responsive disponibles;
- portada de família i grup muscular presents a l’HTML;
- versió correcta després d’una regeneració;
- fallback `None` per a codis sense asset.

Comandes de validació:

```powershell
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py test iatrain.tests.test_library --verbosity 1 --keepdb
docker compose exec -T web python manage.py test iatrain.tests --verbosity 1 --keepdb
git diff --check
git status --short
```

La revisió manual de la pàgina ha de cobrir:

- escriptori;
- amplada inferior a `860 px`;
- amplada inferior a `620 px`;
- targetes amb i sense portada;
- família amb moltes variants;
- detall amb imatge;
- detall sense imatge;
- text alternatiu i navegació per teclat.

Si la pàgina local exigeix autenticació i l’agent no té una sessió autoritzada, no ha d’inventar credencials ni modificar l’autenticació. Ha de deixar constància de la limitació i recolzar-se en tests de render fins que l’usuari faciliti una sessió.

## 12. Criteri de finalització d’un lot

Un lot només es pot marcar com a complet quan totes les respostes són afirmatives:

- [ ] S’han inventariat les variants del `batch` i les variants inicials relacionades.
- [ ] Cada variant té una fitxa de generació basada en les dades.
- [ ] La cara usa exclusivament referències d’`avatar/explaining`.
- [ ] Cada variant té un asset independent.
- [ ] Les famílies i els grups musculars necessaris estan coberts.
- [ ] S’ha fet QA visual per onades.
- [ ] S’ha repetit la QA contra `equipment` i el nom del catàleg.
- [ ] Les correccions han incrementat la versió sense sobreescriure l’acceptada.
- [ ] Només els WebP finals estan registrats al manifest.
- [ ] Les etiquetes de moviment coincideixen amb esquerra i dreta.
- [ ] Els tests específics i la suite d’`iatrain` passen.
- [ ] `git diff --check` no mostra errors.
- [ ] La documentació indica quin lot queda complet i quin és el següent autoritzat.

## 13. Fitxers que un agent ha d’entregar

Per un lot nou, el canvi mínim esperat és:

```text
iatrain/static/iatrain/library/exercises/*.webp
iatrain/static/iatrain/library/families/*.webp
iatrain/static/iatrain/library/groups/*.webp       # només si apareix un grup nou
iatrain/library_visuals.py
iatrain/tests/test_library.py
docs/biblioteca_iatrain.md
docs/generacio_imatges_biblioteca_iatrain.md       # actualitzar estat i decisions noves
```

Els canvis de plantilla o CSS només són necessaris si el lot introdueix una presentació que el sistema actual no pot representar.
