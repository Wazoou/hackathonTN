# IFM+ : couverture France métropolitaine

## Périmètre

La configuration active couvre les **96 départements métropolitains**, y compris
**2A et 2B**, sans outre-mer. La Gironde n’est plus un filtre implicite.
`--departement 33` permet un essai local ; `--departements 33,40` un sous-ensemble.
`--perimetre france_metro` ou `--departements all` demande la métropole entière,
même si un ancien YAML contient une liste locale. Les codes sont validés,
dédoublonnés et ordonnés ; un sous-ensemble ne porte jamais le nom d’une sortie nationale.

## Acquisition et calcul

Depuis `ifm_plus/`, après installation de `requirements.txt` dans un environnement Python :

```bash
# Référentiels nationaux, puis maillage exploitable indépendamment du score
python scripts/01_download_data.py --layers dfci,admin,tmja
python scripts/00_build_grid.py

# Couches lourdes : reprenables, plusieurs heures et plusieurs dizaines de Go transférés
python scripts/10_bulk_download.py --layers all
python scripts/11_build_features_france.py --no-fetch

# Vérifier l'état réel des fichiers et de la table assemblée
python scripts/12_check_coverage.py --require-complete
# Optionnel : vérifier également les catalogues IGN en ligne
python scripts/12_check_coverage.py --catalog
```

Les données sont locales dans `ifm_plus/data/`, ignorées par Git. Les archives
brutes temporaires sont supprimées après conversion, sauf avec `--keep-raw`.
Un garde-fou disque est appliqué avant chaque archive. Le traitement conserve
les couches normalisées et les caches départementaux pour reprendre une interruption.
La voie WFS (`01 --layers all`, puis `02`) reste utilisable, mais la voie bulk
ci-dessus est recommandée pour les volumes nationaux.

Sorties :

- `data/processed/dfci_2km_grid_france_metro.parquet` : **GeoParquet** des polygones,
  identifiants DFCI, département, centroïde et surface. **Pas de score inventé**.
- `data/processed/dfci_2km_grid_france_metro.json` : compte des cellules par département.
- `data/processed/dfci_2km_features_france.parquet` : table des facteurs statiques,
  publiée seulement après acquisition et calcul complets des couches requises.
- `data/processed/coverage_france_metro.json` : état réel des fichiers locaux,
  manques par couche/département et, avec `--catalog`, disponibilité des archives IGN.

Le calcul refuse une couche absente, un département manquant, une cellule
manquante ou dupliquée, ou une association d’identifiants incohérente.
Une couche correctement téléchargée mais vide est distincte d’une couche absente.
`--skip` est réservé à un calcul exploratoire explicitement incomplet : les
omissions restent indiquées dans les métadonnées. Un ancien cache de relief bulk
sans `mosaic_version: 2` est recalculé ; un ancien cache de maillage limité au 33
est reconstruit à l’échelle nationale.

## Audit du 17 novembre 2026

| Source | Couverture vérifiée | Limite / acquisition |
|---|---|---|
| Carroyage DFCI 2 km | 339 264 mailles brutes ; **139 842 terrestres**, affectées aux **96 départements** | Mailles maritimes exclues ; un seul département propriétaire par maille |
| Admin Express | **96 départements**, **34 746 communes** téléchargés | Contours nationaux ; emprise calculée pour chaque département et pour toute la métropole |
| TMJA | **10 373 sections-années** téléchargées (2018, 2019, 2022, 2023) | Réseau routier national seulement ; ni toutes les routes, ni toutes les années 2018–2023 |
| BD Forêt | Archives trouvées pour **96/96 départements** | Disponibilité au catalogue ne signifie pas téléchargement local achevé |
| BD TOPO (routes, habitat, bâtiments) | Archives trouvées pour **96/96 départements** | Une archive départementale est extraite puis normalisée ; les éditions sont tracées |
| RPG | Archives trouvées pour **13/13 régions** | Chaque région est découpée vers ses départements ; Corse comprise |
| Relief Copernicus | Tuiles choisies à partir de toutes les emprises demandées | Mosaïque mono-bande ; dimensions réelles lues dans les en-têtes, y compris au-delà de 50° N |
| Météo EWDS | La requête utilise l’emprise nationale, Corse incluse | Accès utilisateur et licence requis ; absent tant que non téléchargé |
| FIRMS | La requête utilise l’emprise nationale | Clé requise ; le fetcher existant ne couvre que `day_range` jours en fin de période, pas tout 2018–2023 |
| BDIFF | Instructions d’export passées à la métropole | Export manuel à déposer dans `data/raw/manual/bdiff_france_metro/` ; le portail n’est pas téléchargé automatiquement |

Les chiffres de disponibilité du catalogue ne sont **pas** des preuves que
les fichiers sont déjà tous présents sur la machine. Le rapport `12` distingue
explicitement disponibilité distante, fichiers locaux et table statique complète.
Les scripts de météo jointe aux cellules, de labels et de calcul du score quotidien
restent à implémenter : élargir le maillage ne crée pas automatiquement ce score.

Sources vérifiées : [carroyage DFCI](https://www.data.gouv.fr/datasets/carroyage-dfci-2-km),
[catalogue BD Forêt IGN](https://data.geopf.fr/telechargement/resource/BDFORET),
[catalogue BD TOPO IGN](https://data.geopf.fr/telechargement/resource/BDTOPO),
[catalogue RPG IGN](https://data.geopf.fr/telechargement/resource/RPG),
[format des tuiles Copernicus](https://copernicus-dem-30m.s3.amazonaws.com/readme.html).

## Vérifications de non-régression

```bash
python -m unittest discover -s tests -v
```

Les tests couvrent le périmètre national par défaut, les options locales,
les codes corses, les identifiants, les carreaux côtiers/frontaliers, le refus
des tables partielles, les couches absentes et la mosaïque de relief à largeurs variables.

Validation de bout en bout réalisée hors Gironde : **Corse-du-Sud (2A)**,
**1 141 carreaux**, toutes les couches statiques bulk acquises et calculées,
**75 variables** (80 colonnes avec les identifiants). Le TMJA est manquant
sur cet échantillon : il reste `NaN`, jamais interprété comme une pression
routière nulle. Les **14 tests** de non-régression passent.

Pour la longue acquisition lancée sur cette machine, un instantané du code et
une configuration avec chemins absolus sont conservés sous `data/runtime/`.
Cela permet au traitement de continuer même si la branche Git est changée.
Le suivi se fait dans `data/logs/national.log` et `data/logs/national_status.json`.
Après une erreur, les commandes d’acquisition ci-dessus reprennent les fichiers
manquants ; ne pas lancer deux acquisitions simultanées sur les mêmes fichiers.
