"""Petites fonctions de normalisation de libellés."""

from __future__ import annotations

import unicodedata

import pandas as pd


def strip_accents(series: pd.Series) -> pd.Series:
    """Retire les accents et passe en minuscules (comparaisons robustes)."""
    return series.fillna("").astype(str).map(
        lambda value: unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("utf-8")
        .lower()
        .strip()
    )
