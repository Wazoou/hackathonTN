"""Système canadien de l'indice forêt-météo (FWI), base de l'IFM de Météo-France.

Équations de Van Wagner (1987), « Development and structure of the Canadian Forest
Fire Weather Index System », vectorisées sur plusieurs stations : chaque appel de
``step`` fait avancer d'un jour les codes d'humidité (FFMC, DMC, DC) de toutes les
stations, puis calcule les indices de comportement (ISI, BUI, FWI).

Entrées quotidiennes : température (°C), humidité relative (%), vent à 10 m (km/h),
pluie sur 24 h (mm), mois (1-12). La méthode prévoit les valeurs de 12 h (heure locale
normale) ; avec les données climatologiques quotidiennes on utilise TX, UN et le vent
moyen, approximation courante qui surestime légèrement le danger.
"""
import numpy as np

# Longueurs de jour effectives (DMC) et facteurs de durée du jour (DC), latitudes ~46°N.
DMC_DAY = np.array([6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0])
DC_DAY = np.array([-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6])
START = {"ffmc": 85.0, "dmc": 6.0, "dc": 15.0}  # valeurs de démarrage standard


def ffmc(temp, rh, wind, rain, prev):
    mo = 147.2 * (101.0 - prev) / (59.5 + prev)
    rf = rain - 0.5
    wet = rain > 0.5
    rf_safe = np.where(wet, rf, 1.0)
    gain = 42.5 * rf_safe * np.exp(-100.0 / (251.0 - mo)) * (1.0 - np.exp(-6.93 / rf_safe))
    gain = np.where(mo > 150.0, gain + 0.0015 * (mo - 150.0) ** 2 * np.sqrt(rf_safe), gain)
    mo = np.where(wet, np.minimum(mo + gain, 250.0), mo)

    ed = 0.942 * rh ** 0.679 + 11.0 * np.exp((rh - 100.0) / 10.0) + 0.18 * (21.1 - temp) * (1.0 - np.exp(-0.115 * rh))
    ew = 0.618 * rh ** 0.753 + 10.0 * np.exp((rh - 100.0) / 10.0) + 0.18 * (21.1 - temp) * (1.0 - np.exp(-0.115 * rh))
    ko = 0.424 * (1.0 - (rh / 100.0) ** 1.7) + 0.0694 * np.sqrt(wind) * (1.0 - (rh / 100.0) ** 8)
    kd = ko * 0.581 * np.exp(0.0365 * temp)
    k1 = 0.424 * (1.0 - ((100.0 - rh) / 100.0) ** 1.7) + 0.0694 * np.sqrt(wind) * (1.0 - ((100.0 - rh) / 100.0) ** 8)
    kw = k1 * 0.581 * np.exp(0.0365 * temp)
    m = np.where(mo > ed, ed + (mo - ed) * 10.0 ** (-kd),
                 np.where(mo < ew, ew - (ew - mo) * 10.0 ** (-kw), mo))
    return np.clip(59.5 * (250.0 - m) / (147.2 + m), 0.0, 101.0)


def dmc(temp, rh, rain, prev, month):
    t = np.maximum(temp, -1.1)
    rk = 1.894 * (t + 1.1) * (100.0 - rh) * DMC_DAY[month - 1] * 1e-4
    wet = rain > 1.5
    rw = 0.92 * rain - 1.27
    wmi = 20.0 + 280.0 / np.exp(0.023 * prev)
    safe = np.maximum(prev, 1e-6)
    b = np.where(prev <= 33.0, 100.0 / (0.5 + 0.3 * prev),
                 np.where(prev <= 65.0, 14.0 - 1.3 * np.log(safe), 6.2 * np.log(safe) - 17.2))
    wmr = wmi + 1000.0 * rw / (48.77 + b * rw)
    pr = np.where(wet, 43.43 * (5.6348 - np.log(np.maximum(wmr - 20.0, 1e-6))), prev)
    return np.maximum(np.maximum(pr, 0.0) + rk, 0.0)


def dc(temp, rain, prev, month):
    t = np.maximum(temp, -2.8)
    pe = np.maximum((0.36 * (t + 2.8) + DC_DAY[month - 1]) / 2.0, 0.0)
    wet = rain > 2.8
    rw = 0.83 * rain - 1.27
    smi = 800.0 * np.exp(-prev / 400.0)
    dr = np.where(wet, np.maximum(prev - 400.0 * np.log(1.0 + 3.937 * np.maximum(rw, 0) / smi), 0.0), prev)
    return np.maximum(dr + pe, 0.0)


def isi(ffmc_value, wind):
    fm = 147.2 * (101.0 - ffmc_value) / (59.5 + ffmc_value)
    sf = 19.115 * np.exp(-0.1386 * fm) * (1.0 + fm ** 5.31 / 4.93e7)
    return sf * np.exp(0.05039 * wind)


def bui(dmc_value, dc_value):
    denom = np.where(dmc_value + 0.4 * dc_value > 0, dmc_value + 0.4 * dc_value, 1.0)
    low = 0.8 * dc_value * dmc_value / denom
    high = dmc_value - (1.0 - 0.8 * dc_value / denom) * (0.92 + (0.0114 * dmc_value) ** 1.7)
    out = np.where(dmc_value <= 0.4 * dc_value, low, high)
    return np.where((dmc_value == 0) & (dc_value == 0), 0.0, np.maximum(out, 0.0))


def fwi(isi_value, bui_value):
    bb = np.where(bui_value <= 80.0,
                  0.1 * isi_value * (0.626 * bui_value ** 0.809 + 2.0),
                  0.1 * isi_value * (1000.0 / (25.0 + 108.64 * np.exp(-0.023 * bui_value))))
    safe = np.maximum(bb, 1.0 + 1e-12)
    return np.where(bb <= 1.0, bb, np.exp(2.72 * (0.434 * np.log(safe)) ** 0.647))


def step(state, temp, rh, wind, rain, month):
    """Un jour pour toutes les stations. Une station sans donnée garde ses codes ; ses indices sont NaN."""
    rh = np.clip(rh, 0.0, 100.0)
    rain = np.maximum(rain, 0.0)
    ok = ~(np.isnan(temp) | np.isnan(rh) | np.isnan(wind) | np.isnan(rain))
    t, h, w, r = (np.where(ok, v, 0.0) for v in (temp, rh, wind, rain))
    new = {"ffmc": ffmc(t, h, w, r, state["ffmc"]), "dmc": dmc(t, h, r, state["dmc"], month),
           "dc": dc(t, r, state["dc"], month)}
    new = {k: np.where(ok, v, state[k]) for k, v in new.items()}
    i = isi(new["ffmc"], w)
    b = bui(new["dmc"], new["dc"])
    out = {**new, "isi": i, "bui": b, "fwi": fwi(i, b)}
    return new, {k: np.where(ok, v, np.nan) for k, v in out.items()}


def run(temp, rh, wind, rain, months):
    """Séries (jours × stations) -> dict d'indices (jours × stations), calcul continu."""
    n_days, n_stations = temp.shape
    state = {k: np.full(n_stations, v) for k, v in START.items()}
    names = ("ffmc", "dmc", "dc", "isi", "bui", "fwi")
    result = {k: np.full((n_days, n_stations), np.nan) for k in names}
    for day in range(n_days):
        state, values = step(state, temp[day], rh[day], wind[day], rain[day], int(months[day]))
        for k in names:
            result[k][day] = values[k]
    return result
