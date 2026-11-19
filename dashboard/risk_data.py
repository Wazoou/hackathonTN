"""Combinaison des sous-scores de risque statique, indépendante de Streamlit."""

# Classes affichées dans la légende (bornes basses incluses) et couleurs RGB.
CLASSES = [(0, "Très faible", (255, 255, 204)), (20, "Faible", (254, 217, 118)),
           (40, "Modéré", (253, 141, 60)), (60, "Élevé", (227, 26, 28)),
           (80, "Très élevé", (128, 0, 38))]
NATURAL_CLASSES = [(0, "Très faible", (237, 248, 233)), (20, "Faible", (186, 228, 179)),
                   (40, "Modéré", (116, 196, 118)), (60, "Élevé", (49, 163, 84)),
                   (80, "Très élevé", (0, 109, 44))]
HUMAN_CLASSES = [(0, "Très faible", (242, 240, 247)), (20, "Faible", (203, 201, 226)),
                 (40, "Modéré", (158, 154, 200)), (60, "Élevé", (117, 107, 177)),
                 (80, "Très élevé", (84, 39, 143))]
LAYERS = {"p_feu": "Probabilité annuelle d’incendie",
          "score": "Indice de sensibilité territoriale",
          "s_combustible": "Caractéristiques du milieu naturel",
          "s_humain": "Facteurs d’influence humaine"}
# Bornes des classes pour la probabilité (% par an et par carreau), alignées sur CLASSES.
PROBA_BOUNDS = [0, 2, 5, 10, 20, 40]


def to_scale(value, layer):
    """Ramène la valeur sur l'échelle 0-100 des classes (linéaire par morceaux pour p_feu)."""
    if layer != "p_feu":
        return value
    for i, (low, high) in enumerate(zip(PROBA_BOUNDS, PROBA_BOUNDS[1:])):
        if value < high:
            return 20 * i + 20 * (value - low) / (high - low)
    return 100


def class_ranges(layer):
    """Libellés de légende : (nom, borne basse, borne haute, couleur)."""
    if layer == "p_feu":
        bounds = PROBA_BOUNDS[:-1] + [None]
        return [(name, f"{lo} %", f"{hi} %" if hi is not None else None, rgb)
                for (_, name, rgb), lo, hi in zip(CLASSES, bounds, bounds[1:] + [None])]
    palette = (NATURAL_CLASSES if layer == "s_combustible" else
               HUMAN_CLASSES if layer == "s_humain" else CLASSES)
    return [(name, str(low), str(low + 20 if low < 80 else 100), rgb)
            for low, name, rgb in palette]


def combine(s_combustible, s_humain, mode="multiplicatif", poids_combustible=0.6):
    """Score 0-100.

    multiplicatif : S_comb × (0,6 + 0,4·S_hum/100) — sans combustible, pas de risque,
    la pression humaine module le score sans pouvoir le créer (centre-ville = faible).
    additif : moyenne pondérée des deux piliers.
    """
    if mode == "multiplicatif":
        return round(s_combustible * (0.6 + 0.4 * s_humain / 100), 1)
    return round(poids_combustible * s_combustible + (1 - poids_combustible) * s_humain, 1)


def risk_class(score):
    label = CLASSES[0][1]
    for low, name, _ in CLASSES:
        if score >= low:
            label = name
    return label


def color(score, alpha=170, palette=CLASSES):
    """Interpolation linéaire entre les couleurs des classes (centres de classe)."""
    stops = [(low + 10, rgb) for low, _, rgb in palette]
    if score <= stops[0][0]:
        return [*stops[0][1], alpha]
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if score <= x1:
            t = (score - x0) / (x1 - x0)
            return [round(a + t * (b - a)) for a, b in zip(c0, c1)] + [alpha]
    return [*stops[-1][1], alpha]


def apply_scores(geojson, layer="score", mode="multiplicatif", poids_combustible=0.6, alpha=170):
    """Copie du GeoJSON avec score, classe et couleur de la couche choisie."""
    features = []
    for feature in geojson["features"]:
        props = dict(feature["properties"])
        props.setdefault("dept", "")
        props["score"] = combine(props["s_combustible"], props["s_humain"], mode, poids_combustible)
        value = props[layer]
        props["valeur"] = value
        scaled = to_scale(value, layer)
        props["classe"] = risk_class(scaled)
        props["fill"] = color(scaled, alpha)
        for key in ("foret_frac", "resineux_frac", "wui_frac", "agri_frac"):
            if props.get(key) is not None:
                props[f"{key}_pct"] = f"{100 * props[key]:.0f} %"
        features.append({**feature, "properties": props})
    return {"type": "FeatureCollection", "features": features}
