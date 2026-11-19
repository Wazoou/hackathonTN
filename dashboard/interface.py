"""Thème, en-tête et éléments de mise en page partagés par toutes les vues."""
from html import escape

import streamlit as st

MODE_ARCHIVES = "Carte des archives"
MODE_RISK_MAP = "Carte des risques"
MODE_FIRE_HISTORY = "Historique des incendies"
MODE_KEY = "app_mode"

# Onglets : (mode, clé du bouton, libellé, icône, titre de page, description)
PAGES = [
    (MODE_RISK_MAP, "mode_risk_map", "Risques", ":material/local_fire_department:",
     "Risque de départ de feu",
     "Risque du jour calculé à partir du terrain et de la météo, consultable en archives, "
     "en direct ou en prévision. Cliquez un département pour l’explorer."),
    (MODE_ARCHIVES, "mode_archives", "Webcams", ":material/videocam:",
     "Webcams et archives",
     "Consultez les vues de webcams publiques sur la carte ou rejouez des séquences "
     "archivées autour d’épisodes d’incendie, de panache ou de nuages."),
    (MODE_FIRE_HISTORY, "mode_fire_history", "Historique", ":material/history:",
     "Incendies passés",
     "Feux recensés par la BDIFF en France métropolitaine, filtrables par année, mois, "
     "saison et cause."),
]

FLAME_SVG = (
    '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
    '<path fill="currentColor" d="M12.6 2.2c.4 3.1-1.3 4.9-2.9 6.6C8.2 10.4 6.8 12 6.8 14.6'
    'a5.2 5.2 0 0 0 10.4 0c0-2.2-1-3.9-2.1-5.2-.2 1.3-.9 2.3-1.9 2.8.5-3.5-.2-7-.6-10z"/></svg>'
)


def current_mode():
    """Mode actif, avec « Carte des risques » comme vue d’ouverture."""
    return st.session_state.get(MODE_KEY, MODE_RISK_MAP)


def _set_mode(mode):
    st.session_state[MODE_KEY] = mode


def section_title(title, hint=None):
    """Titre de section avec aide facultative à droite."""
    help_html = f'<span>{hint}</span>' if hint else ""
    st.markdown(
        f'<div class="section-label"><h2>{title}</h2>{help_html}</div>',
        unsafe_allow_html=True,
    )


def page_intro(mode):
    """Titre et phrase d’explication de la vue active."""
    page = next((p for p in PAGES if p[0] == mode), None)
    if page:
        st.markdown(
            f'<div class="page-intro"><h2>{escape(page[4])}</h2><p>{escape(page[5])}</p></div>',
            unsafe_allow_html=True,
        )


def apply_theme():
    st.markdown("""<style>
    :root {
      color-scheme: light;
      --brand: #c2410c;
      --navy: #13293d;
      --accent: #0b5d95;
      --accent-strong: #094a77;
      --accent-soft: #e8f1f8;
      --bg: #f4f6f8;
      --surface: #ffffff;
      --surface-alt: #f0f3f6;
      --ink: #1d2b38;
      --muted: #5b6b7a;
      --line: #dbe3ea;
      --radius: 8px;
      --shadow: 0 1px 2px rgba(16, 32, 48, .06), 0 1px 3px rgba(16, 32, 48, .04);
      --font: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    .stApp {
      background: var(--bg);
      color: var(--ink);
      font-family: var(--font);
      font-size: 14px;
    }
    .stApp p, .stApp label, .stApp button, .stApp input, .stApp textarea,
    .stApp [data-baseweb="select"] {
      font-family: var(--font);
    }

    /* Barre Streamlit (Deploy, menu) masquée : l’application a son propre en-tête */
    [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] {
      display: none;
    }

    /* Le bloc <style> lui-même ne doit pas occuper de place dans la page */
    .stElementContainer:has(> .stMarkdown style),
    .element-container:has(style) {
      display: none;
    }

    .block-container {
      padding: 0 2rem 2rem;
      max-width: 1480px;
    }
    [data-testid="stVerticalBlock"] {
      gap: 0.6rem;
    }
    h1, h2, h3 {
      letter-spacing: 0;
      font-family: var(--font);
    }
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p {
      color: var(--muted);
      font-size: 12.5px;
      line-height: 1.5;
    }

    /* Boutons */
    [data-testid="stBaseButton-secondary"],
    [data-testid="stPopoverButton"] {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      color: var(--ink);
      font-size: 13.5px;
      font-weight: 500;
      box-shadow: none;
      transition: background .12s, border-color .12s, color .12s;
    }
    [data-testid="stBaseButton-secondary"]:hover,
    [data-testid="stPopoverButton"]:hover {
      background: var(--accent-soft);
      border-color: var(--accent);
      color: var(--accent-strong);
    }
    [data-testid="stBaseButton-primary"] {
      background: var(--accent);
      color: #ffffff;
      border: 1px solid var(--accent);
      border-radius: var(--radius);
      font-size: 13.5px;
      font-weight: 600;
      box-shadow: none;
    }
    [data-testid="stBaseButton-primary"]:hover {
      background: var(--accent-strong);
      border-color: var(--accent-strong);
      color: #ffffff;
    }
    button:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }

    [data-testid="stExpander"] details {
      border: 1px solid var(--line);
      background: var(--surface);
      border-radius: var(--radius);
    }
    [data-testid="stImage"] img {
      border-radius: 6px;
    }
    [data-testid="stAlert"] {
      border-radius: var(--radius);
    }

    /* En-tête : marque à gauche, onglets à droite */
    .st-key-topbar {
      position: sticky;
      top: 0;
      z-index: 50;
      padding: 0.55rem 0;
    }
    /* Fond et bordure étendus à toute la largeur de la fenêtre */
    .st-key-topbar::before {
      content: "";
      position: absolute;
      top: 0;
      bottom: 0;
      left: calc(50% - 50vw);
      right: calc(50% - 50vw);
      background: var(--surface);
      border-bottom: 1px solid var(--line);
      z-index: -1;
    }
    [data-testid="stMain"], .stApp {
      overflow-x: clip;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .brand-mark {
      display: grid;
      place-items: center;
      width: 36px;
      height: 36px;
      border-radius: 9px;
      background: linear-gradient(135deg, #f97316, var(--brand));
      color: #fff;
      flex: none;
    }
    .brand h1 {
      font-size: 19px;
      line-height: 1.1;
      margin: 0;
      padding: 0;
      font-weight: 750;
      color: var(--navy);
    }
    .brand h1 span {
      color: var(--brand);
    }
    .brand p {
      margin: 2px 0 0;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.2;
    }
    .st-key-nav_bar {
      background: var(--surface-alt);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 4px;
    }
    .st-key-nav_bar [data-testid="stHorizontalBlock"] {
      gap: 4px;
    }
    .st-key-nav_bar button {
      width: 100%;
      min-height: 38px;
      border: 0;
      border-radius: 7px;
      background: transparent;
      color: var(--muted);
      font-size: 13.5px;
      font-weight: 600;
      white-space: nowrap;
    }
    .st-key-nav_bar [data-testid="stBaseButton-secondary"]:hover {
      background: #e3e9ef;
      color: var(--navy);
      border: 0;
    }
    .st-key-nav_bar [data-testid="stBaseButton-primary"],
    .st-key-nav_bar [data-testid="stBaseButton-primary"]:hover {
      background: var(--surface);
      color: var(--accent-strong);
      border: 0;
      box-shadow: 0 1px 3px rgba(16, 32, 48, .14);
    }

    /* Intro de page */
    .page-intro {
      padding: 1.1rem 0 0.4rem;
    }
    .page-intro h2 {
      font-size: 22px;
      font-weight: 700;
      color: var(--navy);
      margin: 0 0 4px;
      padding: 0;
      line-height: 1.25;
    }
    .page-intro p {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      max-width: 820px;
    }

    /* Cartes de contenu */
    .st-key-archive_toolbar,
    .st-key-archive_reader {
      background: var(--surface);
      border: 1px solid var(--line) !important;
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }
    .st-key-archive_reader {
      padding: 0.4rem 0.2rem;
    }

    /* Titre de section */
    .section-label {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 4px 12px;
      margin: 0.6rem 0 0.35rem;
    }
    .section-label h2 {
      font-size: 13px;
      line-height: 1.3;
      margin: 0;
      padding: 0;
      font-weight: 700;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .06em;
    }
    .section-label span {
      font-size: 12.5px;
      line-height: 1.4;
      color: var(--muted);
    }

    .reader-title {
      font-size: 18px;
      font-weight: 700;
      line-height: 1.3;
      margin: 2px 0 2px;
      color: var(--navy);
    }
    .reader-source {
      display: inline-block;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: .04em;
      text-transform: uppercase;
      color: var(--accent-strong);
      background: var(--accent-soft);
      padding: 2px 8px;
      border-radius: 999px;
    }
    .frame-meta {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 0;
      font-size: 12.5px;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
    }
    .frame-meta strong {
      color: var(--ink);
      font-size: 15px;
    }

    .footer {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 2rem;
      padding-top: 0.8rem;
      border-top: 1px solid var(--line);
      font-size: 12px;
      color: var(--muted);
    }

    @media (max-width: 900px) {
      .block-container {
        padding: 0 1rem 1.8rem;
      }
      .st-key-topbar {
        position: static;
      }
      .st-key-nav_bar [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap;
      }
      .st-key-nav_bar [data-testid="stColumn"] {
        min-width: 0;
        width: auto !important;
        flex: 1 1 0 !important;
      }
      .st-key-nav_bar button {
        padding: 4px 6px;
        line-height: 1.2;
      }
      .st-key-nav_bar button [data-testid="stIconMaterial"] {
        display: none;
      }
      .brand p {
        display: none;
      }
      .st-key-nav_bar button {
        font-size: 13px;
        white-space: nowrap;
      }
      .page-intro h2 {
        font-size: 19px;
      }
    }
    </style>""", unsafe_allow_html=True)


def header():
    """Affiche la marque et les onglets de navigation."""
    mode = current_mode()
    with st.container(key="topbar"):
        brand_col, nav_col = st.columns([1.5, 1], vertical_alignment="center")
        brand_col.markdown(
            f'''<div class="brand"><span class="brand-mark">{FLAME_SVG}</span>
                <div><h1>Pyro<span>-Watch</span></h1>
                <p>Prévention et détection des feux de forêt</p></div></div>''',
            unsafe_allow_html=True,
        )
        with nav_col, st.container(key="nav_bar"):
            for col, (page_mode, key, label, icon, *_) in zip(st.columns(3), PAGES):
                col.button(
                    label,
                    key=key,
                    icon=icon,
                    type="primary" if mode == page_mode else "secondary",
                    on_click=_set_mode,
                    args=(page_mode,),
                    use_container_width=True,
                )
