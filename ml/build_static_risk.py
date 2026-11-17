"""Carte de risque statique (solution 1) à partir des features IFM+ de Manon.

Entrée : ``static_features_<dept>.gpkg`` produit par
``ifm_plus/scripts/02_build_static_features.py`` (branche ``manon``).
Sortie : ``<out>/risque_statique_<dept>.geojson`` (WGS84) et ses métadonnées.

Le script calcule deux sous-scores 0-100 par carreau DFCI 2 km, avec les
formules de ``ifm_plus/docs/modelisation_evaluation.md`` (§1.2) :

    S_combustible = 100 × (0,40·resineux_frac + 0,25·foret_frac
                         + 0,15·pct(lisiere_m_ha) + 0,10·pct(pente_moy_deg)
                         + 0,10·pin_frac)
    S_humain      = 100 × (0,40·pct(wui_frac) + 0,25·pct(route_ponderee_km)
                         + 0,20·pct(tmja_max) + 0,15·pct(agri_frac))

``pct`` est la part des carreaux strictement inférieurs (0 pour la valeur
minimale, donc 0 pour un carreau sans forêt ni WUI). La combinaison des deux
sous-scores se fait dans le dashboard, pour pouvoir régler les poids.
Sans météo, ce score décrit une sensibilité du terrain, pas une probabilité.

    python ml/build_static_risk.py --features static_features_33.gpkg --out risk-data
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# (colonne, poids, transformation) ; "frac" = fraction 0-1 utilisée telle quelle.
COMBUSTIBLE = [("resineux_frac", 0.40, "frac"), ("foret_frac", 0.25, "frac"),
               ("lisiere_m_ha", 0.15, "pct"), ("pente_moy_deg", 0.10, "pct"),
               ("pin_frac", 0.10, "frac")]
HUMAIN = [("wui_frac", 0.40, "pct"), ("route_ponderee_km", 0.25, "pct"),
          ("tmja_max", 0.20, "pct"), ("agri_frac", 0.15, "pct")]
# Indicateurs bruts recopiés pour les infobulles.
DETAILS = ["foret_frac", "resineux_frac", "wui_frac", "route_ponderee_km", "agri_frac", "pente_moy_deg"]


def percentile_rank(values: pd.Series) -> pd.Series:
    """Part des carreaux strictement inférieurs, dans [0, 1]. NaN -> 0."""
    clean = values.fillna(values.min() if values.notna().any() else 0)
    if len(clean) < 2:
        return pd.Series(0.0, index=values.index)
    return (clean.rank(method="min") - 1) / (len(clean) - 1)


def pillar(table: pd.DataFrame, terms) -> tuple[pd.Series, list[str]]:
    """Sous-score 0-100 ; les colonnes absentes sont retirées et les poids renormalisés."""
    present = [(c, w, t) for c, w, t in terms if c in table.columns]
    missing = [c for c, _, _ in terms if c not in table.columns]
    if not present:
        raise ValueError(f"Aucune colonne disponible parmi {[c for c, _, _ in terms]}")
    total = sum(w for _, w, _ in present)
    score = pd.Series(0.0, index=table.index)
    for column, weight, kind in present:
        x = table[column].astype(float)
        x = percentile_rank(x) if kind == "pct" else x.fillna(0).clip(0, 1)
        score += weight / total * x
    return (100 * score).round(1), missing


def sub_scores(table: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    combustible, miss_c = pillar(table, COMBUSTIBLE)
    humain, miss_h = pillar(table, HUMAIN)
    return pd.DataFrame({"s_combustible": combustible, "s_humain": humain}), {
        "colonnes_absentes": miss_c + miss_h}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--features", required=True, type=Path, help="static_features_<dept>.gpkg")
    parser.add_argument("--out", default=Path("risk-data"), type=Path)
    parser.add_argument("--dept", help="Code du département (déduit du nom de fichier par défaut)")
    args = parser.parse_args()

    import geopandas as gpd  # import tardif : les tests n'en ont pas besoin

    dept = args.dept or args.features.stem.removeprefix("static_features_")
    cells = gpd.read_file(args.features)
    scores, info = sub_scores(cells)
    if info["colonnes_absentes"]:
        print("Colonnes absentes (poids renormalisés) :", ", ".join(info["colonnes_absentes"]))

    out = gpd.GeoDataFrame(scores, geometry=cells.geometry, crs=cells.crs).to_crs("EPSG:4326")
    out.insert(0, "id", cells.get("id_carreau_dfci", pd.Series(cells.index.astype(str))).astype(str))
    out.insert(1, "commune", cells.get("nom_commune", pd.Series("", index=cells.index)).fillna(""))
    for column in DETAILS:
        if column in cells.columns:
            out[column] = cells[column].astype(float).round(3)
    out.geometry = out.geometry.simplify(1e-5)

    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f"risque_statique_{dept}.geojson"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(out.to_json(drop_id=True, to_wgs84=False), encoding="utf-8")
    tmp.replace(target)
    meta = {
        "departement": dept, "carreaux": len(out),
        "source": args.features.name,
        "source_sha256": hashlib.sha256(args.features.read_bytes()).hexdigest(),
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "formules": {"combustible": COMBUSTIBLE, "humain": HUMAIN},
        **info,
    }
    (args.out / f"risque_statique_{dept}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(out)} carreaux -> {target}")


if __name__ == "__main__":
    main()
