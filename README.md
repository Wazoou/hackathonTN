# 🔥 Pyro-Watch

Détection précoce de feux de forêt à partir de caméras : hackathon Open Data University,
défi « Prévenir et détecter les feux de forêt » (Pyronear × Latitudes).

Voir **[ROADMAP.md](ROADMAP.md)** pour l’état du projet et les prochaines étapes.
Pour retrouver exactement les données de la présentation sur une autre machine,
suivre **[DONNEES_EQUIPE.md](DONNEES_EQUIPE.md)** avec l’archive partagée par le groupe.

## Carte des risques, archives françaises et timeline

Le dashboard s'ouvre sur **Carte des risques**. La couche BDIFF utilise les données
locales de `pyro-watch-risque-france-bdiff/risk-data` (96 départements et environ
140 000 mailles, modèle appris sur les incendies BDIFF 2006–2024). Dans Docker, ce dossier
est monté en lecture seule ; en lancement local, il est détecté automatiquement.
La variable `RISK_DIR` permet de choisir un autre dossier de données.
Le bouton **Webcam** donne accès aux flux YouTube géolocalisés et aux archives :
les webcams générées par l’annuaire apparaissent sur une carte interactive et un clic
sur un repère ouvre le lecteur du direct ; le mode **Archives enregistrées** conserve
la carte, la timeline et le lecteur Pyro-SDIS / webcams. Les manifestes d’archives restent indépendants ;
leur index commun conserve les chemins d’images, dates, sources, splits et annotations.
Les identifiants sont préfixés par la source pour éviter les collisions.
L’import actuel représente **12 252 images, 200 identifiants de caméras et 10 repères** :
6 départements Pyro-SDIS (losanges) et 4 webcams (ronds). La précision des coordonnées
est indiquée dans les infobulles et sous le lecteur.
Le filtre facultatif **Toutes les sources / Pyro-SDIS / Webcams** se trouve dans
**Période et sources**. Les annotations humaines de fumée restent
disponibles pour Pyro-SDIS ; les webcams sont non annotées et YOLO reste à connecter.
La navigation permet de passer entre **Carte des risques**, **Webcam**,
**Alerte simulée** et **Historique des incendies**. La carte des risques conserve
le maillage national, les scores experts et la régression BDIFF,
avec les réglages interactifs sans rechargement des données.
Les contours des 96 départements restent visibles au-dessus des mailles. Un clic
affiche une fiche départementale (effectif, médiane de la couche active et part de
mailles en classe élevée ou plus), avec un bouton **Explorer ce département**.
Les détails de la maille cliquée restent accessibles. Les contours IGN sont fournis
avec le code et simplifiés à 50 m uniquement pour l’affichage ; les géométries du
maillage et les calculs ne sont pas modifiés. Leur export peut être régénéré depuis
le cache IGN avec `ifm_plus/.venv/bin/python ml/build_department_boundaries.py`.
L’historique réunit les exports BDIFF 2006–2024 du dossier
`ifm_plus/data/raw/manual/bdiff/` et l’export 2025
`ifm_plus/data/raw/incendies/Incendies.csv`, sans compter deux fois les mêmes incendies.
Le curseur **Année** sélectionne l’année affichée ; le filtre de période permet
de voir toute l’année ou un mois, en combinaison avec la saison et la cause.
Ces commandes fonctionnent dans le navigateur, sans relancer Python ni recréer la carte.
Les cercles sont mis à jour pendant le déplacement du curseur ; le zoom et la position
sont conservés. Les archives sont chargées une fois à l’ouverture de l’onglet.
Les cercles rouges indiquent les communes
touchées, avec une position approximative dans chaque commune (ou département si le code
communal manque). La carte se limite à la France métropolitaine ; les filtres permettent
de parcourir les mois, les saisons et les causes. Le fond OpenStreetMap est le même
que sur la carte Webcam. Le dossier des exports est monté en lecture seule dans Docker.
Pour récupérer l’export public 2025 :

```bash
ifm_plus/.venv/bin/python ml/download_bdiff.py --debut 2025 --fin 2025 --out ifm_plus/data/raw/incendies
cp ifm_plus/data/raw/incendies/incendies_2025_2025.csv ifm_plus/data/raw/incendies/Incendies.csv
```

Ce CSV est local et reste hors Git. Sans ce fichier, l’onglet affiche une indication
sur les données manquantes si aucun autre export n’est disponible. Les années proposées
correspondent aux CSV présents. Pour récupérer aussi 2006–2024, utilisez la commande
`ml/download_bdiff.py --out ifm_plus/data/raw/manual/bdiff` avec le Python du projet.
Les deux dossiers sont montés dans Docker. Les coordonnées approximatives des communes
proviennent du cache IGN ADMIN EXPRESS COG CARTO (Licence Ouverte 2.0) et peuvent être
régénérées avec `ifm_plus/.venv/bin/python ml/build_fire_centroids.py`. Les anciens codes
non localisés sont représentés au centre du département, avec cette précision indiquée
dans l’infobulle et dans un compteur, ou signalés comme non cartographiés.

La jauge représente le temps de façon continue, avec un histogramme de disponibilité et un
curseur déplaçable. La jauge, les compteurs et la carte Leaflet sont conservés dans un même
composant navigateur. Pendant le glissement, les points sont recolorés sur place, sans appel
Python ni reconstruction de la carte ; le zoom et le déplacement restent conservés.
Au relâchement, la date est transmise à Streamlit pour synchroniser le lecteur d'images.
Une fenêtre centrée sur le curseur est réglable de 15 minutes à 30 jours :
un point devient vert s'il existe au moins une image dans cette fenêtre, gris sinon.
Les compteurs et les infobulles indiquent les images réellement présentes, sans interpoler
les trous entre deux prises de vue. Les boutons **Données** passent à la date source précédente
ou suivante. Le calendrier permet de filtrer une période plus courte.

Sur grand écran, la carte claire et le lecteur sont côte à côte ; sur petit écran,
ils s’empilent. Les boutons des parcours ouvrent directement les exemples de Fréjus,
Saména, du Pic Saint-Loup, de Canéjan ou de Pyro-SDIS. **Toute la période** rétablit
les dates complètes pour les sources choisies.

Le **zoom temporel** agrandit l’échelle autour du curseur, sans modifier la fenêtre
de disponibilité ni recharger la carte. **Tout voir** rétablit l’échelle de la période
filtrée. **Recentrer** affiche tous les repères ; **Point sélectionné** centre la carte
sur la sélection. La molette et le pavé tactile permettent toujours de zoomer.

Le lecteur propose une lecture pas à pas ou automatique. Pour les panoramas très larges,
le cadrage permet de passer du détail droit (affiché initialement) au panorama complet,
au centre ou à gauche. Ce recadrage d’affichage ne modifie aucun fichier source.
Les informations de localisation et de provenance se trouvent dans **Sources et précisions**.

```bash
python3 -m venv .venv
.venv/bin/pip install pyarrow requests pillow
.venv/bin/python ml/import_archives.py --out archives-data --revision ebfc02d0cba7f7dfe0623d13bcf0f0aa8a38e3ee
docker compose up --build -d
```

L'import télécharge tous les fichiers Parquet (`train` et `val`, environ 1,32 Go pour la v2).
La révision `main` est résolue en identifiant de commit précis avant les téléchargements.
Les fichiers sont mis en cache dans `archives-data/parquet/`, et le manifeste est remplacé
seulement à la fin d'un import réussi. L'application reste sur l'ancien import pendant l'opération.
Seules les caméras françaises identifiables sont affichées : partenaires SDIS/SIS/Force avec
numéro de département, ainsi que les caméras ENGIE de Salaunes (Gironde).
Les autres partenaires restent comptabilisés dans les exclusions du manifeste.
Un fichier local peut être fourni avec `--parquet CHEMIN --split val` (ou `train`).
Le manifeste conserve les identifiants source, les dates, les annotations, les noms des images
et le split de chaque image, les effectifs et l'empreinte SHA-256 de chaque Parquet.
Les images restent locales dans `archives-data/` (ignoré par Git).
Les splits `train` et `val` sont réunis pour l’exploration ; leur origine reste conservée
dans les métadonnées et affichée sous les images Pyro-SDIS.

**Géographie :** le dataset ne donne pas les coordonnées des caméras. La carte affiche donc
un point **par département partenaire**, situé au centre de sa commune la plus peuplée
(source : API géographique de l'État ; pour la Gironde, un repère approximatif de Bordeaux
sert de secours si l'API est indisponible). Ce sont des repères territoriaux indicatifs, jamais
des emplacements de caméras. Le point ouvre le choix des caméras associées au partenaire.

**Temps :** le fuseau des dates source n'est pas spécifié et n'est pas converti. Une interruption
de plus de 30 minutes sépare les séquences. Une caméra sans image dans la fenêtre observée est
signalée ; le lecteur permet alors de choisir explicitement une autre séquence. Le replay
avance à une image par seconde avec l'heure source et les intervalles réels visibles ; aucune
interpolation ne comble les images absentes. Le dataset n'est pas une archive continue
ni un catalogue exhaustif des incendies français. Il ne suffit pas à garantir une évaluation
indépendante d'un modèle Pyronear préentraîné.

Vérifications : `python -m unittest discover -s tests -p 'test_*.py'` ; pour l'interface après import,
`docker compose exec -T dashboard python - < tests/check_archive_ui.py`.

## Échantillon de webcams pour la présentation

La carte commune inclut 29 images de webcams locales, sans prédictions YOLO :

| Caméra | Dates | Images | Usage |
|---|---|---:|---|
| Fréjus (Skaping / Estérel) | 7 juillet 2025, 09 h 01–13 h 01 | 9 | Incendie et panache documentés par [AtmoSud](https://www.atmosud.org/actualite/incendie-frejus-le-7-juillet-2025) ; exemple initial à 11 h 31 |
| Marseille-Saména (Infoclimat) | 4–5 août 2020 | 8 | Avant/après un panache à l’horizon ; lien avec Martigues à confirmer |
| Saint-Martin-de-Londres (Infoclimat) | 7 juillet 2025 | 6 | Paysage et nuages de comparaison |
| Canéjan (Infoclimat) | 13 juillet 2022 | 6 | Lisière de pins de comparaison pendant un épisode régional de feux |

Import reproductible (29 URL fixes, aucune collecte en continu) :

```bash
pip install requests pillow
python ml/import_webcam_demo.py --out archives-data
docker compose up --build -d --no-deps dashboard
```

Le manifeste `archives-data/manifest-webcams.json` conserve les URL, crédits, coordonnées
publiées, tailles, SHA-256 et limites d’interprétation. Les images sont exclues de Git.
L'accès constaté sans clé ne vaut pas licence ouverte ; les conditions de redistribution
restent à établir. L’import utilise son cache local lors des exécutions suivantes.

Un clic sur un repère sélectionne sa caméra (ou les caméras du département) et rejoint
une date disponible lorsque nécessaire, sans isoler automatiquement sa source.
La timeline couvre initialement toutes les dates, avec le curseur sur Fréjus à 11 h 31 ;
**Explorer un exemple** propose les webcams et un exemple Pyro-SDIS annoté, et
resserre la période sur les images correspondantes. **Affiner la période et les sources**
permet de réélargir les dates ou de filtrer une source. Les repères restent visibles
même sans données dans la période ; un clic permet de rejoindre leurs archives.
Le fond sombre et le zoom molette sont conservés. Vert signifie « images disponibles »,
pas « incendie détecté ». Les dates Infoclimat sont les créneaux d’archive : l’heure
exacte peut différer et apparaît dans l’image. Les images espacées sont regroupées
manuellement pour le replay, sans inventer d’images dans les intervalles.

Les vues de comparaison ne sont pas des annotations négatives de référence.
Les quatre points sont les positions publiées des webcams ; l’implantation historique
n’est pas vérifiée. Les losanges Pyro-SDIS sont des repères départementaux, jamais
des positions de caméras. Les dates des sources ne sont pas converties : le fuseau
Pyro-SDIS est inconnu et la correspondance exacte des heures entre sources n’est pas garantie.

Vérification du parcours après import :
`docker compose exec -T dashboard python - < tests/check_webcam_ui.py`.

## Annuaire de webcams et de flux vidéo

Ajoutez une ligne par webcam dans `camera-data\cameras.csv` avec son URL et sa ville :

```csv
url_youtube;ville
https://www.youtube.com/watch?v=VIDEO_ID;Lyon
https://youtu.be/VIDEO_ID;Biarritz
https://opencctv.org/still/1.jpg;Grenoble
```

Puis, depuis la racine du dépôt, lancez :

```powershell
python ml\build_camera_directory.py
```

Le script accepte les séparateurs virgule ou point-virgule, géolocalise les villes et place
chaque webcam dans une maille du maillage des risques. À chaque exécution, il recrée
`camera-data\camera.json` avec exactement les webcams du CSV : ajouter ou supprimer une
ligne se répercute sur la carte. Un CSV sans webcam vide aussi l’annuaire. Une connexion
Internet est nécessaire pour géolocaliser les villes ; aucune clé YouTube n’est requise.

Le dashboard lit le JSON depuis `camera-data` (également monté dans Docker) ; ouvrez
**Webcam → Webcams**, puis cliquez sur un repère. Les URL YouTube, les images JPG/PNG
(instantanés actualisés périodiquement), les vidéos et flux directs reconnus sont affichés
dans le dashboard. Les pages web de diffuseurs qui ne sont pas des flux vidéo directs
s'ouvrent sur leur site, car certaines interdisent l'intégration. Les archives restent
disponibles sous **Archives enregistrées**.

## 🔥 IFM+ et carte de risque de départ de feu (prévention)

Le dossier [`ifm_plus/`](ifm_plus/README.md) contient le pipeline de modélisation du risque de départ
de feu à la maille DFCI 2 km : acquisition data.gouv.fr / IGN / Copernicus, features
combustible–relief–pression humaine, puis modèles et benchmark contre l'IFM. Il fonctionne sur un
département pilote **ou sur toute la France métropolitaine** (96 départements, traitement département
par département puis assemblage national). Voir le [README du pipeline](ifm_plus/README.md) et la
[méthodologie](ifm_plus/docs/modelisation_evaluation.md).

Le mode **Carte de risque** du dashboard en affiche le résultat pour chaque carreau de 7 départements :
Alpes-Maritimes (06), Ardèche (07), Bouches-du-Rhône (13), Gironde (33), Hérault (34), Landes (40)
et Var (83), soit 12 710 carreaux. On peut afficher un département ou **Tous les départements**.
Il s'appuie sur les features statiques d'`ifm_plus/` : végétation (BD Forêt V2), relief (MNT Copernicus)
et pression humaine (BD TOPO, trafic, RPG). Le volet est **statique** : aucune couche n’intègre la météo
(étape suivante : IFM/FWI quotidien Copernicus, étape 03 du pipeline).

| Couche | Contenu |
|---|---|
| **Probabilité annuelle de départ (BDIFF)** | Probabilité qu’au moins un feu de forêt démarre dans l’année dans le carreau, apprise sur l’historique BDIFF (France : médiane 0,9 %, 90 % des mailles sous 4,3 %, maximum 32 % à Lacanau). Couche affichée par défaut quand elle est disponible. Classes : < 2 %, 2–5 %, 5–10 %, 10–20 %, ≥ 20 %. |
| **Score de risque (expert)** | Score 0–100 à poids fixés à dire d’expert, combinaison multiplicative ou additive réglable. |
| **Combustible et relief** | Sous-score 0–100 : résineux 40 %, forêt 25 %, lisières 15 %, pente 10 %, pins 10 %. |
| **Pression humaine** | Sous-score 0–100 : habitat à moins de 200 m de la forêt (WUI) 40 %, routes pondérées 25 %, trafic 20 %, agriculture 15 %. |

### Score expert

Les poids viennent de `ifm_plus/docs/modelisation_evaluation.md` ; il n’existe pas de pondération
officielle de ce type en France (l’IFM officiel est purement météorologique).
Par défaut, `score = combustible × (0,6 + 0,4 × humain / 100)` : sans végétation, le risque reste nul,
et la fréquentation augmente le score d’un massif. Le mode additif permet de régler le poids des piliers.

Les indicateurs non fractionnaires sont convertis en rangs calculés sur **tous les départements
passés ensemble** au script (0 = valeur minimale, 1 = valeur maximale) : les scores sont comparables
entre ces départements, mais changent si l’on en ajoute un (relancer le script avec la liste complète).
Un carreau de frontière n’est gardé que dans le département qui en couvre la plus grande part.
Le score classe les carreaux entre eux ; ce n’est pas une probabilité.

### Probabilité apprise sur l’historique BDIFF

Une **régression logistique** apprend les poids à partir des feux de forêt BDIFF 2006–2024.
BDIFF localise chaque feu à la **commune**, pas au point : l’unité d’apprentissage est la
commune-année (1 si au moins un feu dans l’année), décrite par la moyenne des indicateurs du score
expert sur ses carreaux et par le logarithme de sa surface. Le modèle est ensuite appliqué à chaque
carreau, avec ses propres indicateurs et la surface d’un carreau.

**Modèle national** (96 départements, 33 373 communes, 48 203 feux rattachés, trafic exclu) :

| AUC (validation croisée) | Communes inconnues | Département inconnu |
|---|---:|---:|
| Régression logistique (8 indicateurs + surface) | **0,830** | **0,818** |
| Score expert + surface | 0,804 | 0,798 |
| Surface seule | 0,726 | 0,696 |

Coefficients (indicateurs 0–1) : lisières +1,9, résineux +0,8, pins +0,4, forêt +0,4,
WUI ≈ 0, pente −0,4, routes −1,1, agriculture −3,3, log(surface) +0,9. Le modèle retient surtout
l’opposition entre massifs forestiers fragmentés (beaucoup de lisières, résineux) et plaines agricoles
ou zones urbanisées. Une partie de l’AUC nationale vient du contraste entre régions : à l’intérieur
d’un même département, l’AUC médiane n’est que de 0,68 (quartiles 0,64–0,75 sur 81 départements
ayant au moins 20 communes-années avec feu).

**Pilote à 7 départements** (06, 07, 13, 33, 34, 40, 83 ; 18 088 feux) : AUC 0,757 (communes
inconnues) et 0,724 (département inconnu), contre 0,731 et 0,714 pour le score expert + surface.
Résineux +4,7 et pins −3,9 (très corrélés, effet net du pin ≈ +0,9), WUI +0,8, lisières +0,8,
agriculture −1,7. Les poids diffèrent du modèle national : ils dépendent de la zone d’apprentissage.

Limites : rattachement des carreaux et des feux à la commune (on suppose les carreaux d’une commune
semblables), communes trop petites pour contenir un centroïde de carreau ignorées (environ 4 % des feux
au niveau national), qualité de saisie BDIFF variable selon les départements, risque moyen sur l’année
sans météo. Un essai avec les points chauds satellite NASA FIRMS a été écarté : ils mêlent brûlages
agricoles et sites industriels, et ne prédisaient pas mieux que le hasard hors Gironde.

Les réglages de la carte nationale sont appliqués directement dans le navigateur : opacité,
couches, pondérations et départements ne rechargent plus les géométries. Voir le
[rapport de performances et de tests](docs/performances_carte_risque.md).

### Reproduire la carte

Pour afficher les mêmes données que l'équipe sans télécharger les sources brutes,
utilisez l'archive `pyro-watch-risque-france.tar.gz` : les commandes d'installation
et de vérification sont dans [DONNEES_EQUIPE.md](DONNEES_EQUIPE.md).

Pour la table nationale issue de l’acquisition bulk, joindre les indicateurs au maillage
par identifiant et calculer tous les départements ensemble :

```bash
ifm_plus/.venv/bin/python ml/build_static_risk.py \
  --features ifm_plus/data/processed/dfci_2km_features_france.parquet \
  --grid ifm_plus/data/processed/dfci_2km_grid_france_metro.parquet \
  --exclude tmja_max --out risk-data \
  --bdiff ifm_plus/data/raw/manual/bdiff   # régression logistique nationale (couche p_feu), ~1 min
docker compose up --build -d --no-deps dashboard
```

Ouvrir ensuite <http://localhost:8501/?view=risk>. Ce calcul couvre les 139 842 mailles
des 96 départements, sans météo. Le trafic mesuré est exclu car
il manque pour 99,1 % des mailles : les poids de pression humaine sont renormalisés
sur l’habitat proche des forêts, les routes et l’agriculture. Les exclusions, sources
et valeurs manquantes sont enregistrées dans les métadonnées, ainsi que les coefficients
et les AUC de la régression. Sans `--bdiff`, la couche de probabilité n’est pas produite.
L’export BDIFF se récupère avec `ml/download_bdiff.py` (voir ci-dessous).

Les fichiers produits (`risk-data/`, environ 8 Mo pour 7 départements, 75 Mo pour la France) sont ignorés par Git ; on peut aussi les partager
directement et les déposer à la racine du dépôt.

```bash
# 1. Features statiques (ifm_plus/) : 5 à 25 min et ~500 Mo par département
python3 -m venv ifm_plus/.venv
ifm_plus/.venv/bin/pip install -r ifm_plus/requirements.txt scikit-learn
cd ifm_plus
for d in 06 07 13 33 34 40 83; do
  .venv/bin/python scripts/01_download_data.py --departement $d --layers dfci,admin,forest,habitat,roads,rpg,tmja,dem
  .venv/bin/python scripts/02_build_static_features.py --departement $d
done
cd ..

# 2. Historique des feux BDIFF (France entière, 2006-2024, ~5 Mo)
ifm_plus/.venv/bin/python ml/download_bdiff.py --out ifm_plus/data/raw/manual/bdiff

# 3. Scores et probabilité par carreau -> risk-data/risque_statique_<dept>.geojson
#    Passer tous les départements en une fois pour des scores comparables.
ifm_plus/.venv/bin/python ml/build_static_risk.py \
  --features ifm_plus/data/processed/static_features_*.gpkg --out risk-data \
  --bdiff ifm_plus/data/raw/manual/bdiff

# 4. Dashboard
docker compose up --build -d --no-deps dashboard
```

`ml/download_bdiff.py` reproduit l’export CSV du portail https://bdiff.agriculture.gouv.fr/
(Licence Ouverte 2.0 ; 30 000 lignes maximum par export, d’où le découpage par années). Le serveur
envoie une chaîne de certificats incomplète : le script ajoute le certificat intermédiaire manquant,
sans désactiver la vérification TLS. Sans `--bdiff`, seule la partie score expert est produite.

Tests : `python -m unittest tests/test_static_risk.py` ; interface :
`docker compose exec -T dashboard python - < tests/check_risk_ui.py`.

## Architecture

```
 caméras (cam-1..3)                       api (FastAPI + SQLite)            dashboard (Streamlit)
 ┌──────────────────────┐  POST image    ┌──────────────────────┐   GET    ┌──────────────────────┐
 │ source -> détecteur  │ + détections   │ caméras, détections, │ <─────── │ carte, flux, alertes │
 │ (dummy | yolo)       │ ─────────────> │ logique d'alerte     │ ───────> │ confirmer / faux pos.│
 └──────────────────────┘                └──────────────────────┘  PATCH   └──────────────────────┘
```

| Dossier | Rôle |
|---|---|
| `api/` | Reçoit les images et les détections, crée une alerte après `MIN_CONSECUTIVE` images avec une confiance ≥ `CONF_THRESHOLD`. Doc interactive : http://localhost:8000/docs |
| `camera/` | Agent caméra (équivalent simplifié de `pyro-engine`). Sources : `synthetic`, un dossier d'images, une vidéo `.mp4`, un flux `rtsp://`, ou l'URL d'une image de webcam publique |
| `dashboard/` | Interface des pompiers : http://localhost:8501 (carte des archives, carte de risque, surveillance simulée) |
| `ml/` | Téléchargement du dataset `pyro-sdis`, évaluation et fine-tuning YOLO, import BDIFF et calcul de la carte de risque |

## Démarrage

Prérequis : Git et Docker avec le plugin Compose.

Pour la **carte avec les mêmes images que le groupe**, utiliser l’archive partagée
et les commandes de [DONNEES_EQUIPE.md](DONNEES_EQUIPE.md). Aucun téléchargement
Hugging Face, compte ou modèle n’est nécessaire pour consulter ces images.

```bash
# Depuis la racine du dépôt, après réception de l’archive
tar -xzf pyro-watch-images.tar.gz
docker compose up --build -d api dashboard
```

Ouvrir http://localhost:8501. La carte charge les deux manifestes sous `archives-data/`.
Si ce dossier est absent, l’interface explique qu’aucune archive n’est importée.
Les scripts d’import ci-dessus permettent de reconstruire les données depuis les sources,
mais l’archive partagée conserve exactement l’échantillon et les repères de la présentation.

Pour lancer aussi les agents et la **surveillance simulée**, on peut préparer leurs images :

```bash
python3 -m venv .venv
.venv/bin/pip install pyarrow requests
.venv/bin/python ml/pyro_sdis.py samples --out data/samples --cameras 3
docker compose up --build -d
```

`data/samples/` alimente les agents ; `archives-data/` alimente la carte historique.
Sans images dans `data/samples/`, les agents concernés utilisent des images synthétiques.
Par défaut, `DETECTOR=dummy` produit des détections factices. Elles ne doivent pas être
présentées comme des résultats YOLO. La carte historique n’exécute pas encore le détecteur.

### Passer au vrai modèle (phase 2)

```bash
cp .env.example .env
# dans .env : DETECTOR=yolo et INSTALL_YOLO=true
docker compose up --build    # 1er build long : installe torch en version CPU (~2 Go)
```

Le modèle Pyronear (`hf://pyronear/yolo11s_sensitive-detector/best.pt`) est téléchargé au premier
lancement dans `.cache/hf/`. Pour en utiliser un autre (après fine-tuning), changer `YOLO_WEIGHTS`
dans `.env`.

Vérifier que ça marche : `docker compose logs -f cam-1` doit afficher `Détecteur=YoloDetector`.

### Développement sans Docker

```bash
cd api && DATA_DIR=../data/api uvicorn app.main:app --reload
cd camera && SOURCE=../data/samples/cam-1 INTERVAL=2 python camera.py
cd dashboard && streamlit run app.py
```

## Données et modèles

- Dataset : [pyronear/pyro-sdis](https://huggingface.co/datasets/pyronear/pyro-sdis), 12 378 images, format YOLO, licence Apache 2.0
- Modèles : [huggingface.co/pyronear](https://huggingface.co/pyronear)
- Code Pyronear : [github.com/pyronear](https://github.com/pyronear) (`pyro-engine`, `pyro-api`, `pyro-train`, `pyro-openwebcams`)
