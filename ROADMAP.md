# 🗺️ Feuille de route : Pyro-Watch (3 personnes, 5 jours)

## 🎯 La ligne directrice

> **Un dashboard pour les pompiers, relié à des caméras, qui détecte la fumée et apprend de ses erreurs.**

Le message pour le jury tient en 3 points :
1. **Ça marche de bout en bout** : caméra → détection → alerte → qualification par un pompier.
2. **On a mesuré et amélioré la détection** sur des caméras que le modèle Pyronear n'a jamais vues.
3. **La boucle se referme** : les faux positifs signalés dans le dashboard deviennent des données d'entraînement.

**Règle d'or :** chaque soir, `docker compose up` doit donner une démo qui fonctionne. On n'empile
jamais du nouveau sur quelque chose de cassé.

---

## 👥 Les rôles

| Rôle | Responsable de | Livrable final |
|---|---|---|
| **A : Backend & Infra** | `api/`, `camera/`, Docker, sources caméras, déploiement | Une stack stable, de vraies sources vidéo, (bonus) une version en ligne |
| **B : Dashboard & Produit** | `dashboard/`, l'expérience utilisateur, le pitch, les slides | Une interface claire pour un pompier, le scénario de démo, la présentation |
| **C : ML / Détection** | `ml/`, les notebooks Kaggle, l'évaluation, le fine-tuning | Une comparaison chiffrée avant/après, le meilleur modèle branché dans la stack |

Chacun reste responsable de sa zone, mais **tout le monde doit savoir lancer la démo**.

---

## ✅ Le MVP (déjà fourni dans ce dépôt)

- [x] API : caméras, images, détections, alertes avec la logique « N images consécutives »
- [x] Agent caméra : sources synthétique, dossier, vidéo, RTSP et snapshot HTTP ; détecteur factice ou YOLO
- [x] Dashboard : indicateurs, carte, flux avec boîtes de détection, boutons « Feu confirmé » / « Faux positif »
- [x] 3 caméras simulées avec de vraies séquences SDIS (`ml/pyro_sdis.py samples`)
- [x] Scripts d'évaluation et de fine-tuning (`ml/finetune.py`)

⚠️ La partie YOLO (`DETECTOR=yolo`) n'a **pas encore été testée** : c'est la première tâche de C.

---

## 📅 Jour par jour

### J0 : avant de commencer (1 h, ensemble)
1. [ ] Créer le dépôt GitHub, ajouter les 2 autres membres, faire le premier push de ce MVP
2. [ ] Chacun clone le dépôt et lance la démo sur sa machine (voir le README)
3. [ ] Créer un compte Kaggle et **vérifier son numéro de téléphone** (obligatoire pour avoir le GPU) **(C)**
4. [ ] Écrire à Pyronear (contact via pyronear.org ou GitHub) : présenter le projet, demander un accès de test à leur API ou à des images de caméras, et leurs conseils sur les faux positifs **(B)**
5. [ ] Se mettre d'accord sur le rituel : point de 10 min matin et soir, et une branche par fonctionnalité avec merge sur `main` uniquement si la démo tourne

### J1 : comprendre et ancrer (objectif : chacun maîtrise sa brique)
| A : Backend | B : Dashboard | C : ML |
|---|---|---|
| 1. Lire `api/app/main.py` et `camera/` | 1. Lire `dashboard/app.py` | 1. Sur Kaggle, lancer `pyro_sdis.py yolo` puis `finetune.py eval` = **baseline** du modèle Pyronear |
| 2. Trouver **3 à 5 sources réelles** : webcams publiques en JPEG (voir `pyronear/pyro-openwebcams`), vidéos de départs de feu (format .mp4) | 2. Rédiger le **persona** (opérateur SDIS) et lister ce qu'il doit voir en 5 secondes | 2. En local, tester `DETECTOR=yolo` sur `data/samples` et corriger si besoin |
| 3. Brancher ces sources dans `docker-compose.yml` | 3. Faire une maquette papier de la V2 du dashboard | 3. Noter la mAP, la précision et le rappel dans `ml/RESULTS.md` |

**Le soir :** la démo tourne avec au moins 1 source réelle, et la baseline ML est chiffrée.

### J2 : du vrai modèle dans la stack
| A : Backend | B : Dashboard | C : ML |
|---|---|---|
| 1. Construire l'image caméra avec `INSTALL_YOLO=true` et mesurer le temps d'inférence sur CPU | 1. Historique des alertes (toutes, filtrables par statut et par caméra) | 1. Passer le modèle Pyronear sur **vos sources du J1** et observer où il se trompe |
| 2. Endpoint `GET /alerts/export` : alertes qualifiées en zip au format YOLO (la base de la boucle de ré-entraînement) | 2. Cône de vision des caméras sur la carte (champ `azimuth`) | 2. Classer les erreurs : nuages, brume, poussière, soleil, autre |
| 3. Brancher YOLO dans la stack avec C | 3. Page « Statistiques » : alertes par jour, taux de faux positifs | 3. Choisir **l'angle d'amélioration** (voir plus bas) |

**Le soir :** le vrai modèle tourne dans le dashboard, et les erreurs du modèle sont documentées.

### J3 : construire l'apport (le cœur du projet)
| A : Backend | B : Dashboard | C : ML |
|---|---|---|
| 1. Si besoin : passer à PostgreSQL (comme `pyro-api`) | 1. Peaufiner l'UX : son ou notification à l'alerte, image zoomée, ordre de priorité | 1. Constituer le dataset d'adaptation : **200 à 500 images** de vos sources, annotées sur Roboflow |
| 2. **Aider C à annoter** (1 à 2 h) | 2. **Aider C à annoter** (1 à 2 h) | 2. Lancer le fine-tuning (`finetune.py train`, en commençant par `--fraction 0.25` pour un essai rapide) |
| 3. Rendre le seuil et le nombre d'images consécutives réglables depuis le dashboard | 3. Commencer les slides : problème, solution, architecture | 3. Pendant que ça tourne, régler le seuil et le nombre d'images consécutives sur les séquences de validation |

**Le soir :** un premier modèle fine-tuné existe, et l'annotation est terminée.

### J4 : mesurer et intégrer
| A : Backend | B : Dashboard | C : ML |
|---|---|---|
| 1. (Bonus) Déployer la stack sur une VM cloud (cours de Cloud Computing !) | 1. Écrire le **scénario de démo** minute par minute (voir plus bas) | 1. **Comparer avant et après** sur le même jeu de test : mAP, faux positifs par heure, rappel |
| 2. Rejouer en boucle une vidéo de démo « parfaite » pour la soutenance | 2. Faire les graphiques avant/après avec C | 2. Exporter le meilleur modèle et le brancher (`YOLO_WEIGHTS`) |
| 3. Figer les versions et tester une installation propre depuis zéro | 3. Finir les slides | 3. Rédiger `ml/RESULTS.md` : méthode, chiffres, limites |

**Le soir : gel des fonctionnalités.** Après ça, on ne corrige plus que des bugs.

### J5 : préparer la soutenance
1. [ ] Matin : **2 répétitions complètes** de la démo et du pitch, chronométrées **(tous)**
2. [ ] Enregistrer une **vidéo de secours** de la démo, au cas où le wifi ou le Docker de la salle lâche **(B)**
3. [ ] Nettoyer le README, ajouter des captures d'écran et des schémas **(A)**
4. [ ] Publier la réutilisation sur data.gouv.fr (comme le demande le défi) **(B)**
5. [ ] Envoyer le lien du dépôt à Pyronear **(C)**

---

## 🔬 Angle d'amélioration ML (à choisir au J2, un seul !)

| Angle | Effort | Quand le choisir |
|---|---|---|
| **Adaptation à de nouvelles caméras** ⭐ | Annoter 200 à 500 images, faire 1 à 2 fine-tunings | Si le modèle Pyronear se dégrade nettement sur vos sources |
| **Réduction des faux positifs** | Ajouter des images négatives difficiles (nuages, brume), puis fine-tuning | Si le modèle détecte bien mais alerte trop souvent |
| **Réglage du seuil et de la logique temporelle** | Pas de GPU nécessaire : une recherche par grille sur les séquences | Plan B si Kaggle ou le fine-tuning posent problème |

Le temps GPU est limité : prévoyez **au maximum 3 à 5 entraînements dans la semaine**. Pyronear
entraîne en `imgsz=1024`, ce qui est lent ; faites vos essais en 640.

---

## 🎬 Scénario de démo (environ 4 min)

1. **Le problème** (30 s) : 120 000 ha brûlés, et chaque minute de détection gagnée compte.
2. **Le dashboard en direct** (1 min) : la carte, les caméras en ligne, les flux.
3. **Une alerte arrive** (1 min) : la vidéo de départ de feu se déclenche, le cadre rouge apparaît, l'alerte s'affiche, le pompier la confirme.
4. **Un faux positif** (30 s) : un nuage déclenche une alerte, le pompier la signale, et elle part dans les données d'entraînement.
5. **Les chiffres** (1 min) : la comparaison avant/après du fine-tuning sur nos caméras.
6. **La suite** (30 s) : ré-entraînement automatique, intégration à `pyro-api`, déploiement.

---

## 🚫 Ce qu'on ne fait PAS

- Pas de compte utilisateur ni d'authentification
- Pas de modèle temporel complexe (Pyronear y travaille dans `vision-rd`)
- Pas d'images satellites ni de calcul de score de risque météo : c'est un autre projet
- Pas de refonte du dashboard en React : Streamlit suffit pour la démo

## ⚠️ Risques et plans B

| Risque | Plan B |
|---|---|
| Pas de GPU, ou Kaggle bloqué | Choisir l'angle « seuil et logique temporelle », sans GPU |
| Aucune webcam publique exploitable | Vidéos `.mp4` en boucle et séquences `pyro-sdis` |
| Le modèle fine-tuné ne fait pas mieux | C'est un résultat ! Présenter honnêtement l'analyse d'erreurs |
| Le Docker de la salle de soutenance plante | La vidéo de secours enregistrée au J5 |
| YOLO trop lent sur CPU | Utiliser `yolo11n`, `imgsz=640`, ou `INTERVAL=15` |
