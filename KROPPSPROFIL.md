# Kroppsprofil (body type i IGR): status og neste steg

Notat for å fortsette arbeidet senere (19.10.2026).

## Mål (eierens ønske)
Verktøyet skal måle **ingame-følelse**. Kroppstypen betyr mye for hvordan et kort føles: animasjoner, hvor smooth det er, og hvordan samme attributt slår ut (90 Agility på Mbappé-kroppen er ikke det samme som 90 Agility på et vanlig 83-kort). Kroppstypen skal veie mye, litt under attributtene, og særlig hjelpe å finne skjulte perler blant promokort og bronse-, sølv- og gull-evokort. Eierens erfaring går foran det EA sier. Rapid er fortsatt «WOW» selv om EA sier den er svekket. Lean Tall med Technical+ føltes «WOW» i FC 26.

## Ferdig og pushet
- **Data:** `fcrating/sources/futgg.py` `parse_body()` leser `bodytypeCode` og teksten «Body Type» og vekten fra FUT.GG-kortsiden. Kodene 1–9 er standardkroppene. Kode 10 og høyere er unike modeller, og der viser FUT.GG spillerens navn.
  - Kodene: 1 Lean Medium, 2 Average Medium, 3 Stocky Medium, 4 Lean Tall, 5 Average Tall, 6 Stocky Tall, 7 Lean Short, 8 Average Short, 9 Stocky Short.
  - Bekreftet med en probe 19.10: Mbappé, Haaland og Messi har 10 (Unik), Yamal 1, Bonmatí 8 og Ekitiké 4.
- **Henting:** basekort uten `bt` hentes på nytt i den vanlige kjøringen (900 per kjøring). Den nye kommandoen `python -m fcrating hent-kropp --minutter 60` går i bakgrunnen under dypsøket (`dypsok.yml`), med 2,5 s pause mellom sidene (`config/sources.json` `body_delay_seconds`).
  - Én side per spiller, fordi promo- og evokort arver kroppen via `cli._fill_body`.
  - Cachen lagres trygt via en midlertidig fil og `os.replace`.
  - Omtrent 19 800 spillere. Rundt 2–3 døgn før alle er hentet.
- **Scoring:** `fcrating/body.py` (`BodyCard`), med config i `config/weights.json` → `body_profile`. Formelen er poeng = grunnpoeng(bygning × størrelse × posisjon) + forsterkning × smidighet + kombinasjon med PlayStyles, avgrenset per posisjon.
  - **Smidighet:** vektet snitt av Agility .4, Balance .3, Dribbling .15 og Ball Control .15, regnet som (snitt − 72) / 18, med tak 1,4.
  - **Forsterkning:** Lean Medium 1,0 … Stocky Tall 0, ganget med en skala per posisjon (W 3,0, ST 2,6, CAM 2,8, CM/FB 1,8, CDM 1,0, CB 0,6).
  - **Unike modeller:** størrelse fra høyden og bygning fra BMI, forsterkning +0,45 (maks 1,15), pluss et fast tillegg per posisjon.
  - **Kombinasjoner:** Technical, Rapid, Quick Step og Trickster på Lean- og unike kropper, First Touch på høye kropper, og Bruiser og Jockey for forsvarere. Taket er 1,5.
  - **Uten kroppstype:** finnes høyde og vekt, anslås kroppen fra dem med halv vekt. Ellers gir den 0 og en advarsel.
  - **Spenn:** test med samme attributter ga Lean Medium W 85,5 mot Stocky Tall W 78,0, altså ca. 7,5 poeng.
- **Gammel kroppstypejustering:** `feel.body_type` (±0,5) er satt til 0, så kroppen ikke telles to ganger.
- **Brukes overalt:** `model.rate_group` (feltene `body` og `body_detail`), `evolab.FastRater` (inkludert øvre grense med alle kombinasjoner), JS-rateren i `evolab_page.html` (`c.bd` og `R.bd`), Players-siden (raden «Kroppstype» og bonusene i utregningen), Evo Lab-detaljen (raden «Kroppstype»), `explain.py` (linjen «Kropp:») og fingeravtrykket i evolab-cachen (nå også med vekt).

## Endret 19.10 kveld (gjennomgang)
- **Forsterkning målt mot vanlig kropp:** forsterkningen måles nå mot en vanlig kropp (Average Medium = 0). Agility og Balance telles allerede i følelsen og off-balance, så kroppspoengene måler bare det kroppen legger til eller trekker fra.
  - Lean Medium +0,5, Lean Short +0,35, Lean Tall +0,3, Average Short +0,2, Average Tall −0,15, Stocky −0,1 til −0,3, unike modeller +0,4 (maks 0,7).
- **Mindre høydestraff for Lean:** Lean-kropper får bare halve høydestraffen i følelsen (`feel.height.lean_penalty_factor` 0,5).
- **Icons og Heroes:** de har ikke basekort, så kroppstypen hentes fra det beste spesialkortet deres (`fetch_bodies`), og kortene deles per spiller via `futgg.player_key`.
- **Evo Lab:** raden «Kroppstype» i Evo Lab regnes nå i nettleseren og viser tall før og etter evo.
- **Meta:** startnivået lagrer nå startkortene (`data/meta_start.json` → `cards`, fra 16.10) og regnes på nytt med dagens formel. Endringer i formelen ser dermed ikke lenger ut som at metaen beveger seg. Før var ST-nivået blåst opp med ca. 2,9.
- **Ny keeper-PlayStyle:** 1v1 Close Down (FC 27, erstatter Rush Out) er lagt inn. Før ga den 0.

## Lagt til 19.10 kveld (sammenheng)
- **Posisjonsjustering** (`weights.json` → `position_calibration`): IGR flyttes per posisjon, så medianen av IGR minus OVR blir 0 overalt. Rekkefølgen innen hver posisjon endres ikke. Justeringen er kalibrert 19.10 med kroppstype kjent for bare 2 676 kort, så den må kalibreres på nytt når alle er hentet: `python -m fcrating kalibrer-posisjon data/ea_players.json data/spesialkort.json --lagre`. Den brukes i model, FastRater og JS, på siden («posisjonsjustering» i utregningen) og i explain.
- **Skjult perle** (`fcrating/gems.py`, `weights.json` → `hidden_gem`): IGR mot snittet av kort med samme OVR (±1) i posisjonen. Et kort er perle når det er blant topp 2 % og minst +4 over snittet. Siden viser hva som løfter kortet. Filteret «skjulte perler» bruker både dette og løps-perlene.
- **Meta i spillet** (`fcrating/sources/futgg_usage.py`): FUT.GG «Most Used Players», med proffene (ca. 195 lag) og FUT.GG-lagene (ca. 335 000). Siden hentes én gang per kjøring i FUT.GG-delen av `fetch-specials` og lagres i `data/cache/futgg/bruk.json`. Den vises på kortene med eget filter. Den er ikke med i IGR, fordi bruk også styres av pris og hvor mange kort som finnes, men hver kjøring skriver en «Modellsjekk».
  - **Modellsjekk 19.10:** 85 kort proffene bruker hadde median topp 0,9 % i posisjonen hos oss, og ingen lå utenfor topp 10 %. 78 kort FUT.GG-lagene bruker hadde median topp 1,0 %.
  - **Kort vi ikke fant:** 86 av de brukte kortene fantes ikke hos oss, trolig nye promokort eller annen ID. Bør undersøkes.
- Om-siden har fått en egen del, «Slik regnes IGR».

## Lagt til 19.10 sent (selvkalibrering)
- **Kilde:** FUT.GG «pros» er 195 vanlige FUT-lag (Rare Gold, OTW, TOTW og Heroes), ikke lag fra turneringer med kortregler. FUT.GG-lagene er 335 000 vanlige FUT-lag. Begge teller like mye.
- **Kroppspoeng** (`fcrating/selfcal.py`): hver kjøring tilpasser en logistisk modell (sjanse for å bli spilt gitt IGR, per posisjon og kilde) med ett tillegg per kroppstype, felles og per familie (angrep / midtbane og back / midtstopper).
  - Modellen bruker én rad per spiller og posisjon, med IGR uten tidligere lærte poeng, og bare kroppstyper som er hentet (ikke anslåtte).
  - Tilleggene krymper mot 0 når få kort støtter dem (krever minst 4 spilte spillere med kroppen), og de sentreres. Halvparten brukes (50/50 hypotese/data), med tak ±1,0.
  - Tallene glattes over kjøringene og endres bare ved utslag på minst 0,2.
  - De lagres i `data/cache/kalibrering.json` og brukes fra neste kjøring via `load_config`, i `body_profile.learned`, `BodyCard.const` og `learn` i detaljene. Siden viser «(+x av det fra hva folk spiller)».
- **Posisjonsnivå:** regnes også automatisk hver kjøring (median IGR − OVR = 0, endres ved utslag på minst 0,3) og overstyrer `weights.json`. `kalibrer-posisjon` trengs ikke lenger.
- **Testliste:** `output/testliste.txt` (på siden som `/testliste.txt`, ikke lenket) har to deler: kort som spilles mye men ligger utenfor topp 5 % hos oss, og vanlige gullkort i topp 1 % som ingen spiller. Eieren tester bare disse.
- **Første måling 19.10:** 94 spilte spillere med kroppstype. Data sier at høye kropper (Average og Lean Tall) spilles mer enn IGR tilsier, særlig på midtbane og back (+0,6 etter halvering), og at unike kropper i angrep er litt overvurdert (−0,3).
- **Evo Lab:** de lange kildenotatene og «Sjekk selv» under evoene er fjernet fra siden. Notatene står fortsatt i `auto_evoer.json`.

## Lagt til 20.10 (filtre)
- **Players:** to nye filtergrupper som kan kombineres med alle de andre filtrene.
  - **Kropp:** bygning (Lean, Average, Stocky eller unik modell), størrelse og laveste kroppspoeng.
  - **PlayStyles:** knapper for hver PlayStyle. Ett klikk betyr at kortet har den, to klikk betyr PS+ og tre klikk slår den av. Alle valgte må finnes.
  - Kolonnen og sorteringen «Kropp» er lagt til, og «Kroppspoeng» kan brukes i «Ranger etter snittet av».
- **Evo Lab:** bygning og størrelse, og PlayStyle-knapper som regnes etter evoene (planen nå eller anslaget). Kolonnen og sorteringen «Kroppspoeng etter evo» er lagt til.
- **Likhet:** «Ligner på» og «Lignende» tar nå med bygningen (Lean 100, Average 50, Stocky 0) og om kortet har en unik modell (`run_ai.similar.features` kropp 1,2 og unik 0,6). «Lignende» på Players viser prosent.
- **Data:** `rate()` gir feltet `frame` (`body.frame_code`: bygning, størrelse, unik, anslått). Det ligger som r[43] i Players-dataene og som c[16] i Evo Lab-dataene.

## Rettet 20.10 (Evo Lab-omregning og likhet)
- **Omregning:** med «Ligner på» startet omregningen på nytt fra 0 % hvert 0,4 sekund, og ble aldri ferdig på mobil. Nå regnes bare det tabellen trenger.
  - En brukt evo kan aldri gjøre planen bedre, så verdien med alle evoer er et tak. Kortene regnes ovenfra og ned, og siden stopper når de 100 øverste er sikre. Resten regnes når de trengs, for eksempel ved «Vis 100 til» eller et nytt filter.
  - Ved sortering på «Likhet» får IGR-planen en rask reparasjon: planen uten de brukte evoene.
  - Målt med 6 brukte evoer (blant dem Technical, som berører 11 329 kort), på mobil-hastighet: «Plass etter evo» ca. 67 s og «Ligner på» Dembélé ca. 36 s, mot aldri ferdig før.
- **Likhet:** «Ligner på» og «Lignende» sammenligner nå hele kortet.
  - Bevegelse, følelse, høyde (den hadde falt ut via `run_ai.dropped`), vekt, bygning, unik modell, AcceleRATE, posisjonstall og hvor mange PlayStyles som er felles.
  - Mangler kortet høyde, vekt eller kroppstype, regnes det som et gjennomsnittskort på det punktet.
  - Kroppen har faste skalaer, og hvert tall kan bidra med høyst 3 standardavvik.

## Kroppsmodell 2 (20.10, eierens ønske)
- **Kroppen forsterker:**
  - Positive grunnpoeng gis med 35 % fast. Resten ganges med smidigheten fra 65 til 90 (`body_profile.flex`). En god kropp er altså verdt litt også på et lavt kort, og Evo Lab gir resten når evoene øker Agility og Balance.
  - Negative grunnpoeng gis alltid fullt.
- **Rykte** (`body_profile.reputation`, eierens liste): poeng uansett tall, ganget med posisjonsfaktoren. Nå står Mbappé +2,0, Dembélé +1,5, Kim Little +1,5 og Kanu (FUT Heroes) −1,5. Nye navn legges inn når eieren sier fra.
- **Unik modell:** ingen fast bonus.
  - Den forsterker smidigheten litt mer enn en vanlig kropp med samme bygning (`unique.amp_bonus` 0,25). Et smidig kort med unik modell får derfor ca. +0,6 til +0,8 på kant eller spiss, mens et tregt eller tungt kort får 0.
  - Kjente kropper får i tillegg rykte.
- **Rykte smitter** (`reputation.spread`): en kjent god eller dårlig *vanlig* kroppstype gir del av ryktet til andre kort med samme kroppstype, samme kjønn og nær høyde og vekt.
  - Delen er 50 % ved lik høyde og vekt, og 0 ved 4 cm eller 6 kg fra.
  - Pluss ganges med smidigheten (som flex), mens minus gis fullt.
  - Unike modeller deles ikke.
  - `cli._rep_frames` henter de kjente kroppene med høyde og vekt når kortene lastes.
- **Press Proven** (EA: «close control … at jog speed»):
  - Relevansen er hevet til A/S, og synergien er Ball Control, Dribbling og Agility, så gode driblere får mest.
  - Den har fått en egen kombinasjon med kroppen, 0,3/0,8.
- **Følelse med ball:** «Følelse» i tabellene, sorteringen og filtrene (Players og Evo Lab) er følelse + kroppspoeng. I IGR er de fortsatt to deler, så ingenting telles dobbelt.
- **Eierens tester** (`data/eier_tester.csv`, semikolon): tester med ball kan sammenligne kort fra ulike posisjoner. Hver kjøring skriver «Eierens tester: … enig». Første test: Little > Kanu.

## Eierens dokument 20.10 (ChatGPT: «Bodytype Community Tier System»)
- **Hva dokumentet er:** et forskningsopplegg med kandidater å teste, ikke en fasit. Det sier selv at belegget for spillerne er svakt (nivå C, Reddit-anekdoter).
- **Tatt inn:**
  - Unik betyr ikke best (var allerede gjort).
  - Kroppen vurderes per rolle (allerede `frame_points` per posisjon).
  - Korte, lette kropper er litt opp for W, ST og CAM.
  - Første prioritet fra communityen står i `reputation.community` med +0,5 (Messi, Neymar, R9, Ronaldinho, Maradona). Eierens egne vurderinger går foran.
- **Ikke tatt inn:** de sju animasjonskomponentene (left-stick, vending, stride og så videre). De kan ikke måles fra kortdata, bare testes i spillet. Testplanen i dokumentet er det samme som eierens tester (`data/eier_tester.csv`).

## Én modell, ingen dobbel telling (20.10)
Revisjonen fant 7 steder der samme effekt ble telt flere ganger. Alle er rettet, og `tests/test_ingen_dobbel.py` passer på at det ikke skjer igjen.

| Hva | Før | Nå (telles ett sted) |
|---|---|---|
| Høyde | i følelsen (EA: animasjonsfart) og i kroppstypens størrelse | bare i følelsen. Størrelsen gir forskjell bare for CB (rekkevidde) |
| Smidighet × kropp | forsterkning og fleks-regel | én forsterkning (Lean 0,8, Average 0, Stocky −0,2). Lean har 35 % fast grunn |
| Press Proven | PlayStyle-verdi, kroppskombinasjon og «vanskelig å stoppe» | bare PlayStyle-verdien |
| Rapid, Enforcer, Bruiser, Quick Step | PlayStyle-verdi og «vanskelig å stoppe» | bare PlayStyle-verdien. Stopp-tallet på siden viser dem fortsatt |
| Acceleration og AcceleRATE | i følelsen og i farten | bare i farten. Følelsen er kontroll med ball |
| Unik modell med rykte | generell unik-bonus og ryktet | bare ryktet. Community-rykte 0,8, omtrent som den generelle bonusen |
| Selvkalibrering | tall lært på en gammel modell ble brukt videre | forkastes når modellen endres (`model_signature`) |

Effektiv vekt per attributt i IGR (målt):
```
IGR-økning per attributtpoeng (80 -> 90, Lean Medium 178 cm, uten PlayStyles), i % av summen per posisjon
                      ST     W   CAM    CM   CDM    FB    CB
Agility             13.7  15.1  14.9  10.6   6.8   8.6   5.6
Acceleration         9.7  11.1   6.6   6.2   6.8  13.8  11.1
Balance             11.3  11.9  11.6   8.0   5.1   6.0   2.8
Reactions            8.9   7.9   9.1   8.8   8.5   6.0   7.4
Ball Control         8.1   9.5  10.7  10.6   5.9   6.0   2.8
Standing Tackle      0.0   0.0   0.0   7.1  16.1  12.9  17.6
Sprint Speed         7.3   7.9   5.0   3.5   5.1  11.2  11.1
Dribbling            8.1  11.1  10.7   5.3   2.5   5.2   0.9
Short Passing        1.6   3.2   6.6   9.7   6.8   4.3   2.8
Composure            4.8   4.0   5.8   7.1   4.2   3.4   3.7
Interceptions        0.0   0.0   0.0   4.4   9.3   5.2   7.4
Def. Awareness       0.0   0.0   0.0   1.8   7.6   6.0  10.2
Att. Position        8.1   4.8   4.1   0.0   0.0   0.0   0.0
Strength             3.2   1.6   0.8   0.0   4.2   1.7   5.6
Vision               0.0   1.6   5.8   6.2   2.5   0.0   0.0
Stamina              0.8   0.8   0.0   4.4   4.2   4.3   0.0
Finishing            6.5   3.2   3.3   0.0   0.0   0.0   0.0
Long Passing         0.0   0.0   0.8   5.3   3.4   0.0   0.0
Long Shots           1.6   2.4   3.3   0.9   0.0   0.0   0.0
Crossing             0.0   1.6   0.0   0.0   0.0   3.4   0.0
Heading Accuracy     1.6   0.0   0.0   0.0   0.0   0.0   3.7
Sliding Tackle       0.0   0.0   0.0   0.0   0.0   1.7   2.8
Shot Power           3.2   0.0   0.0   0.0   0.0   0.0   0.0
Curve                0.0   2.4   0.8   0.0   0.0   0.0   0.0
Jumping              0.0   0.0   0.0   0.0   0.0   0.0   2.8
Aggression           0.0   0.0   0.0   0.0   0.8   0.0   1.9
Volleys              1.6   0.0   0.0   0.0   0.0   0.0   0.0
Penalties            0.0   0.0   0.0   0.0   0.0   0.0   0.0
FK Accuracy          0.0   0.0   0.0   0.0   0.0   0.0   0.0
```

## Neste steg
1. Etter 1–2 kjøringer: sjekk i loggen at «Kroppstype kjent for X av Y kort» stiger, og at `hent-kropp` i dypsøket ikke feiler (`kropp.log`).
2. Sjekk kjente kort på siden: Mbappé og Messi (unik), Yamal (Lean Medium), Ekitiké og Barcola (Lean Tall), Haaland (unik og tung), en Stocky Tall-kant og et par bronse- eller sølv-evokort med Lean-kropp.
3. Juster tallene i `body_profile` etter eierens følelse. Eieren vil at kroppen skal veie mye.
4. Vurder egen sortering eller filter på kroppstype og et «skjult perle»-merke: god kropp, høy smidighet og lav OVR.
5. Valgfritt: et test-oppsett i Practice Arena (frame-telling) for å måle forskjeller mellom kroppstyper.

Research (to rapporter i samtalen 19.10) er grunnlaget: FUT.GG «What the Pros Use», EA Pitch Notes FC 26/27 (høyde styrer animasjonsfart og AcceleRATE) og ProClubsHQ (høyde og vekt endrer skjulte attributter). Det finnes ingen datamining av kroppstype-animasjoner, så tallene er en hypotese og kan justeres.
