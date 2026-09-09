---
title: OPENCNTX — Roadmap na de 1.7.0-analyse
project: OPENCNTX
type: roadmap
status: planned
created: 2026-09-09
updated: 2026-09-09
planning_revision: 2
source_version: 1.7.0
source_commit: 654c110b59c7df33bdb223c163c5783c79848c30
published_baseline: 1.7.0
target_version: null
public_overview: "roadmap.md"
---

# OPENCNTX — Roadmap na de 1.7.0-analyse

## 1. Doel en actuele stand

**Doel:** de bestaande contextkern betrouwbaar eenvoudiger maken: minder onnodige vragen en stops, geen onterechte eigen weigeringen, meetbaar zuinige context en voorspelbare updates die gebruikersdata behouden.

Dit is de volledige publieke Nederlandstalige planning op basis van de beoordeling van 1.7.0. Zie het [Engelstalige overzicht](roadmap.md) en de [release-inhoud en bekende beperkingen](release-1.7.0.md). Privépaden, lokale bewijsbestanden en persoonlijke herstelgegevens zijn niet opgenomen. Taken en acceptatiecriteria zijn behouden; publicatie betekent niet dat de verbeteringen uitgevoerd zijn.

| Onderdeel | Actuele stand |
|---|---|
| Onderzochte en gepubliceerde basis | OPENCNTX 1.7.0 |
| Broncommit | 654c110b59c7df33bdb223c163c5783c79848c30 |
| Brontree | 1c2de502fd9c7580d2025f779ced68c7f64adc84 |
| Betekenis van 1.7.0 | Versie-/documentatieafstemming; runtimegedrag behouden uit 1.6.3 |
| Nieuwe planning | 24 taken, N01–N24 |
| Afgeronde nieuwe taken | 0 van 24 |
| Actieve taak | Geen |
| Eerstvolgende taak | N01 — Werkbasis, bewijs en wijzigingsscope vastleggen |
| Volgende implementatie-/releaseversie | Nog niet gekozen; 1.7.0 wordt niet hergebruikt |
| Nieuwe publicatie | Niet gestart |
| Installatie/activering | Geen onderdeel van deze roadmap-publicatie |

**Status is niet hetzelfde als resultaat.** Deze roadmap is opgesteld, niet uitgevoerd. Publicatie van de roadmap is geen automatische uitvoering van de taken, nieuwe software-release of installatie.

### Reeds aanwezig bewijs — behouden, niet opnieuw uitvinden

De 1.7.0-publicatie heeft een correct gebonden tag/buildrecord, vier geverifieerde downloads en acht geslaagde CI-jobs op de exacte releasecommit. De CI was afgerond vóór publicatie. De analyse bevestigt vier nog aanwezige problemen met gerichte fixtures: syncbytes buiten de preview, governanceblokkades, overlappende updatecomponenten en dubbele capsulemanifestrecords.

Dat bewijs dient als nulmeting. Het maakt de nieuwe implementatietaken niet automatisch klaar. Reeds geldige resultaten worden hergebruikt zolang bron en relevante omstandigheden ongewijzigd zijn. Een nieuw bewijs is nodig bij een relevante wijziging of een nog onbeantwoorde vraag, niet bij iedere nieuwe gesprekssessie.

**Ontwerples:** achtergebleven globale hosthooks kunnen ongewenste stoplussen veroorzaken. Package, hostkoppelingen en projectdata krijgen daarom een eigen levenscyclus. Geen algemene stopmarker, geen nieuwe laag die iedere afronding onderschept en geen brede opruimactie om één defect onderdeel te herstellen.

## 2. Vijf bindende gebruikseisen

| Eis | Gewenst gedrag | Toetsbare uitkomst |
|---|---|---|
| U1 — Minder stops en goedkeuringen | Doorgaan binnen een duidelijke opdracht en geldige scope | Geen overbodige eigen vragen of fasegebonden stops in de vaste positieve scenarioset |
| U2 — Geen onnodige tokenkosten | Kleine relevante context, hergebruik en deterministische administratie | Geen modelcalls uitsluitend voor boekhouding; geen dubbele beleidsinjectie of onverklaarde verbruiksregressie |
| U3 — Proportioneel eigen beleid | Eén actuele beslisroute; een optionele fout raakt alleen het betreffende onderdeel | Gezonde kern blijft bruikbaar; oude beleidskopieën krijgen geen cumulatieve beslismacht |
| U4 — Toegestane opdrachten uitvoeren | Concrete autoriteit en doelen correct herkennen | Nul onterechte eigen weigeringen in de geteste toegestane scenario's; echte ontbrekende voorwaarden blijven zichtbaar |
| U5 — Schone versieovergangen | Eén duidelijke actieve runtime, eigendomsgebonden opruiming en herstel | Geen onverklaarde eigen actieve restanten, geen dubbele registraties en behoud van gebruikersdata binnen de geteste scope |

Deze eisen betreffen gedrag dat OPENCNTX zelf veroorzaakt of kan sturen. Het product kan providerbeleid, hostbevoegdheden, quota of ontbrekende toegang niet opheffen. Een dergelijke externe beperking wordt apart benoemd en leidt niet tot nutteloze retries of een algemene blokkade van onafhankelijk toegestaan werk.

### Werkregels zonder nieuwe bureaucratie

- Normale leesacties, implementatiestappen en controles binnen de actuele opdracht vragen geen extra OPENCNTX-goedkeuringsronde.
- Geldige toestemming blijft bruikbaar binnen haar concrete scope. Opnieuw lezen of een gewijzigde bestandshash betekent niet automatisch opnieuw toestemming vragen.
- Een fasegrens, een geslaagde test of een afgeronde subtaak is geen zelfstandige reden om te stoppen wanneer opgedragen werk resteert.
- Vraag alleen om werkelijk ontbrekende beslisinformatie, bevoegdheid of een wezenlijk nieuw effect buiten de opdracht. Bundel tegelijk bekende vragen.
- Respecteer een expliciete stop of gewijzigde opdracht. Blokkeer bij een deelprobleem alleen de afhankelijke route.
- Beperk automatische herstelpogingen. Als werkdefault: hoogstens één automatische herstelpoging na dezelfde mislukking zonder nieuwe informatie; daarna pas verder proberen bij een relevante toestandswijziging. Verschillende nuttige diagnosehandelingen zijn niet hetzelfde als dezelfde actie herhalen.
- Gebruik eventgedreven wachten waar beschikbaar. Vermijd identieke statusherhaling en ongewijzigde volledige rapporten in de modelcontext; respecteer wel de communicatieregels van de gebruikte host.
- Leg bewijs compact vast: commit, testresultaat en relevante beperking. Geen apart dossier per toolcall en geen extra modelcall om tellers of status te formuleren.

### Voortgang bijhouden

Taakstatussen: **Gepland**, **Bezig**, **Geblokkeerd**, **Klaar**, **Uitgesteld**. Vink alleen Klaar aan. Uitgesteld betekent expliciet buiten de actuele scope, niet geleverd. Noteer bij Geblokkeerd oorzaak en kleinste vervolgstap; onafhankelijk werk kan doorgaan.

Elke taak heeft doel, werk, acceptatie en afhankelijkheden. Werk na een betekenisvolle afronding de actuele stand en het log bij. De analyse blijft onderzoeksbron; alleen deze notitie is de actieve uitvoeringslijst.

## 3. Fasen en afhankelijkheden

| Fase | Doel | Taken | Mijlpaal |
|---|---|---|---|
| A — Werkbasis | Bestaand bewijs benutten en fouten reproduceerbaar vastleggen | N01–N02 | M-A: bekende bron en vaste regressiebasis |
| B — Defecten en frictie | Autoriteit, routes, sync, updatepreflight en capsules verbeteren | N03–N09 | M-B: aantoonbare fouten opgelost, juiste routekeuze |
| C — Installatie en diagnose | Onderdelen beheren, herstellen en begrijpelijk controleren | N10–N13 | M-C: schone, geteste installatielevenscyclus |
| D — Context en gebruik | Compact hervatten, kosten meten en eenvoudig starten | N14–N17 | M-D: hervatbewijs en eerste gebruiks-/kostenvergelijking |
| E — Gerichte vervolgstappen | Optionele integraties, schaalmeting en bredere pilot | N18–N21 | M-E: gekozen uitbreidingen en praktijkclaims onderbouwd |
| F — Release | Herkomst automatiseren en een werkelijk afgebakende release opleveren | N22–N24 | M-F: geverifieerde publicatie wanneer opgedragen |

Dit is een logische volgorde, geen verplichte wachtrij voor ieder bestand. N03, N05, N07 en N08 kunnen na hun benodigde basis onafhankelijk worden aangepakt. N22 kan vanaf N01 worden voorbereid. N16 begint zodra de benodigde context- en routingfuncties meetbaar zijn; een optionele export hoeft daarvoor niet klaar te zijn.

**Twee opleveringsniveaus:** een afgebakende technische herstelrelease hoeft niet op alle optionele uitbreidingen of twee weken pilot te wachten. Een brede claim over bewezen hostgedrag, kostenwinst of algemene adoptie vereist wel passend praktijkbewijs. N23 legt vast welk niveau werkelijk wordt geleverd.

## 4. Fase A — Werkbasis en reproduceerbaar bewijs

### N01 — Werkbasis, bewijs en wijzigingsscope vastleggen

- [ ] **Status: Gepland**

**Doel:** ontwikkelen vanuit een bekende bron, zonder publicatiebewijs te verwarren met voltooide productverbetering.

**Werk:**

- Controleer de werkelijke repositorytoestand, gekozen bron en bestaande wijzigingen. Behoud de analysebron en gebruikerswijzigingen.
- Kies een afzonderlijke ontwikkelbasis; gebruik de tag 1.7.0 als vergelijkingspunt.
- Neem de bestaande release-, CI- en auditbewijzen over met hun precieze grenzen.
- Leg vast welke voorstellen bij de eerstvolgende wijzigingsset horen en welke optioneel blijven. Nog geen ononderbouwde datum of versiebelofte.
- Gebruik N-codes voor de nieuwe planning; R-codes in eerdere analyses verwijzen naar de vervangen roadmap.

**Acceptatie:** bron en werkdirectory zijn ondubbelzinnig; alle F01–F16 en V01–V12 hebben een bestemming in §12; bestaand bewijs staat los van nieuwe acceptatie.

**Afhankelijk van:** geen. **Bron:** analyse hoofdstukken 1, 2.7 en 5.1; V09–V10.

### N02 — Herhaalproeven opnemen als officiële regressietests

- [ ] **Status: Gepland**

**Werk:**

- Zet de vier begrensde auditproeven om in onderhoudbare tests voor sync, governance, updatepreview en capsuleverificatie.
- Maak positieve en negatieve gevallen expliciet; gebruik onschuldige fixtures en tijdelijke lokale repositories.
- Voeg een kleine gebruikersscenarioset toe voor gewone vraag, lokale wijziging, meerdere doelen, vooraf toegestaan extern schrijven, faseovergang, optionele fout, sessiehervatting en gebruikersstop.
- Bewaar het verschil tussen codebewijs, fixturegedrag en live hostgedrag.

**Acceptatie:** de bestaande fouten zijn op de ongewijzigde basis aantoonbaar reproduceerbaar; bij iedere fix gaat het bijbehorende negatieve geval over naar het correcte resultaat. Een oude fout als verwacht gedrag testen telt niet als oplossen. Diagnostische nog-falende regressies mogen de gewone CI niet ongemerkt onbruikbaar maken; integreer ze samen met de fix of zichtbaar apart.

**Afhankelijk van:** N01. **Bron:** actuele auditproeven, F04/F07/F08/F09, U1–U5.

**M-A:** de implementatie kan starten zonder opnieuw de hele eerdere analyse te maken.

## 5. Fase B — Concrete defecten en onnodige frictie

### N03 — Concrete actie- en toestemmingsbinding implementeren

- [ ] **Status: Gepland**

**Werk:**

- Beschrijf operatie, afzonderlijke doelen of benoemde doelverzameling, effectklasse, opdrachtbron en relevante revisie.
- Scheid een verificatielease van autoriteit: broncontrole vernieuwen is niet hetzelfde als toestemming verliezen.
- Maak expliciet toegestaan extern schrijven onderscheidbaar van ontbrekende toestemming.
- Ondersteun meerdere afzonderlijk gebonden doelen; verwijder niet alleen een blokkade zonder het contract te verbeteren.
- Behoud correcte intrekking en detectie van wezenlijk nieuwe scope.

**Acceptatie:** de F07-proeven blokkeren niet meer uitsluitend wegens extern schrijven of meerdere doelen wanneer concrete geldige bindings bestaan. Dezelfde opdracht vraagt geen herbevestiging per bestand. Een andere bestemming of ingetrokken toestemming wordt wel herkend. Hervatten behoudt de herkomst van autoriteit, niet slechts een algemene goedgekeurd-boolean.

**Afhankelijk van:** N01 en de relevante N02-scenario's. **Bron:** V01, F07.

### N04 — De drie eenvoudige gebruikersroutes werkelijk aansluiten

- [ ] **Status: Gepland**

**Werk:**

- Gebruik ANSWER_ONLY voor gewone antwoorden zonder duurzame procesadministratie.
- Laat kleine omkeerbare wijzigingen LIGHT_TASK gebruiken en behoud GOVERNED_FLOW waar afhankelijkheden of hervatbehoefte dit vragen.
- Maak waarschuwing, herstelbare verouderde projectie, optionele fout en echte bronintegriteitsfout onderscheidbaar.
- Koppel beslissingen aan de daadwerkelijke CLI-/libraryroute; een classifier alleen is niet voldoende.
- Vervang concurrerende eigen beleidskopieën door één actuele beslisbron met duidelijke herkomst.

**Acceptatie:** nul overbodige eigen toestemmingsvragen, onterechte eigen weigeringen of voortijdige eigen stops in de positieve scenarioset. Een optionele fout blokkeert geen gezonde onafhankelijke route. Een expliciete stop wordt gerespecteerd. De live-hostclaim blijft open tot N18 die onderbouwt.

**Afhankelijk van:** N03. **Bron:** V01/V10, F07/F13/F16, U1/U3/U4.

### N05 — Sync aan één onveranderlijke snapshot binden

- [ ] **Status: Gepland**

**Werk:**

- Gebruik dezelfde vastgelegde bytes voor preview, scan, materialisatie en staged Git-tree.
- Maak de behandeling van een gewijzigde bron expliciet: de goedgekeurde snapshot leveren of opnieuw beoordelen.
- Controleer vóór push de inhoudsbinding en na aflevering de bedoelde bestemming en commit.
- Behoud bruikbare lokale voortgang onafhankelijk van extern afleveringsbewijs.

**Acceptatie:** de sync-raceproef kan geen gewijzigde bronbytes onder de oude preview publiceren. Receipt, preview en geleverde inhoud zijn controleerbaar gebonden. Een nieuwe bronrevisie is geen reden om de gehele gebruikersopdracht opnieuw te laten goedkeuren als de scope gelijk blijft.

**Afhankelijk van:** N01 en de relevante N02-proef. **Bron:** V02, F04.

### N06 — Git begrenzen en privacystatus juist benoemen

- [ ] **Status: Gepland**

**Werk:**

- Geef lokale Git-inspectie en netwerkoperaties passende, geteste tijdsbudgetten.
- Voorkom verborgen interactieve prompts en beheer afgebroken subprocessen, relevante descendants en tijdelijke resources per ondersteund platform.
- Onderscheid timeout, ontbrekende authenticatie, conflict en afwijzing; gebruik begrensd retrygedrag.
- Scheid door de gebruiker gedeclareerde privacy van providergecontroleerde privacy en onbekende zichtbaarheid.
- Maak een provideradapter optioneel; geen nieuwe netwerkvoorwaarde voor de lokale kern.

**Acceptatie:** een hang eindigt binnen de gedocumenteerde en geteste routegrens; het lokale checkpoint blijft bruikbaar. Een ongewijzigde fout veroorzaakt geen lus. Een privacyverklaring wordt niet als live providerbewijs gepresenteerd. Test een gewijzigde bestemming en een bekende publieke bestemming.

**Afhankelijk van:** N05 voor geïntegreerd syncbewijs. **Bron:** V02, F05/F06.

### N07 — Overlap van updatepaden volledig vooraf controleren

- [ ] **Status: Gepland**

**Werk:**

- Vergelijk active-, candidate-, backup- en statepaden paarsgewijs, ook tussen verschillende componenten.
- Test gelijkheid, ongeoorloofde nesting, Windows-casevarianten en relevante reparse-/normalisatiegevallen.
- Controleer concrete eigendoms- en directorygrenzen voordat iets wordt gewijzigd.
- Gebruik een begrijpelijke volledige vergelijking binnen de begrensde componentlijst.

**Acceptatie:** twee componenten met hetzelfde activepad worden vóór de eerste mutatie afgewezen. Geldige gescheiden plannen blijven werken. Een afgewezen plan maakt geen staging, backup of journal aan en verandert geen gebruikersdata.

**Afhankelijk van:** N01 en de relevante N02-proef. **Bron:** V03, F08.

### N08 — Capsuleverificatie uniek, strikt en begrensd maken

- [ ] **Status: Gepland**

**Werk:**

- Weiger dubbele genormaliseerde manifestpaden en ongeldige veldtypen.
- Begrens manifest, memberaantal, individuele uitgepakte bytes en totaal zowel vóór als tijdens verwerking.
- Gebruik streaming hashing waar volledige geheugeninlezing onnodig is.
- Test padvarianten, ontbrekende/extra members en kleine synthetische grensgevallen.
- Bewaar standalone archive-verify en volledige import-health als aparte bewijsstappen.

**Acceptatie:** de dubbele-recordproef faalt terecht; te grote input stopt vroeg zonder onbegrensde verwerking; geldige ondersteunde historische capsules blijven bruikbaar. Een groen archieflabel claimt niet zonder meer een gezonde geïmporteerde projecttoestand.

**Afhankelijk van:** N01 en de relevante N02-proef. **Bron:** V04, F09/F10.

### N09 — Kritieke JSON- en bestandscontroles harmoniseren

- [ ] **Status: Gepland**

**Werk:**

- Inventariseer verschillen bij records die import, update, herstel en duurzame voortgang sturen.
- Maak behandeling van dubbele keys, veldtypen, onbekende velden en formatversies expliciet.
- Hergebruik bestaande correcte validators en behoud bedoelde oude leesroutes.
- Leg per route de relevante symlink-/reparse- en concurrentiegrenzen vast.

**Acceptatie:** dezelfde soort kritieke ongeldige input wordt niet toevallig via de ene ingang geaccepteerd en via de andere geweigerd. Nieuwe beperkingen zijn getest en gedocumenteerd; niet-geteste races worden niet als opgelost gepresenteerd.

**Afhankelijk van:** N07–N08. **Bron:** V04, F11.

**M-B:** de vier aangetoonde defecten zijn opgelost in de betrokken routes, Git is begrensd en de positieve/negatieve autoriteitsscenario's slagen. Uitgebreide live hostwerking is nog een aparte claim.

## 6. Fase C — Schone installatielevenscyclus en diagnose

### N10 — Installatie-eigenaarschap en compatibiliteit vastleggen

- [ ] **Status: Gepland**

**Werk:**

- Scheid runtimeversie, dataformat en hostadapterversie.
- Kies één eerste concrete ondersteunde installatievorm en test de gebruikte package-managerinterface.
- Registreer alleen eigen onderdelen: locatie, component, versie, digest of configuratiewaarde en scope.
- Behandel gedeelde configuratie per eigen entry; laat package-manageronderdelen bij de package manager.
- Detecteer meerdere executables en gewijzigde eigen bestanden. Maak installatieherhaling idempotent.

**Acceptatie:** elk eigen onderdeel is herleidbaar; gebruikersdata en onbekende onderdelen zijn niet automatisch verwijderbaar. De gekozen runtime en compatibiliteitscombinatie zijn uitlegbaar. Een ontbrekend oud manifest veroorzaakt geen brede schoonmaak.

**Afhankelijk van:** N01 en N07. **Bron:** V03, F12/F13, U5.

### N11 — De update-toestandsmachine met herstel implementeren

- [ ] **Status: Gepland**

**Werk:** verbind bestaande preview, staging en journalbouwstenen tot onderstaande route. De machine beslist deterministisch op manifests, actuele inhoud en herstelstatus; geen model bepaalt welke bestanden weg mogen.

1. **Inventariseren:** actieve runtime, eigen registraties, oud manifest, nieuwe manifestversie en dataformats bepalen.
2. **Verschilplan:** behouden, toevoegen, vervangen, eigen ongewijzigd verouderd verwijderen, aangepast/onbekend bewaren.
3. **Preflight:** overlap, compatibiliteit, ruimte, locks en relevante uitvoerbevoegdheid controleren; één updater krijgt mutatie-eigenaarschap.
4. **Voorbereiden:** geïsoleerde kandidaat en herstelbare journalovergangen; een datamigratie behoudt een bruikbare herstelbasis.
5. **Kandidaat testen:** inhoudsbinding, import/CLI-rooktests en de gekozen compatibiliteitsroute controleren.
6. **Activeren:** expliciet readercontract uitvoeren; voor de eerste route bij voorkeur korte gecontroleerde stilstand van deelnemende readers. Geen totaalatomiciteit claimen als niet alle betrokken readers meedoen.
7. **Readback:** werkelijk gestarte executable, versie, leesbare data en actieve eigen verwijzingen controleren.
8. **Opruimen:** alleen eigen ongewijzigde verouderde onderdelen binnen opnieuw gecontroleerde grenzen verwijderen; vervolgens definitief resultaat registreren.

Bij falen vóór gezonde activering wordt een consistente vorige toestand hersteld. Bij alleen een opruimfout blijft een gezonde nieuwe runtime bruikbaar met een expliciete nog-op-te-ruimen-status. Hervatten met hetzelfde plan herhaalt voltooide mutaties niet blind.

**Bewaarbeleid:** standaard maximaal één benoemde rollbackgeneratie buiten actieve zoekpaden. Verwijder een oudere eigen generatie pas als de nieuwe herstelbasis geverifieerd is. Noodzakelijke migratiebackups zijn geen wegwerpbare cache. Aangepaste/ongekende bestanden blijven verklaarde uitzonderingen, geen verborgen restanten.

**Acceptatie:** onderbreking bij iedere relevante journalovergang is herstelbaar; er ontstaat geen ongeldige mix voor deelnemende readers. Test twee updaters, stale lock, filelock, weinig ruimte, gewijzigd bestand en hervatten. Geen dubbele eigen hook/launcher en geen onverklaarde actieve oude verwijzing in een geslaagde schone route.

**Afhankelijk van:** N07, N09 en N10. **Bron:** V03, F08/F12.

### N12 — Upgrade, uninstall en het oude hookincident bewijzen

- [ ] **Status: Gepland**

**Werk:**

- Test schone installatie, 1.7.0 naar de gekozen kandidaat, herinstallatie, mislukte upgrade, ondersteunde rollback en uninstall.
- Leg voor eerdere ondersteunde versies een migratiepad of een vroege concrete incompatibiliteitsmelding vast.
- Test een ontbrekend oud manifest, gedeelde configuratie en later toegevoegde gebruikersdata.
- Maak een fixture met een eigen hook die naar een verdwenen script wijst en een oude algemene stopmarker.
- Laat ontkoppelen uitsluitend de exact bedoelde eigen integratie verwijderen; geen globale configuratiereset.

**Acceptatie:** ongewijzigde gebruikersdata blijven bytegelijk; bedoelde migraties slagen inhoudelijk én op herstel. Uninstall verwijdert alleen eigen gekozen onderdelen. De verdwenen hook veroorzaakt geen recursieve stoplus. Geen bewijsclaim dat een verse clone alleen de actieve installatie schoonmaakt.

**Afhankelijk van:** N11. **Bron:** V03/V08, historisch hookscenario, U5.

### N13 — Eén read-only diagnose met bruikbare uitleg leveren

- [ ] **Status: Gepland**

**Werk:**

- Bundel bestaande controles voor executable, package, project, dataformats, bronintegriteit, eigen hooks, sync en export.
- Toon één begrijpelijke hoofdstatus met component, oorzaak, impact en kleinste vervolgstap per relevante afwijking.
- Gebruik NOT_CHECKED voor niet-gecontroleerde onderdelen.
- Maak een machineleesbare uitvoer naast korte mensentekst, zonder modelcall.
- Toon actieve generatie, rollbackset en pending cleanup uit het manifest.

**Voorgestelde interface:** opencntx doctor --project <pad> --json. Dit commando is ontwerp, geen reeds beschikbare functie.

**Acceptatie:** diagnose schrijft niets en initialiseert geen ontbrekende store. Een optionele fout maakt de gezonde kern niet defect. Test meerdere executables, verkeerd dataformat, ontbrekend script en stale projectie. Herstel blijft een concrete operatie, niet een verborgen neveneffect van lezen.

**Afhankelijk van:** N04, N06 en N10; update-/herstelgevallen uit N11–N12 voor volledige afronding. **Bron:** V05, X01/X04.

**M-C:** het gekozen installatiepad is aantoonbaar te installeren, bij te werken, te herstellen en te verwijderen; de hoofdstatus is te begrijpen zonder een tweede uitgebreide AI-analyse.

## 7. Fase D — Compacte context, hervatten en eerste gebruiksmetingen

### N14 — Eén compact en betrouwbaar hervatpakket aansluiten

- [ ] **Status: Gepland**

**Werk:**

- Hergebruik bestaande velden voor doel, uitkomst, relevante besluiten, onzekerheden, bewijs en volgende uitvoerbare stap.
- Maak één actuele projectie; onderscheid historische en vervangen besluiten.
- Lees lange achtergrond alleen wanneer die nodig is.
- Bewaar de oorspronkelijke outcomes na een tijdelijke reparatie.
- Verwijs alleen naar een bestaande contextbasis wanneer de ontvangende sessie die daadwerkelijk heeft.

**Acceptatie:** een nieuwe sessie zonder oude chat vervolgt het juiste doel zonder herhaling van bekende beslissingen. Test bronwijziging, vervangen besluit, ontbrekend bewijs en terugkeer na herstel. Geen verborgen volledige archiefdump en geen ontbrekende basis achter een cacheverwijzing.

**Afhankelijk van:** N04 en relevante kritieke-recordafspraken uit N09. **Bron:** V07, F13/F15.

### N15 — Token-/contextbudgetten en metingen implementeren

- [ ] **Status: Gepland**

**Werk:**

- Scheid nuttige broncontext, eigen instructies/metadata, historie, tooluitvoer en opnieuw verzonden inhoud.
- Tel bytes; gebruik exacte tokens alleen met betrouwbare tokenizer/usagegegevens. Label schattingen en onbekende waarden.
- Voeg geen modelcall toe voor telling, autoriteitscontrole, formattering of statusadministratie.
- Voorkom dubbele beleidsbundels en selecteer context op relevantie en actuele revisie.
- Begin met de onderstaande meetbudgetten; stel ze vóór vergelijkingen vast en pas ze alleen zichtbaar aan.

| Route | Startvoorstel voor eigen extra context |
|---|---|
| Gewoon antwoord | 0–300 instructietokens |
| Kleine taak | 300–800 instructietokens |
| Hervatten | 800–1.500 tokens voor het compacte hervatpakket |

Deze intervallen zijn ontwerpbegrotingen, geen minimumverbruik, bewezen besparing of harde grens op noodzakelijke broninhoud. Minder is goed wanneer het resultaat correct blijft. Overschrijding leidt eerst tot selectie/compactie, niet tot stilzwijgend verlies van verplichtingen of een automatische extra goedkeuringsvraag.

**Acceptatie:** geen administratieve modelcalls; geen dubbele beleidsinjectie in één overdracht; essentiële doelen en bronbinding blijven behouden. Exacte usage, schatting en onbekend zijn zichtbaar verschillend. Euroclaims vereisen een bekende afrekenvorm en toepasselijke tarieven.

**Afhankelijk van:** N04 en N14. **Bron:** V06, U2.

### N16 — Vroeg frictie en kosten vergelijken

- [ ] **Status: Gepland**

**Werk:**

- Gebruik eerst de vaste onschuldige scenarioset; voor een echte taak pas een concreet passend, niet-kritisch project.
- Vergelijk gelijkwaardige taken met hetzelfde model, instellingen en kwaliteitscriterium, met en zonder OPENCNTX.
- Registreer tokens per correct afgeronde taak, tijd, extra vragen, onterechte stops, dubbel onderzoek en herstelwerk.
- Houd OPENCNTX-, host-, provider- en externe-foutoorzaken apart.
- Wissel waar mogelijk volgorde en rapporteer kleine steekproeven als indicatie.

**Acceptatie:** reproduceerbare nulmeting en eerste vergelijking bestaan. Geen onverklaarde regressie in eigen overhead en geen verborgen kwaliteitsverlies. Bevestigde eigen frictiefouten krijgen gerichte regressies. Ontbrekende hostusage betekent onbekend, niet nul. Deze ontwikkelproef claimt niet de brede pilot te vervangen.

**Afhankelijk van:** N14–N15; een echte hostclaim vereist aanvullend N18. **Bron:** V06/V07, F15, X03.

### N17 — Quickstart, upgrade-uitleg en featurestatus vereenvoudigen

- [ ] **Status: Gepland**

**Werk:**

- Geef één kort standaardpad naar init, preview, pack en verify.
- Introduceer workspace, governed flow en host pas waar nodig.
- Beschrijf de werkelijk ondersteunde installatiemethode, actieve executable en readback na upgrade.
- Label CLI, library, contract, fixture, experimenteel en gepland correct.
- Controleer niet alleen het versienummer maar ook welke functies daadwerkelijk geleverd zijn.
- Houd gewijzigde webinhoud, automatische structuurchecks en echte visuele review als verschillende bewijzen herkenbaar.

**Acceptatie:** een nieuwe gebruiker kan de route zonder ontbrekende mondelinge stappen volgen. Uitleg suggereert geen onbewezen schone upgrade, kostenbesparing of algemene hostwerking. Huidige en historische documentatie spreken niet als concurrerende actuele instructies.

**Afhankelijk van:** N04 en N13; relevante gebruikswaarnemingen uit N16. **Bron:** V10, F02/F13/F16.

**M-D:** compact hervatten en eerste gebruiksmetingen werken. De bewijsgrens voor eventuele kosten-/hostclaims blijft expliciet.

## 8. Fase E — Selectieve uitbreidingen en praktijkbewijs

### N18 — Eén optionele hostadapter aantonen

- [ ] **Status: Gepland — optionele uitbreiding**

**Werk:**

- Kies één concrete host voor de eerste integratie; beperk de koppeling tot context/status lezen, opdracht doorgeven en checkpoints terugmelden.
- Hergebruik actie-/autoriteitsbinding en installatie-eigenaarschap.
- Test aansluiten, herstarten, loskoppelen en werken zonder adapter.
- Test expliciete stop, faseovergang, verdwenen script en optionele fout.
- Scheid adviserend gedrag van daadwerkelijk afgedwongen hostgedrag.

**Acceptatie:** de vaste positieve en negatieve scenario's slagen in de gekozen host; geldige scope vraagt geen herbevestiging; een defecte koppeling veroorzaakt geen globale stoplus. De lokale kern blijft zelfstandig werken. Geen algemene installatie op alle projecten.

**Afhankelijk van:** N03–N04, N12–N15. **Bron:** V08, F13, U1/U3/U4.

**Scopegrens:** alleen nodig voor releases die deze nieuwe hostintegratie leveren of haar gedragswinst claimen. Een hosttest gebruikt een overeengekomen geïsoleerde testomgeving; publicatie activeert geen host.

### N19 — Eenrichtings-Obsidian-export implementeren

- [ ] **Status: Gepland — optionele uitbreiding**

**Werk:**

- Bind export aan één gekozen bestand of herkenbare gegenereerde sectie en bronrevisie.
- Behoud menselijke inhoud en detecteer gelijktijdige edits.
- Lees geschreven inhoud terug vóór aflevering als geslaagd geldt.
- Test offline bestemming, filelock, herhaalde aflevering en conflictgedrag van de gekozen synchronisatiemap.
- Houd machine-store en menselijke projectie gescheiden.

**Acceptatie:** menselijke edits worden niet stilzwijgend overschreven; een mislukte export is geen groen ontvangstbewijs en maakt lokale taakvoortgang niet onbruikbaar. Geen brede vaultscan, automatische tweerichtingssynchronisatie of impliciete toegang tot andere notities.

**Afhankelijk van:** N10 en N14; foutuitleg sluit aan op N13. **Bron:** V12.

**Scopegrens:** een kernherstelrelease hoeft niet op deze uitbreiding te wachten. Deze roadmap zelf wordt niet automatisch een machinegestuurd exportdoel.

### N20 — Schaalgedrag meten en alleen bewezen bottlenecks oplossen

- [ ] **Status: Gepland — meting verplicht, optimalisatie conditioneel**

**Werk:**

- Meet koude/warme status, pakketopbouw, voortgang en hervatten bij 10, 100 en 1.000 representatieve taken.
- Registreer tijd, gelezen/geschreven bytes en writes; test lokale opslag en de gekozen synchronisatieroute apart.
- Onderzoek ledgersegmenten, snapshots of caching alleen bij aantoonbaar nut.
- Behoud detectie van drift, historische leesbaarheid en crash-/herstelbetekenis.
- Neem optionele export alleen in de benchmark op als die daadwerkelijk geleverd wordt.

**Acceptatie:** een herhaalbare baseline en gemotiveerde beslissing bestaan. Eventuele optimalisatie heeft vergelijkbaar voor/na-bewijs zonder correctheidsverlies. Een onderbouwd besluit om niets te wijzigen kan deze taak afronden; het is geen claim dat iedere denkbare schaal getest is.

**Afhankelijk van:** N14–N15 voor de contextbasis; betrokken gewijzigde routes moeten testbaar zijn. **Bron:** V11, F14.

### N21 — Brede praktijkpilot en adoptiebeoordeling

- [ ] **Status: Gepland — vereist voor brede praktijkclaims**

**Werk:**

- Selecteer één echt niet-productiekritisch project, kandidaatversie, optionele onderdelen en terugkeerroute.
- Leg de meetcriteria vóór de pilot vast, voortbouwend op N16.
- Voer gewone werkzaamheden uit; registreer alleen betekenisvolle resultaten en incidenten.
- Test minstens drie echte herstarts/overdrachten.
- Behoud de brede evaluatiegrens van minstens twee volledige weken én minstens 25 echte taken.
- Markeer relevante tussentijdse wijzigingen en herneem waar nodig de vergelijking; tel niet ongemerkt verschillende kandidaten samen.

**Acceptatie:** beide minimumgrenzen en de overdrachten zijn gehaald, met een eerlijk oordeel over frictie, kosten, kwaliteit en onderhoud. Geen verloren vereiste outcomes of onbedoelde wijzigingen buiten scope. Een ernstig incident pauzeert de getroffen route tot herstel; onafhankelijk werk hoeft niet stil te vallen. Bevestigde onopgeloste eigen regressies verhinderen een positieve brede adoptieclaim.

**Afhankelijk van:** N12–N17 en de tijdens de pilot gebruikte uitbreidingen. N20 levert relevante schaalinformatie, geen vervanging voor de pilot. **Bron:** F15, analyse hoofdstuk 5, U1–U5.

**Scopegrens:** deze pilot is geen automatische kalenderblokkade voor iedere kleine technische bugfixrelease. Zonder pilot blijven brede claims over bewezen praktijkwinst open.

**M-E:** de geselecteerde uitbreidingen en praktijkclaims hebben passend bewijs. Niet geselecteerde uitbreidingen blijven zichtbaar Gepland of Uitgesteld, niet geleverd.

## 9. Fase F — Releaseherkomst, kandidaat en publicatie

### N22 — De correcte releaseketen automatiseren

- [ ] **Status: Gepland**

**Werk:**

- Bind pakketversie, uiteindelijke tagcommit, tree en artifactdigests aan dezelfde bron.
- Controleer de vereiste CI op de uiteindelijke commit vóór publicatie; geen testmerge als onverklaarde vervanging voor releasecommitbewijs.
- Bouw/verifieer wheel en sdist en test hun geïnstalleerde routes in geïsoleerde omgevingen.
- Maak een herstart na gedeeltelijke upload idempotent en voorkom dubbele publicatie.
- Automatiseer readback van tag, metadata en downloadbytes.
- Hergebruik de bestaande publicatieopdracht binnen scope; geen extra goedkeuringsvraag per asset.

**Acceptatie:** negatieve tests ontdekken verkeerde commit met gelijke tree, pending/failed CI, afwijkend artifact en ontbrekende/partiële aflevering. Dry-run, gepubliceerd en geïnstalleerd zijn afzonderlijke statussen. Bestaande tags en assets blijven intact. De core blijft zonder release-infrastructuur bruikbaar.

**Afhankelijk van:** N01; kan vroeg worden ontwikkeld, definitief kandidaatbewijs via N23. **Bron:** V09, F01/F03.

### N23 — Afgebakende kandidaat en releasegereedheid beoordelen

- [ ] **Status: Gepland**

**Werk:**

- Leg de exacte geleverde scope vast en kies een passend nieuw versienummer; 1.7.0 blijft onveranderd.
- Selecteer de toepasselijke N-taken en U-eisen. Noem niet geleverde onderdelen expliciet.
- Controleer dat fixes werkelijke gedragstests hebben en actuele functionele claims bij de code passen.
- Gebruik N17 voor documentatie, N22 voor bron-/buildbinding en vers bewijs voor de definitieve kandidaat.
- Beoordeel skips, testplatformen, beperkingen en relevante frictie-/kostenmetingen.
- Maak een upgrade- en herstelbeschrijving passend bij wat daadwerkelijk verandert.

**Acceptatie:** voor iedere geclaimde verbetering bestaat een geïmplementeerd resultaat en actueel bewijs. Geen materiële onopgeloste fout wordt groen verklaard. Een afgebakende release kan gereed zijn terwijl optionele taken openstaan, maar niet door ze als uitgevoerd te presenteren. Releasegereed betekent nog niet gepubliceerd of hier geïnstalleerd.

**Afhankelijk van:** N17, N22 en alle taken die bij de vastgelegde release-inhoud horen; voor een integrale herstelrelease in ieder geval N01–N17 en N20. Brede praktijkclaims vereisen N21; host-/exportclaims respectievelijk N18/N19.

### N24 — Publiceren en publieke pagina's verifiëren wanneer opgedragen

- [ ] **Status: Gepland — publicatiestap, niet nu uitgevoerd**

**Werk:**

- Gebruik de dan geldige concrete publicatieopdracht voor de gekozen kandidaat.
- Publiceer exact de geverifieerde tag en assets; bevestig de bedoelde latest-/release-status.
- Werk actuele README, changelog, installatie-/release-informatie en betrokken publieke websitebron consequent bij.
- Claim geen gehoste site of wiki wanneer alleen repositorybron bestaat; een nieuwe hostingdienst is geen impliciet onderdeel.
- Download de echte assets en controleer bytes, commit/tree, metadata en beschikbaarheid.
- Registreer publicatie afzonderlijk van lokale installatie en brede activering.

**Acceptatie:** releasepagina, huidige publieke claims en downloads zijn live gecontroleerd en verwijzen naar de juiste kandidaat. Zonder daadwerkelijke publicatie blijft N24 open. Publicatie is geen installatie of activering.

**Afhankelijk van:** N23 en een geldige opdracht om de volgende concrete release te publiceren. **Bron:** V09/V10.

**M-F:** de geselecteerde inhoud is eerlijk gepubliceerd en teruggelezen. Dit markeert niet automatisch alle optionele onderdelen of de volledige roadmap als voltooid.

## 10. Optionele uitbreidingsthema's zonder extra infrastructuur

De analyse noemt vier uitbreidingsthema's. Zij worden waar passend binnen bovenstaande taken opgenomen, niet als een tweede backlog met eigen verplichte documenten.

| Thema | Verwerking | Bewijsgrens |
|---|---|---|
| X01 — Waarom staat dit stil? | N03/N13: concrete beslisreden en kleinste vervolgstap | Geen tweede policy-engine |
| X02 — Contextverschillen tonen | Later verfijnen binnen N14/N15 | Alleen delta als de ontvanger de juiste basis bezit; anders volledige compacte context |
| X03 — Lokaal frictie-overzicht | N16: kleine deterministische samenvatting | Geen standaard externe telemetrie of extra modelcalls |
| X04 — Gezondheid over generaties | N10–N13: actieve runtime, rollbackset en pending cleanup | Leesvenster op eigen manifest; geen systeemwijde schoonmaak |

Een build-attestatie blijft een mogelijke latere verbetering van N22. Zij versterkt herkomstbewijs, niet functionele correctheid, en wordt geen voorwaarde om de lokale kern te gebruiken.

## 11. Eindcriteria per soort resultaat

### A. Technische herstelkwaliteit

- [ ] De relevante auditreproducties zijn als regressies opgenomen en de afgesproken defecten zijn opgelost.
- [ ] Geldige concrete autoriteit wordt hergebruikt; echte scope-uitbreiding en intrekking blijven herkenbaar.
- [ ] De kern werkt zonder optionele host-/notitiekoppeling.
- [ ] Betrokken externe processen en herstelpogingen zijn begrensd.
- [ ] Updateclaims zijn bewezen met de gekozen installatievorm, onderbrekingen en gebruikersdatabehoud.
- [ ] Diagnose is read-only, compact en geeft een bruikbare vervolgstap.
- [ ] Hervatten behoudt het doel en verplichte outcomes.
- [ ] Contextmeting veroorzaakt geen eigen administratieve modelcalls en geen onverklaarde regressie.
- [ ] De geleverde functies, versies en beperkingen zijn in de documentatie consistent.

### B. Brede gebruiks- en adoptieclaims

- [ ] De gekozen echte hostscenario's zijn bewezen als er hostwerking wordt geclaimd.
- [ ] De echte pilot voldoet aan de afgesproken duur, taken en overdrachten.
- [ ] Een claim over besparing gebruikt vergelijkbare taken, kwaliteit en betrouwbare usage of gelabelde schattingen.
- [ ] Bevestigde eigen frictieregressies zijn opgelost; onmeetbare zaken blijven expliciet onbekend.

### C. Publicatie

- [ ] De definitieve commit, tag, buildrecord en artifacts zijn aan elkaar gebonden.
- [ ] Vereiste CI op de releasecommit is geslaagd vóór publicatie.
- [ ] Publieke downloads en actuele pagina's zijn teruggelezen.
- [ ] Publicatie, installatie en activering worden niet met elkaar verward.

Alleen criteria die horen bij de daadwerkelijk gekozen scope bepalen die releasegereedheid. De niet-toepasselijke criteria blijven zichtbaar en worden niet als geslaagd afgevinkt. Een scopewijziging wordt kort gemotiveerd in het log; zij mag geen kapotte geclaimde functie verhullen.

## 12. Traceerbaarheid naar de analyse

### Voorstellen V01–V12

| Analysevoorstel | Nieuwe taken |
|---|---|
| V01 — Autoriteit en weinig vragen | N03–N04, N18 |
| V02 — Snapshot en begrensde sync | N05–N06 |
| V03 — Schone updates | N07, N10–N12 |
| V04 — Kritieke inputcontrole | N08–N09 |
| V05 — Diagnose | N13 |
| V06 — Zuinige context | N15–N16 |
| V07 — Compact hervatten | N14 |
| V08 — Optionele host | N18 |
| V09 — Releaseketen | N01, N22–N24 |
| V10 — Uitleg en status | N01, N04, N17, N23–N24 |
| V11 — Opslagoptimalisatie | N20 |
| V12 — Obsidian-export | N19 |

### Bevindingen F01–F16

| Bevinding | Verwerking |
|---|---|
| F01 — Buildrecord/tag | Bestaand 1.7.0-bewijs behouden; structurele borging N22–N24 |
| F02 — Versiecommunicatie | Bestaande correctie behouden; N17/N23 voor actuele featureclaims |
| F03 — CI/publicatievolgorde | Bestaand 1.7.0-bewijs behouden; N22–N24 |
| F04 — Sync-race | N02, N05 |
| F05 — Git hangt | N06 |
| F06 — Privacyverklaring | N06 |
| F07 — Governance | N02–N04 |
| F08 — Overlappende updatepaden | N02, N07, N11 |
| F09 — Dubbele capsules | N02, N08 |
| F10 — Capsule-resourcegrenzen | N08 |
| F11 — Kritieke JSON-/padvalidatie | N09 |
| F12 — Samengestelde update/atomiciteit | N10–N12 |
| F13 — Contract versus integratie | N04, N13–N14, N17–N18 |
| F14 — Ledgergroei | N20 |
| F15 — Praktijkwinst | N16, N21, N23 |
| F16 — Onboarding | N04, N13, N17 |
| Historisch hookincident | N10–N13, N18 |

### Verhouding tot de vervangen roadmap

De eerdere R01–R32-codes in notitie 31/32 zijn historische verwijzingen, geen actuele taaknummers. De inhoud is herverdeeld: releasebasis naar N01/N22–N24; defecten naar N02–N09; gebruikersroute naar N03–N04/N13/N17; installatie en host naar N10–N13/N18; handoff en export naar N14–N15/N19; metingen en pilot naar N16/N20–N21. Er zijn geen oude open taken stilzwijgend als klaar overgenomen.

## 13. Buiten scope en bewaarde grenzen

Geen volledige herschrijving, verplichte vector-/cloudstack, algemene ingebouwde AI-agent, globale stopguard, onbeperkte-toestemmingsmodus, systeemwijde schoonmaak, brede vaultkoppeling of grote GUI. Een database, daemon of extra agentrol wordt alleen overwogen bij een aantoonbaar probleem dat niet eenvoudig met de bestaande bouwstenen kan worden opgelost.

Deze publicatie betreft de roadmap en bijbehorende publieke documentatie. Daarmee wordt geen roadmapfunctie geïmplementeerd, volgende software-release uitgebracht of lokale installatie uitgevoerd. Bij latere uitvoering gelden de actuele opdracht en geldige bestaande scope, zonder onnodige herbevestigingen.

## 14. Voortgangslog en hervatpunt

| Datum | Gebeurtenis | Resultaat | Volgende stap |
|---|---|---|---|
| 2026-09-09 | Roadmap volledig herschreven vanuit analyse 1.7.0 | N01–N24 gepland; geen nieuwe implementatie gestart; historische publicatiebasis apart vastgelegd | N01 |

**Hervatten:** lees §1, het laatste logitem en de actieve/eerstvolgende taak. Controleer daarna de werkelijke repositorytoestand. Open alleen de relevante analyseparagrafen en bestaande bewijsbestanden; de volledige oude chat hoeft niet opnieuw in context.

**Compact overdrachtsrecord:** actieve taak; laatste gecontroleerde resultaat; gewijzigde bestanden/commit; resterend werk; blokkade indien aanwezig; eerstvolgende concrete handeling. Bewaar dit bij voorkeur in het log met verwijzing naar bestaand bewijs.

## 15. Publieke bronnen

- [OPENCNTX 1.7.0 release](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.7.0).
- [Release-inhoud en bekende beperkingen](release-1.7.0.md).
- [Release-CI](https://github.com/CNTX-PROJECT/OPENCNTX/actions/runs/34386717966).
- [Tagvergelijking 1.6.3–1.7.0](https://github.com/CNTX-PROJECT/OPENCNTX/compare/v1.6.3...v1.7.0).
- [Historische roadmap bij 1.7.0](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.0/docs/roadmap.md).
- [Engelstalig overzicht van deze planning](roadmap.md).

Deze roadmap beschrijft gepland werk. Een publicatiebewijs bevestigt alleen de publicatie; een testbewijs alleen de geteste route; een pilot alleen de daadwerkelijk beoordeelde praktijk.
