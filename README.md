# 🔥 Pyro-Watch

Détection précoce de feux de forêt à partir de caméras : hackathon Open Data University,
défi « Prévenir et détecter les feux de forêt » (Pyronear × Latitudes).

Voir **[ROADMAP.md](ROADMAP.md)** pour le plan de la semaine et la répartition des tâches.

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

Prérequis : Docker avec le plugin compose (Fedora : `sudo dnf install docker-compose`).

```bash
# 1. Images de démo : vraies séquences de caméras SDIS (~120 Mo)
python3 -m venv .venv && .venv/bin/pip install pyarrow requests
.venv/bin/python ml/pyro_sdis.py samples --out data/samples --cameras 3

# 2. Lancer la stack
docker compose up --build
```

Ouvrir http://localhost:8501. Sans l'étape 1, les caméras passent en images synthétiques.

> En phase 1, le détecteur est **factice** (`DETECTOR=dummy`). Il génère des « épisodes » de fumée
> aléatoires pour tester toute la chaîne ; ses boîtes ne correspondent pas à de la vraie fumée.

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

## 🔥 IFM+ — score de risque intégré (volet données)

Le dossier [`ifm_plus/`](ifm_plus/README.md) contient un pipeline séparé de
modélisation du risque de départ de feu à la maille DFCI 2 km : acquisition
data.gouv.fr / IGN / Copernicus, features combustible–relief–pression humaine,
puis modèles et benchmark contre l'IFM. Le pipeline fonctionne sur un
département pilote **ou sur toute la France métropolitaine** (96 départements,
traitement département par département puis assemblage national).
Voir le [README du pipeline](ifm_plus/README.md) et la
[méthodologie](ifm_plus/docs/modelisation_evaluation.md).
