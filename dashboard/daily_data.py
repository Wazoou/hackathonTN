"""Risque du jour par maille : modèle publié par ml/build_daily_risk.py, sans dépendance Streamlit."""
import math

# Classes de probabilité de départ dans la journée, pour une maille de 2 km (pour 10 000).
DAY_BOUNDS = [0, 0.5, 2, 5, 15, 50]
DAY_LABELS = ["Très faible", "Faible", "Modéré", "Élevé", "Très élevé"]
DAY_COLORS = [(255, 255, 204), (254, 217, 118), (253, 141, 60), (227, 26, 28), (128, 0, 38)]
# Classes usuelles de danger météo FWI (repères indicatifs, ajustés localement par Météo-France).
FWI_CLASSES = [(0, "faible"), (5, "modéré"), (12, "élevé"), (21, "très élevé"), (34, "extrême")]


def variables(indices, log_terrain):
    """Variables du modèle : risque de terrain de la commune et indices FWI de sa station ce jour-là."""
    return {"log_terrain": log_terrain, "ffmc_100": indices["ffmc"] / 100.0,
            **{f"log_{k}": math.log1p(max(indices[k], 0.0)) for k in ("dmc", "dc", "isi", "bui", "fwi")}}


def commune_probability(model, indices, log_terrain):
    """Probabilité qu'au moins un feu démarre dans la commune ce jour-là (0-1)."""
    values = variables(indices, log_terrain)
    z = model["intercept"] + sum(c * values[k] for k, c in model["coefficients"].items())
    return 1.0 / (1.0 + math.exp(-z))


def cell_probability(model, indices, log_terrain, share):
    """Part de la maille dans la probabilité de sa commune (somme des mailles = commune)."""
    return commune_probability(model, indices, log_terrain) * share


def day_class(per_10000):
    for i, high in enumerate(DAY_BOUNDS[1:]):
        if per_10000 < high:
            return i
    return len(DAY_LABELS) - 1


def day_color(per_10000, alpha=180):
    """Interpolation sur une échelle logarithmique entre les couleurs des classes."""
    x = math.log10(max(per_10000, 0.05))
    stops = [(math.log10(b), c) for b, c in zip([0.2, 1, 3, 8, 30], DAY_COLORS)]
    if x <= stops[0][0]:
        return [*stops[0][1], alpha]
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if x <= x1:
            t = (x - x0) / (x1 - x0)
            return [round(a + t * (b - a)) for a, b in zip(c0, c1)] + [alpha]
    return [*stops[-1][1], alpha]


def fwi_class(value):
    label = FWI_CLASSES[0][1]
    for low, name in FWI_CLASSES:
        if value >= low:
            label = name
    return label


def commune_probabilities(model, z_weather, log_terrain):
    """Vectorisé : z_weather (jours × communes, partie météo + constante) et log_terrain (communes)."""
    import numpy as np
    z = z_weather + model["coefficients"]["log_terrain"] * np.asarray(log_terrain)[None, :]
    return 1.0 / (1.0 + np.exp(-z))


def weather_term(model, frame):
    """Constante + contribution météo du modèle, pour un tableau d'indices (pandas)."""
    import numpy as np
    total = np.full(len(frame), model["intercept"], dtype=float)
    for name, coef in model["coefficients"].items():
        if name == "log_terrain":
            continue
        if name == "ffmc_100":
            total += coef * frame["ffmc"].to_numpy() / 100.0
        else:
            total += coef * np.log1p(np.clip(frame[name.removeprefix("log_")].to_numpy(), 0, None))
    return total
