# Daglig evo-sjekk (instruks til Claude)

Dette er instruksen til den planlagte jobben som holder Evo Lab oppdatert. Eieren kan lese og endre den. Jobben starter uten noe minne fra tidligere samtaler, så alt den trenger å vite står her.

## Ukjent frist (regel fra eieren, 14.10.2026)

Mangler **alle** kilder fristen for å starte en evo, men to kilder er enige om krav og oppgraderinger: **legg evoen inn likevel**. Sett `"until_ukjent": true` (i stedet for `until`) og skriv i `note` at fristen er ukjent og hva kildene faktisk sier. Finn aldri på en dato. Evoer med `until_ukjent` fjernes ikke av opprydding på dato; fjern dem når ingen av listene (FUT.GG, futnext, FUTBIN) viser dem som åpne lenger, og sett inn `until` så snart en kilde oppgir fristen. Denne regelen går foran punkt 5 under når det bare gjelder fristen.

## Mål

Finn nye evoer i FC 27 Ultimate Team og legg dem inn i `data/auto_evoer.json`, riktig og kontrollert, slik at Evo Lab planlegger med dem. Eieren vil ha **riktige data eller ingenting**. En evo som mangler, er bedre enn en evo med feil tall.

## Tilgang

Repoet er `JbAl01/fc27-rating`. Er det ikke med i økten, kall `add_repo` med owner `JbAl01`, repo `fc27-rating`, access `push`. Lag **én** grunn klone (`git clone --depth 1`) i en egen mappe, ikke i arbeidsmappen. Du skal bare endre `data/auto_evoer.json`. Ikke rør kode, config eller andre filer.

## Viktig om nettilgang (lærdom 14.10.2026)

Når jobben kjører uten at noen er til stede, kan WebFetch bli stoppet med `PROVENANCE_REQUIRED` fordi tillatelsen for URL-en ikke blir besvart. Da får du ingen evoliste, og jobben svikter uten å finne noe. Derfor:
- **WebFetch avviser adresser med PROVENANCE_REQUIRED** hvis adressen ikke har kommet fra et WebSearch-resultat eller et tidligere WebFetch-svar. Det hjelper ikke at adressen står i denne instruksen eller i oppgaveteksten (testet 16.10.2026). Løsningen, som virker uten at noen er til stede: kjør WebSearch først, så blir adressene i resultatet hentbare. Gjør dette **før** du henter listene:
  1. WebSearch (mode standard) med query `evolutions` og `allowed_domains: ["futnext.com"]`. Gir https://www.futnext.com/evolutions. Side 2 (`?page=2`) og detaljsidene lenkes fra listesvaret og kan hentes etterpå.
  2. WebSearch med query `evolutions FC 27` og `allowed_domains: ["futbin.com"]`. Gir https://www.futbin.com/27/evolutions og noen detaljsider.
  3. FUT.GG: WebSearch `FC 27 evolutions fut.gg`, hent https://www.fut.gg/news/how-are-evolutions-changing-in-ea-fc-27-pathways-previews-and-more/ (be om lenkene til fut.gg/evolutions), og så https://www.fut.gg/evolutions/. Detaljsidene lenkes fra listesvaret.
  4. Feiler en detaljside med PROVENANCE_REQUIRED: kjør WebSearch med `allowed_domains` for domenet og evoens navn som query, og prøv igjen. WebFetch av forsiden https://futbin.com/ lister også detaljsider, men ikke selve listen.
  5. Skal en evo ha to kilder, kan futmind.com og destructoid.com-guider finnes via vanlig WebSearch.
- FUTBIN viser også evoer som ikke er åpnet ennå («Unlock» i uker). Lister og detaljsider (f.eks. https://www.futbin.com/27/evolutions/50/side-step) går bra via WebFetch. Evoer som ikke er åpne ennå, kan nevnes i `_hoppet_over` til en andre kilde har dem.
- Får du ikke hentet **noen** av listene, send varsel om at jobben ikke kunne kjøre, og si hvilken feil du fikk.
- Destructoid har guider per evo (https://www.destructoid.com/best-players-for-fc-27-<evo-navn>-evolution/) som gjelder som egen kilde, men de oppgir ofte ikke fristen. Frister finner du best på futnext (nedtelling) og FUT.GG; FUTBINs «Expires 2 weeks» er ikke en dato og kan ikke brukes alene.
- Evoer som gir et bestemt ferdig kort (f.eks. «Ones to Watch Retro 18/19/20») øker ikke tall og hoppes over.
- Sammenlign alltid med alle tre listene. En evo som bare står på én, er en kandidat som må bekreftes hos en annen kilde, ikke noe du kan se bort fra.

## Fremgangsmåte

1. **Hent listen over evoer som er åpne nå**, helst fra to kilder:
   - FUT.GG: https://www.fut.gg/evolutions/
   - futnext: https://www.futnext.com/evolutions (det er flere sider, se alle)
   - FUTBIN: https://www.futbin.com/27/evolutions (blokkerer ofte automatisk henting, bruk den som bonus)
   - RealSport101 og futmind.com har guider for nye evoer.
   Noter navn, kostnad og fristen for å starte evoen.

2. **Finn de nye.** Sammenlign med `key` og `name` i `config/evolab.json` (under `live`), `data/auto_evoer.json` og `data/mine_evoer.json` (finnes den, så er det eierens egne evoer, ikke rør den). Det som allerede står der, er ikke nytt.

3. **Hopp over** evoer som ikke endrer spillerens tall: merker, kortdesign (badges, «Golden Stars», «Pink Fire», «Prism Lights», «Arrow Spin» og lignende kosmetiske), og `… Roles++`-evoene. De siste er allerede regnet inn i reglene. Hopp også over evoer fra FC 26 eller eldre spill (for eksempel «Quick Step [FC 26 Obj]», som bare låses opp av FC 26-sesongpasset): de gjelder bare noen få og forvirrer.

4. **Hent detaljene for hver ny evo fra minst to ulike kilder** (egen side for evoen på FUT.GG, futnext, FUTBIN, eller en guide). Du trenger:
   - kostnad
   - fristen for å **starte** evoen, i UTC (ikke fristen for å fullføre målene)
   - krav: laveste og høyeste OVR, høyeste Pace, høyeste antall PlayStyles (`max_ps`) og PlayStyle+ (`max_psp`), posisjoner, rase/kortype, om evoen krever en annen evo først (`requires_evo`)
   - hvert nivå: hvilke attributter som økes, hvor mye og til hvilket tak («+X (maks Y)» blir `[X, Y]`), ny OVR, PlayStyles (med tallet EA viser som tak, f.eks. «Tiki Taka 3» blir `["Tiki Taka", 3]`), PlayStyle+ (`psp`), roller, svakfot og skill moves
   - ved valg (pathway): hvert valg som egen oppføring under `paths`, med en `label`

5. **To kilder må være enige** om kravene, tallene og fristen. Gjør de ikke det, eller finnes bare én kilde, så **ikke legg inn evoen**. Skriv den i `_hoppet_over` (se under) med en kort grunn. Enkeltdetaljer som bare én kilde har (f.eks. hvilken PlayStyle et valg gir), kan legges inn hvis resten er sikkert, men da må du forklare det i `note`, og bare det du faktisk så i kilden.

6. **Finn aldri på tall.** Står det ikke i kildene, så utelat feltet, eller hopp over evoen.

7. **Rydd:** fjern evoer fra `data/auto_evoer.json` hvis `until` var for mer enn 7 dager siden. Har kildene endret fristen eller tallene til en evo som allerede står i filen, så rett det.

8. **Sjekk filen:**
   ```
   python -m fcrating evo-sjekk
   python -m unittest discover -s tests
   ```
   Begge må gå uten feil. Feiler evo-sjekk for en evo du la inn, så rett den eller ta den ut. Push aldri en fil som ikke består.

9. **Lagre bare hvis noe er endret.** Er ingenting endret (ingen nye, ingen rettelser, ingen ryddede, ingen endring i `_hoppet_over`), så lag ingen commit, og avslutt med en kort melding om at alt var ajour.
   Ellers: commit til `main` og push. Commit-meldingen skal si hva som kom inn og fra hvilke kilder, f.eks. `Evo: la til Future Stars Academy III (FUT.GG, Futmind)`. Push til `main` starter GitHub-jobben som bygger siden på nytt (5–10 minutter).

## Format

`data/auto_evoer.json` har denne formen. Alle evoer ligger i `evos`.

```json
{
  "_info": "...",
  "_sjekket": "2026-10-14T03:00:00Z",
  "_hoppet_over": [{"navn": "Eksempel", "grunn": "Bare én kilde, kravene er uklare", "dato": "2026-10-14"}],
  "evos": [
    {
      "key": "future_stars_academy_3",
      "name": "Future Stars Academy III",
      "cost": "gratis",
      "until": "2026-10-26T17:00Z",
      "note": "Hva som er usikkert, hvis noe.",
      "req": {"min_ovr": 82, "max_ovr": 82, "max_ps": 7, "requires_evo": "future_stars_academy_2"},
      "up": {
        "ovr": [1, 83],
        "stats": {"finishing": [3, 80]},
        "ps": [["Tiki Taka", 3]],
        "paths": [{"label": "Valg A: fart", "ovr": [1, 83], "stats": {"sprint_speed": [3, 87]}, "ps": ["Rapid"]}]
      },
      "sources": ["https://www.fut.gg/evolutions/...", "https://www.futnext.com/evolutions/..."]
    }
  ]
}
```

- `key`: små bokstaver og understrek, unik. Samme `key` som i `config/evolab.json` betyr at den erstatter den evoen.
- `until`: ISO-tid i UTC med Z. Står bare en dato, regnes den som kl. 17:00 UTC. EA bytter innhold kl. 18:00 britisk tid, som er 17:00 UTC om sommeren og 18:00 UTC om vinteren (klokkene i Storbritannia stilles tilbake siste søndag i oktober). Er du usikker, bruk den tidligste tiden.
- Attributtnavn: `acceleration`, `sprint_speed`, `positioning`, `finishing`, `shot_power`, `long_shots`, `volleys`, `penalties`, `vision`, `crossing`, `fk_accuracy`, `short_passing`, `long_passing`, `curve`, `agility`, `balance`, `reactions`, `ball_control`, `dribbling`, `composure`, `interceptions`, `heading_accuracy`, `def_awareness`, `standing_tackle`, `sliding_tackle`, `jumping`, `stamina`, `strength`, `aggression`. Keepertallene begynner med `gk_`.
- Hovedtall (som «+2 Pace») legges i `face` med `pace`, `shooting`, `passing`, `dribbling`, `defending` eller `physical`.
- Svakfot og skill moves: `wf: [økning, maks]` og `sm: [økning, maks]`.
- Roller: `"roles": [["ST", "Advanced Forward", 2]]` (1 = +, 2 = ++).
- Se `config/evolab.json` for ferdige eksempler på alle felt, og README under «Evoene og hvor de kommer fra».

## Kontroll av det som allerede ligger inne

Står en evo i `config/evolab.json` som kildene ikke lenger viser som åpen, så ikke slett den. Den forsvinner av seg selv når fristen går ut. Nevn den i meldingen din til eieren.

## Avslutt

Svar med noen få linjer til eieren, på norsk: hva som ble lagt inn (med kilder), hva som ble hoppet over og hvorfor, og om noe ser rart ut. Ikke skriv noe som ikke stemmer med det du faktisk fant.
