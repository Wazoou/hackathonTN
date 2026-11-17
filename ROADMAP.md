# Feuille de route — Pyro-Watch

## Objectif actuel

Explorer des images datées de caméras françaises sur une carte, utiliser ensuite un modèle
Pyronear/YOLO préentraîné pour détecter la fumée, puis étudier des corrélations avec d’autres
données, notamment la météo. Le fine-tuning n’est pas requis pour cette étape du projet.
La démonstration actuelle est une exploration d’archives ; elle ne constitue pas un système
opérationnel d’alerte ni un modèle de prédiction du risque validé.

## Disponible dans le dépôt

- [x] Carte commune Pyro-SDIS et webcams, timeline continue et lecteur d’images datées.
- [x] 12 223 images françaises Pyro-SDIS (`train` et `val`) et 29 images de 4 webcams dans l’échantillon partagé.
- [x] 10 repères : 6 losanges départementaux Pyro-SDIS et 4 ronds aux positions publiées des webcams.
- [x] Couleurs actualisées pendant le glissement, sans rechargement de la carte ; zoom molette et déplacement conservés.
- [x] Filtre facultatif des sources, navigation par dates et raccourcis d’exemples.
- [x] Sources, crédits, limites géographiques et temporelles affichés ; annotations humaines Pyro-SDIS facultatives.
- [x] Import de tous les Parquet Pyro-SDIS avec révision et empreintes ; import ciblé de webcams avec cache et provenance.
- [x] Guide de partage des mêmes images : [DONNEES_EQUIPE.md](DONNEES_EQUIPE.md).
- [x] API caméras/détections/alertes et agents synthétique, dossier, vidéo, RTSP ou snapshot HTTP.
- [x] Scripts ML d’évaluation et d’entraînement, disponibles pour une phase ultérieure.

La configuration YOLO des **agents** se fait via `.env` : construction optionnelle, cache
Hugging Face et OpenCV headless. Cela n’active pas encore YOLO dans le lecteur historique.
Les agents utilisent `data/samples/` ; la carte lit `archives-data/`.

## Prochaines étapes, dans l’ordre

1. [ ] Chaque membre récupère `main` et installe l’archive commune selon le guide ; vérifier les mêmes effectifs.
2. [ ] Brancher l’inférence du modèle préentraîné sur les images du lecteur, avec cache des résultats,
   affichage de la confiance et distinction claire entre prédictions et annotations humaines.
3. [ ] Vérifier manuellement les séquences candidates : Fréjus documenté, Saména encore à confirmer,
   paysages et nuages de comparaison. Ne pas transformer une prédiction en vérité terrain.
4. [ ] Mesurer les erreurs sur un échantillon revu : fumée manquée, nuages, brume et autres faux positifs.
   Documenter le seuil, les données utilisées et les limites de l’évaluation.
5. [ ] Ajouter la météo historique aux points dont les coordonnées et heures sont exploitables.
   Clarifier les fuseaux avant les rapprochements. Les repères départementaux Pyro-SDIS ne sont pas des GPS de caméras.
6. [ ] Explorer les corrélations météo/détections sans les présenter comme des facteurs causaux établis
   ni un score de risque validé ; rechercher une source indépendante pour les événements confirmés.
7. [ ] Préparer une présentation reproductible et une vidéo de secours avec les mêmes données pour tout le groupe.

## Répartition proposée pour le groupe

| Chantier | Livrable |
|---|---|
| Interface et données | Carte/timeline, archives, provenance et installation commune |
| Détection | Inférence YOLO, cache, seuils, exemples revus et mesure des erreurs |
| Météo et présentation | Rapprochements historiques fiables, analyse, limites et scénario de démonstration |

## Scénario de démonstration actuel

1. Montrer la carte commune et expliquer les ronds et losanges, puis la disponibilité vert/gris.
2. Ouvrir « Explorer un exemple » : Fréjus, puis comparer les différentes heures de la séquence.
3. Passer à Saint-Martin-de-Londres ou Canéjan pour montrer des vues de comparaison.
4. Ouvrir l’exemple Pyro-SDIS annoté ; préciser que les cadres orange sont des annotations humaines.
5. Expliquer la prochaine connexion YOLO et le rapprochement météo ; ne présenter des résultats
   de détection ou de risque que lorsqu’ils ont été effectivement calculés et vérifiés.

## Vérifications avant fusion et présentation

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
docker compose config --quiet
docker compose exec -T dashboard python - < tests/check_archive_ui.py
docker compose exec -T dashboard python - < tests/check_webcam_ui.py
```

Les tests unitaires nécessitent `pyarrow` et `requests`. Les vérifications d’interface
s’exécutent dans le conteneur dashboard après installation des deux manifestes.
Vérifier aussi dans le navigateur les couleurs au glissement, les clics sur les deux types
de repères et la conservation du zoom. Ne pas pousser les images, archives, poids ou fichiers `.env`.
