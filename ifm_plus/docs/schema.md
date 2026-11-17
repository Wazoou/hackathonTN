# Schéma de la table analytique `carreau × date`

Cette table est le contrat entre l'acquisition (01), les features (02/03),
les labels (04) et la modélisation (05/06/07). Grain : **une ligne par
carreau DFCI et par date**.

```
(id_carreau_dfci, date)  →  features statiques + features météo + cible
```

Pour la Gironde : 2 761 carreaux × 6 ans × 122 jours de saison
(juin–septembre) ≈ **2,0 millions de lignes**. En année complète :
≈ 6,0 millions.

Pour la **France métropolitaine** : 139 842 carreaux terrestres × 6 ans
× 122 jours ≈ **102 millions de lignes** (17 millions par saison annuelle).
Le stockage se fait en Parquet partitionné par année **et par département**
(`analytical_table/dept=33/year=2018/…`) ; l'entraînement devra échantillonner
les négatifs (voir `modelisation_evaluation.md`).

---

## 1. Clés et contexte

| Colonne | Type | Description |
|---|---|---|
| `id_carreau_dfci` | string | Code DFCI 2 km (ex. `AA40D0`), clé spatiale |
| `date` | date | Date locale (Europe/Paris), clé temporelle |
| `cell_id` | int32 | Identifiant interne global, utilisé pour les jointures raster |
| `departement` | string | Code INSEE du département d'appartenance (mode France) |
| `code_insee` | string | Commune du centroïde du carreau |
| `nom_commune` | string | Nom de la commune |
| `annee`, `mois`, `jour_annee` | int | Variables de calendrier |
| `saison` | string | `hors_saison`, `juin`, …, `septembre` |
| `split` | string | `train`, `val`, `test` (défini par la CV temporelle) |

---

## 2. Features statiques (43 variables, dont 6 de contexte)

Elles sont calculées une fois par carreau (script 02) et répliquées sur
chaque date. Le catalogue détaillé est dans `features/catalog.py` et dans
`static_features_<périmètre>_metadata.json`.

### Combustible (BD Forêt V2)

`foret_frac`, `resineux_frac`, `feuillus_frac`, `mixte_frac`,
`peupleraie_frac`, `lande_frac`, `foret_fermee_frac`, `foret_ouverte_frac`,
`foret_sans_couvert_frac`, `pin_frac`, `lisiere_m_ha`, `foret_frac_1km`.

### Relief (Copernicus DEM 30 m)

`alt_moy_m`, `alt_min_m`, `alt_max_m`, `alt_std_m`, `pente_moy_deg`,
`pente_max_deg`, `frac_pente_sup15`, `frac_pente_sup25`.

### Pression humaine (BD TOPO, TMJA, RPG)

`habitat_frac`, `wui_frac`, `part_habitat_wui`, `route_km`,
`route_km_km2`, `route_principale_km`, `route_dfci_km`,
`route_ponderee_km`, `distance_route_principale_m`, `tmja_max`,
`tmja_moyen_pondere`, `exposition_tmja`, `agri_frac`, `agri_frac_1km`,
`habitat_frac_1km`, `wui_frac_1km`, `route_km_km2_1km`.

### Contexte

`area_ha`, `frac_dans_dept`, `x_centroid`, `y_centroid`, `lon`, `lat`.

---

## 3. Features dynamiques (météo)

Produites par `03_build_dynamic_features.py`, sources EWDS (V1) et AROME
(V2). Les noms exacts sont fixés ici pour que 05/06/07 soient stables.

### Indices FWI journaliers

| Colonne | Unité | Rôle |
|---|---|---|
| `fwi` | indice | IFM/FWI du jour (variable de benchmark) |
| `ffmc` | indice | humidité des combustibles fins |
| `dmc` | indice | sécheresse des couches organiques superficielles |
| `dc` | indice | sécheresse profonde (sécheresse de saison) |
| `isi` | indice | vitesse initiale de propagation |
| `bui` | indice | combustible disponible total |

### Transformations temporelles

- `fwi_lag1`, `fwi_lag2`, `fwi_lag3`, `fwi_lag7` ;
- `fwi_roll7_mean`, `fwi_roll14_mean`, `fwi_roll14_max` ;
- `fwi_delta_1d`, `fwi_pente_3j` ;
- `ffmc_lag1`, `dmc_lag7`, `dc_lag14`, `isi_max_3j`, `bui_lag1` ;
- `fwi_percentile` : percentile du FWI dans la distribution **d'entraînement**
  du même mois (calculé uniquement sur le train, appliqué au val/test) ;
- `fwi_anomalie` : écart à la normale 1991–2020 du même jour de l'année
  (calculée sur l'historique EWDS, pas sur la période de test).

### Météo brute (V2 AROME / V1 ERA5)

`temp_max_c`, `temp_min_c`, `hr_min_pct`, `vent_max_kmh`,
`rafales_kmh`, `pluie_24h_mm`, `pluie_7j_mm`, `pluie_30j_mm`,
`jours_sans_pluie` (nombre de jours consécutifs avec < 1 mm).

### Interactions météo × combustible

Calculées à la volée dans le modèle (arbres) ou explicites pour la
régression logistique :

- `fwi_x_resineux = fwi × resineux_frac` ;
- `fwi_x_wui = fwi × wui_frac` ;
- `isi_x_pente = isi × pente_moy_deg` ;
- `dc_x_foret = dc × foret_frac`.

---

## 4. Cible et métadonnées de label

| Colonne | Type | Description |
|---|---|---|
| `feu_depart` | int8 | **Cible binaire** : 1 si au moins un départ de feu est rattaché au carreau ce jour-là, sinon 0 |
| `feu_id` | string | Identifiant de l'événement (BDIFF/SDIS/FIRMS), nullable |
| `source_label` | string | `BDIFF`, `SDIS`, `FIRMS`, `BDIFF+SDIS` |
| `label_confiance` | string | `haute` (coordonnées + date), `moyenne` (commune + date), `basse` (mois seul) |
| `surface_ha` | float | Surface brûlée, si connue |
| `heure_depart` | time | Heure de départ, si connue |
| `cause` | string | Cause connue (humaine, foudre, etc.) |
| `nb_detections_firms` | int | Nombre de détections FIRMS dans le carreau ce jour |
| `feu_firms` | int8 | Cible alternative FIRMS, pour les analyses de sensibilité |

Règles de construction :

1. **Un seul label par carreau × jour** : `feu_depart = max(labels)`.
2. La date BDIFF est la date de **départ**, pas la date d'extinction.
3. Si BDIFF ne fournit que le mois, `label_confiance='basse'` et
   `feu_depart` n'est utilisé qu'en analyse descriptive (exclu du train
   strict).
4. Si le même feu apparaît dans BDIFF et dans les interventions SDIS, on
   déduplique par (carreau, date) et on garde la source la plus fiable.
5. Les feux de moins de 1 ha peuvent être conservés (ils restent des
   départs) mais sont signalés par `surface_ha`.
6. FIRMS ne crée jamais un `feu_depart=1` à lui seul dans le jeu principal :
   il sert de contrôle de rappel et de cible alternative.

---

## 5. Jointures spatio-temporelles : gérer les résolutions

### 5.1 Vecteur → maille DFCI 2 km

Deux méthodes, selon la variable :

| Type de couche | Méthode | Exemple |
|---|---|---|
| Occupation du sol (polygones) | Rasterisation 25 m puis **fraction de surface** par carreau | BD Forêt, RPG, zones d'habitation |
| Linéaires (routes) | Point médian du tronçon → carreau, puis somme des longueurs | BD TOPO, TMJA |
| Ponctuel (feux, détections) | Point-in-polygon strict | BDIFF, FIRMS, SDIS |
| Communes | Centroïde du carreau → commune | Admin Express |

La rasterisation à 25 m puis agrégation par `cell_id` est préférée aux
intersections vectorielles : elle est plus rapide, gère les géométries
invalides et donne des fractions additives. L'erreur de surface est
inférieure à 1 % pour un carreau de 400 ha.

**Carreaux de bord** : le carreau DFCI est conservé en entier, même s'il
déborde du département. La colonne `frac_dans_dept` permet de filtrer ou de
pondérer. Les couches sources sont téléchargées avec une marge de 2,5 km
autour du département pour que les carreaux de bord soient complets.

**Mode France — affectation exclusive** : pour éviter qu'un même carreau
apparaisse dans deux départements, chaque carreau est rattaché au département
qui contient son **centroïde** ; à défaut (carreaux côtiers ou frontaliers),
au département avec la **plus grande surface d'intersection**. Les carreaux
entièrement en mer (~199 000) sont écartés. Un carreau n'apparaît donc
qu'une seule fois dans la table nationale, et `cell_id` est un identifiant
**global** (1…139 842) attribué sur les carreaux terrestres triés, stable
entre les lots. Le mode « un département » conserve la règle historique
(intersection), afin de ne pas modifier les sorties déjà produites.

**Voisinage 3×3** : en mode France, il est calculé sur l'ensemble des
139 842 carreaux terrestres **après** l'assemblage national (`cKDTree` sur les
centroïdes). Les variables `*_1km` sont donc continues au passage d'une
frontière départementale, contrairement à un calcul par département.

**Assemblage** : les features de chaque département sont mises en cache dans
`data/processed/dept/static_features_<dept>_<res>m_<skip>_<empreinte>.parquet`
(le suffixe encode les couches ignorées et une empreinte de taille des
fichiers d'entrée, pour ne jamais réutiliser un cache incomplet). Le script 02
reprend les départements déjà calculés (sauf `--force`), ce qui rend un run
France interrompu reprenable. Seul le voisinage national est recalculé
(quelques secondes).

### 5.2 Raster météo → maille DFCI

- EWDS 0,25° (~25 km) : la valeur est affectée au **point de grille le plus
  proche du centroïde** du carreau, ou interpolée bilinéairement. En V1,
  plusieurs carreaux partagent donc la même valeur météo : c'est normal, le
  signal spatial vient du combustible et de l'humain.
- AROME 2,5 km (V2) : interpolation bilinéaire au centroïde, ou moyenne
  d'emprise pour les variables de pluie.
- Les indices sont datés au **jour civil** ; on utilise la valeur du jour
  `J` disponible avant l'ignition (prévision ou réanalyse). On n'utilise
  jamais une valeur postérieure à l'ignition (voir §6).

### 5.3 Ponctuel → maille DFCI

- BDIFF/SDIS avec coordonnées : `sjoin(points, carreaux, predicate='within')`.
  Les points tombant exactement sur une frontière sont rattachés au carreau
  dont le centroïde est le plus proche.
- BDIFF sans coordonnées mais avec commune : label au niveau commune. On ne
  duplique **pas** le feu sur tous les carreaux de la commune (cela créerait
  des faux positifs). Ces lignes sont exclues du train supervisé et gardées
  pour l'analyse.
- FIRMS : une détection = un point ; plusieurs détections le même jour dans
  le même carreau sont agrégées (`nb_detections_firms`), avec filtre de
  confiance (`confidence` ≥ `nominal` pour VIIRS, `confidence` ≥ 50 pour
  MODIS).

### 5.4 Temporel

- Table **complète** : toutes les combinaisons carreau × date de la période
  existent, y compris les jours sans feu (`feu_depart=0`). C'est
  indispensable pour modéliser l'absence d'événement.
- Les jours hors saison peuvent être conservés avec `saison='hors_saison'`
  mais l'entraînement et l'évaluation principaux portent sur juin–septembre.
- Les lags sont calculés **à l'intérieur de chaque split** : les 14 premiers
  jours d'un bloc de validation/test n'utilisent pas les jours du bloc
  précédent (purge), pour éviter que le modèle apprenne la fin de la
  période d'entraînement.

---

## 6. Prévention du data leakage

Checklist appliquée dans 03/04/05/06 :

1. **Temporel** : split par année, jamais de ligne aléatoire. Les features
   du jour `t` n'utilisent que des informations disponibles avant
   l'ignition (J-1 et antérieurs), sauf le FWI prévisionnel du jour `J`.
2. **Lags** : `rolling` et `shift` calculés après tri par (carreau, date),
   sans `bfill`. Les premiers jours de chaque split sont purgés.
3. **Normalisation** : percentiles FWI, moyennes/écarts-types, encodeurs et
   imputateurs ajustés **uniquement sur le train**, puis appliqués au
   validation/test.
4. **Cible** : aucune variable dérivée des feux (distance au feu précédent,
   nombre de feux passés dans le carreau) n'est utilisée dans la V1. Si on
   l'ajoute, elle doit être calculée en `shift(1)` et uniquement sur le
   passé.
5. **Statique** : les couches BD Forêt/BD TOPO sont postérieures à certains
   feux (millésime 2020–2024). C'est une limite de données, pas une fuite
   de la cible ; elle est documentée. Ne jamais utiliser `surface_ha` ou
   `cause` comme feature.
6. **Sélection de modèle** : le jeu de test 2023 n'est ouvert qu'une fois,
   après la fin de la recherche d'hyperparamètres sur 2018–2022.

---

## 7. Découpage temporel recommandé

```
2018 ─ 2019 ─ 2020 ─ 2021 │ 2022 │ 2023
        train             │ val  │ test
```

- Recherche d'hyperparamètres : validation croisée temporelle à fenêtre
  glissante sur 2018–2021 (voir `modelisation_evaluation.md`).
- Validation : 2022.
- Test final : 2023, ouvert une seule fois.
- Purge : 14 jours au début de chaque bloc (durée maximale des lags).
- Alternative robuste : refaire l'expérience avec test 2022 et validation
  2023 pour vérifier la stabilité des conclusions.

Le split est matérialisé par la colonne `split` et par les partitions
Parquet, pour éviter toute fuite accidentelle lors du chargement.
