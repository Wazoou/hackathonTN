# Carte de risque : performances et vérifications

Mesures locales du 17 novembre 2026, sur les 139 842 mailles des 96 départements.
Elles dépendent du navigateur, du matériel et des autres applications ouvertes.

## Problème constaté

Chaque réglage Streamlit reconstruisait le GeoJSON enrichi, la table de statistiques
et le JSON Pydeck, puis renvoyait toute la France au navigateur.
Avec AppTest, les durées côté serveur étaient : ouverture 6,95 s ; opacité 6,52 s ;
combustible 6,22 s ; retour au score 6,03 s. Ces mesures n'incluent pas le rendu navigateur.

## Changement

`risk_payload.py` prépare un paquet compressé et versionné. Le cache est invalidé
quand un GeoJSON ou ses métadonnées changent (date de modification nanoseconde et taille).
Les fichiers de données restent dans `risk-data/`, hors Git. Les bibliothèques du
composant sont locales, avec versions, licences et empreintes dans `vendor/manifest.json`.
Les noms des départements proviennent du référentiel administratif déjà téléchargé.

Le composant garde les géométries en mémoire et sur le GPU :

- opacité : modification d'un paramètre graphique, sans recalcul statistique ;
- couche et pondération : réutilisation des valeurs et des couleurs déjà préparées ;
- département : filtre GPU, sans nouvelle lecture ni retransfert des géométries ;
- statistiques : cache par périmètre/couche/pondération ; tri numérique natif et top 15
  calculé sans trier une seconde fois toutes les mailles ;
- zoom et position conservés lors des changements de couche et d'opacité ;
- réglages restaurés dans la même session après rechargement.

Les réglages n'envoient pas de `setComponentValue` à Streamlit : ils ne relancent pas Python.

## Résultats observés

Le contenu compressé représente **13,87 Mo** (environ **18,5 Mo** après encodage base64),
au lieu d'un GeoJSON enrichi retransmis à chaque action. La première préparation à froid
prend environ 9 s sur ce PC ; elle ne se répète pas à chaque réglage. Un rerun serveur
avec cache a été mesuré à 0,100 s. Le premier chargement et un rafraîchissement complet
restent plus longs que les interactions locales.

Les mesures dans le composant utilisent `performance.now()` et deux frames d'animation
après la demande de mise à jour. Elles incluent la préparation JS et les frames de rendu,
mais ne constituent pas une mesure instrumentée du temps GPU :

| Action | Temps observé après chargement |
|---|---:|
| Opacité | ~33 ms (préparation JS ~0,3 ms) |
| Retour à une couche déjà utilisée | ~41–45 ms |
| Première sélection de pression humaine | ~72 ms |
| Pondération additive | ~71 ms |
| Filtre département / retour France | ~25–35 ms |

Les outils de test ont vérifié que le compteur de chargements du jeu de données restait
à **1** pendant ces interactions. Les valeurs de diagnostic sont sur les attributs
`data-update-ms`, `data-frame-ms`, `data-load-count` et `data-view` du composant.

## Fidélité et tests

Aucune maille n'est supprimée, aucun indicateur n'est agrégé davantage et aucune coordonnée
n'est arrondie par le transport. Les limites du score restent inchangées : pas de météo,
trafic mesuré exclu faute de couverture, pas de calibration BDIFF nationale.

Le calcul Python existant génère les scores multiplicatifs et les 21 pondérations additives
possibles. Les valeurs sont transportées en dixièmes entiers puis restituées à l'identique :
les arrondis Python ne sont pas réimplémentés en JavaScript. Les couleurs des probabilités
optionnelles sont également préparées par Python, sans quantification supplémentaire.

- Tests unitaires : compression sans perte des géométries et propriétés, valeurs manquantes,
  toutes les pondérations, doublons refusés, invalidation du cache sur données et métadonnées.
- Comparaison nationale : **582 configurations** (France + 96 départements × 6 réglages),
  avec égalité des effectifs, médianes, proportions en classe élevée et ordre des 15 premiers.
- Tests JS : seuils de classes et de probabilité, ex aequo du classement, liste vide,
  échappement des textes affichés.
- Tests navigateur : allers-retours score/combustible/humain, opacité, poids 0/60/100 %,
  Paris (28 mailles), Corse-du-Sud (1 141), Nord (1 550), Gironde (2 634), France (139 842),
  boutons de zoom successifs, zoom molette, conservation du cadrage, classement,
  fiche de maille, métadonnées, restauration des réglages après rechargement.

Commandes reproductibles depuis la racine (Node.js nécessaire uniquement pour les tests JS) :

```bash
ifm_plus/.venv/bin/python -m unittest discover -s tests -p 'test_risk_payload.py' -v
ifm_plus/.venv/bin/python -m unittest discover -s tests -p 'test_static_risk.py' -v
ifm_plus/.venv/bin/python tests/export_risk_reference.py --out /tmp/risk-validation
node tests/test_risk_logic.cjs /tmp/risk-validation/payload.json.gz /tmp/risk-validation/reference.json
docker compose exec -T dashboard python - < tests/check_risk_ui.py
```
