# IFM+ — score de risque intégré des départs de feu

Ce dossier contient le pipeline de modélisation du **score IFM+** : un score
de risque quotidien à la maille **DFCI 2 km**, qui combine la météo
(IFM/FWI), le combustible, le relief et la pression humaine pour estimer la
probabilité d'un départ de feu.

Le périmètre par défaut est la **France métropolitaine : 96 départements,
Corse incluse, outre-mer exclu**, sur la période **2018–2023** (saison
juin–septembre). Chaque département est traité séparément, puis les tables
sont assemblées et le voisinage est recalculé au niveau national.
Le mode local reste disponible avec `--departement 33` (ou un autre code).

Le maillage national est distinct des facteurs explicatifs et du score :
sa présence ne signifie pas que toutes les couches sont déjà téléchargées.
Voir **[docs/couverture_nationale.md](docs/couverture_nationale.md)** pour
les commandes, les contrôles et l’état de l’audit.

> Ce pipeline est indépendant de la partie détection caméra/YOLO du dépôt
> (`api/`, `camera/`, `dashboard/`). Il produit les couches de risque qui
> alimentent le mode « Carte de risque » du dashboard (voir `ml/build_static_risk.py`).

---

## 1. Démarrage rapide

```bash
cd ifm_plus
python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt

cp .env.example .env            # clés optionnelles (FIRMS, EWDS)

# Référentiels nationaux et maillage utilisable sans les couches lourdes
python scripts/01_download_data.py --layers dfci,admin,tmja
python scripts/00_build_grid.py

# Acquisition nationale reprenable (plusieurs dizaines de Go transférés)
python scripts/10_bulk_download.py --layers all
python scripts/11_build_features_france.py --no-fetch
python scripts/12_check_coverage.py --require-complete
```

Sans clé FIRMS/EWDS/BDIFF, le script 01 termine quand même : ces couches sont
marquées `skipped` ou `manual_required`, et le pipeline continue avec les
couches ouvertes.

Pour ne télécharger que le maillage et les contours :

```bash
python scripts/01_download_data.py --layers dfci,admin
```

Pour un test rapide des couches WFS (100 entités par couche) :

```bash
python scripts/01_download_data.py --departement 33 --layers admin,forest,roads --max-features 100
```

### France métropolitaine

```bash
# 1. Acquisition nationale (long : plusieurs heures, plusieurs Go)
python scripts/01_download_data.py --perimetre france_metro --layers all

# 2. Features département par département + assemblage national
python scripts/02_build_static_features.py --perimetre france_metro
```

Test sur deux départements (mêmes règles, plus rapide) :

```bash
python scripts/01_download_data.py --departements 33,40 --layers all
python scripts/02_build_static_features.py --departements 33,40
```

Les deux étapes sont **idempotentes et reprenables** : un fichier déjà présent
n'est pas retéléchargé, et un département déjà calculé par 02 est relu depuis
`data/processed/dept/` (utiliser `--force` pour recalculer). Le mode
« un département » est explicite (`--departement 33`). Une table nationale
n’est publiée que si tous les départements et tous les carreaux attendus sont
présents. Une couche absente provoque un arrêt ; `--skip` reste possible pour
un calcul exploratoire, avec les omissions enregistrées dans les métadonnées.

---

## 2. Arborescence

```
ifm_plus/
├── config.yaml                  # périmètre, département(s), période, résolution
├── requirements.txt
├── .env.example                 # FIRMS_MAP_KEY, CDSAPI_KEY, METEOFRANCE_API_KEY
├── README.md
├── docs/
│   ├── sources.md               # URLs, champs, licences, volumes
│   ├── schema.md                # table analytique et règles de jointure
│   ├── features.md              # les 3 piliers et toutes les variables
│   └── modelisation_evaluation.md
├── scripts/
│   ├── 00_build_grid.py         # maillage GeoParquet sans score
│   ├── 10_bulk_download.py      # archives IGN / Copernicus nationales
│   ├── 11_build_features_france.py # facteurs statiques depuis les archives
│   ├── 12_check_coverage.py     # audit local et catalogue IGN (--catalog)
│   ├── 01_download_data.py      # acquisition (implémenté)
│   ├── 02_build_static_features.py  # features statiques (implémenté)
│   ├── 03_build_dynamic_features.py # météo, lags, table de base (à venir)
│   ├── 04_build_labels.py       # BDIFF / FIRMS / SDIS -> feu_depart (à venir)
│   ├── 05_baseline_score.py     # score expert 0-100 (à venir ; version statique : ../ml/build_static_risk.py)
│   ├── 06_train_model.py        # LightGBM/XGBoost + CV temporelle (à venir)
│   └── 07_evaluate.py           # PR-AUC, lift, SHAP, benchmark IFM (à venir)
├── src/ifmplus/
│   ├── config.py                # chargement YAML
│   ├── datagouv.py              # API data.gouv.fr + téléchargements
│   ├── wfs.py                   # WFS IGN paginé, BBOX + CQL
│   ├── raster.py                # grille 25 m, stats zonales
│   ├── geoutils.py              # maillage DFCI, affectation départementale, lecture/écriture
│   ├── sources.py               # les 8 fetchers (nationaux + boucle départementale)
│   └── features/
│       ├── forest.py            # combustible (BD Forêt V2)
│       ├── relief.py            # pente / altitude (Copernicus DEM)
│       ├── human.py             # WUI, routes, TMJA, RPG, communes
│       ├── neighbourhood.py     # continuité 3x3
│       └── catalog.py           # dictionnaire des features
└── data/                        # gitignoré, créé par les scripts
    ├── raw/                     # couches brutes + _manifest.json
    ├── interim/                 # bbox départementales + carreaux affectés
    └── processed/               # static_features_<périmètre>.parquet (+ GPKG, dept/)
```

---

## 3. Les étapes du pipeline

| Étape | Script | Entrées | Sortie | Rôle |
|---|---|---|---|---|
| 01 | `01_download_data.py` | APIs/WFS | `data/raw/**` | Acquisition filtrée (département ou boucle France) |
| 02 | `02_build_static_features.py` | DFCI, BD Forêt, BD TOPO, RPG, MNT | `static_features_<périmètre>.parquet` | Features fixes par carreau |
| 03 | `03_build_dynamic_features.py` | EWDS/AROME | `analytical_base.parquet` | Météo quotidienne, lags, table `carreau × date` |
| 04 | `04_build_labels.py` | BDIFF/FIRMS/SDIS | `analytical_table.parquet` | Cible binaire `feu_depart` |
| 05 | `05_baseline_score.py` | Table 04 | `score_ifmplus_100` | Score composite expert, interprétable |
| 06 | `06_train_model.py` | Table 04 | modèle + prédictions | LightGBM/XGBoost, CV temporelle |
| 07 | `07_evaluate.py` | Prédictions | rapport + figures | PR-AUC, lift, Recall@Top5%, SHAP |

Le contrat précis de la table finale est dans **[docs/schema.md](docs/schema.md)**.

### 3 bis. Ce que change le mode France

Une grille nationale à 25 m représenterait ~2,5 milliards de pixels : elle ne
tient pas en mémoire. Le mode France applique donc le pipeline **par
département** :

1. **01** télécharge une seule fois les référentiels nationaux (carroyage
   DFCI, départements, communes, TMJA, météo), puis les couches thématiques
   département par département (BD Forêt, habitat, routes, RPG, MNT).
2. **02** affecte chaque carreau DFCI à **un seul** département (centroïde),
   construit les features sur la grille 25 m locale, met le résultat en cache,
   puis concatène les 96 tables.
3. Le voisinage 3×3 (`*_1km`) est recalculé sur la table nationale, sans
   couture aux frontières départementales.

Ordres de grandeur : ~140 000 carreaux terrestres (sur 339 264 mailles du
carroyage, la mer est exclue), ~43 variables statiques,
téléchargements de plusieurs Go (routes et BD Forêt sont les plus lourdes) et
plusieurs heures pour l'acquisition complète. La mémoire de 02 reste celle
d'un département (quelques Go). Le détail des volumes est dans
**[docs/sources.md](docs/sources.md)**.

---

## 4. Ce que fait l'acquisition (01)

Le script interroge l'API data.gouv.fr pour résoudre le jeu de données
`carroyage-dfci-2-km`, récupère ses métadonnées et la ressource
`CARRO_DFCI_2x2_L93.7z`, l'extrait et la convertit en GeoPackage. Il télécharge
ensuite les couches selon le périmètre :

| Couche | Mode | Filtre (un département / France) |
|---|---|---|
| Carroyage DFCI 2 km | API data.gouv.fr | France entière, une seule fois |
| Admin Express départements | WFS IGN | `code_insee='33'` / `NOT LIKE '97%' AND NOT LIKE '98%'` |
| Admin Express communes | WFS IGN | `LIKE '33%'` / national (ou sous-ensemble demandé) |
| BD Forêt V2 | WFS IGN | BBOX locale, tuiles 25 km |
| Zones d'habitation BD TOPO | WFS IGN | BBOX locale, tuiles 50 km |
| Routes BD TOPO | WFS IGN | BBOX + `importance<=4 OR piste_dfci=true` |
| RPG | WFS IGN | BBOX locale, tuiles 25 km |
| TMJA réseau national | CSV data.gouv.fr | national, une seule fois (filtre bbox en mode département) |
| MNT Copernicus 30 m | COG S3 (`/vsicurl`) | 1 fichier par département, lecture fenêtrée |
| FIRMS | API NASA | emprise du périmètre + 5 jours (clé requise) |
| BDIFF | export du portail (`../ml/download_bdiff.py`) ou manuel | dossier `data/raw/manual/bdiff/` |
| FWI/FFMC/DMC/DC/ISI/BUI | Copernicus EWDS | emprise du périmètre, saison (compte requis) |

En mode France, les couches thématiques sont téléchargées **par département**
(96 × 1 fichier), ce qui borne la taille des requêtes et permet de reprendre
un lot interrompu. Les bboxes départementales sont dérivées du référentiel
national, sans requête WFS supplémentaire. Les volumes mesurés sur la
Gironde et les comptes nationaux sont dans **[docs/sources.md](docs/sources.md)**.

Chaque téléchargement est tracé dans `data/raw/_manifest.json` (URL, date,
taille, SHA-256, nombre d'entités), avec une clé par département en mode
France (`forest:33`, `dem:40`, …), ce qui rend les relances idempotentes.

---

## 5. Ce que produit 02

`static_features_33.parquet` contient une ligne par carreau DFCI (environ
**2 761 carreaux** pour la Gironde) et **43 variables** (dont 6 de contexte
géographique, soit 37 variables de risque). En mode France,
`static_features_france_metro.parquet` contient **139 842 carreaux
terrestres** (une ligne par carreau, `cell_id` global, colonne
`departement`) :

- **Combustible** : parts résineux/feuillus/mixte/peupleraie/lande, forêt
  fermée/ouverte, pins, densité de lisière, continuité à 1 km ;
- **Relief** : altitude moyenne/min/max/écart-type, pente moyenne/max, parts
  de pente > 15° et > 25° ;
- **Pression humaine** : part d'habitat, WUI à 200 m, densité routière,
  routes principales, pistes DFCI, distance aux axes, TMJA, exposition au
  trafic, part agricole, voisinage 3×3.

La géométrie et les mêmes attributs sont aussi écrits dans le GPKG pour QGIS
(`static_features_33.gpkg` ; en mode France uniquement avec `--gpkg`, fichier
volumineux). Le catalogue des variables est exporté dans
`static_features_<périmètre>_metadata.json` (avec la liste des départements,
la bbox du périmètre et les contrôles qualité).

---

## 6. Choix techniques

- **Projection** : EPSG:2154 (Lambert-93) partout ; WGS84 uniquement pour
  les API (FIRMS, EWDS) et l'affichage.
- **Résolution des features de couverture** : raster 25 m sur l'emprise du
  département, puis agrégation par `cell_id` DFCI. Cela évite des milliers
  d'intersections vectorielles et rend les calculs reproductibles. En mode
  France, la grille est construite **département par département**, jamais
  pour la France entière.
- **Carreaux de bord** : on conserve le carreau DFCI entier, même s'il
  déborde du département, pour ne pas biaiser les features de surface. En
  mode France, chaque carreau est rattaché à un seul département (centroïde ;
  à défaut, plus grande surface d'intersection ; les carreaux entièrement en
  mer sont écartés) ; `frac_dans_dept` reste disponible pour filtrer ou
  pondérer.
- **Identifiants** : en mode France, `cell_id` est attribué sur les carreaux
  terrestres triés (1…139 842) et reste stable entre les lots ;
  `id_carreau_dfci` reste la clé métier.
- **Idempotence** : chaque couche est sautée si son fichier existe, sauf
  `--force`.
- **Traçabilité** : manifeste JSON + métadonnées de features + versions des
  couches.

---

## 7. Limites assumées (et pistes V2)

1. **Résolution météo** : EWDS `cems-fire-historical-v1` est à 0,25°
   (~25 km). C'est suffisant pour la dynamique temporelle, pas pour des
   gradients locaux. V2 : AROME 2,5 km via l'API Météo-France, ou calcul du
   FWI à partir de la météo horaire.
2. **BDIFF** : pas d'API ; `../ml/download_bdiff.py` reproduit l'export CSV du portail
   (France entière, par tranches d'années). Les feux sont localisés à la commune.
   Les feux non déclarés et les petits feux sont sous-représentés.
3. **FIRMS** : détections satellitaires avec faux positifs (torchères,
   nuages) et passages non quotidiens. À utiliser comme complément, pas comme
   vérité terrain.
4. **Données statiques** : BD Forêt/BD TOPO actuelles appliquées à
   2018–2023 ; les évolutions d'occupation du sol ne sont pas rétroactives.
5. **WUI** : proxy raster à 200 m (habitat BD TOPO), pas un calcul bâtiment
   par bâtiment. V2 : bâti individuel + MNS LiDAR HD.
6. **TMJA** : réseau routier national uniquement (84 sections en Gironde en
   2018, 27 en 2022), et années 2020–2021 absentes du jeu de données. Seuls
   0,6 % des carreaux ont un TMJA ; le modèle utilise aussi la densité
   routière locale comme proxy.
7. **Volume national** : l'acquisition France entière représente plusieurs
   Go (BD Forêt ~2 M de formations, routes ~20 M de tronçons après filtre,
   RPG ~10 M de parcelles) et plusieurs heures de téléchargement. Les scripts
   sont reprenables mais il faut prévoir l'espace disque et lancer l'étape 01
   par lots (`--layers`, `--departements`) si nécessaire.
8. **Météo nationale** : EWDS est téléchargé une fois pour l'emprise
   métropolitaine ; le maillage 0,25° reste grossier pour les gradients
   locaux, et la V1 ne traite pas encore la dynamique à 2,5 km.

---

## 8. Documentation

- **[docs/sources.md](docs/sources.md)** — URLs exactes, champs, licences,
  volumes, procédures manuelles.
- **[docs/schema.md](docs/schema.md)** — schéma de la table `carreau × date`,
  jointures spatio-temporelles, gestion des résolutions, anti-leakage.
- **[docs/features.md](docs/features.md)** — les 3 piliers, formules,
  variables dynamiques et statiques.
- **[docs/modelisation_evaluation.md](docs/modelisation_evaluation.md)** —
  score expert, ML, déséquilibre, CV temporelle, métriques, tests
  statistiques et SHAP.
