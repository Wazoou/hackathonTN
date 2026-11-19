# Complément de couverture du 19 novembre 2026

Le catalogue contient désormais 105 webcams, dont les 69 vues déjà validées,
conservées avec leur nom, leurs coordonnées et leur maille. Les 36 ajouts
élargissent la répartition aux 13 régions de France métropolitaine, Corse incluse.

## Répartition

| Région | Avant | Ajouts | Après |
| --- | ---: | ---: | ---: |
| Auvergne-Rhône-Alpes | 49 | 4 | 53 |
| Bourgogne-Franche-Comté | 0 | 4 | 4 |
| Bretagne | 0 | 1 | 1 |
| Centre-Val de Loire | 0 | 2 | 2 |
| Corse | 0 | 2 | 2 |
| Grand Est | 2 | 5 | 7 |
| Hauts-de-France | 0 | 2 | 2 |
| Île-de-France | 0 | 3 | 3 |
| Normandie | 0 | 3 | 3 |
| Nouvelle-Aquitaine | 1 | 5 | 6 |
| Occitanie | 9 | 3 | 12 |
| Pays de la Loire | 0 | 2 | 2 |
| Provence-Alpes-Côte d'Azur | 8 | 0 | 8 |
| **Total** | **69** | **36** | **105** |

Les régions proviennent de l'intersection des coordonnées avec les contours
départementaux du dépôt. Cette répartition mesure des points géographiques,
pas la surface effectivement visible depuis les caméras. Les Alpes restent
majoritaires puisque les caméras précédemment validées sont conservées.

## Choix des vues

Les recherches ont ciblé les zones éloignées des points existants. Les ajouts
privilégient les versants boisés, lisières, vallées et horizons dégagés. Quelques
vues rurales et de rives boisées complètent la couverture dans les régions où
les panoramas forestiers accessibles sont rares. Quatre vues du catalogue de
réserve initial ont été retenues après un nouveau contrôle.

Les images ont été récupérées, décodées et examinées visuellement, puis les
liens retenus revérifiés le 19 novembre 2026. Les réponses contenant seulement
un logo, une scène intérieure, un cadrage exclusivement céleste, une image
visiblement ancienne ou une image illisible n'ont pas été retenues.

Les catalogues OpenCCTV et les pages des diffuseurs Skaping et
Vision-Environnement ont servi à trouver les sources. Les liens actifs
correspondent à des images publiques stables ; aucune URL de flux à signature
temporaire n'est conservée. Les images restent fournies par leurs diffuseurs.
Un contrôle réussi confirme leur accessibilité à cet instant, sans garantir
une disponibilité continue ni la date exacte de prise de vue lorsque la source
ne la certifie pas. La sélection ne mesure pas les performances de YOLO.

## Coordonnées et reconstruction

`cameras.ajouts.csv` conserve pour chaque ajout le nom, l'URL d'image, les
coordonnées, leur provenance, le département, la région et l'heure du contrôle.
32 ajouts utilisent les coordonnées publiées par leur source. Les 4 vues
réintroduites depuis la réserve conservent leur position communale géocodée,
explicitement indiquée dans le fichier de provenance.

Le CSV actif inclut désormais `lat`, `lon` et `id_maille`. Le dashboard le lit
directement : le JSON local et le maillage brut ne sont pas nécessaires pour
consulter le catalogue après clonage. Le générateur utilise ces
coordonnées lorsqu'elles sont renseignées ; un nom ambigu ou plusieurs vues
d'une même commune ne sont ainsi pas déplacés lors d'une reconstruction.
Les lignes sans coordonnées gardent le fonctionnement antérieur par géocodage.
Les 105 points sont associés à une maille du maillage DFCI local.

Le dossier local `local-coverage-2026-11-19/`, exclu de Git par son propre
`.gitignore`, conserve le CSV et le JSON avant ajout, les preuves des contrôles
et les images de revue. Les sauvegardes du premier tri sont également conservées.
