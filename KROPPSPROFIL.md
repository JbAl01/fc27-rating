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

## Neste steg
1. Etter 1–2 kjøringer: sjekk i loggen at «Kroppstype kjent for X av Y kort» stiger, og at `hent-kropp` i dypsøket ikke feiler (`kropp.log`).
2. Sjekk kjente kort på siden: Mbappé og Messi (unik), Yamal (Lean Medium), Ekitiké og Barcola (Lean Tall), Haaland (unik og tung), en Stocky Tall-kant og et par bronse- eller sølv-evokort med Lean-kropp.
3. Juster tallene i `body_profile` etter eierens følelse. Eieren vil at kroppen skal veie mye.
4. Vurder egen sortering eller filter på kroppstype og et «skjult perle»-merke: god kropp, høy smidighet og lav OVR.
5. Valgfritt: et test-oppsett i Practice Arena (frame-telling) for å måle forskjeller mellom kroppstyper.

Research (to rapporter i samtalen 19.10) er grunnlaget: FUT.GG «What the Pros Use», EA Pitch Notes FC 26/27 (høyde styrer animasjonsfart og AcceleRATE) og ProClubsHQ (høyde og vekt endrer skjulte attributter). Det finnes ingen datamining av kroppstype-animasjoner, så tallene er en hypotese og kan justeres.
