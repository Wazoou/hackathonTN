"""Habillage commun de l’espace d’exploration."""
import streamlit as st


def apply_theme():
    st.markdown("""<style>
    :root {color-scheme:light}
    .stApp {background:#f3f5f4;color:#253747}
    [data-testid="stHeader"] {background:#f3f5f4}
    .block-container {padding:2.8rem 2.2rem 2rem;max-width:1800px}
    [data-testid="stVerticalBlock"] {gap:.5rem}
    h1,h2,h3 {letter-spacing:-.035em}
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color:#5b6d79}
    [data-testid="stBaseButton-secondary"], [data-testid="stPopoverButton"] {
      background:#ffffff;border:1px solid #d4dfda;border-radius:9px;
      transition:background .15s,border-color .15s}
    [data-testid="stBaseButton-secondary"]:hover,[data-testid="stPopoverButton"]:hover {
      background:#edf5f0;border-color:#22745b;color:#185d47}
    [data-testid="stBaseButton-primary"] {background:#216e55;color:#ffffff;border:0}
    [data-testid="stExpander"] {border-color:#d4dfda;background:#ffffff;border-radius:12px}
    .st-key-archive_reader {background:#fff;border-color:#d4dfda;border-radius:14px}
    [data-testid="stBaseButton-primary"]:hover {background:#18543f;color:white}
    button:focus-visible {outline:2px solid #216e55;outline-offset:3px}
    [data-testid="stImage"] img {border-radius:10px}
    .brand {display:flex;align-items:center;gap:14px;margin-bottom:3px}
    .brand-icon {width:42px;height:42px;display:grid;place-items:center;border-radius:13px;
      background:#e1eee7;color:#216e55;font-size:25px;border:1px solid #c4dbce}
    .brand h1 {font-size:29px;padding:0;margin:0;line-height:1.2;font-weight:700}
    .brand p {margin:4px 0 0;color:#5b6d79;font-size:13px}
    .eyebrow {font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:#5b7065;margin:4px 0 6px}
    .reader-title {font-size:21px;font-weight:650;line-height:1.3;margin:0 0 5px}
    .reader-source {display:inline-block;font-size:11px;color:#216e55;background:#eaf4ee;
      border:1px solid #c9e0d2;padding:3px 9px;border-radius:20px;margin-bottom:8px}
    .frame-meta {display:flex;justify-content:space-between;align-items:center;padding:8px 0;
      font-size:13px;color:#5b6d79;font-variant-numeric:tabular-nums}
    .frame-meta strong {color:#253747;font-size:17px}
    @media(max-width:800px){.block-container{padding:2.5rem 1rem 1rem}}
    </style>""", unsafe_allow_html=True)


def header():
    st.markdown('''<div class="brand"><div class="brand-icon">◈</div><div>
      <h1>Pyro-Watch</h1><p>Observer les paysages. Explorer les départs de feu.</p>
      </div></div>''', unsafe_allow_html=True)
