---
title: OPENCNTX 1.7.2 — Herstel, vereenvoudiging en gerichte verbetering
project: OPENCNTX
type: roadmap
status: planned
created: 2026-09-09
updated: 2026-09-09
planning_revision: 3
source_versions: ["1.7.0", "1.7.1"]
source_commit: 6b80cc41529653eac0b16b4238a4b7692eebb4f7
published_baseline: 1.7.1
target_version: 1.7.2
analysis_basis: "Deep review of versions 1.7.0 and 1.7.1"
publication_scope: roadmap-only
---

# OPENCNTX 1.7.2 — Herstel, vereenvoudiging en gerichte verbetering

[English overview](roadmap.md) · [README](../README.md) · [Current release](release-1.7.1.md)

## 1. Richting en actuele stand

**Doel:** de nuttige technieken behouden en hun samenwerking betrouwbaarder en eenvoudiger maken. Minder onnodige stops en vragen, minder verspilde context, geen eigen onterechte blokkades en voorspelbare updates zonder onbekende actieve restanten.

De hoofdregel is: **maak overgangen slimmer, niet de verzameling regels groter.** Toestemming, controlebewijs, native voortgang, geheugenweergave en actieve installatie krijgen ieder een duidelijke verantwoordelijkheid. Een fout in een optioneel onderdeel mag niet de hele taak opnieuw laten beginnen.

Deze revisie vervangt het vorige publieke plan. Zij verwerkt de diepteanalyse van 1.7.0 en 1.7.1, behoudt de eerdere herstelpunten en houdt de bestaande taakcodes N01–N24 aan. Het is één uitvoeringslijst; de analyses blijven bronnen, geen concurrerende taakadministraties.

| Onderdeel | Stand |
|---|---|
| Onderzochte basis | 1.7.0 en 1.7.1; runtime identiek afgezien van het versienummer |
| Laatst vastgelegde publicatiebasis | 1.7.1, commit `6b80cc41529653eac0b16b4238a4b7692eebb4f7` |
| Betekenis van 1.7.1 | Gepubliceerde documentatie en roadmap, niet de implementatie daarvan |
| Planning | Revisie 3; 24 taken; 0 nieuwe taken afgerond |
| Actieve taak | Geen — uitsluitend de roadmap opgesteld |
| Eerstvolgende uitvoeringsstap | N01; daarna de gerichte regressiebasis N02 |
| Volgende versie | 1.7.2 — vastgelegde doelversie voor de volgende update; bestaande tags en releases blijven ongewijzigd |
| GitHub-publicatie van deze revisie | Gepubliceerd als plan; geen software-release 1.7.2 |
| Lokale installatie en activering | Geen onderdeel van roadmappublicatie |

Een fase is een groepering, geen verplichte pauze. De roadmap opstellen geeft geen opdracht om haar uit te voeren. Zodra uitvoering wordt opgedragen, zijn normale implementatie- en verificatiestappen binnen die opdracht geen reden voor nieuwe toestemmingsrondes. Publiceren, installeren en brede activering blijven afzonderlijke effecten met hun eigen concrete opdracht.

### Bestaand bewijs gebruiken

De diepteanalyse bevat acht nieuw gereproduceerde gedragingen D01–D08 en twee bron-/architectuurbevindingen D09–D10. De resultaten zijn op beide releases gelijk. Op 1.7.1 slaagden daarnaast opnieuw 60 bestaande gerichte tests. Dat bewijst behoud van die tests, niet dat de nieuwe problemen opgelost zijn.

Eerdere F04–F16 blijven relevante herstelpunten waar hun code ongewijzigd is. F01–F03 betreffen onder meer releaseherkomst, versiecommunicatie en publicatievolgorde: de concrete publicaties zijn verbeterd, structurele automatisering blijft gepland. Bestaand geldig bewijs hoeft niet iedere sessie opnieuw volledig te worden verzameld.

**Historische les:** de beschreven stoplus kwam van achtergebleven gebruikersbrede hooks. De roadmap introduceert daarom geen algemene stopmarker, geen verplichte globale afrondhook en geen systeemwijde schoonmaak.

## 2. Wat behouden blijft en wat niet wordt toegevoegd

| Behouden techniek | Nieuwe grens |
|---|---|
| Lokale contextpakketten, bronselectie en hashes | Bewijzen bytes, niet waarheid of toestemming |
| Ledger, receipts, oorspronkelijke outcomes en AUTO PILOT | Eén gezaghebbende voortgang; iedere mutatie gebonden aan dezelfde bedoelde taak |
| Drie proportionele werkprofielen | Bewijszwaarte geeft nooit extra bevoegdheid |
| Verification leases en herbruikbare controles | Alleen relevante wijzigingen maken een controle ongeldig |
| Recovery met bewijs en fingerprints | Nieuwe aanpak binnen geldige scope; geen verplichte scopegroei |
| Combo, supersession en compacte kennis | Weergavelimieten verwijderen geen nog geldige beslissing |
| Adaptive storage, deduplicatie en optionele index | Zoekdekking en actuele bronbinding zijn zichtbaar |
| Connected state en compacte hervatinformatie | Afgeleide weergave, geen tweede planner of voortgangsautoriteit |
| Updatejournal, staging en generaties | Eén reader ziet één combinatie; data en koppelingen hebben eigen compatibiliteit |
| Providerneutrale adapters | Optioneel en alleen als bewezen integratie gepresenteerd wanneer aangesloten |

Geen volledige herschrijving, nieuwe algemene policy-engine, verplichte modelcall, vectorserver, extra coördinatieagent, daemon, cloudstack of grote GUI. Een extra component komt alleen in beeld als een gemeten probleem niet eenvoudiger met de bestaande bouwstenen is op te lossen.

Dit document is een productplan, geen nieuwe gebruikersbrede hostinstructie. Historische analyses, oude regels en deze notitie worden niet automatisch als extra uitvoeringsbeleid in iedere AI-beurt geladen.

## 3. Vijf gebruikseisen en acht vaste correctheidscriteria

| Eis | Gewenst resultaat | Beoordeling |
|---|---|---|
| U1 — Minder stops en vragen | Doorgaan binnen duidelijke bestaande scope | Nul overbodige eigen herbevestigingen in de vastgelegde positieve scenarioset |
| U2 — Geen onnodige tokenkosten | Relevante context, controlehergebruik en compacte output | Geen modelcalls voor administratie; geen onverklaarde overheadregressie bij gelijke taakcorrectheid |
| U3 — Proportionele bescherming | Eén actuele beslisroute en geïsoleerde optionele fouten | Oude beleidskopieën krijgen geen extra beslismacht; gezonde kern blijft bruikbaar |
| U4 — Geen onterechte eigen weigeringen | Correcte actie-/doelbinding en herstel van verouderde blokkades | Nul eigen foutieve weigeringen in de toegestane scenarioset; externe oorzaken apart benoemd |
| U5 — Schone updates | Eén verklaarde actieve generatie met veilige terugkeer | Geen verweesde eigen actieve koppelingen; gebruikersdata behouden; rollback en cleanup verklaarbaar |

OPENCNTX kan hostbeleid, providerlimieten en ontbrekende toegang niet opheffen. Het kan wel zijn eigen onterechte weigeringen oplossen, nutteloze herhalingen vermijden en onafhankelijk toegestaan werk laten doorgaan. “Nooit meer weigeren” wordt geen onhoudbare algemene garantie.

De onderstaande criteria zijn testinvarianten, geen acht nieuwe goedkeuringsschermen:

1. **I1:** een antwoordtaak krijgt door geen enkele promotie of cachemiss schrijfrecht.
2. **I2:** ingetrokken of gewijzigde autoriteit wordt niet via oud bewijs hergebruikt.
3. **I3:** dezelfde operatie-ID kan nooit twee verschillende opdrachten afronden.
4. **I4:** een optionele fout verandert een geslaagde native commit niet achteraf in “niets gebeurd”.
5. **I5:** iedere open verplichting blijft canoniek aanwezig en gericht bereikbaar.
6. **I6:** iedere nog geldige beslissing blijft op ID vindbaar en correct vervangbaar.
7. **I7:** onvolledig zoeken wordt niet als volledige afwezigheid gepresenteerd.
8. **I8:** een reader ziet één compatibele runtimegeneratie; cleanup raakt geen vreemde of nog benodigde data.

### Uitvoeren zonder extra bureaucratie

- Stel alleen een vraag bij werkelijk ontbrekende beslisinformatie of een wezenlijk nieuw effect buiten de opdracht. Bundel tegelijk bekende keuzes.
- Een geslaagde test, subtaak of fasegrens is geen zelfstandige stopreden.
- Gebruik één budget voor herhaalde pogingen per concrete operatie; meerdere lagen mogen hun eigen retries niet ongemerkt vermenigvuldigen.
- Zonder relevante verandering wordt dezelfde mislukte aanpak onderdrukt. Wel mogen nieuwe, begrensde diagnosehandelingen nuttige informatie verzamelen.
- Een echte stop of scopewijziging wordt gerespecteerd. Blokkeer alleen de afhankelijke route.
- Houd lange ruwe logs buiten de standaardcontext. Bewaar één verwijzing plus uitslag en beperking.
- Geen apart dossier per toolcall, geen nieuwe beleidsnotitie per fout en geen modelcall om tellers bij te houden.
- Relevante verplichte CI blijft gelden. Lokale testselectie en bewijshergebruik zijn geen omweg om repositoryregels uit te schakelen.

## 4. Uitvoeringsvolgorde en opleveringen

| Fase | Resultaat | Taken |
|---|---|---|
| A — Bekende basis | Herbruikbaar bewijs, echte regressies en een vroege nulmeting | N01–N02; nulmeting N16 |
| B — Correcte overgangen | Juiste bevoegdheid, herhaalveilige voortgang, begrensde neveneffecten en kritieke inputcontrole | N03–N09 |
| C — Begrijpelijk dagelijks werk | Diagnose, betrouwbaar geheugen, compact hervatten en aantoonbare efficiëntie | N13–N17; N20 waar nodig |
| D — Schone levenscyclus | Kanaaleigenaarschap, generaties, readers, datacompatibiliteit en herstel | N10–N12 |
| E — Gekozen praktijkverbreding | Eén echte adapter, optionele export en passende pilot | N18–N21 |
| F — Eerlijke release | Brongebonden build, aantoonbare inhoud en geverifieerde publicatie | N22–N24 |

**Eerste herstelvolgorde:** N01 → gerichte basis N02 → N03 → N04. D01/D02 krijgen voorrang in N03; D06 krijgt een expliciete implementatie-eenheid in N04. Werk daarna de relevante sync-, recovery-, input- en isolatieproblemen af. De nulmeting uit N16 gebeurt vóór wijzigingen aan het te meten gedrag, niet pas aan het einde.

Dit is geen bevel tot parallelle agents. Onafhankelijke taken mogen logisch naast elkaar worden voorbereid, mits dezelfde bestanden en verantwoordelijkheden niet conflicteren. N05/N06, N07/N08 en N22 hoeven niet op alle latere functies te wachten.

### Vier mogelijke opleveringen

- **Herstelkern:** concrete defectfixes en herhaalveilige overgangen. Geen claim dat de complete updater of alle hostintegraties klaar zijn.
- **Dagelijkse eenvoud:** aangesloten lichte routes, diagnose, geheugen/hervatten en eerste vergelijkbare metingen.
- **Schone update:** één volledig bewezen installatieroute met reader- en data-rollbackgrens.
- **Praktijkuitbreiding:** uitsluitend gekozen adapter/exportfuncties en onderbouwde gebruiksclaims.

Dit zijn scopekeuzes, geen vier verplichte releases. N01 kiest bij de latere uitvoering één eerste afgebakende inhoud op basis van de opdracht; N23 beoordeelt precies die inhoud. Ongeleverde onderdelen blijven open. Een beperkte defectfix hoeft niet op een tweeweekse pilot te wachten; brede besparings- of adoptieclaims wel op passend praktijkbewijs.

## 5. Taken N01–N09 — Werkbasis en correcte overgangen

### N01 — Bron, eerste opleveringsscope en nulmeting vastleggen

- [ ] **Status: Gepland**

**Werk:** bevestig de echte checkout en wijzigingen; gebruik de onderzochte 1.7.1-commit als referentie. Leg één eerste opleveringsscope en de relevante U-/I-criteria vast. Koppel bestaand auditbewijs in plaats van het over te schrijven. Kies de vaste scenario's en leg de minimale nulmeting voor de eerste scope vast vóór gedragswijzigingen; N16 breidt die meting later uit. Ontwerpkeuzes blijven in het taaklog of bestaande code/documentatie.

**Klaar wanneer:** bron en opdracht zijn eenduidig, gebruikerswijzigingen behouden, geclaimde inhoud afgebakend en de nulmeting voor die inhoud beschikbaar of expliciet beperkt. Geen nieuwe release- of installatiestatus gesuggereerd.

**Afhankelijk van:** geen. **Bron:** diepteanalyse hoofdstuk 1; F01–F03.

### N02 — Auditproeven omzetten naar echte regressies en toestandstests

- [ ] **Status: Gepland**

**Werk:** neem D01–D08 en relevante F04/F07/F08/F09 over als begrensde regressies. Test gewenste invarianten, niet het blijvend bestaan van een fout. Maak de red/green-uitkomst lokaal zichtbaar; houd de uiteindelijke wijziging coherent met de fix. Voeg actiereeksen toe: begin, herhaal, wijzig feiten, trek in, crash en hervat. Gebruik de bestaande testinfrastructuur.

**Klaar wanneer:** iedere betrokken fix een proef heeft die de oude fout detecteert en de gewenste uitkomst controleert. De gedeelde harness is klaar; aanvullende taakgerichte gevallen groeien mee met hun implementatie. Tests schrijven uitsluitend in eigen tijdelijke fixtures; een helperproef wordt niet als echte hostproef geteld.

**Afhankelijk van:** N01. **Bron:** D01–D08, I1–I8.

### N03 — Toestemming, bewijszwaarte en blokkades uit elkaar halen

- [ ] **Status: Gepland**

**Werk:** herstel D01 en D02. Bind acties aan concrete doelen en actuele opdracht; ondersteun expliciet gebonden meerdere doelen en toegestane externe acties. Risicoprofiel, actuele blokkeerredenen en toegestane acties worden afzonderlijk berekend. Een herstelde bevoegdheid vereist geldige herbinding; een gewijzigde boolean is geen zelfstandig autoriteitsbewijs. Hergebruik bestaande padbouwstenen; nieuwe controles worden bij N09 geharmoniseerd.

**Klaar wanneer:** antwoordtaken nooit writes toestaan; een stale lease alleen relevante hercontrole veroorzaakt; aantoonbaar herstelde blokkades verdwijnen; scope-uitbreiding en intrekking worden correct verwerkt. Positieve meerdoelscenario's vragen niet telkens opnieuw toestemming.

**Afhankelijk van:** N02. **Bron:** D01–D02, F07; I1–I2, U1/U3/U4.

### N04 — Lichte routes aansluiten én voortgang herhaalveilig maken

- [ ] **Status: Gepland**

**Werk, expliciet als één kritieke mutatieketen:**

1. Bind iedere voortgangsmutatie aan operatie-ID, verwachte opdracht, relevante parameters en verwachte revisie.
2. Leg operationele uitkomst en voortgang onder dezelfde bewezen lokale vastleggrens vast.
3. Dezelfde ID met dezelfde parameters geeft het eerdere resultaat; dezelfde ID met andere parameters wordt afgewezen.
4. Scheid native resultaat van latere sync-/weergave-/diagnosefouten.
5. Sluit ANSWER_ONLY, LIGHT_TASK en GOVERNED_FLOW aan op echte gebruikersroutes, met werkelijk gemeten writes en output.
6. Herstel D08: nieuw relevant bewijs en een andere aanpak mogen binnen dezelfde reeds volledig onderzochte keten worden beoordeeld.

**Klaar wanneer:** de D06-proef bij responsverlies nooit de volgende taak afvinkt; retries na crash dezelfde operatie hervatten; antwoordtaken nul projectmutaties veroorzaken; lichte taken geen volledig dossier afdwingen. Alle retrylagen delen één begrensde operatietoestand. Recovery vergroot geen bevoegdheid en vraagt niet verplicht om meer taken.

**Afhankelijk van:** N03. **Bron:** D06/D08/D09, F13/F16; I1–I4.

### N05 — Sync aan onveranderlijke bytes en een eigen levering binden

- [ ] **Status: Gepland**

**Werk:** maak de beoordeelde snapshot de bron van verzending. Controleer bestemming, bronidentiteit en privacyverklaring met de juiste betekenis. Een mutatie tussen preview en levering leidt tot dezelfde snapshot of een gerichte driftmelding. Bewaar een kleine leveringsintentie en herhaalidentiteit; maak geen tweede voortgangsledger. Bouw geen daemon zonder concrete gebruikseis.

**Klaar wanneer:** iedere verzonden byte bij het juiste beoordeelde manifest hoort; de lokale sync-race als regressie slaagt; herhaalde levering geen andere snapshot of dubbele logische operatie oplevert. Extern onbekende uitkomsten worden eerst teruggelezen of via ondersteunde idempotentie afgehandeld.

**Afhankelijk van:** N04. Voorbereidende snapshotproeven kunnen na N02. **Bron:** F04, D06; I3–I4.

### N06 — Externe processen en optionele fouten begrenzen

- [ ] **Status: Gepland**

**Werk:** begrens Git/subprocessduur, output, retryaantal en relevante procesbomen per ondersteund platform. Onderscheid lokale commit, levering en foutregistratie. Een onbeschikbare adapter veroorzaakt geen globale stoplus. Gebruik alleen waar nodig een eenvoudige adapterpauze na herhaalde fouten. Een bevestiging “privérepository” is geen zelfstandig providerbewijs.

**Klaar wanneer:** hangende fixtureprocessen eindigen binnen de vastgelegde grens; dubbele foutinjectie na commit bewaart het native resultaat; onafhankelijk lokaal werk blijft mogelijk. Een foutmelding die zelf niet kan worden opgeslagen wordt compact gemeld, niet opnieuw onbeperkt geprobeerd.

**Afhankelijk van:** N04–N05. **Bron:** F05/F06, D06; I4, U1/U3.

### N07 — Doelidentiteit en update-/sidecaroverlap vooraf controleren

- [ ] **Status: Gepland**

**Werk:** maak concrete doelidentiteit en scope-overlap gemeenschappelijk bruikbaar. Behandel gelijke paden, ouder/kind, patronen, kandidaat/active/backup-overlap, hoofdlettergedrag, symlinks en Windows-reparsepunten. Onopgeloste scope krijgt geen bewezen-isolatielabel. Zij vereist oplossing of een gerichte fout, geen optimistische stringvergelijking.

**Klaar wanneer:** D03 en de eerdere overlappende updatecomponenten worden gedetecteerd vóór writes. Disjuncte concrete doelen blijven toegestaan. Tests onderscheiden bestandspaden, mapbereik, platformidentiteit en toekomstige nog ontbrekende doelen. Niet elk platform wordt geforceerd hoofdletterongevoelig behandeld.

**Afhankelijk van:** N02. **Bron:** D03, F08/F11; I2/I8.

### N08 — Capsules uniek, strikt en resourcebegrensd maken

- [ ] **Status: Gepland**

**Werk:** controleer unieke genormaliseerde manifestpaden én unieke archiefmembers, juiste veldtypes en een eenduidige mapping. Begrens aantallen, manifestgrootte, individuele en totale uitgepakte bytes vóór en tijdens lezen. Hash zo nodig streaming. Houd archiefintegriteit apart van valide geïmporteerde projecttoestand.

**Klaar wanneer:** de duplicaatproef wordt afgewezen; onverwachte members, ongeldige paden/types en overschrijdingen veilig eindigen; normale bestaande capsules blijven leesbaar volgens de compatibiliteitsafspraak. Fixtures zijn klein en bewijzen grensgedrag zonder de machine uit te putten.

**Afhankelijk van:** N02. **Bron:** F09–F11.

### N09 — Kritieke primitives harmoniseren zonder grote herschrijving

- [ ] **Status: Gepland**

**Werk:** inventariseer alleen de controles die N03–N08 en de updater daadwerkelijk gebruiken. Harmoniseer kritieke JSON-, digest-, pad- en schrijfhelpers in de bestaande lichte utilitylaag. Scheid domeinfouten van pure hulpmiddelen. Houd waar nodig tijdelijke compatibele re-exports; verander duurzame formaten niet stilzwijgend. Verminder de D10-verknoping op echte wijzigingspaden.

**Klaar wanneer:** de gewijzigde routes dezelfde bedoelde validatie hebben, bestaande compatibiliteitsfixtures slagen en ongewenste nieuwe afhankelijkheidscycli uitblijven. Minder private imports is ondersteunend bewijs, geen doel dat gedrag mag breken. Onverwante modules worden niet “voor de zekerheid” herschreven.

**Afhankelijk van:** N03, N07, N08. **Bron:** F11, D10.

## 6. Taken N10–N12 — De schone updatelevenscyclus

### N10 — Eén installatieroute, eigenaarschap en compatibiliteit vastleggen

- [ ] **Status: Gepland**

**Werk:** kies één concrete installatieroute voor de eerste update-oplevering. Leg vast wie pakketbestanden beheert; gebruik een passende kanaaladapter in plaats van willekeurig beheer door elkaar. Inventariseer installatie-ID, actieve executable/generatie, eigen registraties, gebruikersdata en reader-/writercompatibiliteit. Beschrijf de datamigratie- en rollbackgrens vóór mutaties worden gebouwd.

**Klaar wanneer:** het eigendomsmanifest eigen beheerde bestanden onderscheidt van vreemde en aangepaste inhoud; een nieuwe clone niet als bewijs van een nieuwe actieve installatie geldt; ondersteunde oude formaten en terugkeergrenzen expliciet zijn. Eén kanaal is concreet gekozen, onbekende kanalen niet stilzwijgend ondersteund.

**Afhankelijk van:** N01, N07. **Bron:** F12/F13, diepteanalyse hoofdstuk 5; U5/I8.

### N11 — Generationele updater met herhaalbare overgang implementeren

- [ ] **Status: Gepland**

**Werk:** inventariseren → plannen → complete kandidaat voorbereiden → controleren → één generatie selecteren → actieve toestand bevestigen → eigendomsgebonden cleanup. Bouw op bestaande staging/journal/receipt-technieken. Een reader bindt één keer aan zijn generatie. Bestaande readers mogen een oude generatie tijdelijk behouden. Maak identieke updates een echte no-op.

**Klaar wanneer:** fasegewijze crashinjectie consistent herstel geeft; dezelfde update niet dubbel wordt toegepast; één reader geen gemengde combinatie ziet. Data-rollback past bij de gebruikte formats. Open Windows-bestanden leiden tot verklaarde uitgestelde cleanup, niet blind verwijderen. Atomiciteit en duurzaamheid worden apart en alleen binnen bewezen filesystemgrenzen geclaimd.

**Afhankelijk van:** N04, N07, N09, N10. **Bron:** F08/F12; I3/I8.

### N12 — Upgrade, rollback, uninstall en hookrestanten bewijzen

- [ ] **Status: Gepland**

**Werk:** test verse installatie, herhaling, upgrade met reader actief, crashes rond selectie, schijfruimtegebrek, ontbrekende kandidaat, veranderde eigen configuratie, vreemde entries, incompatibele data, rollback en uninstall. Voeg een historische-hookfixture toe met een eigen registratie naar een verdwenen versiepad. Test op de bedoelde Windows-/Linuxroutes, uitsluitend geïsoleerd.

**Klaar wanneer:** gebruikersdata behouden blijven; verwijdering alleen aantoonbaar eigen ongebruikte onderdelen raakt; één gekozen rollbackset en noodzakelijke readergeneraties verklaard zijn. Geen verweesde eigen actieve koppelingen. “Geen rommel” betekent geen onverklaarde toestand, niet dat noodzakelijk herstelbewijs onmiddellijk verdwijnt.

**Afhankelijk van:** N11. **Bron:** herstelnotitie, U5/I8. **Grens:** geen installatie in een bestaande gebruikersomgeving door het uitvoeren van fixtures.

## 7. Taken N13–N17 — Eenvoud, geheugen en gemeten efficiëntie

### N13 — Eén read-only diagnose met herkomst en vervolgstap

- [ ] **Status: Gepland**

**Werk:** toon opdracht/scope, eigen blokkeerreden, native resultaat, optionele leveringen, actieve runtime en relevante configuratieherkomst in één compacte ingang. Onderscheid kerncorruptie, stale view, onbereikbare adapter en ontbrekende autoriteit. Geen systeemwijde scan; geen automatische globale configuratie-reset.

**Klaar wanneer:** diagnose geen project- of hostmutaties verricht en geen ontbrekende store aanmaakt. D06 en D07 leveren begrijpelijke deelsuccessen op, geen misleidende totale fout. Eén probleem krijgt één actuele verklaring en kleinste vervolgstap. Installatievelden worden uitgebreid wanneer N10–N12 beschikbaar zijn; niet verzonnen.

**Afhankelijk van:** N04, N06. **Bron:** V05, D02/D06/D07, U1/U3/U4.

### N14 — Canoniek geheugen en compact hervatten zonder informatieverlies

- [ ] **Status: Gepland**

**Werk:** scheid canonieke beslissingen en verplichtingen van Combo-/connected-presentatie. Bewaar stabiele ID's, bron, scope en levenscyclus; actieve beslissingen verdwijnen niet door een recentheidslimiet. Zorg voor gerichte details en gecontroleerde supersession. Maak een klein startpakket met doel, scope, actuele taak, open outcomes, blokkades en eerstvolgende handeling.

**Klaar wanneer:** D04 en D07 zijn opgelost; de 33e beslissing verdringt geen actuele waarheid uit zoekbaarheid; expliciete vervanging blijft mogelijk. Grote roadmaps passen via compacte root plus gecontroleerde detailverwijzingen. Na chatreset blijven alle oorspronkelijke outcomes bereikbaar. Een weergavefout blokkeert geen reeds geslaagde native mutatie.

**Afhankelijk van:** N04, N09. **Bron:** D04/D07, V07; I5–I6.

### N15 — Zoekdekking, contextbudget en gerichte controlecache

- [ ] **Status: Gepland**

**Werk:** herstel D05 met expliciete volledigheid en een bronversiegebonden scancursor. Zoek exacte record-ID's rechtstreeks waar mogelijk. Houd resultaatlimiet, scanwerk en tijdsbudget uit elkaar. Selecteer context op relevante huidige taak en bronverwijzingen. Een delta vereist een bekende basis; anders een volledig compact startpakket. Hergebruik controles per werkelijk relevante afhankelijkheid, los van autorisatie.

**Klaar wanneer:** Z uit de audit niet als afwezig wordt gesuggereerd na een afgebroken scan; een hervatte query niet stilzwijgend een gewijzigde store combineert. Ongewijzigde controles worden hergebruikt, relevante veranderingen ongeldig verklaard. Bytes, tokenraming en echte hostusage zijn duidelijk verschillende metingen. Geen modelcall voor selectieboekhouding.

**Afhankelijk van:** N03, N09, N14. **Bron:** D01/D05, V06; I1/I2/I7, U2.

### N16 — Frictie en taakresultaat vóór en na wijzigingen vergelijken

- [ ] **Status: Gepland**

**Werk:** begin de nulmeting met N01. Gebruik vaste taken voor antwoord, kleine wijziging, meerdere doelen, hervatten, ingetrokken scope, adapterfout en begrensde recovery. Meet werkelijke writes, context-/tooloutputomvang, herhaalde controles, vragen, retries, tijd en taakcorrectheid. Voeg betrouwbare hostusage toe wanneer beschikbaar; geen verborgen externe telemetrie of volledige promptarchieven.

**Klaar wanneer:** nul- en nameting vergelijkbare bron-/hostcondities hebben, uitschieters zichtbaar zijn en kostenramingen als zodanig zijn gelabeld. Geen verlies van correctheid of gebruikersdata wordt weggemiddeld tegen snelheid. Onverklaarde regressies in gekozen claims zijn opgelost; zonder betrouwbare usage geen euro-/percentageclaim.

**Afhankelijk van:** starten na N01; nameting na de gewijzigde routes, in ieder geval N04/N14/N15 voor brede eenvoudclaims. **Bron:** U1–U4, F15.

### N17 — Gebruikersroute en featureclaims laten overeenkomen met code

- [ ] **Status: Gepland**

**Werk:** vereenvoudig quickstart en uitleg rond antwoord, kleine taak, hervatten en update. Koppel claims aan de concrete route en bewijssoort: contract aanwezig, lokaal aangesloten, adapter bewezen of praktijk gemeten. Benoem release-, installatie- en activeringsstatus afzonderlijk. Een berekend shard-aantal bewijst geen werkelijk aangesloten opslagroute.

**Klaar wanneer:** voorbeelden uitvoerbaar zijn op de gekozen kandidaat en ieder geclaimd voordeel passend bewijs heeft. Open roadmapwerk is nergens een geleverd feature. Er is één korte startplaats met detailverwijzingen; geen herhaling van het complete beleids-/historiearchief.

**Afhankelijk van:** N04, N13–N16; updateclaims ook N12. **Bron:** D09, F02/F16.

## 8. Taken N18–N21 — Optionele verbreding en praktijkbewijs

### N18 — Eén kleine echte hostadapter bewijzen

- [ ] **Status: Gepland — scopeafhankelijk**

**Werk:** kies één beschikbare host en adaptercontract. Sluit alleen benodigde capabilities aan op de bewezen native routes. Geen globale Stop-hook als standaard. Test werkelijke toestemming, antwoord zonder writes, lichte taak, hervatten, intrekking, adapteruitval en operatieherhaling. Ontbreekt echte hosttoegang, presenteer fixtures uitsluitend als fixtures.

**Klaar wanneer:** de gekozen echte adapter aantoonbaar werkt en uitval alleen die koppeling raakt; de lokale kern zonder adapter bruikbaar blijft. Native hostbevoegdheden blijven leidend. Geen providerbrede belofte afgeleid uit één werkende host.

**Afhankelijk van:** N04, N06, N13–N15; N10 bij beheerde registratie. **Bron:** F13/D09, U1/U4.

### N19 — Gecontroleerde eenrichtingsexport naar Obsidian

- [ ] **Status: Gepland — scopeafhankelijk**

**Werk:** exporteer afgeleide leesbare informatie uitsluitend naar de gekozen doelmap. Bind export aan bronrevisie, doel en operatie-ID; beheer alleen eigen gegenereerde bestanden. Behoud menselijke wijzigingen met een conflictstatus of aparte conflictcopy. Gebruik geen live transactionele machine-store in een gedeelde notitiemap als impliciete oplossing.

**Klaar wanneer:** herhalen geen duplicaten maakt, vreemde notities onaangeraakt blijven, bronwijziging zichtbaar is en onbereikbare export de kern niet stopt. Geen brede vaulttoegang, bidirectionele sync of extra geïnstalleerde integratie zonder concrete scope.

**Afhankelijk van:** N05–N07, N14. **Bron:** V12, I3–I6.

### N20 — Alleen bewezen opslag- en afhankelijkheidsproblemen optimaliseren

- [ ] **Status: Gepland**

**Werk:** meet ledgerlezen/-schrijven, Combo-generaties, indexconsistentie en querywerk op kleine en grotere vaste datasets. Een veranderde zoekindex blijft een afgeleide van de juiste canonieke bron. Onderzoek gerichte impactkaarten en symbolenselectie alleen na een eenvoudige basisvergelijking. Verminder D10-verknoping op gemeten of foutgevoelige paden.

**Klaar wanneer:** een wijziging aan een vooraf gemeten bottleneck gekoppeld is en herhaalbare winst toont zonder semantische regressie. Geen verplichte databank, daemon of embeddings toegevoegd zonder noodzaak. Als er geen relevante bottleneck is, volstaat gedocumenteerde meting met besluit “geen wijziging nodig”.

**Afhankelijk van:** N01 voor meting; N09/N14/N15 voor beoordeling van die nieuwe routes. **Bron:** D05/D10, F14.

### N21 — Praktijkpilot voor brede gebruiksclaims

- [ ] **Status: Gepland — vereist voor brede adoptieclaims**

**Werk:** behoud de eerdere pilotbasis: minstens twee weken, 25 echte taken en drie echte restart-/handoffmomenten. Kies representatieve taken en leg vooraf vast welke host- en efficiëntieclaims worden getoetst. Gebruik N16-metingen, registreer ook mislukte en afgebroken taken en onderscheid product-, host- en externe oorzaken.

**Klaar wanneer:** de feitelijke pilot aan de afgesproken omvang voldoet, de claimrelevante problemen opgelost of als beperking afgebakend zijn en echte resultaten terugleesbaar zijn. Synthetische taken testen de harness maar tellen niet als pilotsucces. Onvoldoende praktijkdata blijft onbekend, niet groen.

**Afhankelijk van:** N16–N17 en alle geclaimde functies; N18 bij hostclaims, N12 bij updateclaims. **Bron:** F15, U1–U5.

## 9. Taken N22–N24 — Een release die haar inhoud bewijst

### N22 — Correcte releaseherkomst automatiseren

- [ ] **Status: Gepland**

**Werk:** automatiseer de keten van definitieve bronidentiteit naar tests, build, exact gebonden tag/artifacts en verificatie. Houd vier huidige distributiebestanden als uitgangspunt. Bouw van de definitieve commit/tree, niet van een eerdere PR-head. Gebruik bestaande geslaagde checks alleen met aantoonbare geldigheid en binnen de repositoryregels; voorkom onnodige lokale volledige herhalingen.

**Klaar wanneer:** bronmismatch, verkeerd versienummer en ontbrekende vereiste eind-CI publicatie van die kandidaat verhinderen; buildrecord en distributie naar dezelfde definitieve bron verwijzen. Unsigned provenance blijft als unsigned benoemd. Ondertekening/TUF is mogelijke latere downloadketenversterking, geen verplichte extra infrastructuur voor de herstelkern.

**Afhankelijk van:** N01. **Bron:** F01–F03, V09.

### N23 — Geleverde scope en kandidaat beoordelen

- [ ] **Status: Gepland**

**Werk:** bereid de kandidaat voor de vastgelegde doelversie 1.7.2 voor op basis van de werkelijk geleverde inhoud. Verbind iedere releaseclaim aan geïmplementeerd gedrag, actuele tests en relevante meting. Beoordeel platformskips, compatibiliteit, migratie-/rollbackuitleg en bekende beperkingen. Neem alleen passende N-taken mee; geen onbewezen voordelen via het woord Stable.

**Klaar wanneer:** alle taken en criteria binnen de gekozen opleveringsscope aantoonbaar gereed zijn, geen bekende materiële fout een geclaimde werking tegenspreekt en niet geleverde onderdelen expliciet openstaan. Een beperkte fixrelease kan gereed zijn zonder brede pilot, maar claimt dan geen bewezen algemene besparing of hostadoptie.

**Afhankelijk van:** N22, relevante N17-documentatie en alle taken van de gekozen scope; brede praktijkclaims vereisen N21. **Bron:** D09, U1–U5 naar gekozen scope.

### N24 — Publiceren en publieke readback uitvoeren wanneer opgedragen

- [ ] **Status: Gepland — geen actuele publicatiestap**

**Werk:** gebruik de concrete publicatieopdracht voor de dan gekozen kandidaat. Publiceer exact de geverifieerde tag en vier assets; controleer latest-/release-status. Werk actuele README, changelog, roadmap, installatie-/release-informatie en betrokken publieke websitebron bij. Maak een private notitie niet rechtstreeks publiek: verwijder lokale paden en persoonlijke herstelcontext uit de afgeleide publieke versie.

**Klaar wanneer:** echte downloads bytegelijk zijn gecontroleerd, commit/tree en metadata passen en publieke claims teruggelezen zijn. Geen gehoste website of wiki claimen wanneer alleen bron bestaat. Publicatie betekent niet lokale installatie, hookactivatie of voltooiing van optionele roadmaptaken.

**Afhankelijk van:** N23 en een concrete publicatieopdracht. **Bron:** F01–F03, V09/V10.

## 10. Acceptatiescenario's per oplevering

| Scenario | Minimale verwachte uitkomst | Eigenaarstaak |
|---|---|---|
| Antwoord plus verlopen lease | Geen writes; alleen relevante hercontrole | N03–N04 |
| Blokkade herstellen / autoriteit intrekken | Actuele redenen; geldige herbinding respectievelijk blokkade | N03 |
| Meerdere toegestane doelen | Eén gebonden scope; geen kunstmatige één-doelweigering | N03 |
| Respons verloren na voortgangscommit | Dezelfde taakuitkomst terug; volgende taak niet afgevinkt | N04 |
| Sync én foutregistratie falen | Native resultaat blijft zichtbaar; retry beperkt | N04/N06 |
| Volledige keten al onderzocht, nieuw bewijs | Nieuwe begrensde aanpak mogelijk zonder meer taakdekking | N04 |
| Map/patroon/alias naast actieve writer | Overlap opgelost of afgewezen; nooit onbewezen ISOLATED | N07 |
| Dubbele capsule / grensoverschrijding | Gerichte afwijzing vóór ongecontroleerde verwerking | N08 |
| 33e actuele beslissing | Oudere actuele beslissing nog vindbaar en vervangbaar | N14 |
| Grote roadmap en nieuwe chat | Alle outcomes bereikbaar via compacte root en details | N14 |
| Z ligt buiten onderzocht zoekdeel | Gedeeltelijke dekking plus veilige vervolgroute | N15 |
| Irrelevante wijziging versus autoriteitswijziging | Passend controlehergebruik versus verplichte invalidatie | N15 |
| Update met oude reader en crash | Eén generatie per reader; verklaarde terugkeer/cleanup | N11–N12 |
| Eigen kapotte hook naast vreemde configuratie | Gerichte diagnose; vreemd materiaal onaangeraakt | N12–N13 |
| Echte hosttaak en optionele exportfout | Kern bruikbaar; fout blijft bij de adapter | N18–N19 |

Testniveaus blijven gescheiden: pure contractproef, tijdelijke native fixture, proces-/filesystemproef, echte adapter en praktijkpilot. Geen niveau krijgt automatisch de claims van een hoger niveau. De samenhangende toestandstests uit N02 bewaken I1–I8 over meerdere stappen.

## 11. Volledige traceerbaarheid

### Nieuwe diepteanalyse

| Bevinding | Verwerking |
|---|---|
| D01 — Stale lease geeft antwoordtaak write-indicatie | N02–N04, N15 |
| D02 — Verouderde blokkade blijft hangen | N02–N04, N13 |
| D03 — Sidecar vergelijkt alleen strings | N02, N07, N09 |
| D04 — Actieve Combo-beslissing verdwijnt uit zoeklaag | N02, N14 |
| D05 — Zoekbudget verbergt onvolledigheid | N02, N15, N20 |
| D06 — Retry kan volgende opdracht afronden | N02, expliciete mutatieketen N04, N05–N06 |
| D07 — Geldige grotere roadmap past niet in current view | N02, N04, N13–N14 |
| D08 — Recovery vereist onmogelijke verplichte verbreding | N02, N04 |
| D09 — Contract versus aangesloten gebruikersroute | N04, N17–N18, N23 |
| D10 — Algemene helpers en productlogica verknoopt | N09, N20 |

### Eerdere analyse — niets stilzwijgend laten vallen

| Bevindingen | Verwerking |
|---|---|
| F01 build/tag, F02 versieclaims, F03 CI/publicatie | N01, N17, N22–N24 |
| F04 syncbytes, F05 Git-timeout, F06 privacyverklaring | N05–N06 |
| F07 autoriteit/doelen | N03–N04 |
| F08 updatepad-overlap | N07, N11–N12 |
| F09 capsuleduplicaten, F10 resourcegrenzen | N08 |
| F11 kritieke JSON-/padvalidatie | N07–N09 |
| F12 samengestelde update/atomiciteit | N10–N12 |
| F13 hostcontract versus integratie | N04, N13, N17–N18 |
| F14 ledger-/opslaggroei | N20 |
| F15 onbewezen praktijkwinst | N16, N21, N23 |
| F16 zware onboarding | N04, N13, N17 |
| Historisch globaal hookincident | N10–N13, N18 |

| Eerder voorstel | Behouden taakruimte |
|---|---|
| V01 autoriteit en minder vragen | N03–N04, N18 |
| V02 betrouwbare sync | N05–N06 |
| V03 schone updatelevenscyclus | N07, N10–N12 |
| V04 capsule/inputcontrole | N08–N09 |
| V05 diagnose | N13 |
| V06 zuinige context | N15–N16 |
| V07 compact hervatten | N14 |
| V08 optionele host | N18 |
| V09 releaseherkomst | N01, N22–N24 |
| V10 uitleg en featurestatus | N04, N17, N23–N24 |
| V11 opslagoptimalisatie | N20 |
| V12 Obsidian-export | N19 |

De uitbreidingsthema's krijgen geen tweede backlog: uitleg van effectieve toestand valt onder N13; geheugen-/contextverschillen onder N14–N15; lokaal frictie-overzicht onder N16; gezondheid over generaties onder N10–N13; een impactkaart onder N20. De oude R01–R32-verwijzingen blijven historische verwijzingen in eerdere analyses, geen actieve taaknummers.

## 12. Voortgang, beslissingen en hervatten

Statussen: **Gepland**, **Bezig**, **Geblokkeerd**, **Klaar**, **Uitgesteld**. Alleen Klaar krijgt een vinkje. Een taak is pas Klaar wanneer haar gekozen acceptatiecriteria werkelijk zijn bewezen; “de helper bestaat” of “de testlijst is groen” volstaat niet voor een bredere claim.

Bij scopeafhankelijke taken betekent Uitgesteld: niet in deze oplevering, met korte reden. Geen stilzwijgende omzetting naar geleverd. Een geblokkeerde taak vermeldt oorzaak en kleinste benodigde verandering. Onafhankelijk opgedragen werk kan doorgaan.

Gebruik dit log voor betekenisvolle resultaten en keuzes. Bewaar geen tweede actuele roadmap, apart statusbestand of omvangrijk beslisdossier wanneer een kort logitem en bestaand bewijs volstaan.

| Datum | Gebeurtenis | Resultaat | Hervatpunt |
|---|---|---|---|
| 2026-09-09 | Planning revisie 3 vanuit diepteanalyse 1.7.0/1.7.1 | N01–N24 behouden en verdiept; D01–D10 plus eerdere F/V-punten verwerkt; geen implementatie gestart | N01 bij latere uitvoeringsopdracht |
| 2026-09-09 | Doelversie expliciet vastgesteld | Volgende update wordt 1.7.2; publicatiebasis blijft 1.7.1; geen uitvoering of publicatie gestart | N01 bij latere uitvoeringsopdracht |

**Compact hervatrecord:** actuele opdracht en scope; actieve taak; laatste geverifieerde resultaat; relevante bestanden/commit; resterend werk; blokkade indien aanwezig; volgende concrete stap. Lees daarna alleen de relevante analyseparagrafen en bewijsbestanden. De hele oude chat, alle policies en alle analyses hoeven niet opnieuw de context in.

**Geen automatische model-/kostenclaims:** deze roadmap schrijft geen model voor en belooft geen aantal uren of tokens. Modelkeuze volgt de actuele opdracht/host. Efficiëntie wordt met N16 aangetoond, niet uit profielnamen afgeleid.

## 13. Bronnen en geldigheidsgrenzen

- [Release 1.7.1](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.7.1) en [definitieve CI](https://github.com/CNTX-PROJECT/OPENCNTX/actions/runs/34395546489) — publicatiebasis, geen bewijs dat deze roadmap is geïmplementeerd.
- [Verschillen 1.7.0–1.7.1](https://github.com/CNTX-PROJECT/OPENCNTX/compare/v1.7.0...v1.7.1) — runtimeverschil beperkt tot het versienummer.
- [Governance](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/governance.py), [voortgang](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/continuity.py) en [recovery](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/recovery.py) — onderzochte contracten en overgangen.
- [Combo](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/combo.py), [adaptive storage](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/adaptive_storage.py) en [connected state](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/connected_state.py) — geheugen, zoekdekking en afgeleide weergaven.
- [Updater](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/transactional_update.py) en [sync](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/continuity_sync.py) — bestaande implementatiebouwstenen.
- [Bekende releasebeperkingen](release-1.7.0.md) en [scope van 1.7.1](release-1.7.1.md) — eerdere bevindingen en publicatiegrenzen.
- [Voorgaande roadmap op de vaste 1.7.1-commit](https://github.com/CNTX-PROJECT/OPENCNTX/blob/6b80cc41529653eac0b16b4238a4b7692eebb4f7/docs/roadmap-plan.nl.md) — historische N01–N24-context.

De D-bevindingen komen uit de onderliggende gerichte analyse; de bijbehorende auditproeven moeten in N02 als publieke regressietests worden opgenomen. Private notities en lokale bewijsbestanden worden niet meegepubliceerd.

Deze publicatie levert alleen de roadmap voor 1.7.2. Zij levert geen nieuwe runtimefunctionaliteit, release-assets, installatie of hostactivering. De huidige gepubliceerde software blijft 1.7.1.
