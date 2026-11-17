"""Habillage commun de l’espace d’exploration."""
import streamlit as st


def apply_theme():
    st.markdown("""<style>
    :root {color-scheme:dark}
    .stApp {background:#0b1119;color:#e5edf5}
    [data-testid="stHeader"] {background:#0b1119}
    .block-container {padding:2.8rem 2.2rem 2rem;max-width:1800px}
    [data-testid="stVerticalBlock"] {gap:.5rem}
    h1,h2,h3 {letter-spacing:-.035em}
    [data-testid="stCaptionContainer"] {color:#91a3b7}
    [data-testid="stBaseButton-secondary"], [data-testid="stPopoverButton"] {
      background:#131e2b;border:1px solid #2a3a4c;border-radius:9px;
      transition:background .15s,border-color .15s}
    [data-testid="stBaseButton-secondary"]:hover,[data-testid="stPopoverButton"]:hover {
      background:#1b2c3d;border-color:#53d5b1;color:#b9f5e3}
    [data-testid="stBaseButton-primary"] {background:#65e0bd;color:#09261e;border:0}
    [data-testid="stExpander"] {border-color:#263747;background:#101a26;border-radius:12px}
    [data-testid="stImage"] img {border-radius:10px}
    .brand {display:flex;align-items:center;gap:14px;margin-bottom:3px}
    .brand-icon {width:42px;height:42px;display:grid;place-items:center;border-radius:13px;
      background:#19362f;color:#71e5c1;font-size:25px;border:1px solid #2b5b4c}
    .brand h1 {font-size:29px;padding:0;margin:0;line-height:1.2;font-weight:700}
    .brand p {margin:4px 0 0;color:#91a3b7;font-size:13px}
    .eyebrow {font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:#7f98ae;margin:4px 0 6px}
    .reader-title {font-size:21px;font-weight:650;line-height:1.3;margin:0 0 5px}
    .reader-source {display:inline-block;font-size:11px;color:#82e6ca;background:#16382f;
      border:1px solid #285547;padding:3px 9px;border-radius:20px;margin-bottom:8px}
    .frame-meta {display:flex;justify-content:space-between;align-items:center;padding:8px 0;
      font-size:13px;color:#b2c2d3;font-variant-numeric:tabular-nums}
    .frame-meta strong {color:#eef6ff;font-size:17px}
    @media(max-width:800px){.block-container{padding:2.5rem 1rem 1rem}}
    </style>""", unsafe_allow_html=True)


def header():
    st.markdown('''<div class="brand"><div class="brand-icon">◈</div><div>
      <h1>Pyro-Watch</h1><p>Observer les paysages. Explorer les départs de feu.</p>
      </div></div>''', unsafe_allow_html=True)
