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
minimale, donc 0 pour un carreau sans forêt ni WUI). Avec plusieurs
départements, les rangs sont calculés sur l'ensemble des carreaux : les scores
sont comparables d'un département à l'autre (et changent si l'ensemble change).
Un carreau de frontière présent dans deux fichiers n'est gardé que dans le
département où ``frac_dans_dept`` est la plus grande.
La combinaison des deux sous-scores se fait dans le dashboard, pour pouvoir
régler les poids. Sans météo, ce score décrit une sensibilité du terrain,
pas une probabilité.

    python ml/build_static_risk.py --features static_features_33.gpkg static_features_40.gpkg --out risk-data
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
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
        score += weight / total * indicator(table[column], kind)
    return (100 * score).round(1), missing


def indicator(values: pd.Series, kind: str) -> pd.Series:
    """Indicateur 0-1 : fraction bornée, ou rang pour les grandeurs non bornées."""
    x = values.astype(float)
    return percentile_rank(x) if kind == "pct" else x.fillna(0).clip(0, 1)


def sub_scores(table: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    combustible, miss_c = pillar(table, COMBUSTIBLE)
    humain, miss_h = pillar(table, HUMAIN)
    return pd.DataFrame({"s_combustible": combustible, "s_humain": humain}), {
        "colonnes_absentes": miss_c + miss_h,
        "taux_valeurs_manquantes": {c: round(float(table[c].isna().mean()), 4)
                                   for c, _, _ in COMBUSTIBLE + HUMAIN if c in table}}


# --- Régression logistique sur l'historique BDIFF (feux localisés à la commune) ---

def load_bdiff(folder: Path) -> pd.DataFrame:
    """Exports CSV du portail BDIFF (ml/download_bdiff.py) -> (code_insee, annee), un feu par ligne."""
    import io

    frames = []
    for path in sorted(folder.glob("*.csv")):
        lines = path.read_text(encoding="utf-8").splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("Année;"))
        frames.append(pd.read_csv(io.StringIO("\n".join(lines[start:])), sep=";", dtype=str))
    if not frames:
        raise FileNotFoundError(f"Aucun export BDIFF (*.csv) dans {folder}")
    fires = pd.concat(frames, ignore_index=True).drop_duplicates(["Année", "Numéro"])
    return pd.DataFrame({"code_insee": fires["Code INSEE"].str.strip(), "annee": fires["Année"].astype(int)})


def design_matrix(table: pd.DataFrame) -> pd.DataFrame:
    """Les indicateurs 0-1 du score expert, mêmes transformations, pour comparer les poids."""
    return pd.DataFrame({c: indicator(table[c], k) for c, _, k in COMBUSTIBLE + HUMAIN
                         if c in table.columns}, index=table.index)


def commune_table(X: pd.DataFrame, cells: pd.DataFrame, fires: pd.DataFrame, years) -> pd.DataFrame:
    """Une ligne par commune : indicateurs moyens de ses carreaux, surface, années avec ≥ 1 feu.

    Les carreaux sont rattachés à la commune de leur centroïde ; une commune sans
    carreau (trop petite) est ignorée, ainsi que ses feux.
    """
    years = list(years)
    table = X.assign(code_insee=cells["code_insee"].values, dept=cells["dept"].values, n=1)
    communes = table.groupby("code_insee").agg({**{c: "mean" for c in X.columns}, "dept": "first", "n": "sum"})
    communes["log_surface"] = np.log(communes.pop("n").astype(float))  # 0 pour un carreau seul
    fires = fires[fires["annee"].isin(years)]
    communes["annees_feu"] = fires.groupby("code_insee")["annee"].nunique().reindex(communes.index, fill_value=0)
    communes["feux"] = fires.groupby("code_insee").size().reindex(communes.index, fill_value=0)
    communes["annees"] = len(years)
    return communes


def _expand(communes: pd.DataFrame, features):
    """Vraisemblance binomiale commune × année : une ligne « feu » et une « sans feu », pondérées."""
    pos = communes.assign(y=1, w=communes["annees_feu"])
    neg = communes.assign(y=0, w=communes["annees"] - communes["annees_feu"])
    rows = pd.concat([pos, neg])
    rows = rows[rows["w"] > 0]
    return rows[features], rows["y"], rows["w"], rows.index.to_series(index=rows.index)


def fit_logistic(communes: pd.DataFrame, features, expert_col="expert", folds=5, seed=0) -> tuple:
    """Régression logistique P(≥ 1 feu dans l'année) + validation croisée par communes et par département."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    def model():
        return LogisticRegression(C=10.0, max_iter=5000)

    variants = {"modele": features, "surface_seule": ["log_surface"],
                "score_expert_et_surface": [expert_col, "log_surface"]}

    def cross_validated(split):
        scores = {}
        for name, cols in variants.items():
            oof = pd.Series(np.nan, index=communes.index)
            for test_ids in split:
                train = communes.drop(index=test_ids)
                Xt, yt, wt, _ = _expand(train, cols)
                oof[test_ids] = model().fit(Xt, yt, sample_weight=wt).predict_proba(communes.loc[test_ids, cols])[:, 1]
            Xa, ya, wa, ids = _expand(communes, cols)
            scores[name] = round(roc_auc_score(ya, oof[ids.values].values, sample_weight=wa), 3)
        return scores

    rng = np.random.default_rng(seed)
    ids = communes.index.to_numpy().copy()
    rng.shuffle(ids)
    metrics = {
        "communes": int(len(communes)), "communes_annees": int(communes["annees"].sum()),
        "communes_annees_avec_feu": int(communes["annees_feu"].sum()), "feux_rattaches": int(communes["feux"].sum()),
        "auc_communes_inconnues": cross_validated(np.array_split(ids, folds)),
    }
    depts = sorted(communes["dept"].unique())
    if len(depts) >= 3:
        metrics["auc_departement_inconnu"] = cross_validated([communes.index[communes["dept"] == d] for d in depts])
    X, y, w, _ = _expand(communes, features)
    final = model().fit(X, y, sample_weight=w)
    info = {"intercept": round(float(final.intercept_[0]), 3),
            "coefficients": {c: round(float(v), 3) for c, v in zip(features, final.coef_[0])}, **metrics}
    return final, info


def dedupe_border_cells(table: pd.DataFrame) -> pd.DataFrame:
    """Un carreau par identifiant DFCI : le département qui en couvre la plus grande part."""
    if "id_carreau_dfci" not in table.columns:
        return table
    frac = table["frac_dans_dept"] if "frac_dans_dept" in table.columns else pd.Series(0.0, index=table.index)
    order = table.assign(_frac=frac.fillna(0)).sort_values(["_frac", "dept"], ascending=[False, True])
    return table.loc[order.drop_duplicates("id_carreau_dfci").index.sort_values()]


def load_cells(paths, grid_path=None):
    """Join analytical Parquet to its grid by IDs, never by row position."""
    import geopandas as gpd

    parts = []
    for path in paths:
        if path.suffix.lower() == ".parquet":
            if grid_path is None:
                raise ValueError("Une table Parquet nécessite --grid (maillage GeoParquet).")
            table = pd.read_parquet(path)
            grid = gpd.read_parquet(grid_path).to_crs("EPSG:2154")
            keys = ["cell_id", "id_carreau_dfci", "departement"]
            for name, frame in (("table", table), ("maillage", grid)):
                if frame[keys].isna().any().any() or frame.cell_id.duplicated().any() or frame.id_carreau_dfci.duplicated().any():
                    raise ValueError(f"Identifiants absents ou dupliqués dans {name}")
            check = table[keys].merge(grid[keys], on=keys, how="outer", indicator=True, validate="one_to_one")
            if not check["_merge"].eq("both").all():
                raise ValueError("La table et le maillage ne couvrent pas exactement les mêmes cellules/départements.")
            part = grid[keys + ["geometry"]].merge(table, on=keys, validate="one_to_one")
        else:
            part = gpd.read_file(path).to_crs("EPSG:2154")
        part["dept"] = (part["departement"].astype(str) if "departement" in part
                        else path.stem.removeprefix("static_features_"))
        parts.append(part)
    cells = dedupe_border_cells(pd.concat(parts, ignore_index=True)).reset_index(drop=True)
    return gpd.GeoDataFrame(cells, geometry="geometry", crs="EPSG:2154")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--features", required=True, nargs="+", type=Path, help="GeoPackage départementaux ou table nationale Parquet")
    parser.add_argument("--grid", type=Path, help="Maillage GeoParquet associé à la table nationale")
    parser.add_argument("--exclude", nargs="*", default=[], choices=[c for c, _, _ in COMBUSTIBLE + HUMAIN],
                        help="Indicateurs exclus du calcul ; poids restants renormalisés")
    parser.add_argument("--out", default=Path("risk-data"), type=Path)
    parser.add_argument("--bdiff", type=Path, metavar="DOSSIER",
                        help="Exports BDIFF (ml/download_bdiff.py) : ajoute la régression logistique (couche p_feu)")
    parser.add_argument("--annees", default="2006-2024", help="Période BDIFF, ex. 2006-2024")
    args = parser.parse_args()

    import geopandas as gpd  # import tardif : les tests n'en ont pas besoin

    cells = load_cells(args.features, args.grid)
    cells = cells.drop(columns=args.exclude, errors="ignore")
    scores, info = sub_scores(cells)
    if info["colonnes_absentes"]:
        print("Colonnes absentes (poids renormalisés) :", ", ".join(info["colonnes_absentes"]))

    out = gpd.GeoDataFrame(scores, geometry=cells.geometry, crs=cells.crs).to_crs("EPSG:4326")
    out.insert(0, "id", cells.get("id_carreau_dfci", pd.Series(cells.index.astype(str))).astype(str))
    out.insert(1, "commune", cells.get("nom_commune", pd.Series("", index=cells.index)).fillna(""))
    out.insert(2, "dept", cells["dept"])
    for column in DETAILS:
        if column in cells.columns:
            out[column] = cells[column].astype(float).round(3)
    out.geometry = out.geometry.simplify(1e-5)

    model_info = None
    if args.bdiff:
        first, last = (int(v) for v in args.annees.split("-"))
        X = design_matrix(cells)
        X["expert"] = (scores["s_combustible"] * (0.6 + 0.4 * scores["s_humain"] / 100) / 100).values
        features = [c for c in X.columns if c != "expert"] + ["log_surface"]
        communes = commune_table(X, cells, load_bdiff(args.bdiff), range(first, last + 1))
        model, model_info = fit_logistic(communes, features)
        model_info = {"cible": f"≥ 1 feu BDIFF dans l'année (commune), {args.annees}",
                      "unite_prediction": "carreau DFCI 2 km (log_surface = 0)", **model_info}
        # Application au carreau : ses propres indicateurs, surface d'un carreau.
        out["p_feu"] = (100 * model.predict_proba(X[features[:-1]].assign(log_surface=0.0))[:, 1]).round(2)
        print(json.dumps(model_info, ensure_ascii=False, indent=2))

    args.out.mkdir(parents=True, exist_ok=True)
    depts = sorted(out["dept"].unique())
    common = {
        "departements_de_reference": depts, "carreaux_de_reference": len(out),
        "sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in args.features + ([args.grid] if args.grid else [])},
        "indicateurs_exclus": args.exclude,
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "formules": {"combustible": COMBUSTIBLE, "humain": HUMAIN}, **info,
        **({"regression_logistique": model_info} if model_info else {}),
    }
    for dept in depts:
        subset = out[out["dept"] == dept]
        target = args.out / f"risque_statique_{dept}.geojson"
        tmp = target.with_suffix(".tmp")
        tmp.write_text(subset.to_json(drop_id=True, to_wgs84=False), encoding="utf-8")
        tmp.replace(target)
        meta = {"departement": dept, "carreaux": len(subset), **common}
        (args.out / f"risque_statique_{dept}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{dept} : {len(subset)} carreaux -> {target}")
    # Fichiers d'un ancien calcul hors de cet ensemble : leurs rangs ne sont plus comparables.
    for stale in args.out.glob("risque_statique_*.geojson"):
        if stale.stem.removeprefix("risque_statique_") not in depts:
            print(f"Attention : {stale.name} vient d'un autre calcul (rangs non comparables)")


if __name__ == "__main__":
    main()
