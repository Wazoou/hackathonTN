"""Risque quotidien de départ de feu : terrain (couche p_feu) × météo du jour (FWI Météo-France).

Entrées
- ``risk-data/risque_statique_<dept>.geojson`` avec ``p_feu`` (``ml/build_static_risk.py --bdiff``) ;
- la table nationale des indicateurs (identifiant de maille -> code INSEE) ;
- les données climatologiques quotidiennes Météo-France par département
  (``ml/download_meteo.py``) : TX, UN, FFM, RR ;
- les exports BDIFF (``ml/download_bdiff.py``), dont la date de première alerte.

Méthode
1. Stations : celles qui ont TX, UN, FFM et RR au moins 80 % des jours. Un trou est
   comblé par la station retenue la plus proche qui a la mesure ce jour-là.
2. FWI quotidien par station (``ml/fwi.py``), calcul continu depuis le 1er janvier 2005.
3. Unité d'apprentissage : la commune-jour (1 si au moins un feu BDIFF ce jour-là).
   Variables : ``log_terrain`` = log du nombre annuel attendu de feux de la commune,
   déduit de p_feu de ses mailles (Σ −ln(1 − p)), et les indices de la station la plus
   proche du centre de la commune. Les jours sans feu sont échantillonnés (poids 1/taux).
4. Validation temporelle : apprentissage 2006-2018, test 2019-2024, puis modèle final
   sur 2006-2024.
5. Passage à la maille : la probabilité du jour est calculée pour la commune, puis répartie
   entre ses mailles au prorata de leur risque de terrain (−ln(1 − p_feu)). Appliquer le
   modèle maille par maille surestimerait le total (~1,7×), car le coefficient du terrain
   est inférieur à 1 ; la répartition garde la calibration communale.

    python ml/build_daily_risk.py --risk-data risk-data --features dfci_2km_features_france.parquet \
        --meteo ifm_plus/data/raw/meteo --bdiff ifm_plus/data/raw/manual/bdiff --departements 06 07 13 33 34 40 83
"""
import argparse
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

INDICES = ["ffmc", "dmc", "dc", "isi", "bui", "fwi"]
SEASON = ["saison_sin", "saison_cos", "saison_sin2", "saison_cos2"]
MODELS = {  # références d'abord ; le dernier est le modèle publié
    "terrain_seul": ["log_terrain"],
    "terrain_et_saison": ["log_terrain", *SEASON],
    "terrain_et_fwi": ["log_terrain", "log_fwi"],
    "terrain_saison_et_sous_indices": ["log_terrain", *SEASON, "ffmc_100", "log_dmc", "log_dc", "log_isi"],
    "terrain_et_sous_indices": ["log_terrain", "ffmc_100", "log_dmc", "log_dc", "log_isi"],
}
START = "2005-01-01"


def _fwi_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("fwi", Path(__file__).with_name("fwi.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- météo

def read_meteo(folder: Path, depts, start=START) -> pd.DataFrame:
    """Une ligne par station-jour : TX (°C), UN (%), vent (km/h), RR (mm)."""
    frames = []
    for dept in depts:
        main, other = [], []
        for path in sorted(folder.glob(f"Q_{dept}_*_RR-T-Vent.csv.gz")):
            main.append(pd.read_csv(path, sep=";", usecols=["NUM_POSTE", "NOM_USUEL", "LAT", "LON",
                                                             "AAAAMMJJ", "RR", "TX", "FFM"]))
        for path in sorted(folder.glob(f"Q_{dept}_*_autres-parametres.csv.gz")):
            other.append(pd.read_csv(path, sep=";", usecols=["NUM_POSTE", "AAAAMMJJ", "UN"]))
        if not main or not other:
            raise FileNotFoundError(f"Données Météo-France absentes pour le département {dept} dans {folder}")
        a, b = pd.concat(main), pd.concat(other)
        frames.append(a.merge(b, on=["NUM_POSTE", "AAAAMMJJ"], how="left").assign(dept=dept))
    data = pd.concat(frames, ignore_index=True)
    data["date"] = pd.to_datetime(data["AAAAMMJJ"].astype(str), format="%Y%m%d")
    data = data[data["date"] >= start].drop_duplicates(["NUM_POSTE", "date"])
    return pd.DataFrame({"station": data["NUM_POSTE"].astype(str).str.zfill(8), "nom": data["NOM_USUEL"],
                         "lat": data["LAT"], "lon": data["LON"], "dept": data["dept"], "date": data["date"],
                         "temp": data["TX"], "rh": data["UN"], "wind": data["FFM"] * 3.6, "rain": data["RR"]})


def select_stations(meteo: pd.DataFrame, min_share=0.8) -> pd.DataFrame:
    n_days = meteo["date"].nunique()
    counts = meteo.groupby("station")[["temp", "rh", "wind", "rain"]].count() / n_days
    keep = counts[counts.min(axis=1) >= min_share].index
    info = meteo[meteo["station"].isin(keep)].groupby("station")[["nom", "lat", "lon", "dept"]].first()
    return info.assign(completude=counts.loc[info.index].min(axis=1).round(3))


def distance_km(lat1, lon1, lat2, lon2):
    """Distance équirectangulaire, suffisante à l'échelle d'un département."""
    lat = np.radians((np.asarray(lat1)[:, None] + np.asarray(lat2)[None, :]) / 2)
    dx = np.radians(np.asarray(lon2)[None, :] - np.asarray(lon1)[:, None]) * np.cos(lat)
    dy = np.radians(np.asarray(lat2)[None, :] - np.asarray(lat1)[:, None])
    return 6371.0 * np.hypot(dx, dy)


def station_indices(meteo: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """FWI quotidien par station retenue, trous comblés par les stations voisines."""
    dates = pd.date_range(meteo["date"].min(), meteo["date"].max(), freq="D")
    ids = list(stations.index)
    sub = meteo[meteo["station"].isin(ids)]
    grids = {v: sub.pivot(index="date", columns="station", values=v).reindex(index=dates, columns=ids).to_numpy(copy=True)
             for v in ("temp", "rh", "wind", "rain")}
    order = np.argsort(distance_km(stations.lat, stations.lon, stations.lat, stations.lon), axis=1)[:, 1:]
    for values in grids.values():
        for j in range(len(ids)):
            for k in order[j][:5]:  # jusqu'à 5 voisines, de la plus proche à la plus lointaine
                gap = np.isnan(values[:, j])
                if not gap.any():
                    break
                values[gap, j] = values[gap, k]
    result = _fwi_module().run(grids["temp"], grids["rh"], grids["wind"], grids["rain"], dates.month.to_numpy())
    frame = pd.DataFrame({"date": np.repeat(dates, len(ids)), "station": np.tile(ids, len(dates))})
    for name in INDICES:
        frame[name] = result[name].ravel()
    return frame


# ---------------------------------------------------------------- feux, communes, modèle

def load_bdiff_dated(folder: Path) -> pd.DataFrame:
    frames = []
    for path in sorted(folder.glob("*.csv")):
        lines = path.read_text(encoding="utf-8").splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("Année;"))
        frames.append(pd.read_csv(io.StringIO("\n".join(lines[start:])), sep=";", dtype=str))
    fires = pd.concat(frames, ignore_index=True).drop_duplicates(["Année", "Numéro"])
    surface = pd.to_numeric(fires["Surface parcourue (m2)"], errors="coerce") / 1e4
    return pd.DataFrame({"code_insee": fires["Code INSEE"].str.strip(),
                         "date": pd.to_datetime(fires["Date de première alerte"]).dt.normalize(),
                         "surface_ha": surface.round(2)})


def transform(frame: pd.DataFrame) -> pd.DataFrame:
    """Indices -> variables du modèle (log1p pour les codes cumulatifs, très asymétriques)."""
    out = pd.DataFrame(index=frame.index)
    out["ffmc_100"] = frame["ffmc"] / 100.0
    for name in ("dmc", "dc", "isi", "bui", "fwi"):
        out[f"log_{name}"] = np.log1p(frame[name].clip(lower=0))
    if "date" in frame:  # saisonnalité (deux harmoniques du jour de l'année), pour les références
        angle = 2 * np.pi * (pd.to_datetime(frame["date"]).dt.dayofyear - 1) / 365.25
        out["saison_sin"], out["saison_cos"] = np.sin(angle), np.cos(angle)
        out["saison_sin2"], out["saison_cos2"] = np.sin(2 * angle), np.cos(2 * angle)
    return out


def sample_commune_days(communes: pd.DataFrame, fire_days: pd.DataFrame, dates, rate, seed=0) -> pd.DataFrame:
    """Tous les jours avec feu, et une fraction ``rate`` des autres jours (poids 1/rate)."""
    rng = np.random.default_rng(seed)
    n = len(communes) * len(dates)
    picks = rng.random(n) < rate
    rows = pd.DataFrame({"code_insee": np.repeat(communes.index.to_numpy(), len(dates))[picks],
                         "date": np.tile(np.asarray(dates), len(communes))[picks]})
    positives = fire_days[["code_insee", "date"]].drop_duplicates().assign(y=1, w=1.0)
    rows = rows.merge(positives[["code_insee", "date"]], how="left", indicator=True)
    rows = rows[rows["_merge"] == "left_only"].drop(columns="_merge").assign(y=0, w=1.0 / rate)
    return pd.concat([positives, rows], ignore_index=True)


def fit_daily(table: pd.DataFrame, split_year: int):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, roc_auc_score

    train = table["date"].dt.year <= split_year
    metrics, models = {}, {}
    for name, cols in MODELS.items():
        model = LogisticRegression(C=10.0, max_iter=5000)
        model.fit(table.loc[train, cols], table.loc[train, "y"], sample_weight=table.loc[train, "w"])
        pred = model.predict_proba(table.loc[~train, cols])[:, 1]
        y, w = table.loc[~train, "y"], table.loc[~train, "w"]
        metrics[name] = {"auc": round(roc_auc_score(y, pred, sample_weight=w), 3),
                         "pr_auc": round(average_precision_score(y, pred, sample_weight=w), 4)}
        final = LogisticRegression(C=10.0, max_iter=5000).fit(table[cols], table["y"], sample_weight=table["w"])
        models[name] = {"variables": cols, "intercept": round(float(final.intercept_[0]), 4),
                        "coefficients": {c: round(float(v), 4) for c, v in zip(cols, final.coef_[0])}}
    return models, metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--risk-data", type=Path, default=Path("risk-data"))
    parser.add_argument("--features", type=Path, required=True, help="Table nationale (id_carreau_dfci, code_insee)")
    parser.add_argument("--meteo", type=Path, required=True)
    parser.add_argument("--bdiff", type=Path, required=True)
    parser.add_argument("--departements", nargs="+", required=True)
    parser.add_argument("--fin-apprentissage", type=int, default=2018, help="Dernière année d'apprentissage")
    parser.add_argument("--taux-negatifs", type=float, default=0.02)
    args = parser.parse_args()

    # Mailles du pilote : p_feu (déjà publié), commune et centre.
    cells = []
    for dept in args.departements:
        path = args.risk_data / f"risque_statique_{dept}.geojson"
        for f in json.loads(path.read_text(encoding="utf-8"))["features"]:
            p = f["properties"]
            if p.get("p_feu") is None:
                raise ValueError(f"{path.name} sans p_feu : lancer build_static_risk.py --bdiff")
            cells.append({"id": p["id"], "dept": dept, "p_feu": p["p_feu"]})
    cells = pd.DataFrame(cells)
    table = pd.read_parquet(args.features, columns=["id_carreau_dfci", "code_insee", "lon", "lat"])
    cells = cells.merge(table.rename(columns={"id_carreau_dfci": "id"}), on="id", how="left", validate="one_to_one")
    if cells["code_insee"].isna().any():
        raise ValueError("Mailles sans commune dans la table des indicateurs")
    cells["rate"] = -np.log1p(-cells["p_feu"].clip(upper=99.9) / 100.0)  # feux attendus par an
    communes = cells.groupby("code_insee").agg(rate=("rate", "sum"), lon=("lon", "mean"), lat=("lat", "mean"),
                                               dept=("dept", "first"))
    communes["log_terrain"] = np.log(communes["rate"])

    # Météo et FWI.
    meteo = read_meteo(args.meteo, args.departements)
    stations = select_stations(meteo)
    print(f"{len(stations)} stations retenues sur {meteo['station'].nunique()} ;"
          f" du {meteo['date'].min():%d/%m/%Y} au {meteo['date'].max():%d/%m/%Y}")
    indices = station_indices(meteo, stations)
    sid = np.array(stations.index)
    communes["station"] = sid[distance_km(communes.lat, communes.lon, stations.lat, stations.lon).argmin(axis=1)]
    cells["part"] = cells["rate"] / cells["code_insee"].map(communes["rate"])

    # Feux datés et échantillon commune-jour.
    fires = load_bdiff_dated(args.bdiff)
    fires = fires[fires["code_insee"].isin(communes.index)]
    last_bdiff = fires["date"].max()
    dates = pd.date_range("2006-01-01", min(last_bdiff, indices["date"].max()), freq="D")
    fires_in = fires[fires["date"].isin(dates)]
    sample = sample_commune_days(communes, fires_in, dates, args.taux_negatifs)
    sample = sample.merge(communes[["log_terrain", "station"]], left_on="code_insee", right_index=True)
    sample = sample.merge(indices, on=["date", "station"], how="left").dropna(subset=INDICES)
    sample = pd.concat([sample, transform(sample)], axis=1)
    print(f"{int(sample['y'].sum())} communes-jours avec feu, {int((sample['y'] == 0).sum())} sans feu échantillonnés")
    models, metrics = fit_daily(sample, args.fin_apprentissage)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    # Sorties pour le dashboard.
    out = args.risk_data / "meteo"
    out.mkdir(parents=True, exist_ok=True)
    keep = indices.dropna(subset=["fwi"]).copy()
    keep[INDICES] = keep[INDICES].round(2)
    keep.assign(date=keep["date"].dt.strftime("%Y-%m-%d")).to_csv(out / "indices.csv.gz", index=False)
    stations.reset_index().to_json(out / "stations.json", orient="records", force_ascii=False, indent=1)
    (out / "mailles.json").write_text(json.dumps(
        {i: [c, round(float(p), 6)] for i, c, p in zip(cells["id"], cells["code_insee"], cells["part"])}), encoding="utf-8")
    (out / "communes.json").write_text(json.dumps(
        {c: [r.station, round(float(r.log_terrain), 6)] for c, r in communes.iterrows()}), encoding="utf-8")
    names = pd.concat([pd.read_parquet(args.features, columns=["code_insee", "nom_commune"])]).drop_duplicates("code_insee")
    fires_out = fires.merge(communes[["lon", "lat"]], left_on="code_insee", right_index=True)
    fires_out = fires_out.merge(names, on="code_insee", how="left")
    fires_out.assign(date=fires_out["date"].dt.strftime("%Y-%m-%d"), lon=fires_out["lon"].round(4),
                     lat=fires_out["lat"].round(4)).to_csv(out / "feux_bdiff.csv.gz", index=False)
    meta = {
        "departements": args.departements, "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "meteo": {"source": "Météo-France, données climatologiques de base quotidiennes (data.gouv.fr)",
                  "variables": "TX (°C), UN (%), FFM (m/s -> km/h), RR (mm)",
                  "stations": len(stations), "debut": f"{indices['date'].min():%Y-%m-%d}",
                  "fin": f"{indices['date'].max():%Y-%m-%d}", "fwi": "Van Wagner (1987), calcul continu"},
        "bdiff": {"feux": int(len(fires_in)), "communes_jours_avec_feu": int(sample["y"].sum()),
                  "fin": f"{last_bdiff:%Y-%m-%d}"},
        "apprentissage": {"unite": "commune-jour", "validation": f"apprentissage 2006-{args.fin_apprentissage}, "
                          f"test {args.fin_apprentissage + 1}-{last_bdiff.year}", "taux_negatifs": args.taux_negatifs,
                          "auc_test": metrics},
        "modele_retenu": "terrain_et_sous_indices", "modeles": models,
    }
    (out / "modele.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
