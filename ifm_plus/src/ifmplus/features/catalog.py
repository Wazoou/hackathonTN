"""Catalogue des features statiques (documentation embarquée).

Ce dictionnaire est exporté dans les métadonnées du jeu de features et sert
de référence unique pour les scripts de modélisation et l'interface SDIS.
"""

from __future__ import annotations

STATIC_FEATURES: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------
    # Identifiants et contexte
    # ------------------------------------------------------------------
    "id_carreau_dfci": {
        "famille": "identifiant",
        "source": "Carroyage DFCI 2 km",
        "unite": "-",
        "description": "Code DFCI du carreau 2 km (champ NOM du carroyage national).",
    },
    "code_insee": {
        "famille": "identifiant",
        "source": "Admin Express COG",
        "unite": "-",
        "description": "Code INSEE de la commune du centroïde du carreau.",
    },
    "nom_commune": {
        "famille": "identifiant",
        "source": "Admin Express COG",
        "unite": "-",
        "description": "Nom de la commune du centroïde du carreau.",
    },
    "frac_dans_dept": {
        "famille": "contexte",
        "source": "Admin Express COG",
        "unite": "0-1",
        "description": "Part de la surface du carreau située dans le département pilote.",
    },
    "area_ha": {
        "famille": "contexte",
        "source": "Carroyage DFCI 2 km",
        "unite": "ha",
        "description": "Surface du carreau (environ 400 ha).",
    },
    "x_centroid": {
        "famille": "contexte",
        "source": "Carroyage DFCI 2 km",
        "unite": "m",
        "description": "Abscisse Lambert-93 du centroïde du carreau.",
    },
    "y_centroid": {
        "famille": "contexte",
        "source": "Carroyage DFCI 2 km",
        "unite": "m",
        "description": "Ordonnée Lambert-93 du centroïde du carreau.",
    },
    "lon": {
        "famille": "contexte",
        "source": "Carroyage DFCI 2 km",
        "unite": "degrés",
        "description": "Longitude WGS84 du centroïde (jointure météo EWDS/AROME).",
    },
    "lat": {
        "famille": "contexte",
        "source": "Carroyage DFCI 2 km",
        "unite": "degrés",
        "description": "Latitude WGS84 du centroïde (jointure météo EWDS/AROME).",
    },
    # ------------------------------------------------------------------
    # Pilier combustible / relief
    # ------------------------------------------------------------------
    "foret_frac": {
        "famille": "combustible",
        "source": "BD Forêt V2",
        "unite": "0-1",
        "description": "Part du carreau couverte par une formation forestière.",
    },
    "resineux_frac": {
        "famille": "combustible",
        "source": "BD Forêt V2",
        "unite": "0-1",
        "description": "Part du carreau en peuplement de conifères (hors mélange).",
    },
    "feuillus_frac": {
        "famille": "combustible",
        "source": "BD Forêt V2",
        "unite": "0-1",
        "description": "Part du carreau en peuplement de feuillus (hors mélange).",
    },
    "mixte_frac": {
        "famille": "combustible",
        "source": "BD Forêt V2",
        "unite": "0-1",
        "description": "Part du carreau en peuplement mixte feuillus/conifères.",
    },
    "peupleraie_frac": {
        "famille": "combustible",
        "source": "BD Forêt V2",
        "unite": "0-1",
        "description": "Part du carreau en peupleraie.",
    },
    "lande_frac": {
        "famille": "combustible",
        "source": "BD Forêt V2",
        "unite": "0-1",
        "description": "Part du carreau en lande ou formation herbacée (combustible fin).",
    },
    "foret_fermee_frac": {
        "famille": "combustible",
        "source": "BD Forêt V2",
        "unite": "0-1",
        "description": "Part du carreau en forêt fermée (continuité de houppiers).",
    },
    "foret_ouverte_frac": {
        "famille": "combustible",
        "source": "BD Forêt V2",
        "unite": "0-1",
        "description": "Part du carreau en forêt ouverte (moins de continuité).",
    },
    "foret_sans_couvert_frac": {
        "famille": "combustible",
        "source": "BD Forêt V2",
        "unite": "0-1",
        "description": "Part du carreau en forêt sans couvert arboré (coupe, régénération) : peu de combustible disponible.",
    },
    "pin_frac": {
        "famille": "combustible",
        "source": "BD Forêt V2",
        "unite": "0-1",
        "description": "Part du carreau dominée par les pins (très inflammables, Gironde).",
    },
    "lisiere_m_ha": {
        "famille": "combustible",
        "source": "BD Forêt V2 (raster 25 m)",
        "unite": "m/ha",
        "description": "Densité de lisière forêt/non-forêt : fragmentation et interface de propagation.",
    },
    "foret_frac_1km": {
        "famille": "combustible",
        "source": "BD Forêt V2 + voisinage 3x3",
        "unite": "0-1",
        "description": "Couverture forestière moyenne dans un rayon d'environ 2 km (continuité du massif).",
    },
    "alt_moy_m": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "m",
        "description": "Altitude moyenne du carreau.",
    },
    "alt_min_m": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "m",
        "description": "Altitude minimale du carreau.",
    },
    "alt_max_m": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "m",
        "description": "Altitude maximale du carreau.",
    },
    "alt_std_m": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "m",
        "description": "Écart-type de l'altitude (rugosité du terrain).",
    },
    "pente_moy_deg": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "degrés",
        "description": "Pente moyenne du carreau.",
    },
    "pente_max_deg": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "degrés",
        "description": "Pente maximale du carreau (accélération du front de flamme).",
    },
    "frac_pente_sup15": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "0-1",
        "description": "Part du carreau avec une pente supérieure à 15°.",
    },
    "frac_pente_sup25": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "0-1",
        "description": "Part du carreau avec une pente supérieure à 25° (pente forte).",
    },
    "aspect_moyen_deg": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "degrés (0=N, 90=E)",
        "description": "Exposition moyenne du carreau (azimut de la pente descendante), moyenne circulaire pondérée par les pentes > 0,5°.",
    },
    "aspect_sin": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "-1 à 1",
        "description": "Composante sinusoïdale de l'exposition dominante (encodage circulaire pour les modèles).",
    },
    "aspect_cos": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "-1 à 1",
        "description": "Composante cosinusoïdale de l'exposition dominante (encodage circulaire pour les modèles).",
    },
    "aspect_concentration": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "0-1",
        "description": "Concentration de l'exposition (0 = versants dispersés/plat, 1 = versant unique).",
    },
    "exposition_dominante": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "N/NE/E/SE/S/SO/O/NO",
        "description": "Secteur d'exposition dominant du carreau (8 secteurs de 45°).",
    },
    "exposition_dominante_code": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "1-8",
        "description": "Code numérique de l'exposition dominante (1=N, 2=NE, …, 8=NO, 0=indéterminé).",
    },
    "exposition_dominante_frac": {
        "famille": "relief",
        "source": "Copernicus DEM 30 m",
        "unite": "0-1",
        "description": "Part du carreau dans le secteur d'exposition dominant.",
    },
    # ------------------------------------------------------------------
    # Pilier pression humaine
    # ------------------------------------------------------------------
    "habitat_frac": {
        "famille": "pression_humaine",
        "source": "BD TOPO zone_d_habitation",
        "unite": "0-1",
        "description": "Part du carreau occupée par des zones d'habitation.",
    },
    "wui_frac": {
        "famille": "pression_humaine",
        "source": "BD TOPO + BD Forêt V2 (raster)",
        "unite": "0-1",
        "description": "Part du carreau en interface habitat-forêt (habitat à moins de 200 m de la forêt).",
    },
    "part_habitat_wui": {
        "famille": "pression_humaine",
        "source": "BD TOPO + BD Forêt V2 (raster)",
        "unite": "0-1",
        "description": "Part de l'habitat du carreau située à moins de 200 m de la forêt.",
    },
    "route_km": {
        "famille": "pression_humaine",
        "source": "BD TOPO troncon_de_route",
        "unite": "km",
        "description": "Linéaire routier total (réseau classé et pistes DFCI).",
    },
    "route_km_km2": {
        "famille": "pression_humaine",
        "source": "BD TOPO troncon_de_route",
        "unite": "km/km²",
        "description": "Densité routière du carreau.",
    },
    "route_principale_km": {
        "famille": "pression_humaine",
        "source": "BD TOPO troncon_de_route",
        "unite": "km",
        "description": "Linéaire de routes principales (autoroutes et nationales).",
    },
    "route_dfci_km": {
        "famille": "pression_humaine",
        "source": "BD TOPO troncon_de_route",
        "unite": "km",
        "description": "Linéaire de pistes DFCI (accès et fréquentation).",
    },
    "route_ponderee_km": {
        "famille": "pression_humaine",
        "source": "BD TOPO troncon_de_route",
        "unite": "km équivalent",
        "description": "Linéaire routier pondéré par l'importance de la voie (1 autoroute, 0,8 nationale, 0,5 départementale, 0,1 piste DFCI).",
    },
    "distance_route_principale_m": {
        "famille": "pression_humaine",
        "source": "BD TOPO troncon_de_route",
        "unite": "m",
        "description": "Distance du centroïde du carreau à la route principale la plus proche.",
    },
    "tmja_max": {
        "famille": "pression_humaine",
        "source": "TMJA réseau routier national",
        "unite": "véh/j",
        "description": "Trafic journalier maximal observé sur les routes du carreau.",
    },
    "tmja_moyen_pondere": {
        "famille": "pression_humaine",
        "source": "TMJA réseau routier national",
        "unite": "véh/j",
        "description": "TMJA moyen pondéré par la longueur des sections.",
    },
    "exposition_tmja": {
        "famille": "pression_humaine",
        "source": "TMJA réseau routier national",
        "unite": "10³ véh·km/j",
        "description": "Exposition au trafic : somme longueur x TMJA.",
    },
    "agri_frac": {
        "famille": "pression_humaine",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en parcelles agricoles (interface cultures-forêt).",
    },
    "agri_frac_1km": {
        "famille": "pression_humaine",
        "source": "RPG + voisinage 3x3",
        "unite": "0-1",
        "description": "Couverture agricole moyenne dans un rayon d'environ 2 km.",
    },
    "habitat_frac_1km": {
        "famille": "pression_humaine",
        "source": "BD TOPO + voisinage 3x3",
        "unite": "0-1",
        "description": "Couverture d'habitat moyenne dans un rayon d'environ 2 km.",
    },
    "wui_frac_1km": {
        "famille": "pression_humaine",
        "source": "BD TOPO + BD Forêt V2 + voisinage 3x3",
        "unite": "0-1",
        "description": "Interface habitat-forêt moyenne dans un rayon d'environ 2 km.",
    },
    "route_km_km2_1km": {
        "famille": "pression_humaine",
        "source": "BD TOPO + voisinage 3x3",
        "unite": "km/km²",
        "description": "Densité routière moyenne dans un rayon d'environ 2 km.",
    },
    "route_totale_km": {
        "famille": "pression_humaine",
        "source": "BD TOPO troncon_de_route",
        "unite": "km",
        "description": "Linéaire de tous les tronçons (routes, chemins, sentiers, pistes).",
    },
    "route_totale_km_km2": {
        "famille": "pression_humaine",
        "source": "BD TOPO troncon_de_route",
        "unite": "km/km²",
        "description": "Densité totale de desserte, tous types de voies confondus.",
    },
    "route_chemin_km": {
        "famille": "pression_humaine",
        "source": "BD TOPO troncon_de_route",
        "unite": "km",
        "description": "Linéaire de chemins et sentiers non DFCI (importance 5-6).",
    },
    "route_chemin_km_km2": {
        "famille": "pression_humaine",
        "source": "BD TOPO troncon_de_route",
        "unite": "km/km²",
        "description": "Densité de chemins et sentiers non DFCI.",
    },
    "batiment_frac": {
        "famille": "pression_humaine",
        "source": "BD TOPO batiment",
        "unite": "0-1",
        "description": "Part du carreau couverte par l'emprise au sol des bâtiments.",
    },
    "batiment_n": {
        "famille": "pression_humaine",
        "source": "BD TOPO batiment",
        "unite": "bâtiments",
        "description": "Nombre de bâtiments dont le point représentatif est dans le carreau.",
    },
    "batiment_n_km2": {
        "famille": "pression_humaine",
        "source": "BD TOPO batiment",
        "unite": "bâtiments/km²",
        "description": "Densité de bâtiments du carreau.",
    },
    "batiment_residentiel_frac": {
        "famille": "pression_humaine",
        "source": "BD TOPO batiment (usage_1)",
        "unite": "0-1",
        "description": "Part du carreau couverte par des bâtiments à usage résidentiel.",
    },
    "contact_bati_foret_m_ha": {
        "famille": "pression_humaine",
        "source": "BD TOPO batiment + BD Forêt V2 (raster 25 m)",
        "unite": "m/ha",
        "description": "Linéaire de contact bâti-forêt à moins de 50 m, par hectare (interface WUI).",
    },
    "contact_habitat_foret_m_ha": {
        "famille": "pression_humaine",
        "source": "BD TOPO zone_d_habitation + BD Forêt V2 (raster 25 m)",
        "unite": "m/ha",
        "description": "Périmètre de la zone d'interface habitat-forêt (habitat à moins de 200 m de la forêt), par hectare.",
    },
    "cereales_frac": {
        "famille": "agriculture",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en céréales (blé, maïs, orge, autres céréales, riz).",
    },
    "oleagineux_frac": {
        "famille": "agriculture",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en oléagineux (colza, tournesol, autres).",
    },
    "proteagineux_frac": {
        "famille": "agriculture",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en protéagineux et légumineuses à grains.",
    },
    "fourrage_frac": {
        "famille": "agriculture",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en fourrage (luzerne, betterave fourragère…).",
    },
    "estives_landes_frac": {
        "famille": "agriculture",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en estives, alpages, landes et parcours (combustible fin).",
    },
    "prairies_frac": {
        "famille": "agriculture",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en prairies permanentes ou temporaires.",
    },
    "vergers_frac": {
        "famille": "agriculture",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en vergers, fruits à coque, oliviers et arboriculture.",
    },
    "vigne_frac": {
        "famille": "agriculture",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en vignes.",
    },
    "cultures_industrielles_frac": {
        "famille": "agriculture",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en cultures industrielles, semences et plantes à fibres.",
    },
    "legumes_fleurs_frac": {
        "famille": "agriculture",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en légumes, fleurs et pommes de terre.",
    },
    "gels_frac": {
        "famille": "agriculture",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en surfaces gelées ou jachères.",
    },
    "divers_frac": {
        "famille": "agriculture",
        "source": "RPG",
        "unite": "0-1",
        "description": "Part du carreau en cultures diverses (bois, énergie, hors culture).",
    },
    "prairie_permanente_frac": {
        "famille": "agriculture",
        "source": "RPG (cat_cult_p=PP)",
        "unite": "0-1",
        "description": "Part du carreau classée en prairie permanente.",
    },
    "culture_permanente_frac": {
        "famille": "agriculture",
        "source": "RPG (cat_cult_p=CP)",
        "unite": "0-1",
        "description": "Part du carreau classée en culture permanente.",
    },
    "terre_arable_frac": {
        "famille": "agriculture",
        "source": "RPG (cat_cult_p=TA)",
        "unite": "0-1",
        "description": "Part du carreau classée en terre arable.",
    },
}


NEIGHBOURHOOD_SOURCES = [
    "foret_frac",
    "agri_frac",
    "habitat_frac",
    "wui_frac",
    "route_km_km2",
]
