# Sources de données, accès et licences

Ce document donne les URLs, les noms de couches et les filtres utilisés par
`01_download_data.py`, avec les volumes observés sur la Gironde (33) et les
ordres de grandeur France entière. Il sert aussi de mode opératoire pour les
couches qui ne sont pas entièrement automatisables (BDIFF, EWDS, FIRMS).

En mode France, les couches thématiques sont téléchargées **une fois par
département** (96 fichiers), tandis que le carroyage, les contours, le TMJA et
la météo sont nationaux. Cela borne la taille des requêtes WFS et permet de
reprendre un lot interrompu.

### Ordres de grandeur France entière

Comptes WFS mesurés sur l'emprise métropolitaine (avant filtre attributaire) :

| Couche | Entités |
|---|---|
| BD Forêt V2 (`formation_vegetale`) | ~2 035 951 |
| Routes BD TOPO (`troncon_de_route`) | ~20 569 083 (dont le filtre `importance<=4 OR piste_dfci=true` retire les chemins/sentiers) |
| RPG (`parcelles_graphiques`) | ~9 776 227 |
| Bâtiments BD TOPO (non téléchargés en V1) | ~51 484 368 |

Le stockage brut complet est de l'ordre de plusieurs Go à plusieurs dizaines
de Go ; le temps d'acquisition dépend fortement du débit et du service WFS
(compter plusieurs heures). Les scripts sont idempotents : un run interrompu
reprend au fichier suivant.

---

## 1. Carroyage DFCI 2 km (grille de référence)

- Page : https://www.data.gouv.fr/datasets/carroyage-dfci-2-km
- Page « réutilisations et dataservices » :
  https://www.data.gouv.fr/datasets/carroyage-dfci-2-km/reuses_and_dataservices
- API : https://www.data.gouv.fr/api/1/datasets/carroyage-dfci-2-km/
- Ressource principale :
  `CARRO_DFCI_2x2_L93.7z` (7,7 Mo)
  https://static.data.gouv.fr/resources/carroyage-dfci-france-2-km/20160607-104129/CARRO_DFCI_2x2_L93.7z
- Licence : Licence Ouverte (`fr-lo`)

Contenu : **339 264 polygones** en **EPSG:2154**, avec un champ `NOM` de
6 caractères (ex. `AA40D0`). C'est l'identifiant `id_carreau_dfci`. Le
carroyage couvre la France métropolitaine **et ses abords maritimes** :
seuls **139 842 carreaux** intersectent le territoire et sont conservés
(les 199 422 autres sont en mer ou hors territoire). Les carreaux côtiers
dont le centroïde est en mer sont rattachés au département le plus couvert.

La page `reuses_and_dataservices` ne contient pas de service web
supplémentaire exploitable : elle référence une réutilisation communautaire
(« Carroyage DFCI 2 Km à 5 zones », geonov) et le téléchargement direct. Le
pipeline utilise donc l'API data.gouv.fr + la ressource 7z.

**Récupération en Python** (ce que fait `01_download_data.py`) :

```python
import requests, py7zr
from pathlib import Path

api = "https://www.data.gouv.fr/api/1/datasets/carroyage-dfci-2-km/"
dataset = requests.get(api, timeout=60).json()
resource = next(r for r in dataset["resources"] if r["format"] == "7z")

archive = Path("data/raw/dfci/CARRO_DFCI_2x2_L93.7z")
archive.parent.mkdir(parents=True, exist_ok=True)
with requests.get(resource["url"], stream=True, timeout=300) as r:
    r.raise_for_status()
    with archive.open("wb") as fh:
        for chunk in r.iter_content(1 << 20):
            fh.write(chunk)

with py7zr.SevenZipFile(archive) as bundle:
    bundle.extractall("data/raw/dfci/extracted")
```

---

## 2. Admin Express COG (contours)

- WFS : `https://data.geopf.fr/wfs/ows`
- Couches :
  - `ADMINEXPRESS-COG-CARTO.LATEST:departement`
  - `ADMINEXPRESS-COG-CARTO.LATEST:commune`
- Filtres CQL :
  - mode département : `code_insee='33'`, `code_insee LIKE '33%'` ;
  - mode France : `code_insee NOT LIKE '97%' AND NOT LIKE '98%'` (96
    départements métropolitains, Corse incluse), communes nationales ou
    restreintes au sous-ensemble demandé (`(code_insee LIKE '33%' OR …)`).
- Licence : Etalab 2.0
- Fichiers : `admin/departements_france_metro.gpkg`,
  `admin/communes_france_metro.gpkg` (ou
  `communes_france_metro_<sous-ensemble>.gpkg`).

La bbox de chaque département est calculée après téléchargement et stockée
dans `data/interim/dept_<dept>_bbox.json` (Lambert-93 + WGS84). C'est cette
bbox qui filtre toutes les autres couches. La bbox englobante du périmètre
(TMJA, FIRMS, météo) est dans `data/interim/scope_<périmètre>_bbox.json`.

---

## 3. BD Forêt V2 (combustible)

- Présentation : https://geoservices.ign.fr/bdforet
- WFS, couche `LANDCOVER.FORESTINVENTORY.V2:formation_vegetale`
- Champ géométrique WFS : **`geom`** (attention, ce n'est pas `geometrie`)
- Champs utiles : `id`, `code_tfv`, `tfv`, `tfv_g11`, `essence`
- Filtre : `BBOX(geom, xmin, ymin, xmax, ymax, 'EPSG:2154')`
- Licence : Etalab 2.0

Valeurs `tfv` observées : `Forêt fermée de pin maritime pur`,
`Forêt fermée à mélange de feuillus`, `Forêt ouverte de feuillus purs`,
`Peupleraie`, `Lande`, `Forêt fermée sans couvert arboré`, etc.
Valeurs `essence` : `Pin maritime`, `Pin laricio, pin noir`, `Chênes décidus`,
`Feuillus`, `Mixte`, `Peuplier`, `NR`, `NC`.

Volume Gironde : **99 359 polygones** sur l'emprise élargie de 2,5 km
(95 278 sur le strict contour départemental), téléchargement WFS paginé
par tuiles de 25 km en 2 min 30 environ (285 Mo de GeoPackage).

---

## 4. BD TOPO (habitat, routes)

- Présentation : https://geoservices.ign.fr/bdtopo
- WFS, couches :
  - `BDTOPO_V3:zone_d_habitation` — zones d'habitat (tissu urbain, habitat
    rural, zones d'activité) ;
  - `BDTOPO_V3:troncon_de_route` — réseau routier, avec `importance`,
    `nature`, `piste_dfci`, `etat_de_l_objet`.
- Champ géométrique WFS : `geometrie`
- Licence : Etalab 2.0

Filtre routes : `importance<=4 OR piste_dfci=true` (autoroutes, nationales,
départementales, voies communales importantes + pistes DFCI). Les chemins et
sentiers (`importance=5`) sont exclus : 496 000 tronçons en Gironde, trop
bruités pour la V1.

Volumes Gironde (emprise + 2,5 km) :
- zones d'habitation : **51 948 polygones** (50 872 sur le strict contour) ;
- routes filtrées : **163 825 tronçons** (dont 42 220 pistes DFCI).

Le bâti individuel (`BDTOPO_V3:batiment`) n'est pas téléchargé en V1 :
1,9 million de bâtiments en Gironde, pour un gain marginal par rapport aux
zones d'habitation à la maille 2 km. Il est prévu en V2 pour un WUI bâtiment
par bâtiment.

---

## 5. Registre parcellaire graphique (RPG)

- WFS, couche `RPG.LATEST:parcelles_graphiques`
- Champ géométrique : `geom`
- Champs : `code_group`, `code_cultu`, `surf_parc`
- Licence : Etalab 2.0

Volume Gironde : **271 383 parcelles** (265 291 sur le strict contour).
Utilisé pour `agri_frac` et `agri_frac_1km`.

---

## 6. TMJA réseau routier national

- Page : https://www.data.gouv.fr/fr/datasets/trafic-moyen-journalier-annuel-sur-le-reseau-routier-national/
- Ressources CSV par année (`TMJA_RRNc_2022`, etc.), séparateur `;`,
  décimales `,`.
- Colonnes utiles : `route`, `xD`, `yD`, `xF`, `yF`, `TMJA`, `anneeMesureTrafic`.
- Licence : Licence Ouverte

Le TMJA ouvert ne couvre que le **réseau routier national** (autoroutes et
nationales) : **84 sections** en Gironde en 2018, 27 en 2022. Les années
2020 et 2021 ne sont pas publiées dans ce jeu de données. Résultat : seuls
0,6 % des carreaux ont un TMJA. Les routes départementales n'ont pas de TMJA
homogène ouvert : on utilise la densité routière et la classe de voie comme
proxy, et le modèle traite le TMJA comme une information rare (LightGBM gère
les NaN nativement). Une V2 peut intégrer les comptages des Conseils
départementaux.

---

## 7. MNT Copernicus DEM 30 m

- Bucket public :
  `https://copernicus-dem-30m.s3.amazonaws.com/`
- Tuile :
  `Copernicus_DSM_COG_10_N44_00_W001_00_DEM/Copernicus_DSM_COG_10_N44_00_W001_00_DEM.tif`
- Résolution : 1 arc-seconde (~30 m), COG (Cloud Optimized GeoTIFF)
- Licence : Copernicus DEM, attribution ESA

Le pipeline lit **seulement les fenêtres nécessaires** via GDAL `/vsicurl`,
puis reprojette sur la grille 25 m EPSG:2154. Pour la Gironde, 6 tuiles sont
ouvertes (N44W002, N44W001, N44E000, N45W002, N45W001, N45E000), soit
environ 250 Mo lus, mais aucun téléchargement de la France entière.

---

## 8. Indices FWI Copernicus EWDS

- Portail : https://ewds.climate.copernicus.eu/
- Collection : `cems-fire-historical-v1`
  (API catalogue :
  https://ewds.climate.copernicus.eu/api/catalogue/v1/collections/cems-fire-historical-v1)
- Variables : `fine_fuel_moisture_code`, `duff_moisture_code`,
  `drought_code`, `initial_fire_spread_index`, `build_up_index`,
  `fire_weather_index`, + options (`fire_daily_severity_rating`, etc.)
- Résolution : 0,25° (~25 km), grille ERA5
- Période : 1940 → aujourd'hui
- Licence : CC-BY 4.0

**Procédure** :

1. Créer un compte sur le portail EWDS.
2. Accepter la licence du dataset.
3. Récupérer l'URL et la clé API dans son profil.
4. Créer `~/.cdsapirc` :

```
url: https://ewds.climate.copernicus.eu/api
key: <votre-clé>
```

5. `pip install cdsapi`
6. Lancer `python scripts/01_download_data.py --layers weather`.

Requête utilisée :

```python
import cdsapi
client = cdsapi.Client()
client.retrieve(
    "cems-fire-historical-v1",
    {
        "product_type": "reanalysis",
        "variable": [
            "fine_fuel_moisture_code", "duff_moisture_code",
            "drought_code", "initial_fire_spread_index",
            "build_up_index", "fire_weather_index",
        ],
        "dataset_type": "consolidated_dataset",
        "system_version": ["4_1"],
        "year": ["2018", "2019", "2020", "2021", "2022", "2023"],
        "month": ["06", "07", "08", "09"],
        "day": [f"{d:02d}" for d in range(1, 32)],
        "grid": "0.25/0.25",
        "data_format": "netcdf",
        "area": [46.0, -2.0, 43.5, 1.0],  # N, W, S, E
    },
    "data/raw/weather/cems_fire_historical_33.nc",
)
```

**Limite** : 0,25° est grossier pour un modèle 2 km. La V1 l'accepte car la
météo est surtout un signal temporel ; le spatial vient du combustible et de
l'humain. V2 : AROME 2,5 km via l'API Météo-France, ou calcul du FWI à partir
de la météo horaire.

Le WMS EFFIS (`https://maps.effis.emergency.copernicus.eu/effis`) expose
les mêmes indices en visualisation (`mf010.fwi`, `mf010.ffmc`, `mf010.dmc`,
`mf010.dc`, `mf010.isi`, `mf010.bui`), mais pas de valeurs brutes
téléchargeables facilement. Il peut servir de contrôle visuel.

---

## 9. NASA FIRMS (optionnel)

- Portail : https://firms.modaps.eosdis.nasa.gov/
- Clé API gratuite : https://firms.modaps.eosdis.nasa.gov/api/map_key/
- API area :
  `https://firms.modaps.eosdis.nasa.gov/api/area/csv/{KEY}/{SOURCE}/{W,S,E,N}/{DAYS}/{DATE}`
- Sources : `VIIRS_SNPP_SP` (historique), `VIIRS_SNPP_NRT` (temps réel),
  `MODIS_SP`, `MODIS_NRT`
- Licence : données NASA ouvertes, attribution

L'API area est limitée à **5 jours par requête**. Pour couvrir 2018–2023, il
faut soit boucler jour par jour (lent), soit télécharger les archives
annuelles FIRMS (CSV globaux, plusieurs centaines de Mo par an) et filtrer
sur l'emprise. Le pipeline V1 ne récupère que les 5 derniers jours de la
période comme contrôle ; BDIFF reste la source de vérité.

---

## 10. BDIFF (variable cible principale)

- Portail : https://bdiff.agriculture.gouv.fr/
- Jeu de données data.gouv.fr :
  https://www.data.gouv.fr/fr/datasets/base-de-donnees-sur-les-incendies-de-forets-en-france-bdiff/
- Licence : Lov2 (Licence Ouverte 2.0)

Le jeu de données data.gouv.fr ne contient qu'un lien vers le portail, pas de
fichier téléchargeable ni d'API documentée. Le script `ml/download_bdiff.py`
(racine du dépôt) reproduit l'export CSV du formulaire : France entière, feux
de forêt, par tranches d'années (30 000 lignes maximum par export) :

```bash
python ml/download_bdiff.py --out ifm_plus/data/raw/manual/bdiff --debut 2006 --fin 2024
```

Colonnes utiles : `Année`, `Numéro`, `Département`, `Code INSEE`,
`Date de première alerte`, surfaces par type (m²), `Nature` (cause).
**Pas de coordonnées** : le feu est localisé à la commune. Le serveur envoie
une chaîne de certificats incomplète (intermédiaire HARICA « GEANT TLS RSA 1 »
absent), que le script complète sans désactiver TLS.

Récupération manuelle, si le script ne fonctionne plus :

1. Ouvrir le portail BDIFF.
2. Filtrer **France métropolitaine (96 départements, Corse incluse)**, période **2018-01-01 → 2023-12-31**.
3. Exporter en CSV ou GeoJSON.
4. Déposer le fichier dans `ifm_plus/data/raw/manual/bdiff_france_metro/` (périmètre national par défaut).
5. Vérifier les colonnes : `date`, `x`/`y` ou `lon`/`lat`, `surface_ha`,
   `commune`, `code_insee`, `cause`.

Le script 01 crée le dossier et un README avec ces instructions ; le script
04 normalisera les colonnes.

**Interventions SDIS** : non ouvertes. Une convention avec chaque SDIS concerné est
nécessaire pour obtenir date/heure, commune, coordonnées, surface et cause.
Ces données sont plus précises que BDIFF pour les petits feux, mais leur
accès n'est pas garanti dans le cadre du hackathon.

---

## 11. Météo-France (V2)

- API publique : https://portail-api.meteofrance.fr/
- Produits : AROME 2,5 km (PAQUETS), observations, vigilance.
- Clé API gratuite après inscription.
- « Météo des forêts » : indice de danger publié par Météo-France, pas
  encore d'API ouverte documentée. À demander pour la V2.

Le pipeline V1 ne dépend pas de Météo-France : EWDS suffit pour la
dynamique temporelle. La V2 ajoutera AROME pour descendre à 2,5 km.

---

## 12. Aide-mémoire WFS IGN

Le service WFS de la Géoplateforme a quelques particularités :

1. **`BBOX` et `CQL_FILTER` sont mutuellement exclusifs** en paramètres
   séparés. Pour combiner spatial et attributaire, utiliser la fonction CQL
   `BBOX(...)` :

```
CQL_FILTER=BBOX(geometrie,361791,6349292,487890,6507152,'EPSG:2154')
           AND importance<=4
```

2. **Le champ géométrique change selon la couche** :
   - BD TOPO : `geometrie`
   - BD Forêt V2 / RPG : `geom`
   - Admin Express : `geometrie`
3. **Pagination** : `COUNT` + `STARTINDEX`, `numberMatched` dans la réponse
   JSON.
4. **Projection** : `SRSNAME=EPSG:2154` pour éviter des reprojections
   locales.
5. **`PROPERTYNAME`** réduit fortement le volume (routes : 2,5 Mo / 5 000
   entités au lieu de 15 Mo). Il faut inclure le champ géométrique
   (`geometrie`) pour conserver la géométrie.
6. **Timeouts** : les grosses couches (BD Forêt) peuvent dépasser 60 s sur
   une page. Le client utilise des retries et des pages de 2 000 à 5 000.

---

## 13. Licences et attribution

| Donnée | Licence | Attribution |
|---|---|---|
| Carroyage DFCI | Licence Ouverte | data.gouv.fr / DFCI |
| Admin Express, BD Forêt, BD TOPO, RPG | Etalab 2.0 | IGN |
| TMJA | Licence Ouverte | Ministère de la Transition écologique |
| Copernicus DEM | Attribution ESA | Copernicus Programme |
| EWDS / CEMS Fire | CC-BY 4.0 | Copernicus EMS / EFFIS |
| FIRMS | NASA open data | NASA FIRMS |
| BDIFF | Lov2 | IGN / Ministère de l'Agriculture |

Toute publication (rapport, carte, dashboard) doit citer ces sources.
