"""Checkpoint exact des indices cumulatifs, partagé par les exports historique et LIVE."""
import numpy as np
import pandas as pd


def save_state(folder, indices, stations, last_day):
    ids = list(stations)
    grids = []
    for key in ('ffmc', 'dmc', 'dc'):
        grid = indices.pivot(index='date', columns='station', values=key).reindex(columns=ids).sort_index()
        grids.append(grid.loc[:last_day].ffill().iloc[-1].to_numpy())
    state = np.asarray(grids, dtype=float)
    if not np.isfinite(state).all():
        raise ValueError('Impossible de prolonger le FWI : état incomplet.')
    target = folder / 'live_initial_state.npz'
    temp = target.with_suffix('.part')
    with temp.open('wb') as out:
        np.savez_compressed(out, date=np.array(str(pd.Timestamp(last_day).date())),
                            stations=np.array(ids), state=state)
    temp.replace(target)
    return target

