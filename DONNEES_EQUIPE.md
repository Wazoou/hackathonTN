# Partager les données de l'équipe

## Carte de risque nationale : sans télécharger les sources brutes

Récupérez auprès de Mathieu les fichiers `pyro-watch-risque-france.tar.gz` et
`pyro-watch-risque-france.tar.gz.sha256`, puis placez-les à la racine du dépôt.
Cette archive contient les résultats calculés ; elle évite les quelque 46 Go
d'archives sources et le traitement national.
Le paquet du 17 novembre 2026 pèse **77,1 Mo** et occupe **142 Mo** une fois extrait.

Depuis la racine du dépôt, avec Docker et Compose installés :

```bash
git switch main
git pull --ff-only origin main
sha256sum -c pyro-watch-risque-france.tar.gz.sha256
tar -xzf pyro-watch-risque-france.tar.gz
docker compose up --build -d api dashboard
```

Sur macOS, la vérification peut se faire avec
`shasum -a 256 -c pyro-watch-risque-france.tar.gz.sha256`.

Ouvrez **http://localhost:8501/?view=risk** : **96 départements et 139 842 mailles**
doivent être disponibles. Les scores, indicateurs et géométries sont les mêmes
que sur la machine de référence. Aucun téléchargement géographique ni calcul
national n'est nécessaire pour afficher la carte. Docker peut télécharger ses
images et dépendances ; le fond de carte nécessite une connexion Internet.

L'archive inclut :

- `risk-data/` : les 96 GeoJSON de scores et leurs métadonnées, directement utilisables ;
- `ifm_plus/data/processed/dfci_2km_features_france.parquet` : les indicateurs nationaux ;
- `ifm_plus/data/processed/dfci_2km_grid_france_metro.parquet` : les géométries des mailles ;
- les métadonnées et le rapport de couverture associés.

Les deux fichiers Parquet permettent aussi de recalculer les scores avec la commande
du README, sans les couches géographiques brutes. Pour modifier la manière dont les
indicateurs eux-mêmes sont construits, ces couches brutes peuvent en revanche être nécessaires.
La couche de probabilité BDIFF et le risque du jour (météo) ne sont pas inclus dans cette archive.
Pour le risque du jour, copier le dossier `risk-data/meteo/` (28 Mo) d'un membre de l'équipe, ou suivre
la section « Risque du jour » du README (téléchargement Météo-France d'environ 1,5 Go, puis ~3 min de calcul, après la probabilité BDIFF ci-dessous).

Pour ajouter la régression logistique nationale à partir des deux fichiers Parquet (environ 1 min, BDIFF téléchargé
automatiquement depuis le portail, ~5 Mo) :

```bash
ifm_plus/.venv/bin/pip install -r ifm_plus/requirements.txt scikit-learn
ifm_plus/.venv/bin/python ml/download_bdiff.py --out ifm_plus/data/raw/manual/bdiff
ifm_plus/.venv/bin/python ml/build_static_risk.py \
  --features ifm_plus/data/processed/dfci_2km_features_france.parquet \
  --grid ifm_plus/data/processed/dfci_2km_grid_france_metro.parquet \
  --exclude tmja_max --out risk-data --bdiff ifm_plus/data/raw/manual/bdiff
```

Si vous avez déjà des résultats locaux à conserver, renommez votre dossier `risk-data/`
et sauvegardez les fichiers nationaux de `ifm_plus/data/processed/` avant extraction.
L'archive s'extrait directement à la racine ; ne créez pas de dossier imbriqué supplémentaire.
Les données restent ignorées par Git : un `git pull` seul ne les récupère pas.

### Recréer l'archive depuis la machine de référence

```bash
tar -czf pyro-watch-risque-france.tar.gz \
  risk-data \
  ifm_plus/data/processed/dfci_2km_features_france.parquet \
  ifm_plus/data/processed/dfci_2km_features_france_metadata.json \
  ifm_plus/data/processed/dfci_2km_grid_france_metro.parquet \
  ifm_plus/data/processed/dfci_2km_grid_france_metro.json \
  ifm_plus/data/processed/coverage_france_metro.json
sha256sum pyro-watch-risque-france.tar.gz > pyro-watch-risque-france.tar.gz.sha256
```

## Retrouver les mêmes images sur la carte des archives

Le paquet de risque ne contient pas les images des caméras. Pour cet onglet,
utilisez aussi l'archive d'images déjà partagée, suivant les instructions ci-dessous.

Prérequis : le dépôt cloné, Docker avec Compose, et le fichier
`pyro-watch-images.tar.gz` envoyé par le groupe.

Placez l’archive **à la racine du dépôt** (à côté de `docker-compose.yml`), puis lancez :

```bash
git switch main
git pull --ff-only origin main
tar -xzf pyro-watch-images.tar.gz
docker compose up --build -d api dashboard
```

Ouvrez **http://localhost:8501/** puis l’onglet **Webcam**. La carte doit annoncer **12 252 images** :
12 223 Pyro-SDIS et 29 images de webcams, avec 10 repères au total.
Le filtre « Toutes les sources » est sélectionné au départ.

## Historique des incendies 2006–2025

La carte de risque charge par défaut `risk-data/` à la racine. Si votre archive est
extraite dans un autre dossier, définissez `RISK_DATA_DIR` dans `.env` avec le chemin
du dossier contenant les GeoJSON, puis recréez le dashboard.

Cet onglet utilise des CSV distincts des images et des scores de risque, également hors Git.
Partagez le dossier `ifm_plus/data/raw/manual/bdiff/` (2006–2024) et
`ifm_plus/data/raw/incendies/Incendies.csv` (2025), en conservant ces chemins,
ou récupérez l’export public avec les commandes du README. Docker monte automatiquement
ces deux dossiers ; relancez le dashboard si vous venez de mettre
à jour sa configuration. Le curseur d’année couvre les années présentes dans ces fichiers.
Les positions sont approximatives, à l’échelle communale ou départementale lorsque
la commune historique ne peut pas être localisée ; l’interface indique ces cas.

## Extraction des images

L’extraction crée `archives-data/manifest.json`, `manifest-webcams.json`, `images/`
et `webcam-demo/` sous `archives-data/`. Évitez un dossier imbriqué
`archives-data/archives-data/`. Ces fichiers restent locaux et ne sont pas poussés sur Git.
Aucun import supplémentaire n’est nécessaire : l’archive contient déjà l’échantillon exact.

Si le port 8501 est déjà utilisé par une autre application, libérez-le avant le lancement.
Si vous aviez déjà un import local, renommez son dossier `archives-data/` avant l’extraction
pour conserver vos données ; l’archive rétablit les manifestes de la présentation.

## Préparer l’archive à envoyer (machine de référence)

Depuis la racine du dépôt :

```bash
tar -czf pyro-watch-images.tar.gz \
  archives-data/manifest.json \
  archives-data/manifest-webcams.json \
  archives-data/images \
  archives-data/webcam-demo
```

L’archive est ignorée par Git. Partagez-la par votre espace de fichiers de groupe ;
les fichiers Parquet de téléchargement et les poids YOLO ne sont pas nécessaires pour la carte.


## Ajouter LIVE et PRÉDICTION

Partager aussi le dossier **`risk-data/meteo/`**, en incluant désormais
**`live_initial_state.npz`** (environ 16 Ko). Ce fichier permet de prolonger les
indices de sécheresse sans télécharger les données brutes de la France.

```bash
docker compose up --build -d weather dashboard
```

Le collecteur récupère ensuite Open-Meteo toutes les 90 minutes et publie aujourd’hui
ainsi que J+1 à J+7. Les nouvelles archives restent dans `data/weather/`, hors Git.
Le PC doit rester allumé pour les collectes automatiques. Consulter
[LIVE_PREDICTION.md](LIVE_PREDICTION.md) pour préparer le fichier initial, partager
une archive opérationnelle et éviter plusieurs collecteurs pour le groupe.


Pour les journées anciennes manquées (J−7 et avant), le collecteur utilise désormais
les observations publiques Météo-France. Le dossier de données brutes déjà présent
est réutilisé en lecture seule ; il n’est pas nécessaire de l’envoyer à toute l’équipe.
Si les fichiers sont absents, les seuls lots nécessaires sont téléchargés dans
`data/weather/meteo-france/`. Ce rattrapage ne consomme pas le quota Open-Meteo.
