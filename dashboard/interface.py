
import streamlit as st

MODE_ARCHIVES = "Carte des archives"
MODE_SIMULATION = "Surveillance simulée"
MODE_FIRE_HISTORY = "Historique des incendies"
MODE_KEY = "app_mode"


def current_mode():
    """Mode actif, avec « Carte des archives » comme vue d’ouverture."""
    return st.session_state.get(MODE_KEY, MODE_ARCHIVES)


def _set_mode(mode):
    st.session_state[MODE_KEY] = mode


def section_title(title, hint=None):
    """Bandeau de titre sobre façon portail météo."""
    help_html = f'<span>{hint}</span>' if hint else ""
    st.markdown(
        f'<div class="section-label"><h2>{title}</h2>{help_html}</div>',
        unsafe_allow_html=True,
    )


def apply_theme():
    st.markdown("""<style>
    :root {
      color-scheme: light;
      --navy: #1b3c59;
      --navy-dark: #142d44;
      --blue: #235a8c;
      --accent: #0078bf;
      --bg: #f6f8fa;
      --surface: #ffffff;
      --surface-alt: #eef2f6;
      --ink: #1f2933;
      --muted: #5a6875;
      --line: #cfd8e0;
    }

    .stApp {
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 13px;
    }

    [data-testid="stHeader"] {
      background: transparent;
      color: var(--ink);
      height: 2.5rem;
    }
    [data-testid="stHeader"] button,
    [data-testid="stHeader"] a {
      color: var(--ink);
    }

    .block-container {
      padding: 1.2rem 1.8rem 2rem;
      max-width: 1480px;
    }
    [data-testid="stVerticalBlock"] {
      gap: 0.45rem;
    }

    h1, h2, h3 {
      letter-spacing: 0;
    }
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p {
      color: var(--muted);
      font-size: 12px;
    }

    /* Contrôles plats, anguleux (2px), lisibles */
    [data-testid="stBaseButton-secondary"],
    [data-testid="stPopoverButton"] {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 2px;
      color: var(--ink);
      font-size: 12.5px;
      padding: 0.25rem 0.65rem;
      box-shadow: none;
    }
    [data-testid="stBaseButton-secondary"]:hover,
    [data-testid="stPopoverButton"]:hover {
      background: var(--surface-alt);
      border-color: var(--blue);
      color: var(--navy);
    }
    [data-testid="stBaseButton-primary"] {
      background: var(--accent);
      color: #ffffff;
      border: 1px solid var(--accent);
      border-radius: 2px;
      font-size: 12.5px;
      box-shadow: none;
    }
    [data-testid="stBaseButton-primary"]:hover {
      background: var(--blue);
      border-color: var(--blue);
      color: #ffffff;
    }

    [data-testid="stExpander"] {
      border: 1px solid var(--line);
      background: var(--surface);
      border-radius: 2px;
      box-shadow: none;
    }
    button:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 1px;
    }
    [data-testid="stImage"] img {
      border-radius: 2px;
      border: 1px solid var(--line);
    }

    /* Navigation principale sur fond clair */
    .st-key-topbar {
      margin: -1.2rem -1.8rem 0;
      padding: 0.45rem 1.8rem 0;
      background: transparent;
      border: 0;
      border-radius: 0;
      box-shadow: none;
    }
    .st-key-topbar [data-testid="stColumn"] {
      padding-top: 0;
    }
    .st-key-topbar button {
      min-height: 38px;
      border: 0;
      border-top: 2px solid transparent;
      border-radius: 2px 2px 0 0;
      background: transparent;
      color: var(--navy);
      font-size: 13px;
      font-weight: 600;
      padding: 0 0.75rem;
      white-space: nowrap;
    }
    .st-key-topbar [data-testid="stBaseButton-primary"] {
      background: var(--surface-alt);
      color: var(--navy);
      border: 0;
      border-top: 2px solid transparent;
      box-shadow: none;
    }
    .st-key-topbar [data-testid="stBaseButton-primary"]:hover {
      background: var(--surface-alt);
      color: var(--navy);
    }
    .st-key-topbar [data-testid="stBaseButton-secondary"]:hover {
      background: var(--surface-alt);
      color: var(--navy);
      border-color: transparent;
    }
    .st-key-nav_bar {
      background: var(--navy);
      margin: 0 -1.8rem;
      padding: 0.3rem 1.8rem;
      width: 100vw;
      max-width: none;
    }
    .st-key-nav_bar [data-testid="stColumn"] {
      padding-top: 0;
    }
    .st-key-nav_bar button {
      min-height: 40px;
      border: 0;
      border-top: 2px solid transparent;
      border-radius: 2px;
      background: transparent;
      color: #f5f8fb;
      font-size: 13px;
      font-weight: 600;
      padding: 0 0.75rem;
      white-space: nowrap;
    }
    .st-key-nav_bar [data-testid="stBaseButton-primary"] {
      background: var(--surface);
      color: var(--navy);
      border-top-color: var(--accent);
    }
    .st-key-nav_bar [data-testid="stBaseButton-primary"]:hover {
      background: var(--surface);
      color: var(--navy);
    }
    .st-key-nav_bar [data-testid="stBaseButton-secondary"]:hover {
      background: #274f73;
      color: #ffffff;
      border-color: transparent;
    }

    .brand {
      display: flex;
      align-items: baseline;
      gap: 10px;
      padding-bottom: 1.2rem;
    }
    .brand h1 {
      font-size: 20px;
      padding: 0;
      margin: 0;
      line-height: 1.1;
      font-weight: 700;
      color: var(--navy);
    }
    .brand h1 span {
      color: var(--blue);
      font-weight: 400;
    }
    .brand p {
      margin: 0;
      color: var(--muted);
      font-size: 12px;
    }

    /* Barre utilitaire collée au bandeau, sans coins arrondis */
    .statusbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      background: var(--surface-alt);
      border-bottom: 1px solid var(--line);
      margin: 0 -1.8rem 0.9rem;
      padding: 0.35rem 1.8rem;
      font-size: 11.5px;
      color: var(--muted);
    }
    .statusbar strong {
      color: var(--navy);
      font-weight: 700;
    }
    .statusbar .status-ok {
      color: #216e39;
      font-weight: 600;
    }

    /* Zones de contenu : sobres, sans ombres ni gros arrondis */
    .st-key-archive_toolbar,
    .st-key-live_overview,
    .st-key-archive_reader,
    [class*="st-key-cam_"] {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 2px;
      box-shadow: none;
    }

    /* Titre de section façon bandeau Infoclimat */
    .section-label {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
      background: var(--surface-alt);
      border-top: 2px solid var(--blue);
      border-bottom: 1px solid var(--line);
      padding: 0.35rem 0.7rem;
      margin: 0.75rem 0 0.35rem;
    }
    .section-label h2 {
      font-size: 13.5px;
      line-height: 1.3;
      margin: 0;
      font-weight: 700;
      color: var(--navy);
    }
    .section-label span {
      font-size: 11.5px;
      color: var(--muted);
    }

    .reader-title {
      font-size: 18px;
      font-weight: 700;
      line-height: 1.3;
      margin: 0 0 4px;
      color: var(--ink);
    }
    .reader-source {
      display: inline-block;
      font-size: 11px;
      color: var(--navy);
      background: var(--surface-alt);
      border: 1px solid var(--line);
      padding: 1px 6px;
      border-radius: 2px;
      margin-bottom: 6px;
    }
    .frame-meta {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 6px 0;
      border-top: 1px solid #e6ecf1;
      font-size: 12px;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
    }
    .frame-meta strong {
      color: var(--ink);
      font-size: 14px;
    }

    .footer {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 1.5rem;
      padding-top: 0.6rem;
      border-top: 1px solid var(--line);
      font-size: 11px;
      color: var(--muted);
    }

    @media (max-width: 800px) {
      .block-container {
        padding: 1.2rem 0.6rem 1.8rem;
      }
      .st-key-topbar {
        margin: -1.2rem -0.6rem 0;
        padding: 0.45rem 0.6rem 0;
      }
      .st-key-nav_bar {
        margin: 0 -0.6rem;
        padding: 0.3rem 0.6rem;
      }
      .statusbar {
        margin: 0 -0.6rem 0.8rem;
        padding: 0.35rem 0.6rem;
        flex-direction: column;
        align-items: flex-start;
      }
      .st-key-topbar button {
        font-size: 11.5px;
        white-space: normal;
      }
      .brand p {
        display: none;
      }
    }
    </style>""", unsafe_allow_html=True)


def header():
    """Affiche le titre et les onglets de navigation."""
    mode = current_mode()
    with st.container(key="topbar"):
        st.markdown(
            '''<div class="brand">
                <h1>Pyro<span>-Watch</span></h1>
            </div>''',
            unsafe_allow_html=True,
        )
        with st.container(key="nav_bar"):
            archives_col, simulation_col, history_col, _ = st.columns(
                [1.2, 1.35, 2.1, 6], gap="small"
            )
            archives_col.button(
                "Webcam",
                key="mode_archives",
                type="primary" if mode == MODE_ARCHIVES else "secondary",
                on_click=_set_mode,
                args=(MODE_ARCHIVES,),
            )
            simulation_col.button(
                "Alerte simulée",
                key="mode_simulation",
                type="primary" if mode == MODE_SIMULATION else "secondary",
                on_click=_set_mode,
                args=(MODE_SIMULATION,),
            )
            history_col.button(
                MODE_FIRE_HISTORY,
                key="mode_fire_history",
                type="primary" if mode == MODE_FIRE_HISTORY else "secondary",
                on_click=_set_mode,
                args=(MODE_FIRE_HISTORY,),
            )