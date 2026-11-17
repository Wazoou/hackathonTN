"""Combinaison des sous-scores de risque statique, indépendante de Streamlit."""

# Classes affichées dans la légende (bornes basses incluses) et couleurs RGB.
CLASSES = [(0, "Très faible", (255, 255, 204)), (20, "Faible", (254, 217, 118)),
           (40, "Modéré", (253, 141, 60)), (60, "Élevé", (227, 26, 28)),
           (80, "Très élevé", (128, 0, 38))]
LAYERS = {"score": "Score de risque", "s_combustible": "Combustible et relief",
          "s_humain": "Pression humaine"}


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


def color(score, alpha=170):
    """Interpolation linéaire entre les couleurs des classes (centres de classe)."""
    stops = [(low + 10, rgb) for low, _, rgb in CLASSES]
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
        props["score"] = combine(props["s_combustible"], props["s_humain"], mode, poids_combustible)
        value = props[layer]
        props["valeur"] = value
        props["classe"] = risk_class(value)
        props["fill"] = color(value, alpha)
        for key in ("foret_frac", "resineux_frac", "wui_frac", "agri_frac"):
            if props.get(key) is not None:
                props[f"{key}_pct"] = f"{100 * props[key]:.0f} %"
        features.append({**feature, "properties": props})
    return {"type": "FeatureCollection", "features": features}
