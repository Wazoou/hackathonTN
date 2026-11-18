# LIVE et PRÉDICTION

La carte conserve son historique et propose, à droite de la timeline :

- **ARCHIVES** : jours passés ; stations Météo-France pour l’historique initial,
  puis météo **modélisée Open-Meteo** pour les jours collectés, ou **observations
  Météo-France** pour les jours anciens manqués, avec provenance distincte.
- **LIVE** : risque estimé pour **toute la journée d’aujourd’hui**, révisé toutes les
  **90 minutes**. Ce n’est pas une probabilité pour l’heure qui vient.
- **PRÉDICTION** : jours **J+1 à J+7**, avec sélection automatique des modèles
  Open-Meteo selon le lieu et l’échéance.

Le modèle reste figé sur son apprentissage 2006–2024. Les nouvelles données ne le
réentraînent pas. Les observations BDIFF affichées vont jusqu’à 2025 ; leur absence
sur les dates récentes ne signifie pas qu’aucun incendie n’a eu lieu.

## Lancer sur une autre machine

Le dossier partagé `risk-data/meteo/` doit contenir les six fichiers météo habituels
**et `live_initial_state.npz`**. Ce dernier fichier fait environ **16 Ko** et suffit
à transmettre l’état de sécheresse calculé à la fin de l’historique : les autres
membres n’ont pas besoin de télécharger les données brutes nationales.

Depuis la racine du dépôt :

```bash
docker compose up --build -d weather dashboard
docker compose logs -f weather
```

Ouvrir http://localhost:8501/. La première collecte prend généralement au moins une
minute : les requêtes sont étalées pour respecter les quotas. Les boutons LIVE et
PRÉDICTION deviennent accessibles quand la collecte nationale complète est publiée.
Le navigateur vérifie cette publication toutes les minutes, sans relancer Python,
recharger l’historique ou recréer la carte. Le collecteur continue même sans visiteur.
**La machine et les conteneurs doivent rester allumés et connectés.**

Pour arrêter la collecte sans arrêter la carte :

```bash
docker compose stop weather
```

La dernière carte reste disponible et son ancienneté est signalée.

### Préparer le petit fichier initial sur la machine qui a les données brutes

Il est maintenant exporté automatiquement par `ml/build_daily_risk.py`.
Pour l’ajouter à un historique déjà calculé, **sans réentraîner le modèle** :

```bash
ifm_plus/.venv/bin/python ml/prepare_live_state.py \
  --risk-data risk-data --meteo ifm_plus/data/raw/meteo
```

Partager ensuite `risk-data/meteo/live_initial_state.npz` avec le dossier météo.
L’ordre des stations et la date de fin doivent correspondre à `meteo.npz`.

## Calcul et continuité temporelle

Une seule collecte nationale utilise les coordonnées des **587 stations de référence**.
La météo n’est pas demandée pour chacune des 139 842 mailles. Les quatre variables
sont température maximale quotidienne, humidité relative minimale, vent moyen à
10 mètres en km/h et précipitations cumulées en mm, agrégées par jour Europe/Paris.
Les périodes d’agrégation ne sont pas nécessairement identiques à celles des
observations climatologiques initiales : cette transition de source doit être évaluée.

Le collecteur conserve FFMC, DMC et DC. Chaque révision repart du dernier jour
consolidé, puis recalcule chronologiquement la fenêtre récente et les prévisions.
Elle n’applique jamais plusieurs fois le même jour à l’état de sécheresse.
Les jours manquants après un arrêt sont récupérés avant le calcul des prévisions.
**Jusqu’à J−7 inclus**, le rattrapage utilise les observations quotidiennes publiques
**Météo-France**, sans consommer le quota Open-Meteo. Le seuil J−7 garde la fenêtre
Open-Meteo à 14 jours : J−6 à J+7, aujourd’hui inclus.

Le collecteur réutilise d’abord les fichiers présents dans
`ifm_plus/data/raw/meteo/`, montés en lecture seule. S’ils ne couvrent pas la période,
il consulte le catalogue officiel data.gouv.fr et télécharge uniquement les familles,
départements et périodes nécessaires dans `data/weather/meteo-france/`. Le catalogue
est mis en cache six heures, et les fichiers ne sont retéléchargés que lorsque leur
version change. Il s’agit de téléchargements de fichiers publics, pas d’appels à
l’API climatologique authentifiée. Les lots des deux années récentes représentent
environ 52 Mo pour la métropole ; les lots historiques peuvent être plus volumineux.

Les variables sont identiques à l’apprentissage : TX, UN, FFM converti en km/h et RR.
Les valeurs manquantes peuvent être remplacées par une observation disponible parmi
les cinq stations de référence voisines, sans propager une substitution entre stations.
Le nombre de valeurs remplacées est enregistré et indiqué dans les détails de la carte.
Si les observations restent incomplètes, la dernière carte est conservée : **aucun
repli automatique sur Open-Meteo** ne dépense son quota pour ces dates anciennes.

Chaque tranche de 14 jours récupérée est sauvegardée avec son état FWI. Un arrêt du
processus ne fait pas perdre le rattrapage déjà calculé. De J−6 à aujourd’hui et pour
les prévisions, le collecteur conserve Open-Meteo. Les anciennes archives déjà
collectées ne sont pas remplacées rétroactivement ; la base existante est migrée
sans perte pour enregistrer la source de chaque nouveau jour.

Le risque communal est calculé avec la régression existante, puis réparti entre ses
mailles suivant les parts de terrain existantes. Les calculs restent quotidiens ;
une donnée météorologique horaire ne transforme pas ce modèle en modèle horaire.

## Fréquence, budget et incidents

Les créneaux sont espacés de 5 400 secondes et enregistrés sur disque : redémarrer
le conteneur ne déclenche pas une collecte supplémentaire dans le même créneau.
Une collecte alimente **à la fois LIVE et PRÉDICTION**. Les requêtes sont groupées
par 50 points et par intervalles d’au plus 14 jours. Grouper les coordonnées ne
supprime pas le coût équivalent de chaque lieu.

En régime courant : **587 × 16 = 9 392 appels équivalents par 24 heures**.
Le collecteur impose localement des plafonds prudents de 550/minute, 9 800/24 h et
295 000/31 jours, et compte aussi les tentatives échouées. Ces limites ne voient
pas les appels effectués par d’autres applications utilisant la même IP.
Le rattrapage ancien Météo-France ne consomme pas ce budget. Les nouvelles données sont
récupérées toutes les 90 minutes en mode `best_match` : les métadonnées de certains
modèles ne suffisent pas à identifier toutes ses mises à jour. Si les valeurs sont
inchangées, aucune révision supplémentaire n’est stockée.

Une réponse partielle, des valeurs absentes, un quota dépassé ou une panne réseau
conservent la dernière publication complète. L’heure de collecte, la prochaine
vérification et les erreurs sont affichées. Au-delà de trois heures, les données
sont signalées comme anciennes. Une nouvelle collecte météo ne signifie pas
nécessairement qu’un nouveau calcul du fournisseur a été publié ; l’API combinée
ne fournit pas une heure d’émission unique pour tous les modèles.

## Archives et volume

Tout est enregistré dans **`data/weather/`**, hors Git :

- `weather.sqlite` : météo des points de référence, états de sécheresse, partie météo
  de la régression, provenance et compteurs d’appels ; aucun instantané par maille.
- `public/current.json` : petit manifeste de disponibilité.
- `public/bundle-*.json` : données compressées destinées à la carte ; seuls les deux
  derniers fichiers publiés sont conservés.

Les révisions sont conservées **sept jours**. Ensuite, une seule version quotidienne
est figée à partir de la dernière météo rétrospective Open-Meteo récupérée pour ce
jour. Pour les journées anciennes manquées, la version est calculée avec les observations
Météo-France. La source et les éventuelles substitutions sont conservées par date.
La consolidation ne fait pas une moyenne de probabilités.
Son état de sécheresse et ses données d’entrée sont conservés avant toute suppression
des révisions. Les pages SQLite libérées sont réutilisées lors des écritures suivantes.

Pour mesurer ultérieurement la qualité des prévisions, la dernière collecte de chaque
journée servant aux échéances **J+1, J+3 et J+7** est conservée avec son chemin météo et
son état initial. La déduplication évite de la copier trois fois. Le volume dépend
de la compressibilité ; il n’inclut pas 24 cartes de 140 000 scores par jour.
La première publication réelle pour neuf jours représente environ 122 Ko à transférer.

Pour partager exactement les mêmes nouvelles archives, arrêter le collecteur avant
une copie complète de `data/weather/`, puis le relancer. Ne pas copier une base SQLite
en cours d’écriture sans ses fichiers WAL. **Un collecteur central pour le groupe**
évite que chacun dépense le quota et obtienne une heure de collecte différente.

Si le modèle, les stations ou le socle historique sont remplacés, conserver l’ancien
dossier d’archives et repartir avec un nouveau dossier cohérent. Les modèles
incompatibles sont refusés ; les archives ne sont pas mélangées silencieusement.

## Limites et sources

Cette version reste expérimentale : le modèle a été entraîné avec des observations
de stations, alors que LIVE et PRÉDICTION utilisent de la météo modélisée. Il faut
vérifier la calibration sur cette nouvelle source et par échéance, sans présenter
les probabilités comme une prévision opérationnelle validée de sécurité civile.
La finesse de la grille météo dépend des modèles ; une maille d’affichage de 2 km
n’implique pas une mesure météo indépendante tous les 2 km.

Observations de rattrapage : [Météo-France, données quotidiennes](https://www.data.gouv.fr/datasets/donnees-climatologiques-de-base-quotidiennes), Licence Ouverte 2.0.

Données récentes et prévisions : [Open-Meteo](https://open-meteo.com/en/docs), modèles des services nationaux,
licence [CC BY 4.0](https://open-meteo.com/en/licence).
L’offre publique est destinée à l’usage non commercial et soumise aux
[quotas du fournisseur](https://open-meteo.com/en/pricing).
