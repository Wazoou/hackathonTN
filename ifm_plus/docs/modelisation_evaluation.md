# Modélisation et évaluation

Deux approches sont développées en parallèle :

- **A — score composite expert** : 0–100, transparent, utilisable sans ML ;
- **B — modèle supervisé** : probabilité calibrée, plus performant, expliqué
  par SHAP.

Les deux sont évaluées sur le **même découpage temporel** et comparées à
l'IFM brut.

---

## 1. Approche A — score composite expert (baseline interprétable)

### 1.1 Principe

Chaque pilier produit un sous-score 0–100, obtenu en normalisant ses
indicateurs par leur **CDF empirique sur la période d'entraînement** :

```
pct(x) = 100 × F_train(x)
```

où `F_train` est la fonction de répartition empirique (ou une interpolation
linéaire entre quantiles). On évite ainsi les seuils arbitraires et on rend
les sous-scores comparables entre variables d'unités différentes.

### 1.2 Sous-scores

**Météo** (à partir des sous-indices, pas seulement du FWI) :

```
S_meteo = 0,35·pct(FWI) + 0,25·pct(FFMC) + 0,20·pct(DC) + 0,20·pct(ISI)
```

Variante « sécheresse de saison » :

```
S_meteo_secheresse = 0,30·pct(DC) + 0,25·pct(BUI) + 0,25·pct(DMC) + 0,20·pct(FFMC)
```

**Combustible & relief** :

```
S_combustible = 100 × (0,40·resineux_frac
                     + 0,25·foret_frac
                     + 0,15·pct(lisiere_m_ha)
                     + 0,10·pct(pente_moy_deg)
                     + 0,10·pin_frac)
```

**Pression humaine** :

```
S_humain = 100 × (0,40·pct(wui_frac)
                + 0,25·pct(route_ponderee_km)
                + 0,20·pct(tmja_max)
                + 0,15·pct(agri_frac))
```

Les poids ci-dessus sont un **dire d'expert de départ**, pas une vérité. Ils
sont documentés, versionnés et testés en sensibilité.

### 1.3 Agrégation

Version additive (par défaut) :

```
IFM+ = 0,45·S_meteo + 0,35·S_combustible + 0,20·S_humain
```

Version multiplicative (facteurs limitants) :

```
IFM+ = S_meteo × (0,50 + 0,50·S_combustible/100)
                × (0,60 + 0,40·S_humain/100)
```

La version multiplicative traduit l'idée qu'un combustible sec ne sert à
rien sans conditions météo, et inversement. Elle est plus conservative :
un pilier faible tire le score vers le bas.

### 1.4 Calibration en probabilité

Le score 0–100 n'est pas une probabilité. Pour comparer à l'IFM et calculer
un Brier score, on apprend une **calibration monotone** sur le train :

- régression logistique `feu_depart ~ logit(IFM+/100)` (2 paramètres) ;
- ou isotonic regression, plus souple mais à surveiller (sur-apprentissage
  possible avec peu de positifs).

On vérifie la monotonie et on conserve la courbe de calibration.

### 1.5 Sensibilité

- Grille de poids sur le simplexe (pas de 0,05) : mesurer la stabilité du
  classement (Spearman, Recall@Top5%) ;
- comparaison additif vs multiplicatif ;
- retrait d'un pilier (ablation) : météo seule, combustible seul, humain seul.

Le score expert sert de **plancher de performance** et de langage commun
avec les SDIS. Le ML doit le battre pour justifier sa complexité.

---

## 2. Approche B — modèle supervisé

### 2.1 Cible et modèle

Cible binaire `feu_depart ∈ {0, 1}`. Trois modèles :

| Modèle | Rôle |
|---|---|
| Régression logistique | baseline linéaire, interprétable, vérifie que le signal est additif |
| LightGBM | modèle principal (rapide, NaN natif, SHAP exact) |
| XGBoost | contrôle de robustesse |

LightGBM/XGBoost sont adaptés : relations non linéaires, interactions
(FWI × combustible), données manquantes, millions de lignes.

Hyperparamètres de départ (à ajuster sur 2018–2022) :

```
objective      = binary
learning_rate  = 0.03
num_leaves     = 31
max_depth      = 6
min_data_in_leaf = 200
feature_fraction = 0.8
bagging_fraction = 0.8
bagging_freq   = 1
lambda_l2      = 1.0
n_estimators   = 2000 (early stopping sur la validation)
```

Avec ~2 000 positifs et ~2 M de lignes, `min_data_in_leaf` élevé et une
profondeur modérée limitent le sur-apprentissage.

### 2.2 Déséquilibre extrême

Ordre de grandeur : en Gironde, 1 000–5 000 feux pour ~2 M de couples
carreau × jour, soit un taux de positifs de l'ordre de **0,05 % à 0,2 %**.
À l'échelle France (139 842 carreaux × 6 saisons ≈ 102 M de couples), le taux
descend plutôt vers **0,01 % à 0,05 %** : le sous-échantillonnage des négatifs
devient indispensable.

Trois leviers combinés :

1. **Pondération** : `scale_pos_weight = n_négatifs / n_positifs` (LightGBM)
   ou `scale_pos_weight` (XGBoost). Simple, mais change l'échelle des
   probabilités.
2. **Sous-échantillonnage des négatifs** : conserver **tous** les positifs
   et tirer 10 à 50 négatifs par positif, stratifié par date et par
   département. Réduit le temps d'entraînement et équilibre le gradient.
   Les négatifs « faciles » (cœur de massif en hiver) sont sous-représentés,
   ce qui peut améliorer le rappel sur les cas difficiles.
3. **Correction de probabilité** après sous-échantillonnage. Si le taux de
   positifs dans l'échantillon d'entraînement est `π_s` et le taux réel
   `π`, on corrige les odds :

```
odds_corrigé = odds_modèle × (π / (1-π)) / (π_s / (1-π_s))
p_calibrée   = odds_corrigé / (1 + odds_corrigé)
```

On vérifie ensuite la calibration sur la validation **non sous-échantillonnée**.

**Alternative recommandée en V2** : modèle de comptage (Poisson ou binomial
négatif) du nombre de feux par carreau × jour, puis
`P(feu ≥ 1) = 1 − exp(−λ)`. Le comptage exploite mieux l'information
« plusieurs feux le même jour » et évite de jeter des négatifs.

### 2.3 Validation croisée temporelle

Jamais de `train_test_split` aléatoire : les jours voisins sont corrélés
(météo persistante), et un split aléatoire donnerait des scores optimistes.

```
Fold 1 : train 2018–2019  → val 2020
Fold 2 : train 2018–2020  → val 2021
Fold 3 : train 2018–2021  → val 2022
Test final : 2023 (ouvert une seule fois)
```

- **Purge** : retirer les 14 premiers jours de chaque bloc de validation
  (durée maximale des lags) pour éviter que les features du début de bloc
  utilisent la fin du bloc précédent.
- **Embargo** : optionnel, 7 jours après la fin du train, si l'on craint une
  autocorrélation résiduelle.
- La recherche d'hyperparamètres se fait sur les folds 1–3 ; le test 2023
  n'est utilisé que pour le rapport final.
- **Échelle France** : les mêmes folds temporels s'appliquent à tous les
  départements (on ne mélange jamais 2022 et 2023). En complément, prévoir un
  **holdout spatial** de quelques départements (par exemple un bloc
  atlantique 33/40 et un bloc méditerranéen 13/83/34) pour mesurer la
  généralisation à des massifs non vus ; sans cela, un modèle national peut
  surtout apprendre les particularités des massifs présents dans le train.
  Le sous-échantillonnage des négatifs se fait **dans chaque fold** et
  **par département**, jamais avant le découpage.

### 2.4 Anti-leakage — règles opérationnelles

1. Trier par `(id_carreau_dfci, date)` avant tout `shift`/`rolling`.
2. Aucun `bfill`, aucun `interpolate` qui regarde le futur.
3. Les imputateurs, scalers, percentiles et encodeurs sont `fit` sur le
   train du fold, puis `transform` sur la validation.
4. Pas de feature construite à partir de `feu_depart`, `surface_ha`,
   `cause`, `heure_depart`.
5. Pas de feature « nombre de feux dans le carreau l'été dernier » en V1.
   Si elle est ajoutée, elle doit être calculée avec `shift(1)` et uniquement
   sur les années passées.
6. Les variables statiques sont identiques sur toutes les dates : pas de
   fuite temporelle, mais une limite de millésime (documentée).
7. Le jeu de test 2023 est physiquement séparé (fichiers Parquet
   `year=2023`) et n'est chargé qu'à l'étape 07.

### 2.5 Baseline et ablations

Toujours comparer :

| Modèle | Features |
|---|---|
| IFM brut | `fwi` seul |
| Climatologie | moyenne de `feu_depart` par carreau (ou par mois) |
| Météo seule | indices + lags |
| Statique seule | combustible + relief + humain |
| IFM+ expert | score composite |
| IFM+ ML | toutes les features |

Cela permet de dire **d'où vient le gain** : météo mieux exploitée,
combustible, ou pression humaine.

---

## 3. Évaluation

### 3.1 Métriques adaptées aux événements rares

| Métrique | Définition | Pourquoi |
|---|---|---|
| **PR-AUC / Average Precision** | aire sous la courbe précision–rappel | Métrique principale : la classe positive est rare, la ROC-AUC est trop optimiste |
| ROC-AUC | aire sous la courbe ROC | Comparable à la littérature, mais secondaire |
| **Recall@Top5%** | part des feux capturés dans les 5 % de carreaux les plus risqués | Traduit une capacité opérationnelle (patrouilles) |
| **Lift@5%** | `Recall@5% / 0,05` | Combien de fois mieux que le hasard |
| Precision@k | précision dans les k alertes les plus fortes | Utile pour un SDIS avec une capacité limitée |
| Brier score | erreur quadratique moyenne des probabilités | Calibration |
| Log loss | idem, plus sensible aux extrêmes | Comparaison de modèles |
| Courbe de calibration | `P(feu=1 \| score)` observé par décile | Confiance dans les probabilités |
| Capture@budget | feux capturés si on surveille N carreaux/jour | Décision opérationnelle |

Le **Recall@Top5%** doit être calculé **par jour** puis moyenné (et non sur
l'ensemble du test), sinon les jours à forte activité dominent.

Exemple de lecture : « Avec 5 % des carreaux (≈ 138 carreaux/jour en
Gironde), IFM+ capte 62 % des départs, contre 38 % pour l'IFM brut. »

### 3.2 Démontrer statistiquement que IFM+ > IFM

Trois niveaux de preuve :

1. **Bootstrap par blocs de dates** (recommandé) : rééchantillonner les
   journées du test avec remise (1 000 répétitions), recalculer ΔAP et
   ΔRecall@5%, produire un intervalle de confiance à 95 %. Le bootstrap par
   jour respecte l'autocorrélation intra-journée.
2. **Test de DeLong** pour comparer deux ROC-AUC sur des prédictions
   appariées (même jeu de test). Implémentation via `scikit-learn`/`scipy`
   ou une fonction dédiée.
3. **Test de permutation apparié** pour l'AP : permuter les scores IFM+ et
   IFM entre carreaux **au sein de chaque journée**, recalculer ΔAP,
   obtenir une p-value empirique. Cette permutation préserve la structure
   journalière et teste l'apport informatif du classement.

Compléments :

- **McNemar** à seuil opérationnel fixe (même nombre d'alertes/jour) ;
- comparaison à **budget d'alertes égal** (top-k) plutôt qu'à seuil égal,
  car les deux scores n'ont pas la même distribution ;
- correction de multiplicité si l'on teste plusieurs métriques
  (Holm–Bonferroni).

Un gain n'est considéré comme démontré que si :

- l'IC 95 % de ΔAP exclut 0 ;
- le gain se retrouve sur les deux années de test (2022 et 2023) ;
- le gain reste positif à budget d'alertes égal ;
- la calibration n'est pas dégradée.

### 3.3 Rapport de benchmark

Table type :

| Modèle | AP | ΔAP vs IFM | ROC-AUC | Recall@5% | Lift@5% | Brier |
|---|---|---|---|---|---|---|
| IFM brut | … | — | … | … | … | … |
| IFM+ expert | … | … | … | … | … | … |
| IFM+ LightGBM | … | … | … | … | … | … |

Avec IC bootstrap et p-values. Les chiffres doivent être reproductibles
(seed fixe, versions figées).

---

## 4. Interprétabilité SHAP

### 4.1 Global

- **TreeSHAP** sur LightGBM (exact, rapide) ;
- bar plot des importances moyennes `|SHAP|` ;
- beeswarm pour voir la direction des effets ;
- comparaison des rankings entre 2022 et 2023 (stabilité).

### 4.2 Dépendance et interactions

- dépendance SHAP de `fwi`, `wui_frac`, `pin_frac`, `pente_moy_deg` ;
- interaction SHAP `fwi × resineux_frac` et `fwi × wui_frac` ;
- attention aux corrélations : `foret_frac` et `foret_frac_1km` portent une
  information proche ; SHAP répartit l'effet entre elles. Ne pas conclure
  hâtivement qu'une variable « ne sert à rien ».

### 4.3 Local — pour les SDIS

Pour un carreau × jour donné, produire :

- une **waterfall** : contribution de chaque feature au score, en points de
  probabilité ou en log-odds ;
- une phrase automatique : « Risque élevé : FWI au 98ᵉ percentile, pinède
  dense (72 % du carreau), interface habitat-forêt forte (WUI 18 %),
  proximité d'une nationale à 30 000 véh/j » ;
- une carte des contributions agrégées par massif/commune.

### 4.4 Précautions d'interprétation

- SHAP explique **le modèle**, pas la causalité physique ;
- les valeurs SHAP sont relatives à une baseline (moyenne du train) : le
  choix de la baseline doit être documenté ;
- sur des variables corrélées, les attributions sont instables : utiliser
  des groupes de features (combustible, météo, humain) pour une lecture
  robuste ;
- vérifier que les effets appris sont plausibles (FWI ↑ → risque ↑, WUI ↑ →
  risque ↑) et investiguer les inversions.

---

## 5. Reproductibilité

- `random_state` fixé (42) partout ;
- versions figées dans `requirements.txt` et `requirements-ml.txt` ;
- manifeste d'acquisition (URL, SHA-256, date) ;
- splits temporels écrits dans la table (`split`) ;
- seeds et hyperparamètres dans un fichier `config_model.yaml` ;
- rapport final généré par `07_evaluate.py`, pas à la main.

---

## 6. Pièges à éviter

1. **Split aléatoire** : scores artificiellement élevés, modèle inutilisable
   en production.
2. **Sous-échantillonnage sans recalibration** : probabilités trop hautes,
   Brier et calibration faux.
3. **Optimiser l'accuracy** : un modèle qui prédit toujours 0 a 99,9 %
   d'accuracy et aucun intérêt.
4. **Fuite par les lags** : un `rolling` mal aligné peut inclure le jour du
   feu ou le lendemain.
5. **Fuite par la cible** : `surface_ha`, `cause`, `heure_depart` sont des
   conséquences du feu, pas des features.
6. **Comparer IFM et IFM+ à seuil égal** : les échelles ne sont pas
   comparables ; comparer à budget d'alertes égal.
7. **Oublier les jours sans feu** : la table doit contenir les zéros, sinon
   le modèle apprend une prevalence artificielle.
8. **Surinterpréter SHAP** : une contribution n'est pas une cause.
