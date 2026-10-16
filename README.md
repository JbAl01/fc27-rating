# FC 27 Ingame-rating (IGR)

Din egen rating av FC 27-spillere. Den måler hvor god en spiller *føles og er* i spillet, ikke bare hva OVR sier. Hver spiller får en IGR per posisjon og sammenlignes bare med spillere som kan spille samme posisjon. En spiss rangeres altså aldri mot en CDM. Du får plassering, bokstavkarakter (S–D), evo-potensial og en forklaring av hvert tall.

Krever bare Python 3.9 eller nyere. Ingen pakker må installeres.

## Kom i gang

```bash
# 1. Hent alle basekort fra EAs database (ca. 200 sider, tar noen minutter)
python -m fcrating fetch-ea

# 2. Hent Icons, Heroes, TOTW, kampanjekort og lekkasjer (første gang tar det en stund)
python -m fcrating fetch-specials

# 3. Rater alt og lag rapport, med rangering per posisjon
python -m fcrating rate data/ea_players.json data/spesialkort.json

# Eller la alt gå av seg selv: henter og rater hver 6. time
python -m fcrating watch

# Åpne output/rapport.html i nettleseren

# Se hele utregningen for én spiller, med plassering i hver posisjon
python -m fcrating explain data/ea_players.json --name Haaland

# Evo Lab: hvor gode kortene kan bli med evoer (output/evolab.html lages av rate)
python -m fcrating evolab data/ea_players.json data/spesialkort.json --maks-ovr 79 --group ST

# Enkel rangering av evo-kandidater
python -m fcrating evo data/ea_players.json data/spesialkort.json
python -m fcrating evo data/ea_players.json --group W --sort gevinst

# Løps-AI: skjulte perler og kort som løper som et kort du liker
python -m fcrating perler data/ea_players.json data/spesialkort.json --group ST
python -m fcrating lignende data/ea_players.json data/spesialkort.json data/eksempel_spillere.json --name Geyse

# Tilpass Løps-AI til løp du har talt selv (se «Løps-AI» under)
python -m fcrating kalibrer data/ea_players.json data/spesialkort.json

# Sjekk modellen mot det du kjenner i spillet: blinde A-mot-B-tester (se «Slik blir systemet mer treffsikkert»)
python -m fcrating test-par data/ea_players.json data/spesialkort.json --a "Pichon" --b "Vicky López" --vinner a --styrke 2
python -m fcrating evaluer data/ea_players.json data/spesialkort.json

# Uten nett: prøv med eksempelspillerne
python -m fcrating rate data/eksempel_spillere.json

# Kjør testene
python -m unittest discover -s tests
```

På Windows bruker du `py` i stedet for `python` hvis `python` ikke finnes. Du kan også dobbeltklikke `start.bat` (Windows) eller kjøre `./start.sh` (Mac), som rater alle filene i `data/` og åpner rapporten.

IGR er på samme skala som OVR, men kan gå over 99 for de aller beste kortene fordi bonusene legges oppå.

### Oppdatere til en ny versjon av programmet

Pakk ut den nye zip-filen oppå den gamle mappen. `data/` (EA-kortene, spesialkortene og alt som er lagret fra FIFA Rosters og RealSport101) blir liggende, så ingenting må hentes på nytt. Bygg spesialkortene på nytt fra det som er lagret, og rater:

```bash
py -m fcrating fetch-specials --offline
py -m fcrating rate data/ea_players.json data/spesialkort.json
```

## Legge ut siden for vennene dine

Det enkleste er GitHub Pages. Det er gratis, siden oppdateres av seg selv fire ganger i døgnet, og PC-en din trenger ikke stå på. Du trenger bare en GitHub-konto. Siden er åpen for alle som har lenken, men søkemotorer får ikke ta den med, så i praksis ser bare de du sender lenken til den.

```
GitHub: fire ganger i døgnet hentes nye kort, alt rates og siden legges ut  →  https://BRUKERNAVN.github.io/fc27-rating/  →  du deler lenken
```

### Slik gjør du det

1. Kjør `py -m fcrating publiser` én gang. Da lages `data/side.json`. Skriv navnet ditt i `eier` og en e-postadresse i `kontakt`. Begge vises på `om.html`, så bruk en adresse du er komfortabel med å vise.
2. Lag en gratis konto på github.com. Installer GitHub Desktop og logg inn.
3. I GitHub Desktop: File > Add local repository. Velg mappen `fc27-rating`, trykk «create a repository» og så Create repository.
4. Trykk Publish repository. **Fjern haken ved «Keep this code private».** GitHub Pages er bare gratis for offentlige repoer. Koden blir synlig, men kortdataene og dine egne filer blir ikke med (se `.gitignore`).
5. På github.com: repoet > Settings > Pages. Under Source velger du **GitHub Actions**.
6. Gå til Actions > Oppdater siden > Run workflow. Første gang tar det 45–60 minutter, fordi alt hentes fra bunnen. Senere tar en runde noen minutter.
7. Lenken står i Settings > Pages og i kjøringen: `https://BRUKERNAVN.github.io/fc27-rating/`. Send den til vennene dine.

Når du publiserer i punkt 4, starter en kjøring av seg selv. Rekker den å bli ferdig før du har gjort punkt 5, stopper den på slutten med «Get Pages site failed». Det gjør ingenting. Trykk Run workflow igjen. Da går det fort, fordi dataene er lagret.

### Hva som oppdateres, og når

- **Fire ganger i døgnet** kommer nye spesialkort, TOTW, kampanjer og lekkasjer, og rangeringen og evo-planene regnes ut på nytt. **Kveldsrunden starter kl. 19:25 norsk tid**, 25 minutter etter at EA bytter innhold kl. 19:00 (18:00 britisk tid), og er ferdig ca. 19:35–19:50. De tre andre er ca. 03:25, 09:25 og 15:25 (sommertid; om vinteren en time tidligere. Kveldsrunden holder seg på 19:25 hele året). GitHub kan være 5–20 minutter sen. Vil du oppdatere med en gang, trykk Run workflow.
- **Evo-sjekken** går kl. 19:08 og 19:45 norsk tid hver dag. Den første er rett etter at nye evoer er ute i spillet, og den bygger siden på nytt hvis den fant noe.
- **Evoer som stenger**, forsvinner fra planene neste runde. Siden viser i tillegg «stengt» ut fra klokka til den som ser på.
- **Nye evoer** legges inn av en daglig sjekk som Claude kjører (se «Daglig evo-sjekk» under). Den skriver til `data/auto_evoer.json`, og siden bygges på nytt etterpå. Vil du legge inn en evo selv, bruk `evo-import` (se «Holde evoene oppdatert»), og trykk Fetch/Pull før du trykker Commit og Push i GitHub Desktop, siden sjekken også pusher til repoet.
- **Ny versjon av programmet:** pakk ut zip-filen oppå mappen, og trykk Commit og Push.
- **Brukte evoer:** siden regner som om ingen evoer er brukt opp. Hver venn huker av sine egne under «Brukt» i Evo Lab, og det lagres bare i nettleseren deres.

### Daglig evo-sjekk

Programmet kan ikke lese evo-sider selv (FUTBIN blokkerer det, og HTML-en endrer seg). Derfor sjekker en planlagt oppgave hos Claude nye evoer hver dag. Instruksen står i `EVO-JOBB.md`. Kort fortalt:
- Den leser evolistene på FUT.GG, futnext og FUTBIN, og finner evoer som ikke er med ennå.
- Den legger bare inn en evo hvis **to kilder er enige** om krav, tall og frist. Er de uenige, eller finnes bare én kilde, hoppes evoen over og står i `_hoppet_over` i `data/auto_evoer.json`.
- Den sjekker filen (`py -m fcrating evo-sjekk`) og kjører testene før den pusher. Er ingenting nytt, gjør den ingenting.
- Evoer fra sjekken vises i Evo Lab på lik linje med de andre, med lenker til kildene. Din egen `data/mine_evoer.json` overstyrer evoer med samme key.
- Den kan ta feil eller gå glipp av en evo. Står noe som ikke stemmer, så si fra, eller rett det i `data/auto_evoer.json` og push.

### Gratis, og hvor lenge

- **Actions:** gratis uten minuttgrense i offentlige repoer.
- **Pages:** maks 1 GB per side og rundt 100 GB trafikk i måneden. Med 20 000 kort sendes rangeringen som ca. 3,5 MB og Evo Lab som ca. 5 MB (komprimert). Det rekker til over 10 000 besøk i måneden.
- **Pause etter 60 dager:** i offentlige repoer setter GitHub de faste kjøringene på pause etter 60 dager uten endringer, og du får e-post om det. Hver evo du pusher, teller som en endring. Ellers: Actions > Oppdater siden > Enable workflow.

### Det juridiske (bygd inn)

Jeg er ikke advokat, men dette er gjort for å holde seg innenfor EAs regler for fanprosjekter og personvernreglene:

- **Ikke-kommersiell:** ingen reklame, betalingsmur, Patreon eller donasjoner. Behold det slik. GitHub Pages tillater heller ikke kommersielle sider.
- **Ansvarsfraskrivelse:** nederst på hver side og på `om.html`, på norsk og med EAs egen engelske tekst: «This website is not endorsed by or affiliated with EA or its licensors.»
- **Ingen EA-grafikk:** ingen logoer, kortbilder eller spillgrafikk. Ikonet er laget for prosjektet.
- **Kilder:** `om.html` viser hvor tallene kommer fra, med lenker, og hver evo lenker til sine kilder.
- **Ingen rådata:** `publiser` tar ikke med `ratings.csv`, `ratings.json` eller `evolab.csv`, og kortdataene ligger ikke i repoet.
- **Fjerning:** `om.html` sier at rettighetshavere kan få ting fjernet, og viser kontakten din.
- **Personvern:** ingen innlogging, sporing, analyse, reklame eller informasjonskapsler, så du trenger ikke samtykkebanner. Valgene lagres bare i nettleseren til den som ser på (localStorage). `om.html` forklarer det, og at GitHub lagrer IP-adresser av sikkerhetshensyn.
- **Skrifttyper på siden selv:** ingenting hentes fra Google Fonts. En tysk domstol sa i 2022 at det sender IP-adressen ulovlig til Google.
- **Ikke i søk:** hver side har `noindex`.

### Vil du ha innlogging?

Skal bare de du har valgt komme inn, kan siden ligge på Cloudflare Pages bak Cloudflare Access: vennene logger inn med e-posten sin og en engangskode. Det er også gratis, og repoet kan da være privat. Men det tar mer oppsett, og Cloudflare ber om kort eller PayPal (de trekker ingenting).

1. Flytt `ekstra/cloudflare-oppdater.yml` til `.github/workflows/`, og slett `.github/workflows/oppdater.yml`. Skriv `cloudflare-access` i `innlogging` i `data/side.json`.
2. Lag en gratis konto på cloudflare.com. Gå til My Profile > API Tokens > Create Token > Create Custom Token. Gi nøkkelen tilgangen Account, Cloudflare Pages, Edit.
3. På GitHub: Settings > Secrets and variables > Actions. Legg inn `CLOUDFLARE_API_TOKEN` (nøkkelen) og `CLOUDFLARE_ACCOUNT_ID` (står under Workers & Pages i Cloudflare).
4. Run workflow. Siden havner på `https://fc27-rating.pages.dev`.
5. Lås den: Workers & Pages > prosjektet > Settings > General > Enable access policy. Gå så til Zero Trust > Access > Applications > prosjektet > Configure. Fjern `*.` foran domenet og lagre. Under Policies velger du Allow, så Include > Emails, og legger inn e-postene til vennene dine.

Vil du ikke bruke Access, kan du låse siden med ett felles passord i stedet. Legg inn en Secret som heter `SIDE_PASSORD` under Settings > Variables and Secrets i Pages-prosjektet, og skriv `passord` i `innlogging`.

### Hvis GitHub blir blokkert

FIFA Rosters eller EA kan stenge for maskiner i datasentre. Da står «feilet» i loggen under «Hent spesialkort». Siden legges fortsatt ut, men med dataene fra forrige gang. Da kan PC-en din hente kortene i stedet. `publiser.bat` henter, rater og laster opp til Cloudflare Pages. Den trenger Node.js og at du har kjørt `npx wrangler login` én gang.

### For hånd

```
py -m fcrating rate data\ea_players.json data\spesialkort.json --ignorer-brukte
py -m fcrating publiser            # lager site/ (det som legges ut)
```

Er en side over 20 MiB, legges kortdataene i egne filer (`evolab-data-1.js` osv.).

## Kommandoer

| Kommando | Hva den gjør |
|---|---|
| `rate FILER... [--chem none/best/Finisher] [--group ST] [--uten-evolab] [--ignorer-brukte]` | Rater spillere fra JSON eller CSV, rangerer dem per posisjon og skriver `output/ratings.csv`, `ratings.json`, `rapport.html`, `evolab.html` og `om.html`. `--ignorer-brukte` regner som om ingen evoer er brukt opp (for siden du deler). `--lagre-meta-start` lagrer startnivået for Meta hvis det mangler |
| `explain FILER... --name NAVN` | Forklarer hvorfor spilleren ligger der han ligger, viser evo-potensialet og hele utregningen |
| `evo FILER... [--group W] [--sort etter/gevinst]` | Rangerer kortene som kan evolueres: IGR nå og etter, gevinst og plass før og etter |
| `perler FILER... [--group ST] [--alle] [--sorter iq\|effekt\|stopp] [--min-iq N] [--min-effekt N]` | Skjulte perler: spisser, kanter og CAM-er som løper mye bedre enn kort med samme OVR |
| `evolab FILER... [--maks-ovr 79] [--group ST] [--horisont nå/s2/s4/aar] [--sorter forventet/tak/op/gevinst/dna/sikker] [--name NAVN]` | Evo Lab: evo-plan med evoene som er ute nå, og et anslag for resten av året |
| `evo-sjekk [FIL] [--min-kilder 2]` | Sjekker evo-filen (standard `data/auto_evoer.json`) for feil: ukjente attributter og PlayStyles, ugyldige tall og datoer, for få kilder |
| `brukt [NAVN...] [--fjern NAVN] [--tom]` | Evoer du har brukt opp på andre kort. Evo Lab og rapporten regner uten dem (lagres i `data/brukte_evoer.json`) |
| `evo-import tekst.txt [--til DATO] [--kostnad ...]` | Legger inn en ny evo fra tekst kopiert fra FUTBIN/FUT.GG (lagres i data/mine_evoer.json) |
| `kombo FILER... --kat følelse løp dribling [--group ST] [--min-ovr N] [--min-iq N] [--min-effekt N]` | Rangerer etter en kombinasjon av kategorier, også Løps-IQ, løpseffekt og stopp |
| `lignende FILER... --name NAVN [--group alle]` | Kort med mest lik løpsprofil som et kort du liker |
| `kalibrer FILER... [--fasit data/loep.csv] [--lagre]` | Tilpasser Løps-AI til løp du har talt selv, og viser hvilke tall som faktisk henger sammen med løpene |
| `test-par FILER... --a NAVN --b NAVN --vinner a/b/lik [--styrke 1-3] [--type alt/ball/løp] [--posisjon ST]` | Lagrer en blind test: hvilket av to kort som spilte best (i `data/tester.csv`) |
| `evaluer FILER... [--fil data/tester.csv]` | Hvor ofte IGR og hver del av modellen velger samme vinner som deg, og en rangering av kortene fra testene dine |
| `import-text side.txt --name ... --position ST` | Lager en spiller av tekst du har kopiert fra en spillerside |
| `fetch-ea [--dump-sample]` | Henter EAs ratingdatabase. `--dump-sample` lagrer ett rått svar så du kan sjekke formatet |
| `fetch-specials [--full] [--offline]` | Henter spesialkort fra FIFA Rosters og lekkasjer fra RealSport101, og lagrer dem i `data/spesialkort.json` |
| `watch [--interval 360] [--publiser] [--deploy]` | Henter EA-data og spesialkort, rater alt og oppdaterer rapporten med jevne mellomrom. Med `--publiser` lages også `site/`, og med `--deploy` lastes den opp |
| `publiser [--deploy]` | Lager `site/` til å legge ut for vennene dine: sidene, `om.html`, skrifttyper og ikoner, uten rådata. `--deploy` laster opp til Cloudflare Pages (se «Vil du ha innlogging?») |

`--group` tar `ST` (spiss), `W` (kant), `CAM`, `CM`, `CDM`, `FB` (back), `CB` eller `GK`.

## Sammenligning innen posisjon

Hver posisjonsgruppe (spiss, kant, CAM, CM, CDM, back, midtstopper, keeper) har sine egne vekter, og spillere rangeres bare mot spillere som kan spille samme posisjon. En spiller som har posisjonen som alternativ, tas med i den posisjonens rangering og merkes «alternativ».

`output/rapport.html` er en enkel tabell:

- **Søk, Posisjon og Sorter etter** øverst. «Alle, i sin egen posisjon» viser hvert kort i posisjonen det står i. Velger du en posisjon, ser du hele rangeringen der.
- **Kolonnene:** Pos (farget etter angrep, midtbane, forsvar og keeper), OVR, IGR, Plass («2 av 1 282»), Følelse (med off-balance under, «OB 87»), Fart, Ferdighet, Løps-AI (med Løps-IQ og effekt under), Stopp (med ball og uten ball under), PS, AcceleRATE, Etter evo og Pris. Trykk på en kolonne for å sortere.
- **Etter evo** er IGR med evoene som er ute nå, fra Evo Lab. Ikke anslaget for resten av året.
- **Filtre** (åpnes under søket): OVR fra–til, maks høyde, korttype, kjønn, minste følelse, off-balance og stopp, AcceleRATE, minste Løps-AI, Løps-IQ og effekt, PlayStyle (eventuelt bare PS+), skjulte perler, evo-kandidater, svakfot og skill moves 4 eller 5, og «Ranger etter snittet av» kategorier du liker. «Nullstill filtre» fjerner alle. Nettleseren husker filtrene.
- **Spesialkort** står i samme rangering som basekortene, med versjon under navnet og «lekket» eller «estimert» når det gjelder.
- **Tier** (S–D) brukes fortsatt i `explain` og CSV: S = topp 1 %, A = topp 5 %, B = topp 15 %, C = topp 35 %, D = resten.

### Meta: når bedre kort kommer

IGR er fast. Den kommer bare fra kortets egne tall, så et kort har samme IGR hele året. **Meta** er IGR målt mot kortene som finnes nå, slik GG-rating på FUT.GG fungerer:

- For hver posisjon følger vi snittet av de 50 beste kortene (lekkasjer telles ikke).
- Første gang GitHub-jobben kjører, lagres det snittet som startnivå i `data/meta_start.json`.
- Etterpå er Meta = IGR minus hvor mye snittet har steget siden start. Har de beste spissene blitt 3 bedre, har alle spisser 3 lavere Meta. En gull-spiss med IGR 91 viser da Meta 88.
- Meta blir aldri høyere enn IGR. Plass og bokstav synker også av seg selv, fordi de måles mot alle kortene som finnes.

Vil du starte Meta på nytt (for eksempel ved et nytt spill), slett `data/meta_start.json` i repoet. Antallet kort i snittet endrer du under `meta` i `config/weights.json`.

### Spillerprofil: hvordan kortet spiller

Hvert kort får åtte kategorier på samme skala som OVR: **følelse, fart, løp, dribling, avslutning, pasning, fysikk og forsvar**. Kategoriene er definert under `profile` i `config/weights.json`.

- **Stil:** en merkelapp ut fra kategoriene kortet er best på sammenlignet med kort i samme posisjon på omtrent samme nivå (±2 OVR), for eksempel «Kvikk dribler og løper», «Fysisk avslutter» eller «Playmaker». Er kortet jevnt, står det «Jevn profil». Stilen vises i tabellen og øverst på kortet.
- **Passer hvis du liker:** hva kortet egner seg til, for eksempel «kjappe vendinger og responsiv kontroll» eller «løp bak backlinja uten at du trykker».
- **Profil:** én søyle per kategori på kortet, med plassering i posisjonen.

**Ranger etter kombinasjon:** åpne «Filtre» og velg én eller flere kategorier under «Ranger etter». Kortene rangeres da etter snittet av plasseringene sine i de kategoriene, i kolonnen «Kombo» (100 = best i posisjonen). Vil du ha kort som føles som Aimar og Pichon, prøv følelse + løp + dribling. I terminalen:

```
py -m fcrating kombo data\ea_players.json data\spesialkort.json --kat følelse løp dribling --group ST --top 20
```

Uten `--group` vises hvert kort i sin egen posisjon. `--min-ovr 80` tar bare med kort på 80 eller mer.

**Filtrer på Løps-IQ, Effekt og Stopp:** Løps-AI er delt i to. **Løps-IQ** sier hvor og når spilleren løper (Att. Position, Reactions). **Effekt** sier om løpet skaper avstand til forsvareren: fart, smidighet, kropp, lav høyde og Stamina. **Stopp** er hvor vanskelig kortet er å stoppe med ball og på løp (se «Vanskelig å stoppe»). I rapporten kan du:

- sette «Løp, minst» → Løps-IQ og/eller Effekt, og «Med ball, minst» → Stopp, under «Filtre» (for eksempel Effekt 85 for kort som kommer fri når de løper),
- sortere etter «Løps-IQ», «Løpseffekt» eller «Vanskelig å stoppe» i sorteringsmenyen,
- velge dem under «Ranger etter», også sammen med andre kategorier (for eksempel følelse + løpseffekt + vanskelig å stoppe).

Tabellen viser Løps-IQ og effekt under Løps-AI-tallet («IQ 95, eff. 91»), og stopp med og uten ball under Stopp-tallet. De gjelder bare spisser, kanter og CAM-er, og de teller ikke i stil-merkelappen, siden Løp allerede gjør det. I terminalen:

```
py -m fcrating kombo data\ea_players.json data\spesialkort.json --kat følelse effekt --group ST
py -m fcrating kombo data\ea_players.json data\spesialkort.json --kat dribling --min-effekt 85
py -m fcrating perler data\ea_players.json data\spesialkort.json --alle --sorter effekt --min-iq 80 --group W
py -m fcrating kombo data\ea_players.json data\spesialkort.json --kat følelse stopp --group ST
```

### Hvorfor er kortet høyt?

Trykk på en rad i rapporten. Under raden står:

- **Én setning øverst:** IGR, plass i posisjonen, stilen og hva kortet passer til.
- **Ratingen:** følelse, fart, ferdighet, Løps-AI og Stopp med verdi, plass i posisjonen og hvor mye delen teller, pluss PlayStyles og bonuser (rolle, svakfot, skill moves, off-balance).
- **Med og uten ball:** off-balance (med eller ikke), stopp med ball, Løps-AI med plass og forskjell mot samme OVR, Løps-IQ, effekt, stopp på løp, AcceleRATE og høyde, og fem kort som løper likt. Trykk på et navn for å søke det opp.
- **Profil:** én søyle per kategori med plass i posisjonen.
- **Sterkest, Svakest og PlayStyles** som vanlig tekst, og hva evoene som er ute nå gir.
- **Utregning og kilde:** åpnes ved behov og viser hele formelen, alle posisjoner, kilden og merknader.

`explain` i terminalen viser det samme som tekst.

Prosenter og snitt vises bare når minst 10 kort kan spille posisjonen (`explain.min_pool_size` i `config/weights.json`).

**PlayStyles som mangler:** FIFA Rosters viser ikke PlayStyles. Kort uten basekort (for eksempel Icons) får derfor medianen for kort i samme posisjon med omtrent samme OVR (±3), merket «PS anslått». Sett `playstyles_missing.mode` til `"zero"` hvis du heller vil gi dem 0.

**Doble kort:** FIFA Rosters viser noen kort to ganger med ulik ID. Kort med samme spiller, versjon, OVR, posisjon og hovedtall regnes som ett, og kopien med hentet kortside beholdes. Det samme gjelder en lekkasje som står i flere artikler.

Grensene står under `position_tiers` i `config/weights.json`.

## Løps-AI: bevegelse uten ball

Løps-AI måler hvor godt spisser, kanter og CAM-er beveger seg uten ball: hvor smart de går i rom, og om løpet faktisk gir avstand. Tallet er på samme skala som OVR og rangeres per posisjon som resten. **Det teller også i IGR:** 12 % for spiss, 10 % for kant og 6 % for CAM (`run` under `blend`).

Løps-AI er delt i to, fordi det er to ulike ting som kan gjøre at et kort «løper bra»:

- **Løps-IQ** (het Løpsvilje før): *hvor og når* spilleren løper. Att. Position og Reactions.
- **Løpseffekt:** om løpet skaper avstand til forsvareren. Acceleration, Sprint Speed, Agility, Balance, Strength, «kvikk og sterk», faktisk høyde og Stamina.

Geyse (FC 25) har for eksempel Løps-IQ 82 og Løpseffekt 90: styrken hennes var selve løpet, ikke at hun valgte de smarteste løpene.

**Hvorfor IQ og ikke vilje.** Gjennom FIFA-historien har *hvor ofte* en spiller løper vært styrt av noe annet enn kortets attributter: arbeidsraten fram til FC 24, og rollen og familiariteten (+/++) fra FC 25. EA sier at Att. Position og familiariteten brukes i formlene for løpene, at familiariteten står for 10–40 % av resultatet, og at høyere familiaritet gir bedre typer løp og bedre timing. Det kortet selv bidrar med, er altså hvor smart det plasserer seg og hvor raskt det reagerer, ikke hvor mye det løper. FIFPlay beskriver Att. Position som evnen til å se ledige rom og flytte seg dit det gir en fordel.

**Unødvendige løp** kommer derfor mest fra rollen og fokuset, og fra manglende ++. En spiss med «løp i bakrom»-rolle løper mye, også når laget trenger støtte. Vil du ha færre unødvendige løp, velg en rolle som holder posisjonen, og sørg for ++ (Evo Lab tar med Roles++-evoen). Løps-IQ sier hvem som gjør det beste ut av løpene rollen ber om.

## Vanskelig å stoppe

Hvor vanskelig kortet er å stoppe når det først er i gang. Det har to deler, på samme skala som OVR:

- **Med ball:** når kortet bærer ballen i fart. Sprint Speed 18 %, Strength 16 %, Balance 14 %, Ball Control 12 %, Dribbling 12 %, Acceleration 10 %, Agility 8 %, Reactions 5 % og «rask og sterk» 5 %. Pluss PlayStyles: Rapid (+1,5, PS+ +3), Press Proven og Enforcer (+1, PS+ +2), Technical og Bruiser (litt). Maks +4.
- **Uten ball, på løp:** hvor vanskelig kortet er å ta igjen og dytte av før pasningen kommer. Sprint Speed 32 %, Strength 20 %, Acceleration 16 %, Balance 14 %, «rask og sterk» 12 % og Stamina 6 %. Lengthy gir +1, Explosive +0,4. Bruiser og Quick Step gir litt.

**Stopp** er snittet av de to. Det teller i IGR med 7 % for spiss og kant og 4 % for CAM, tatt mest fra fart, siden fart allerede er med i tallet (`stop` under `blend`).

Det bygger på det som har holdt seg gjennom mange FIFA- og FC-år, ikke på ett spills særheter:

- **Strength** vinner skulderdueller og skjerming, og **Balance** holder spilleren på beina og i fart etter kontakt.
- **Rask og sterk** (den laveste av Sprint Speed og Strength) har vært den vanskeligste kombinasjonen å stoppe i alle meta-år. Kort som er raske *og* sterke får mer enn kort som bare er det ene.
- **Lengthy** (AcceleRATE fra FIFA 23) trenger lenger tid på å komme i gang, men tar igjen eller går forbi alle over lang nok avstand. På et langt løp er det dem som er vanskeligst å ta igjen.
- **PlayStyles (EA, FC 24–27):** Rapid holder toppfarten lenger og gjør færre feil i sprint-dribling, Press Proven skjermer bedre mot sterkere spillere, Enforcer gir bedre skulderdueller og skjerming, og Bruiser gir mer styrke i fysiske dueller (svekket i FC 27).
- **Off-balance** i FC 27 (Agility, Balance, Dribbling) ligger allerede i attributtene og gir egen bonus i IGR.

Du finner Stopp i rapporten (kolonne, filter, sortering, «Ranger etter» og på kortet under *Med ball* og *Uten ball*), i Evo Lab (kolonnen «Stopp», Bevegelse-panelet og sandkassen) og i `explain`. Vektene står under `hard_to_stop` i `config/weights.json` og er startverdier. Test dem med `test-par --type ball` og `--type løp`.

**Liga og land.** Både rapporten og Evo Lab kan filtreres på liga og land («Passer i laget ditt» / «Flere valg»), så du bare ser kort som passer inn i laget du har. Liga, land og klubb kommer fra EAs FC 27-ratingsider. Spesialkort arver dem fra basekortet til samme spiller. Icons regnes som «Icons» og vises uansett hvilken liga du velger, siden de gir kjemi med alle ligaer.

**PlayStyles på spesialkort.** FIFA Rosters viser ikke PlayStyles, og promokort har ofte flere enn basekortet. PlayStyles og PlayStyle+ for spesialkort leses derfor fra kortets side på FUT.GG (bare de offentlige spillersidene, siden robots.txt forbyr `/api/`). Hvert kort leses én gang, 150 per kjøring. Til et kort er lest, brukes basekortets PlayStyles. Evoer med maks antall PlayStyles havner da under «Kan passe, men sjekk selv» hvis kortet ligger på grensen.

**Hva som teller** (startvekter i `run_ai` i `config/weights.json`, vist som andel av totalen):

| Tall | Andel | Hvorfor |
|---|---|---|
| Att. Position | 28 % | Hvor ofte og hvor smart spilleren går i rom. I FC 27 styrer «Attacking Spatial Awareness» hvor løpet går |
| Acceleration | 18 % | De første 5–15 meterne. FC 27-løpene er korte: manuelle løp stopper etter en viss distanse |
| Reactions | 11 % | Hvor raskt løpet starter |
| Sprint Speed / Agility | 9 % / 9 % | Sprint Speed holder avstanden. Agility tar svingen i de nye buede løpene |
| Kvikk og sterk | 6 % | Laveste av Agility og Strength. Høy bare når spilleren er begge deler, som Geyse i FC 25 |
| Balance / Stamina | 5 % / 5 % | Balance: holder farten gjennom kontakt. Stamina: bare AI-styrte spillere mister fart når de blir slitne, og løpene tas av AI-en |
| Strength | 4 % | Ikke dyttet av ballen i løpet |
| Lav høyde | 3 % | Faktisk høyde gjort om til et tall (175 cm = 80, ett poeng per cm). Mindre enn før, fordi EA har jevnet ut animasjonsfarten mellom høye og lave |
| Ball Control / Composure | 0 % | Tatt ut: de avgjør mottaket etter at spilleren er fri, ikke om løpet gir avstand, og de teller allerede i følelse og ferdigheter |
| Arbeidsrate (angrep) | 0 % | Den gamle H/M/L-verdien. EA fjernet den i FC 25, derfor 0. `kalibrer` viser om den likevel henger sammen med løpene dine |

**Rollen er ikke med i tallet.** EA bekrefter at rollen bestemmer *hvilke* løp spilleren tar, og at familiariteten (+/++) bestemmer hvor ivrig han tar dem. Men nesten alle kort kan få ++ (alle spesialkort har det, og basekort får det med Roles++-evoen), og likevel oppfører de seg ulikt uten ball. Løps-AI regner derfor som om kortet har ++ i rollen, og måler forskjellen som ligger i kortet. Evo Lab tar med Roles++-evoen i planen og merker kort som mangler ++.

**Arbeidsraten:** EA fjernet arbeidsrater i FC 25 og erstattet dem med roller, men verdien ligger fortsatt i kortdataene. Ingen vet om spillet bruker den. Programmet henter den fra FIFA Rosters' lagrede liste for alle kort, også EAs basekort, uten å hente noe nytt. Om den betyr noe, finner `kalibrer` ut. Gamle «traits» (som «Tries To Beat Defensive Line») ble fjernet i FC 24 og erstattet av PlayStyles, så de er ikke med.

**Skjult perle:** kortet løper mye bedre enn andre kort med samme OVR (±1) i posisjonen. Det må være blant de 5 % som slår snittet for sin OVR mest, minst 2 poeng over, og selv være i topp 40 % på Løps-AI. Det må også finnes minst 8 kort med samme OVR å sammenligne med. I rapporten er perlene merket «skjult perle», og menyen har «Bare skjulte perler».

**Kroppsprofil:** «Kvikk og sterk», «Liten og kvikk» (175 cm eller lavere), «Stor og tung» (188 cm eller høyere, eller mye sterkere enn kvikk) eller «Balansert». Faktisk høyde brukes, også for kvinner.

**Lignende løpsprofil:** sammenligner Att. Position, fart, Reactions, Agility, Balance, Strength, Ball Control, Composure, høyde og arbeidsrate. Geyse-kortet fra FC 25 ligger i `data/eksempel_spillere.json` som referanse, så `lignende ... data/eksempel_spillere.json --name Geyse` finner FC 27-kortene som løper mest som henne. I rapporten ser du de fem nærmeste under hvert kort, og du kan trykke på navnene.

### Kalibrer mot dine egne kamper

Startvektene er et godt utgangspunkt, ikke en fasit. Den eneste måten å vite hvor ofte et kort løper i rom, er å telle:

1. Spill Kick-off mot CPU med samme lag, samme taktikk og samme rolle og fokus (gjerne ++) hver gang.
2. Bytt bare spissen. Spill 5 minutter og tell hvor mange ganger spilleren setter opp et løp bak backlinja uten at du trykker noe.
3. Gjør det to–tre ganger per kort og bruk snittet. Ta med både kort du synes løper bra og kort som løper dårlig.

Tell gjerne tre ting per kort:

- **løp:** hvor mange løp bak backlinja spilleren startet.
- **unødvendige:** løp som ikke ga noe: offside, løp bort fra spillet, løp når laget trengte støtte. Andelen fornuftige løp (løp minus unødvendige, delt på løp) måler Løps-IQ.
- **frie:** hvor mange av løpene der han kom fri eller fikk en sjanse. Det måler Løpseffekt.

Velg gjerne par som skiller dem: to kort med lik fart men ulik Att. Position, og to med lik Att. Position men ulik fart eller høyde.

Kjør så `kalibrer`. Første gang lager den en mal i `data/loep.csv`:

```
navn;versjon;løp;unødvendige;frie;notat
Geyse;FC 25;9;1;5;
Erling Haaland;;4;0;3;tom versjon = basekortet
```

`unødvendige` og `frie` kan stå tomme, og du kan skrive 1–5 eller bra/dårlig i stedet for antall løp. Med `unødvendige` for minst 4 kort kalibreres Løps-IQ mot andelen fornuftige løp (uten den: mot antall løp, som mest sier noe om rollen). Med `frie` for minst 4 kort kalibreres Løpseffekt mot andelen frie løp. Hver del for seg. Kjør `kalibrer` igjen, så får du:

- hvilke tall som henger sammen med løpene dine, fra +1 (jo høyere, jo flere løp) til −1
- hvor godt OVR, dagens Løps-AI og den kalibrerte Løps-AI-en treffer rekkefølgen din. Den kalibrerte testes på kort den ikke ble tilpasset til, så tallet er ærlig
- nye vekter. Med få kort flyttes de bare litt: med 10 kort teller dine data og startvektene like mye. Treffer de nye vektene ikke bedre enn dagens på kort de ikke ble tilpasset til, beholdes dagens

Med `--lagre` lagres vektene i `config/run_ai_kalibrert.json`, og rapporten bruker dem fra neste `rate`. Slett filen for å gå tilbake.

## Evo Lab: hvor god kan kortet bli?

`rate` lager også `output/evolab.html` (og `evolab.csv`). Lenken «Evo Lab» står øverst i rapporten.

**Øverst** velger du posisjon, hvor høy OVR kortet har i dag (74, 79, 81, 83 eller alle), hva du vil sortere etter og hva du vil se: **med evoene som er ute nå** (standard) eller **et anslag for resten av året**. Under «Flere valg» kan du velge korttype og kjønn, bare kort som kan ta en evo nå, og «Ligner på» et kort du liker (for eksempel Pichon), som gir en kolonne med hvor likt kortene beveger seg etter evo.

**«Evoene som er ute nå»** åpner en liste over evoene planene bygger på: hvem som kan ta dem, hva de koster, når du senest kan starte dem (i norsk tid) og lenker til kildene. Har en evo stengt siden siden ble laget, står det øverst, og du bør kjøre `rate` på nytt.

**Slik finnes planen:** programmet prøver alle kombinasjoner av evoene kortet kan ta: for hver evo både å ta den og å hoppe over den, i tre rekkefølger (strengeste OVR-krav først, strengeste PlayStyle-krav først og strengeste fartskrav først). Å hoppe over betyr noe, fordi en evo som løfter OVR kan stenge kortet ute fra en bedre evo senere. En evo som er hoppet over, men som kortet fortsatt kan ta til slutt, tas til slutt. Det tar lengre tid enn før, men planene ble bedre for omtrent halvparten av kortene i testen (i snitt +1 IGR, opptil +12).

Kravene til posisjon gjelder alle posisjonene kortet har, også de alternative: «LW, RW» betyr at kortet må ha en av dem, og «ikke ST, CM, CAM» at det ikke kan ha noen av dem. Derfor må de alternative posisjonene være riktige. De hentes fra EAs FC 27-database (se «EAs offisielle ratingdatabase»).

**Tabellen:** OVR i dag og etter, IGR i dag, IGR etter evo (med økningen under), plass i posisjonen etter evo, følelse, Løps-AI og Stopp etter evo. Med «Alle utespillere» sorteres det på plass i posisjonen, så spisser og midtstoppere kan blandes rettferdig. Keepere er utelatt (sett `include_gk` til `true` i `config/evolab.json`).

**Trykk på et kort** for å se:

- **Slik gjør du det:** evoene i den rekkefølgen som gir mest, med hva hver koster, når den stenger, hvilket valg du skal ta i pathway-evoer («På siste nivå: velg B (dribling + Press Proven)» eller «Velg Incisive Pass på nivå 1 og Press Proven på nivå 2»), hva den gir kortet og hva det betyr for IGR, følelse, Løps-AI og stopp. Viktige terskler står som en setning: «Blir Explosive», «Mister Explosive», «Off-balance går fra 72 til 77, og kortet er med i mekanikken». Til slutt Roles++, og hvorfor rekkefølgen betyr noe. Under står evoer kortet nesten kommer inn i, evoer det ikke kan ta, og evoer med krav du må sjekke selv (som fødselsdato).
- **Plan:** planen følger det du sorterer etter. Sorterer du etter «Løp uten ball etter evo», «Følelse etter evo» eller «Vanskelig å stoppe etter evo», viser tabellen og kortet den beste evo-kombinasjonen for akkurat det, med alle tallene for den planen. Ellers vises planen som gir høyest IGR. I kortet kan du bytte mellom planene.
- **Før og etter:** IGR, plass, OVR, følelse, fart, off-balance, Løps-AI, Løps-IQ, effekt, stopp med ball og på løp og AcceleRATE, i dag og med evoene nå (og i anslaget når du har valgt det), og alt som endres.
- **Prøv andre evoer selv:** huk av evoene i den rekkefølgen du vil, velg pathway, legg til egne oppgraderinger og PlayStyles. Tallene regnes på nytt med en gang, med samme regler som Python (det er testet at de gir like tall).
- **Legg til i sammenligning:** opptil tre kort side om side.

**Evoer du har brukt opp:** åpne «Evoene som er ute nå» og huk av «Brukt» ved evoene du allerede har brukt på andre kort. Planene for kortene som brukte dem, regnes på nytt i nettleseren, og rangeringen følger med: kortene som er best med evoene som er igjen, kommer øverst. Kortene som står øverst i visningen din regnes først, og tabellen oppdateres mens det regnes, så toppen er riktig etter et øyeblikk. Anslaget for resten av året justeres også: Python regner hvert kort både med og uten dagens evoer, og siden legger anslaget mellom de to etter hvor mye av evo-gevinsten kortet beholder. Nettleseren husker valget. Vil du at rapporten og `rate` også skal regne uten dem, kjør for eksempel:

```
py -m fcrating brukt "Batigol Precision" "Nine Duty"
py -m fcrating brukt --fjern "Nine Duty"
py -m fcrating brukt --tom
```

Siden bruker det samme søket som Python når den regner på nytt, så planen blir like god.

**Anslaget for resten av året** er en gjetning. EA slipper nye evoer hele året, og ingen vet hvilke. Evo Lab lar kortet ta evoer som ligner dem EA har sluppet i FC 27, i 8 tenkte fortsettelser av året. Spennet (for eksempel 89.8–96.0) viser dårlig og god flaks. Ingen av de evoene finnes ennå, så planen og «Etter evo» i rapporten bruker bare evoene som er ute nå.

I terminalen:

```
py -m fcrating evolab data\ea_players.json data\spesialkort.json --maks-ovr 79 --group ST
py -m fcrating evolab data\ea_players.json data\spesialkort.json --maks-ovr 74 --sorter op --horisont s2
py -m fcrating evolab data\ea_players.json data\spesialkort.json --name "Vicky López"
```

`--sorter` kan være `forventet`, `tak`, `op`, `gevinst`, `dna` eller `sikker`, og `--horisont` kan være `nå`, `s2`, `s4` eller `aar`. `--name` viser hele planen for ett kort. `--bare-live` viser bare kort som har en live-evo nå. Terminalen viser også anslagene og «OP-sjanse» (andelen av de tenkte årene der kortet havner blant de 5 % beste).

**Første kjøring** simulerer alle kortene og tar noe tid (flere prosesser brukes samtidig). Etterpå ligger resultatene i `data/evolab_cache.pkl`, så bare nye eller endrede kort simuleres. Vil du hoppe over Evo Lab, bruk `rate ... --uten-evolab`.

### Evoene og hvor de kommer fra

Evoene som var ute 13. oktober kl. 22 ligger i `config/evolab.json`. Hver evo er sjekket mot minst to av FUT.GG, futnext, FUTBIN og RealSport101, og lenkene står under `sources` på hver evo og i listen på siden. Det som er sjekket for hver: krav, alle nivåer med «+X (maks Y)», PlayStyles, roller, svakfot og skill moves, valgene i pathway-evoer, pris og når du senest kan starte den.

- **Sluttidspunkt:** `until` er når du senest kan starte evoen, i UTC (`"2026-10-17T17:00Z"` er 17. oktober kl. 19 norsk tid). EA bytter innhold kl. 18 britisk tid. Sesongpass-evoene må hentes før sesong 1 slutter 22. oktober kl. 09. En evo forsvinner fra planene fra det klokkeslettet, ikke ved midnatt.
- **PlayStyles med tak:** tallet EA viser ved en PlayStyle i en evo (for eksempel «Tiki Taka 3») betyr at den bare legges til så lenge kortet har færre PlayStyles enn det. Skrives `["Tiki Taka", 3]`.
- **Valg (pathway):** under `paths`. Et valg kan gi attributter, PlayStyles, svakfot og skill moves. Valget kommer etter nivåene alle får, slik som i spillet, så en attributt som står begge steder løftes to ganger, hver gang opp til sin egen maks.
- **Ikke med:** kosmetiske evoer (merker, kortdesign) og Regista Realm, Wing Specialization og Backline Conductor, som har stengt. Intro to Pathway Evolutions har to valg i spillet, men bare valget med Gamechanger er kjent, så det andre er ikke regnet med.

**Holde evoene oppdatert:** evoer som stenger, forsvinner av seg selv fra planene på klokkeslettet de stenger, neste gang `rate` kjører. `py -m fcrating watch` kjører alt på nytt hver 6. time, så rangeringen og planene følger med. Nye evoer kommer ikke inn av seg selv, fordi programmet ikke henter evo-lister fra nettsider (FUTBIN blokkerer automatisk henting). Når EA slipper en ny evo, kopier teksten fra evoens side på FUTBIN eller FUT.GG til en tekstfil og kjør:

```
py -m fcrating evo-import ny_evo.txt --til 2026-10-25 --kostnad gratis
```

Den viser krav og oppgraderinger den fant, og lagrer evoen i `data/mine_evoer.json`. Den filen overskrives ikke når du oppdaterer systemet. Ligger siden ute for vennene dine, Commit og Push filen i GitHub Desktop, så kommer evoen på siden. Med `--vis` lagres ingenting. Stemmer ikke alt, kan du rette i filen. Formatet er det samme som i `config/evolab.json`: `"stats": {"finishing": [7, 83]}` betyr +7, men aldri over 83.

### Hva bygger det på (FC 27)

- En oppgradering «+X (maks Y)» løfter attributten med X, men aldri over Y og aldri ned. +40/+50 i treningsleir-evoer betyr i praksis «fyll opp til maks». Kilde: evo-lister fra FUTBIN, FUT.GG og futnext.
- Krav: maks OVR, maks Pace (PAC-hovedtallet), maks antall PlayStyles og PlayStyle+, posisjon og antall posisjoner.
- Maks 3 PlayStyle+ per kort i FC 27, ned fra 5 (EA Pitch Notes).
- EA sier at oppgraderingene blir mindre gjennom året enn i FC 26. De fremtidige evoene er derfor satt forsiktig. Alle tall står under `future` i `config/evolab.json` og kan endres.

## Spesialkort: Icons, Heroes, TOTW, kampanjer og lekkasjer

EAs database har bare basekortene. Spesialkortene hentes fra to andre kilder og havner i samme rangering:

| Kilde | Hva den gir | Brukes til |
|---|---|---|
| **FIFA Rosters** (fifarosters.com) | Alle utgitte FC 27-kort (ca. 23 000), også Icons, Heroes, TOTW og kampanjekort. Hvert kort har en egen side med alle attributter og høyde | Utgitte spesialkort |
| **RealSport101** (realsport101.com) | Ukentlige artikler med lekkede TOTW-kort før de slippes: OVR, PlayStyle+ og de seks hovedtallene | Lekkasjer |

Slik fungerer det:

1. **FIFA Rosters:** Hele FC 27-listen gås gjennom én gang i uka (ca. 920 sider, rundt en halvtime med pauser), og TOTW-listen sjekkes hver gang. Basekortene hoppes over, fordi de kommer fra EA. For hvert spesialkort hentes kortsiden med alle attributter, maks 300 per kjøring. Kortsider som er hentet, lagres og hentes aldri igjen. Første gang kan det derfor ta noen kjøringer før alle spesialkortene har fulle attributter.
2. **Kobling til basekortet:** FIFA Rosters bruker EAs egne spiller-ID-er, så hvert spesialkort kobles nøyaktig til riktig basekort. Derfra arver kortet PlayStyles og kroppstype. Spesialkort får ++ i alle roller i posisjonene sine, slik EA har bekreftet for FC 27.
3. **Før kortsiden er hentet:** Kortet lages fra basekortet og de seks hovedtallene. Økningen i hvert hovedtall fordeles på attributtene bak det, med EAs vekter (sjekket mot Bellinghams TOTW-kort, der alle seks treffer). Slike kort merkes «estimert» og kan bomme med 1–3 poeng på enkeltattributter.
4. **Lekkasjer:** RealSport101-artikler med kort-tabell leses, og kortene lages fra basekortet på samme måte. De merkes «lekket». Når FIFA Rosters har det samme kortet (samme spiller og OVR), fjernes lekkasjen automatisk.
5. **Icons:** Icons har ikke noe basekort hos EA, så de trenger kortsiden fra FIFA Rosters. Til den er hentet, står de under «Merk» etter kjøringen.

**Hensyn til sidene:** Programmet følger robots.txt, venter 2 sekunder mellom hver forespørsel til samme side, og stopper hvis en side svarer at den er overbelastet eller blokkerer (429/403). Jeg fant ikke bruksvilkår hos FIFA Rosters. Spør gjerne eieren via kontaktsiden deres om det er greit, eller om de kan dele et datauttrekk.

**Begrensninger:**
- FIFA Rosters viser ikke PlayStyles, så spesialkort arver PlayStyles fra basekortet. Nye PlayStyle+ fra lekkasjer legges til.
- Composure står ikke på FIFA Rosters' kortsider, så den arves fra basekortet.
- RealSport101 har tall bare i TOTW-artiklene. Kampanjeartikler med bare navn hoppes over.
- Sidene kan endre oppsett. Da sier programmet fra at den ikke fant kort, og parserne i `fcrating/sources/` må justeres.

## Justert etter kildegjennomgangen (FC 27)

En gjennomgang av EAs Pitch Notes for FIFA 23 til FC 27, FC 27 Closed Beta Feedback Update (3. september 2026), NickRTFM, fifauteam og andre kilder ga disse endringene. Kortdataene er ikke endret, så du trenger bare å kjøre `rate` på nytt.

| Endring | Hvorfor | Evidens |
|---|---|---|
| Faktisk høyde for følelse, også for kvinner | Animasjonsfart følger høyde; kjønnsdelte grenser gjelder bare AcceleRATE | EA (høyde, FC 26) + NickRTFM (kvinner) |
| AcceleRATE-effekten halvert | Typene er «closer together» i FC 27 | Offisiell |
| Mer vekt på Acceleration og Balance | Quick Step svekket for å gi Acceleration mer betydning; off-balance dribbling | Offisiell |
| Ti PlayStyles svekket, Pinged Pass bare øverst for midtbane | FC 27 Gameplay Deep Dive | Offisiell (størrelsene er ukalibrerte) |
| Intercept mindre verdt ved høy Interceptions | Spillere uten PlayStyle får lengre rekkevidde | Offisiell |
| Bonus for off-balance dribbling | Ny mekanikk drevet av Balance, Agility, Dribbling | Offisiell (grensen er ukjent) |
| Standing Tackle-nivåer 71 og 85 | Grenser for taklingsanimasjoner | Offisiell (FC 26) |
| Skill moves under 3 stjerner straffes mer | Mange skill moves krever 3–5 stjerner | Offisiell |
| Mer følelse for CB/CDM, litt mindre for backer | Mindre automatisk forsvar i FC 27; backer bruker farten til å ta igjen terreng | Offisiell + slutning |
| Arbeidsrate ut av Løps-AI, Stamina inn | Work rate «no longer present» fra FC 25; AI-spillere blir slitne | Offisiell |
| «Balanse og sterk» som alternativ hypotese i `kalibrer` | Ingen kilde støtter «kvikk og sterk» direkte | Hypotese |
| Off-balance = snittet av Agility, Balance og Dribbling, inne fra 75 | Slik EasySBC viser verdien per kort (Nagasato 90/83/87 → 87, med Finisher 93) | Offisiell mekanikk, formelen fra EasySBC |
| Løps-AI: Acceleration og Agility opp, Ball Control og Composure ut | FC 27-løpene er korte og buede (Attacking Spatial Awareness, Triggered Curved Runs, manuelle løp med begrenset lengde) | Offisiell (vektene er startverdier) |
| Vilje blir Løps-IQ | Hvor ofte styres av arbeidsrate (til FC 24) og rolle/++ (FC 25+); kortet bidrar med hvor og når (EA FC IQ Deep Dive) | Offisiell + slutning |
| Nytt tall: Vanskelig å stoppe, med i IGR | Strength/Balance, rask og sterk, Lengthy over avstand, Rapid/Press Proven/Enforcer/Bruiser | FIFA-historikk + offisielle PlayStyle-beskrivelser (vektene er startverdier) |
| `kalibrer` teller unødvendige løp | Løps-IQ måles mot andelen fornuftige løp, ikke antall | Metode |
| Quick Step og Rapid svekket mer | EA: «impact reduced» på begge i FC 27 | Offisiell (størrelsen er ukalibrert) |
| Mindre utslag for høyde | EA jevnet ut animasjonsfarten mellom høye og lave (FC 26), og proffene bruker både høye og lave kort i FC 27 | Offisiell + slutning |

Det finnes ingen publiserte prosenter for hvor mye PlayStyles eller AcceleRATE gir, så alle bonusstørrelser er startverdier. Test dem slik:

- **Fart og vending:** i Practice Arena, 30 meter fra stillestående og 10 meter med vending, filmet i 60 fps.
- **Høyde:** to kort med nesten like tall men ulik høyde, for eksempel en kvinne på 160 cm og en mann på 180 cm.
- **PlayStyles:** samme spiller med og uten PS+ (for eksempel før og etter en evo).
- **Løp uten ball:** se «Kalibrer mot dine egne kamper» over.

Grensene for menn i FC 27 er ikke gjentatt av EA (kildene sier 183 eller 185 cm for Lengthy). Spillet viser AcceleRATE-typen i Team Management, så sjekk et kort på grensen der.

## Slik blir systemet mer treffsikkert

**99 % er ikke mulig fra kortdata.** EA publiserer ikke animasjonskurvene, og det som avgjør en enkelt situasjon (lag, motstanderen, rollen, taktikken, hvordan du spiller) flytter følelsen mer enn et par attributtpoeng. Det som *kan* måles, er hvor ofte modellen er enig med deg når du spiller to kort mot hverandre. Et realistisk tak er omtrent:

| IGR-forskjell | Realistisk treff |
|---|---|
| Over 3 | 85–90 % |
| 1–3 | 65–75 % |
| Under 1 | Omtrent som å kaste kron og mynt. Da er kortene i praksis like gode |

Slik kommer du nær taket:

1. **Blinde A-mot-B-tester.** Spill to kort i samme drill eller kamp, helst uten å vite hvilket som er hvilket (la noen andre bytte, eller gi dem samme kjemi og samme draktnummer). Noter hvem som var best og hvor tydelig.
2. **Lagre testen:** `py -m fcrating test-par FILER --a "Pichon" --b "Vicky López" --vinner a --styrke 2 --type ball`. `--type` sier hva du testet: `ball` (med ball), `løp` (uten ball) eller `alt`. `--styrke` er 1 (litt bedre) til 3 (klart bedre).
3. **Evaluer:** `py -m fcrating evaluer FILER`. Du får hvor ofte IGR, følelse, Løps-AI, fart, ferdigheter, Off-balance og OVR velger samme vinner som deg, også bare for med ball- og uten ball-testene. Du får også treff etter IGR-forskjell, en rangering av kortene fra testene dine (Bradley-Terry) og testene der IGR bommet med 2+ poeng.
4. **Juster det som bommer.** Treffer for eksempel Off-balance bedre enn følelse på med ball-testene, er det et tegn på at Balance og Dribbling bør telle mer i følelsen. For løp uten ball: tell løp og bruk `kalibrer` (se over).

**Drillene som skiller best** (samme lag, samme taktikk, samme kjemi, samme rolle med ++):

- **Med ball:** Skill Games eller Practice Arena: slalom gjennom kjegler, 10 meter med vending, og dribling mot en CPU-forsvarer som dytter (off-balance). Film i 60 fps hvis du vil måle tid.
- **Uten ball:** Kick-off mot CPU, 5 minutter, tell løp bak backlinja uten at du trykker, og hvor mange som ga en sjanse.
- **Velg par som skiller én ting:** samme fart men ulik høyde, samme Agility men ulik Balance, eller samme kort før og etter en evo.

Med 25 kort og 2–3 tester per kort ser du om modellen rangerer kortene dine som deg (Spearman over 0,75 er godt).

## Hvordan modellen regner

For hver posisjon:

```
IGR = følelse × vekt + fart × vekt + posisjonsferdighet × vekt
      (+ Løps-AI × vekt + Stopp × vekt for spiss, kant og CAM)
      + PlayStyle-bonus + rollebonus + svakfot/skill moves + off-balance + Standing Tackle
```

Vektene per posisjon står i `config/weights.json` under `blend`. En spiss vekter følelse 26 %, fart 15 %, ferdighet 40 %, Løps-AI 12 % og Stopp 7 %. En midtstopper vekter ferdighet mye mer.

### Følelse: hva som gjør at en spiller føles kvikk

Dette er delen som skiller IGR fra OVR. Den bygger på hva hvert attributt gjør i spillet:

| Attributt | Vekt | Hva det styrer |
|---|---|---|
| Agility | 22 % | Hvor raskt spilleren vender og skifter retning |
| Reactions | 18 % | Hvor fort han reagerer på det som skjer, på løse baller og når du trykker |
| Balance | 17 % | Om han holder seg på beina etter kontakt (styrer også off-balance dribbling i FC 27) |
| Acceleration | 16 % | De første stegene (teller mer i FC 27, der Quick Step er svekket) |
| Ball Control | 15 % | Førstetouch og hvor tett ballen holdes |
| Dribbling | 6 % | Ballkontroll i fart |
| Composure | 6 % | Hvor sent han kjenner press når han skal skyte eller sende |

I tillegg justerer modellen for kroppen:

- **Høyde.** Høye spillere har lengre animasjoner og føles tyngre. Over 180 cm trekkes 0,28 poeng per cm (maks −4). Under 175 cm gis 0,14 per cm (maks +2). Mindre enn før, fordi EA i FC 26 justerte animasjonsfarten for å jevne ut høye og lave spillere. **Faktisk høyde brukes, også for kvinner.** EAs lavere grenser for kvinner gjelder bare AcceleRATE, mens animasjonene etter alt å dømme bruker faktisk høyde (NickRTFM: små spillere er mye mer responsive, derfor føles små kvinnekort best). Det er en påstand fra en innholdsskaper, ikke bekreftet av EA. Vil du tilbake til den gamle måten, sett `female_offset_cm` til 17 under `feel.height`.
- **AcceleRATE.** Explosive +0,75, Lengthy −0,75. Halvert fra før, fordi EA sier typene er «closer together» i FC 27.
- **Kroppstype** (hvis kilden oppgir den). Lean +0,5, Stocky −0,5.

Eksempel fra eksempeldataene: Haaland får følelse 73 (Agility 66, Balance 69, 195 cm, Lengthy), mens Mbappé får 91. Det stemmer med hvordan de føles i spillet, selv om begge er 91 OVR.

### AcceleRATE (FC 27)

Modellen regner ut AcceleRATE selv, også etter kjemistil:

| Type | Krav |
|---|---|
| Explosive | Høyde ≤ 182 cm (kvinner ≤ 162), Agility ≥ 65, Agility − Strength ≥ 10, Acceleration ≥ 80 |
| Lengthy | Høyde ≥ 185 cm (kvinner ≥ 172), Strength ≥ 65, Strength − Agility ≥ 4, Acceleration ≥ 40 |
| Controlled | Alle andre |

Kjemistiler som øker Strength kan gjøre en Explosive spiller Controlled, og en Controlled spiller Lengthy. Høyde kan ikke endres, så noen spillere kan aldri bli Explosive.

### Off-Balance Dribbling

Nytt i FC 27: driblere holder kontrollen når de blir dyttet eller taklet skulder mot skulder. EA sier det styres av Balance, Agility og Dribbling, og EasySBC viser en verdi for hvert kort. Modellen regner den på samme måte: **snittet av Agility, Balance og Dribbling**, avrundet. Nagasato (90/83/87) får 87, og med Finisher 93, akkurat som EasySBC.

- Kort med 75 eller mer er inne i mekanikken. Over 75 gir hvert poeng litt mer IGR, maks +1,8, mest for kanter, så CAM og spiss (`off_balance` i `config/weights.json`).
- Limer du inn en spillerside fra EasySBC med `import-text`, leses «Off-Balance Dribbling: 87» og brukes direkte.
- Evo Lab viser Off-balance før og etter evo, og merker evoer som tar kortet over 75.

### Fart

`Acceleration × 60 % + Sprint Speed × 40 %` (midtstoppere 50/50, backer 55/45). Acceleration teller mer enn i EAs PAC-tall: i FC 27 er Quick Step svekket «for å gi Acceleration mer betydning», og manuelt utløste løp har begrenset lengde. AcceleRATE gir +0,5 (Explosive) eller −0,25 (Lengthy).

### PlayStyles

Hver PlayStyle har en verdi (`config/playstyles.json`). Verdiene er justert etter EAs FC 27-endringer: Quick Step (0,7 / PS+ 1,3) og Rapid (0,6 / 1,2) er svekket mest, og Technical, Technical, Finesse Shot, Precision Header, Tiki Taka, Jockey, Low Driven Shot og Pinged Pass er svekket eller har mindre forskjell mellom PS og PS+, og Bruiser+ er litt svekket. Intercept er mindre verdt for spillere som allerede har høy Interceptions, siden de får lengre rekkevidde uten PlayStylen.

**Pinged Pass** har fortsatt høyest verdi, men bare for sentrale midtbanespillere. I FC 27 har den mistet effekten som ga mottakeren bedre førstetouch, så for spiss og kant er Finesse Shot+, Quick Step+ og Rapid+ mer verdt.

Verdien ganges med:

1. **Relevans for posisjonen.** Skudd-PlayStyles teller fullt for spiss og nesten ingenting for midtstopper.
2. **Synergi med attributtene.** I FC 27 avhenger PlayStyles mer av statsene. Finesse Shot på en spiller med 70 Finishing er derfor verdt mindre enn på en med 92. Synergien er 1,0 når de relevante attributtene er rundt 90.

Den beste PlayStylen teller fullt, de neste litt mindre, og totalen er maks 7 poeng. Det hindrer at kort med mange merker blåses opp.

### Roller, svakfot og skill moves

- Rolle ++ gir +2, rolle + gir +1, i beste rolle for posisjonen.
- Svakfot 5 gir +1,5 for angripere, svakfot 3 gir −1. Effekten er mindre for forsvarere.
- Skill moves teller mest for kantspillere og nesten ikke for forsvarere. Under 3 stjerner straffes mer, fordi mange skill moves krever 3–5 stjerner.
- **Off-balance dribbling (FC 27):** 0,12 poeng per poeng over 75, maks +1,8, mest for kantspillere, så CAM og spisser.
- **Standing Tackle-nivåer:** EA har bekreftet at under 71 gir bare enkle taklingsanimasjoner, 71–84 de fleste og 85+ alle. Modellen gir −1,5, 0 og +1 (for CB og CDM, mindre for backer og CM).

### Evo-potensial

Når Evo Lab kjører (standard i `rate`), viser kolonnen «Etter evo» i rapporten IGR med evoene som er ute nå (se «Evo Lab» over). Kommandoen `evo` og `explain` bruker fortsatt den enkle modellen under.

Bare kort som kan evolueres er med. Ikke med: kort over OVR 84, Icons, Heroes, Hall of FUT, lekkasjer og keepere. De får «–» i kolonnen «Etter evo», og detaljene sier hvorfor.

Lavere OVR gir større økning, slik det er i spillet (et lavt kort kan ta flere evoer før det når taket). Hver attributt øker med (88 − OVR) × 1, maks 12, og maks 95:

| OVR | Økning per attributt |
|---|---|
| 74 eller lavere | +12 |
| 78 | +10 |
| 82 | +6 |
| 84 | +4 |

Svakfot og skill moves løftes til minst 4. Kortet rates så på nytt i sin egen posisjon, og du ser IGR før og etter, gevinsten og hvor kortet havner blant dagens kort (for eksempel «plass 583 → 37 av 6 605»).

I rapporten sorterer «Beste evo-kandidater» etter IGR etter evo, og «Størst evo-økning» etter gevinst. Alt kan endres under `evo` i `config/weights.json`: `max_ovr`, `target_ovr`, `points_per_ovr`, `max_boost`, hvilke versjoner som er utelatt, og `attribute_boosts` hvis du vil etterligne én bestemt evo, for eksempel `{"acceleration": 5, "sprint_speed": 5, "agility": 4}`.

## Data inn

### 1. Kopiert tekst fra en spillerside (enklest)

Åpne spillersiden på EA, FUT.GG eller EasySBC, merk alt (Ctrl+A), kopier og lim inn i en `.txt`-fil. Velg ingen kjemistil på siden, ellers kopierer du boostede verdier.

```bash
python -m fcrating import-text side.txt --name "Spillernavn" --position CAM --height 170 \
    --wf 4 --sm 4 --ps "Pinged Pass+" "Technical" --role "CAM:Playmaker:2"
```

Spilleren lagres i `data/mine_spillere.json`. `--role` tar `POSISJON:Rolle:nivå`, der 2 = ++ og 1 = +.

### 2. CSV

Én rad per spiller. Kolonnenavn kan være «Sprint Speed», «sprint_speed» eller «sprintSpeed». PlayStyles i én kolonne `PlayStyles`, adskilt med komma, med `+` etter PlayStyle+. Se `tests/fixtures/spillere.csv`.

### 3. EAs offisielle ratingdatabase (alle basekort)

**FC 27 (fra 16. oktober 2026):** `fetch-ea` leser spillerlisten fra EAs egne ratingsider (ea.com/games/ea-sports-fc/ratings?page=1, 2, ...). Hver side har 100 spillere som JSON i siden, med FC 27-posisjon, alternative posisjoner, attributter, PlayStyles, høyde, svakfot og skill moves. Rundt 200 sider, så det tar noen minutter. GitHub-jobben henter dem én gang i uka (`fetch-ea --hvis-gammel 7`). Feiler en side tre ganger, beholdes filen fra forrige gang.

FC 27-basekortene bygges fortsatt fra FIFA Rosters' liste (`use_base_cards`), men attributtene, høyden, PlayStyles og de alternative posisjonene kommer nå fra EAs FC 27-kort. Før kom de fra et FC 25-kort, og da manglet for eksempel CM hos Hugo Vetlesen, så Evo Lab trodde han kunne ta Touchline Magic (som ikke tillater CM).

Den gamle JSON-adressen under gir fortsatt FC 25-kort og brukes bare hvis du fjerner `html_url_template` i `config/sources.json`.

Adressen er lagt inn i `config/sources.json`:

```
https://drop-api.ea.com/rating/ea-sports-fc?locale=en&limit={limit}&offset={offset}
```

Det er denne EAs ratingside (ea.com/games/ea-sports-fc/ratings) henter spillerlisten fra. EA har ikke dokumentert den. Adressen er hentet fra et offentlig FC 25-verktøy på GitHub (sauravhiremath/ea-fc25-scraper), og den kunne ikke testes mot FC 27 da programmet ble laget. Sjekk den første gang:

1. Kjør `python -m fcrating fetch-ea --dump-sample`. Det lagrer ett rått svar i `data/ea_sample.json`.
2. Åpne filen og se at det er FC 27-spillere med attributter (for eksempel `acceleration`, `sprintSpeed`) og PlayStyles.
3. Kjør `python -m fcrating fetch-ea`. Med 100 spillere per side og 1,5 sekunder pause tar alle ca. 19 800 spillere rundt fem minutter.

Hvis adressen ikke virker lenger, finner du den nye slik:

1. Åpne ea.com/games/ea-sports-fc/ratings i Chrome eller Edge og trykk F12.
2. Gå til Network, filtrer på Fetch/XHR og bla i spillerlisten.
3. Klikk forespørselen som returnerer spillerlisten og kopier URL-en.
4. Bytt tallene for antall og side med `{limit}` og `{offset}`, og lim inn som `url_template`.

Hvis et felt ikke fanges opp (for eksempel PlayStyles), se i `data/ea_sample.json` hvor det ligger og legg stien inn under `field_overrides`.

Databasen har bare Gold, Silver og Bronze. Icons, Heroes og spesialkort hentes med `fetch-specials` (se over). Rollene (+/++) så ikke ut til å være med i EAs data i tidligere år. Mangler de, blir rollebonusen 0 for spillere derfra til du legger inn roller selv. Hold pausen mellom forespørsler (standard 1,5 sekunder).

**Om FUTBIN og FUT.GG:** FUTBIN blokkerer automatisk henting, og begge sidene har egne bruksvilkår. Sjekk vilkårene før du henter data fra dem automatisk. EAs database og kopiert tekst er de tryggeste kildene.

## Justere modellen

Alt ligger i `config/`:

- `weights.json`: følelse, fart, ferdighet per posisjon, blanding, høyde, AcceleRATE-terskler, roller, svakfot, tiers, evo-regler, forklaringer, PlayStyles som mangler og Løps-AI (`run_ai`)
- `run_ai_kalibrert.json`: lages av `kalibrer --lagre` og brukes i stedet for vektene i `run_ai`
- `playstyles.json`: verdien til hver PlayStyle, relevans per posisjon og synergiattributter
- `chem_styles.json`: kjemistil-boosts. Finisher er bekreftet mot kortet ditt. De andre må fylles inn (fra FUT.GG eller spillet) før `--chem best` kan bruke dem.

Kjør testene etter endringer. De sjekker blant annet at AcceleRATE og Finisher-verdiene stemmer med ekte kort, og at rekkefølgen på følelse er Mbappé > Messi > Nagasato > Ekitiké > Haaland.

## Begrensninger

- Vektene er en modell, ikke EAs kode. De bygger på EAs beskrivelser av attributtene, FC 27-endringene og hvordan kjente kort føles. Juster dem når du ser at spillere føles annerledes enn ratingen.
- Lengthy-grensen for menn (185 cm) er hentet fra fifauteam og ikke bekreftet av EA.
- Off-Balance Dribbling regnes som snittet EasySBC viser. Hvor mye det gir i kamp (bonusen), er en startverdi.
- Ingen formel bygd på kortdata kan treffe 99 %. Se «Slik blir systemet mer treffsikkert».
- Bare Finisher er lagt inn av kjemistilene.
- Hvis EAs database ikke har roller (+/++), får spillere derfra ingen rollebonus før du legger dem inn.
- Adressen til EAs database er udokumentert og kan endres av EA.
- Eksempeldataene mangler noen PlayStyles og roller (merket i filen). Spillere med ufullstendige data får lavere PlayStyle- og rollebonus enn de burde.

## Neste steg

1. Priser og IGR per 1 000 coins (krever en priskilde).
2. Historikk i SQLite, så du ser når en spiller endres.
3. Alle kjemistiler inn, så `--chem best` velger riktig stil for hver spiller.
4. Kalibrering mot dine blinde tester: når `evaluer` har 30+ tester, la den foreslå nye vekter for følelse og Løps-AI (slik `kalibrer` gjør for løp).

## Kilder

- EA, FC 27 Gameplay Deep Dive og PlayStyles-oversikt: ea.com/games/ea-sports-fc/fc-27/news
- EA, FC 27 Closed Beta Feedback Update (AcceleRATE for kvinner)
- FUT.GG: PlayStyle-endringer i FC 27, beste PlayStyles per rolle, kjemistiler og spillerdata
- fifauteam.com: FC 27 Attributes og FC 27 AcceleRATE
- FIFPlay: FC 27 Dribbling Guide (Off-Balance Dribbling)
- EasySBC: Off-Balance Dribbling-verdi per kort (snittet av Agility, Balance og Dribbling)
- EA, Pitch Notes: FC 25 FC IQ Deep Dive (roller, familiaritet, «timing of attacking runs», arbeidsrate fjernet)
- EA, FC 24 PlayStyles Deep Dive (Rapid, Press Proven, Quick Step, Bruiser, Technical)
- FUT.GG: AcceleRATE (Lengthy tar igjen alle over avstand)
- RealSport101: FC 27 PlayStyles overhaul (Rapid, Press Proven, Enforcer, Bruiser i FC 27)
- FIFPlay: FIFA 23 Attributes Explained (Att. Position, Balance)
- EA, FC 27 FUT Deep Dive (Evolutions, Roles++, maks 3 PlayStyle+)
- EA, «EA’s content policy» (ikke-kommersielt, ansvarsfraskrivelse, ingen logoer): help.ea.com/en/articles/security-and-rules/ea-content-policy
- GitHub: Pages-grenser og gratis Actions i offentlige repoer, og at faste kjøringer settes på pause etter 60 dager uten aktivitet
- Cloudflare: Pages-grenser (25 MiB per fil), Access på pages.dev-domenet og engangskode (One-time PIN)
- LG München, 20.01.2022 (3 O 17493/20): Google Fonts og IP-adresser
- FUTBIN: Haaland-attributter (FC 27)
