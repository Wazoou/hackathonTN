# Retrouver les mêmes images sur la carte

Prérequis : le dépôt cloné, Docker avec Compose, et le fichier
`pyro-watch-images.tar.gz` envoyé par le groupe.

Placez l’archive **à la racine du dépôt** (à côté de `docker-compose.yml`), puis lancez :

```bash
git switch main
git pull --ff-only origin main
tar -xzf pyro-watch-images.tar.gz
docker compose up --build -d api dashboard
```

Ouvrez **http://localhost:8501/**. La carte doit annoncer **12 252 images** :
12 223 Pyro-SDIS et 29 images de webcams, avec 10 repères au total.
Le filtre « Toutes les sources » est sélectionné au départ.

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
