# Feature engineering — les 3 piliers de l'IFM+

L'IFM/FWI ne mesure que la **propension météorologique** à la propagation.
Un départ de feu dépend aussi de :

1. **ce qui peut brûler** (combustible, continuité, relief) ;
2. **ce qui peut provoquer l'étincelle** (activité humaine, interfaces).

IFM+ combine ces trois piliers à la maille DFCI 2 km. Les features statiques
sont calculées par `02_build_static_features.py`, les features dynamiques
par `03_build_dynamic_features.py`.

---

## 1. Pilier météo — au-delà de l'IFM final

### 1.1 Pourquoi les sous-indices

Le FWI est une synthèse. Ses composantes portent des informations
différentes et complémentaires :

| Indice | Ce qu'il mesure | Pourquoi il compte pour le **départ** |
|---|---|---|
| `FFMC` | humidité des litières fines (< 1 kg/m²) | Allumage : une litière sèche prend feu avec une flamme ou une étincelle |
| `DMC` | sécheresse des couches organiques superficielles | Combustion lente, durées de flamme |
| `DC` | sécheresse profonde (saison) | Disponibilité de gros combustibles, feux de sol |
| `ISI` | vitesse initiale de propagation | Vitesse de montée en puissance |
| `BUI` | combustible total disponible | Énergie disponible, propagation |
| `FWI` | synthèse | Benchmark et communication |

Deux journées peuvent avoir le même FWI avec des FFMC/DC très différents :
un printemps humide avec un coup de vent (FFMC élevé, DC bas) ne se comporte
pas comme une fin d'été sèche (DC très élevé). Les sous-indices permettent au
modèle de distinguer ces régimes.

### 1.2 Variables construites

Pour chaque carreau × date :

- **Niveau** : `fwi`, `ffmc`, `dmc`, `dc`, `isi`, `bui` ;
- **Lags** : `x_lag1`, `x_lag2`, `x_lag3`, `x_lag7` (mémoire de la sécheresse) ;
- **Fenêtres glissantes** : `fwi_roll7_mean`, `fwi_roll14_mean`,
  `fwi_roll14_max`, `isi_max_3j` ;
- **Dynamique** : `fwi_delta_1d`, `fwi_pente_3j` ;
- **Position dans la distribution** : `fwi_percentile` (percentile mensuel
  calculé sur le train), `fwi_anomalie` (écart à la normale 1991–2020) ;
- **Météo brute** (si AROME/ERA5 disponible) : `temp_max_c`, `hr_min_pct`,
  `vent_max_kmh`, `rafales_kmh`, `pluie_24h_mm`, `pluie_7j_mm`,
  `jours_sans_pluie`.

`jours_sans_pluie` est calculé comme le nombre de jours consécutifs avec
moins de 1 mm, en remontant dans le passé. C'est un concurrent direct du DC,
mais à échelle locale.

### 1.3 Précautions

- Les lags sont calculés **par carreau**, après tri `(id_carreau_dfci, date)`.
- Aucun `bfill` : une valeur manquante reste manquante (ou est imputée par
  la médiane du train, jamais par le futur).
- Le percentile FWI est ajusté sur le train uniquement.
- La météo du jour `J` doit être une **prévision disponible avant
  l'ignition** (FWI EFFIS J+0/J+1) ou une réanalyse utilisée en recherche
  rétrospective. Ne jamais utiliser les observations post-incendie.

---

## 2. Pilier combustible & relief

### 2.1 Classes de combustible (BD Forêt V2)

La BD Forêt V2 fournit `tfv` (type de formation végétale) et `essence`.
On construit les classes suivantes :

| Classe | Règle (après normalisation des accents) | Intérêt risque |
|---|---|---|
| Résineux | `tfv` contient `conifère`/`pin` ou essence contient `pin`, `sapin`, `épicéa`, `douglas`, `mélèze`, `cèdre` | Haute inflammabilité, feux de cime |
| Feuillus | `tfv` contient `feuillu`, `chêne`, `robinier`, `châtaignier` | Moins inflammables, humides |
| Mixte | `tfv` contient `mélange` ou essence `Mixte` | Intermédiaire |
| Peupleraie | `tfv` = `Peupleraie` ou essence `Peuplier` | Combustible fin, souvent riverain |
| Lande / herbacée | `tfv` = `Lande` ou `Formation herbacée` | Allumage rapide, propagation de surface |
| Forêt sans couvert | `Forêt fermée sans couvert arboré` | Contexte, moins de fuel |

Variables produites (fractions de surface du carreau) :

```
foret_frac          = surface forêt / surface carreau
resineux_frac       = surface résineux / surface carreau
feuillus_frac       = ...
mixte_frac          = ...
peupleraie_frac     = ...
lande_frac          = lande + formation herbacée
foret_fermee_frac   = forêt fermée (continuité de houppiers)
foret_ouverte_frac  = forêt ouverte
foret_sans_couvert_frac = forêt sans couvert arboré (coupe, régénération)
pin_frac            = pins (Pin maritime en Gironde)
```

### 2.2 Continuité et fragmentation

Un massif compact se comporte différemment d'un bois isolé. Deux variables :

1. **Voisinage 3×3** (`foret_frac_1km`) : moyenne de `foret_frac` sur le
   carreau et ses 8 voisins (≈ 2 km). Capture l'effet de masse.
2. **Densité de lisière** (`lisiere_m_ha`) : longueur de frontière
   forêt/non-forêt par hectare, calculée sur le raster 25 m :

```
lisiere_m_ha = (nombre de transitions forêt ↔ non-forêt × 25 m) / surface_ha
```

Une valeur élevée = massif fragmenté, beaucoup d'interfaces ; une valeur
faible = cœur de massif. Les deux peuvent augmenter le risque selon le
mécanisme (allumage vs propagation), d'où l'intérêt de laisser le modèle
apprendre la forme de la relation.

### 2.3 Relief

À partir du MNT Copernicus 30 m, reprojeté à 25 m :

```
pente = atan(sqrt((∂z/∂x)² + (∂z/∂y)²))
```

Variables : `alt_moy_m`, `alt_min_m`, `alt_max_m`, `alt_std_m`,
`pente_moy_deg`, `pente_max_deg`, `frac_pente_sup15`, `frac_pente_sup25`.

La pente influence la vitesse de propagation (le feu monte plus vite) et la
difficulté d'accès. En Gironde, le relief est faible : `pente_max_deg` et
`alt_std_m` resteront souvent proches de 0, ce qui est attendu.

### 2.4 Ce qu'on ne met pas (V1)

- **MNS LiDAR HD** : structure verticale, hauteur de canopée, biomasse.
  Excellent pour la V2, mais lourd à ingérer.
- **Humidité de la végétation satellite** (NDMI/Sentinel-2) : utile, mais
  nécessite une série temporelle cloud-free et un décalage de plusieurs
  jours. À ajouter en V2 avec un lag explicite.
- **Historique de feux** : risque de fuite et de biais de suppression
  (les zones qui ont brûlé sont mieux surveillées). À traiter séparément.

---

## 3. Pilier pression humaine

### 3.1 Interface habitat-forêt (WUI)

Définition opérationnelle : **habitat situé à moins de 200 m d'une zone
forestière**. Calcul raster :

```
forest_200m = dilatation(forest_mask, 200 m)
wui_mask    = habitat_mask AND forest_200m
wui_frac    = surface(wui_mask) / surface(carreau)
part_habitat_wui = surface(wui_mask) / surface(habitat_mask)
```

`habitat_mask` vient de `BDTOPO_V3:zone_d_habitation` (tissu urbain,
habitat rural, zones d'activité). Le WUI est un proxy : il ne remplace pas
un calcul bâtiment par bâtiment, mais il capture l'essentiel de l'interface
où se produisent la majorité des départs d'origine humaine.

### 3.2 Routes et trafic

Trois idées distinctes :

1. **Densité d'accès** : plus il y a de routes, plus il y a de passages,
   de mégots, de véhicules, d'activités.
2. **Trafic** : une nationale à 50 000 véh/j n'a pas le même risque qu'une
   voie communale à 200 véh/j.
3. **Pistes DFCI** : accès des secours, mais aussi fréquentation (chasse,
   promenade, travaux).

Variables :

```
route_km          = Σ longueur des tronçons du carreau
route_km_km2      = route_km / surface_km2
route_principale_km = autoroutes + nationales
route_dfci_km     = pistes DFCI
route_ponderee_km = Σ longueur × poids
                    (1,0 autoroute ; 0,8 nationale ; 0,5 départementale ;
                     0,2 communale ; 0,1 piste DFCI)
distance_route_principale_m = distance du centroïde à l'axe principal
tmja_max          = trafic max observé sur le carreau
tmja_moyen_pondere = Σ(longueur × TMJA) / Σ(longueur)
exposition_tmja   = Σ(longueur_km × TMJA) / 1000
```

Le TMJA ouvert ne couvre que le **réseau routier national**. Pour les
routes départementales, on utilise la densité routière et la classe de voie
comme proxy. Une V2 peut intégrer les comptages des Conseils
départementaux.

### 3.3 Agriculture et interfaces

`agri_frac` (RPG) mesure la part de parcelles agricoles. L'intérêt est
double :

- les cultures sont généralement **moins inflammables** que la forêt ;
- mais les interfaces cultures/forêt et les travaux agricoles (écobuage,
  machines) sont des sources d'ignition.

On ajoute `agri_frac_1km` pour capter la mosaïque agricole à l'échelle du
massif. Le modèle apprendra le signe, qui peut être non linéaire.

### 3.4 Saisonnalité et calendrier

Variables dynamiques simples, à ajouter dans 03 :

- `jour_annee_sin`, `jour_annee_cos` (saisonnalité continue) ;
- `weekend`, `jours_feries` (pic de fréquentation) ;
- `vacances_scolaires` (optionnel, zone A/B/C) ;
- `chasse_ouverte` (optionnel, calendrier départemental).

Ces variables sont connues à l'avance : aucun risque de fuite.

---

## 4. Tableau récapitulatif des features statiques

| Famille | Variables | Source | Signe attendu (départ) |
|---|---|---|---|
| Forêt | `foret_frac`, `foret_frac_1km` | BD Forêt V2 | + |
| Essence | `resineux_frac`, `pin_frac` | BD Forêt V2 | ++ |
| Essence | `feuillus_frac`, `peupleraie_frac` | BD Forêt V2 | + / variable |
| Continent | `mixte_frac`, `foret_fermee_frac` | BD Forêt V2 | + |
| Coupe | `foret_sans_couvert_frac` | BD Forêt V2 | − (peu de fuel) |
| Fragmentation | `lisiere_m_ha` | BD Forêt V2 raster | variable |
| Fuel fin | `lande_frac` | BD Forêt V2 | + |
| Relief | `pente_moy_deg`, `pente_max_deg` | Copernicus DEM | + (propagation) |
| Relief | `frac_pente_sup15`, `frac_pente_sup25` | Copernicus DEM | + |
| Habitat | `habitat_frac` | BD TOPO | + |
| Interface | `wui_frac`, `part_habitat_wui` | BD TOPO + forêt | ++ |
| Routes | `route_km_km2`, `route_ponderee_km` | BD TOPO | + |
| Trafic | `tmja_max`, `exposition_tmja` | TMJA | + |
| Accès | `route_dfci_km` | BD TOPO | + |
| Distance | `distance_route_principale_m` | BD TOPO | − |
| Agriculture | `agri_frac`, `agri_frac_1km` | RPG | variable |

Ces signes sont des **attendus métier**, pas des contraintes. Le modèle peut
les contredire ; c'est justement ce qu'on vérifie avec SHAP. Une contradiction
forte (ex. `wui_frac` associé négativement) doit déclencher une enquête :
proxy inversé, fuite, ou effet de confusion avec l'urbain.

---

## 5. Normalisation et valeurs manquantes

- Les fractions sont dans `[0, 1]`, bornées après calcul.
- Les compteurs (routes, TMJA) subissent `log1p` avant les modèles
  linéaires ; les arbres n'en ont pas besoin.
- Les modalités manquantes sont imputées par la médiane du **train** pour la
  régression logistique ; LightGBM/XGBoost gèrent nativement les NaN.
- Les variables catégorielles (`code_insee`, `saison`) ne sont pas utilisées
  comme features brutes dans la V1 (risque de sur-apprentissage spatial).
  On peut ajouter des effets aléatoires par commune en V2.
- Toute transformation ajustée (percentiles, moyennes, encodeurs) est
  **fit sur le train uniquement**.
