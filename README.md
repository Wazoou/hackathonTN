# 🔥 Pyro-Watch

Détection précoce de feux de forêt à partir de caméras : hackathon Open Data University,
défi « Prévenir et détecter les feux de forêt » (Pyronear × Latitudes).

Voir **[ROADMAP.md](ROADMAP.md)** pour l’état du projet et les prochaines étapes.
Pour retrouver exactement les données de la présentation sur une autre machine,
suivre **[DONNEES_EQUIPE.md](DONNEES_EQUIPE.md)** avec l’archive partagée par le groupe.

## Archives françaises et timeline

Le dashboard s'ouvre sur **Carte des archives** : Pyro-SDIS et les webcams partagent
une carte, une timeline et un lecteur. Les deux manifestes locaux restent indépendants ;
leur index commun conserve les chemins d’images, dates, sources, splits et annotations.
Les identifiants sont préfixés par la source pour éviter les collisions.
L’import actuel représente **12 252 images, 200 identifiants de caméras et 10 repères** :
6 départements Pyro-SDIS (losanges) et 4 webcams (ronds). La précision des coordonnées
est indiquée dans les infobulles et sous le lecteur.
Le filtre facultatif **Toutes les sources / Pyro-SDIS / Webcams** se trouve dans
**Période et sources**. Les annotations humaines de fumée restent
disponibles pour Pyro-SDIS ; les webcams sont non annotées et YOLO reste à connecter.
La surveillance simulée reste accessible dans le sélecteur de mode.

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

## Carte de risque statique (prévention, solution 1)

Le mode **Carte de risque** du dashboard colore chaque carreau DFCI de 2 km selon la
sensibilité du terrain au feu. Il réutilise les features statiques du pipeline IFM+
(branche `manon`, dossier `ifm_plus/`) et les formules de
`ifm_plus/docs/modelisation_evaluation.md` :

- **Combustible et relief** (0–100) : résineux 40 %, forêt 25 %, lisières 15 %, pente 10 %, pins 10 % ;
- **Pression humaine** (0–100) : habitat à moins de 200 m de la forêt (WUI) 40 %, routes pondérées 25 %,
  trafic 20 %, agriculture 15 % ;
- **Score** : par défaut `combustible × (0,6 + 0,4 × humain / 100)`. Sans végétation, le risque reste nul,
  et la fréquentation augmente le score d’un massif. Le mode additif permet de régler le poids des piliers.

Les indicateurs non fractionnaires sont convertis en rangs relatifs au département
(0 = valeur minimale, 1 = valeur maximale). Le score compare donc les carreaux **entre eux** :
ce n’est ni une probabilité ni un indice comparable d’un département à l’autre, et il n’intègre
pas la météo (étape suivante : IFM/FWI quotidien Copernicus).

```bash
# 1. Features statiques de la Gironde (branche manon, plusieurs centaines de Mo téléchargés)
git worktree add ../hackathon-ifm origin/manon --detach
cd ../hackathon-ifm/ifm_plus && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/01_download_data.py --departement 33 --layers all
.venv/bin/python scripts/02_build_static_features.py --departement 33
cd -

# 2. Scores par carreau -> risk-data/risque_statique_33.geojson (ignoré par Git)
../hackathon-ifm/ifm_plus/.venv/bin/python ml/build_static_risk.py \
  --features ../hackathon-ifm/ifm_plus/data/processed/static_features_33.gpkg --out risk-data

# 3. Dashboard
docker compose up --build -d --no-deps dashboard
```

Tests : `python -m unittest tests/test_static_risk.py`.

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
| `dashboard/` | Interface des pompiers : http://localhost:8501 |
| `ml/` | Téléchargement du dataset `pyro-sdis`, évaluation et fine-tuning YOLO |

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
