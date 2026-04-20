# askwol report — `examples/13012026_FT_UTT_v3.ttl`

| | Count |
|---|---|
| Namespaces | 10 (6 RDF, 1 HTML-only, 3 unreachable) |
| Terms | 111 (33 confirmed, 78 not checkable) |

> **Issues found** — see details below.

## Namespaces with valid RDF (6)

| Prefix | URI | Terms |
|--------|-----|-------|
| `rdfs` | http://www.w3.org/2000/01/rdf-schema# | 8 ✓ |
| `skos` | http://www.w3.org/2004/02/skos/core# | 5 ✓ |
| `rdf` | http://www.w3.org/1999/02/22-rdf-syntax-ns# | 1 ✓ |
| `owl` | http://www.w3.org/2002/07/owl# | 9 ✓ |
| `prov` | http://www.w3.org/ns/prov# | 4 ✓ |
| `dcterms` | http://purl.org/dc/terms/ | 6 ✓ |

## HTML-only namespaces (1)

Server responds but returns HTML instead of RDF — terms cannot be verified.

| Prefix | URI | Terms |
|--------|-----|-------|
| `geo` | http://www.opengis.net/ont/geosparql# | 3: `Feature`, `Geometry`, `hasGeometry` |

## Unreachable namespaces (3)

| Prefix | URI | Error |
|--------|-----|-------|
| `utt` | https://w3id.org/utt/def/ | HTTP 404 |
| `xsd` | http://www.w3.org/2001/XMLSchema# | HTTP 406 |
| `imkl` | https://data.geostandaarden.nl/imkl/def/ | DNS resolution failed |

<details>
<summary>75 unverifiable terms</summary>

**`utt:`** `Aannemer`, `DataFormaat`, `DataFormaatScheme`, `Landmeter`, `Meetmethode`, `MeetmethodeScheme`, `Nauwkeurigheid`, `OndersteunendeData`, `PositieAfwijking`, `Proefsleuf`, `Project`, `VerificatieActiviteit`, `WaargenomenKenmerken`, `WaargenomenPositie`, `Waarneming`, `actorNaam`, `afwijkingRichting`, `bestandsFormaat`, `bestandsReferentie`, `cadTekening`, `diepteAangrijpingspunt`, `diepteNAP`, `diepteTovMaaiveld`, `foto`, `fotogrammetrie`, `gebruiktMethode`, `gecombineerd`, `geverifieerdDoor`, `gisBestand`, `gnssRtk`, `handmatig`, `heeftAfwijking`, `heeftKenmerken`, `heeftNauwkeurigheid`, `heeftOndersteunendeData`, `heeftPositie`, `heeftWaarneming`, `horizontaleAfwijking`, `horizontaleOnzekerheid`, `komtOvereenMet`, `lidar`, `nauwkeurigheidDiepteklasse`, `nauwkeurigheidXYklasse`, `onderdeelVanProject`, `opdrachtVan`, `pdfRapport`, `positieGeometrie`, `projectNaam`, `projectNummer`, `puntenwolk`, `sleufBreedte`, `sleufDiepte`, `sleufGeometrie`, `sleufLengte`, `totaalstation`, `uitgevoerdDoor`, `verificatieDatum`, `verticaleAfwijking`, `verticaleOnzekerheid`, `waargenomenDiameter`, `waargenomenIn`, `waargenomenKleur`, `waargenomenMateriaal`, `waargenomenType`

**`xsd:`** `anyURI`, `date`, `dateTime`, `decimal`, `string`

**`imkl:`** `DiepteAangrijpingspuntValue`, `KabelOfLeiding`, `NauwkeurigheidDiepteValue`, `NauwkeurigheidXYvalue`, `PipeMaterialTypeIMKLvalue`, `Thema`

</details>
