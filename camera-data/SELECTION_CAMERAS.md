# Sélection des webcams du 19 novembre 2026

Ce document décrit le premier tri de 69 vues. Un complément ultérieur conserve
ces 69 caméras et ajoute 36 vues : voir `COUVERTURE_CAMERAS.md` et
`cameras.ajouts.csv`. Le catalogue actif compte désormais 105 vues. Les CSV
`cameras.audit.csv`, `cameras.reserve.csv` et `cameras.indisponibles.csv` décrivent
l'état au moment du premier tri ; la liste de réserve est conservée telle quelle
comme trace de cet audit initial.

Le catalogue actif `cameras.csv` contient 69 vues sur 45 noms de lieux, à partir
des 1 841 liens du catalogue initial. Le fichier local `camera.json` a été
synchronisé avec cette sélection et validé avec le lecteur du dashboard.

## Résultat du tri

| Destination | Entrées | Critère |
| --- | ---: | --- |
| `cameras.csv` | 69 | Image décodable à deux contrôles et vue inspectée pour son intérêt visuel |
| `cameras.indisponibles.csv` | 201 | HTTP 404 lors de deux contrôles |
| `cameras.reserve.csv` | 1 571 | Autres entrées : priorité moindre, visibilité insuffisante, localisation à confirmer ou disponibilité non vérifiable |

`cameras.audit.csv` donne la décision, le motif et les contrôles pour chaque
lien initial. Les erreurs 403, 429 et 503, les pages sans flux vérifié et les
échecs de décodage ne prouvent pas qu'une caméra est définitivement hors ligne.
Ils sont classés en réserve. Un second passage a récupéré 16 images dont le
premier contrôle avait échoué.

Les vues retenues privilégient les versants boisés, vallées, lisières et
panoramas avec de la végétation et de l'espace pour voir un panache. Les gros
plans routiers, centres-villes, ports, plages et pistes sans végétation ont une
priorité moindre. Les vues bouchées, très dégradées, redondantes ou présentant
des indications de date/localisation douteuses ont été écartées de la sélection.
Ce tri est qualitatif et ne constitue pas une mesure de performance de YOLO.

## Portée des contrôles

Contrôles effectués le 19 novembre 2026, entre environ 13 h 54 et 14 h 05,
heure de Paris. Le catalogue initial a fourni 904 images décodables, 636 pages
web, 299 erreurs HTTP et 2 images invalides au terme des vérifications.
Une réponse HTML 200 n'a jamais été assimilée à une caméra fonctionnelle.

Les 69 liens retenus ont fourni deux images lisibles. Leur contenu était
identique entre les captures. Le diffuseur annonce un cache pouvant aller
jusqu'à dix minutes : ces contrôles confirment l'accès à une image, sans
certifier sa date de prise de vue ni une diffusion continue. Les horodatages
HTTP ne sont pas une preuve de fraîcheur de la scène.

Les positions du JSON proviennent du géocodage des villes du CSV. Elles ne
correspondent pas nécessairement aux positions exactes des caméras. La maille
associée doit donc être comprise comme celle du point géocodé. Les coordonnées
manquantes de Toulon et de Saint-Raphaël ont été récupérées avec une recherche
précisée par département ou code postal.

## Sauvegardes locales

Le dossier `local-audit-2026-11-19/`, exclu de Git par son propre `.gitignore`,
conserve le CSV initial, le JSON initial, les réponses des contrôles, les images
de revue et la sélection intermédiaire. Les suppressions du catalogue actif
sont ainsi réversibles. Les images restent locales.

Le catalogue actif et le JSON ont été modifiés sur la branche `webcam`.
Aucun réentraînement, raccordement de YOLO, commit, push ou redémarrage Docker
n'a été effectué dans le cadre de ce tri.
