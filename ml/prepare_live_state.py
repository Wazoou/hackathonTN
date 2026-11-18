"""Export the exact last FWI state for the fixed stations, without retraining any model.

python ml/prepare_live_state.py --risk-data risk-data --meteo ifm_plus/data/raw/meteo
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from build_daily_risk import read_meteo, station_indices
from live_state import save_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--risk-data', type=Path, default=Path('risk-data'))
    parser.add_argument('--meteo', type=Path, default=Path('ifm_plus/data/raw/meteo'))
    args = parser.parse_args()
    folder = args.risk_data / 'meteo'
    stations = pd.DataFrame(json.loads((folder/'stations.json').read_text())).set_index('station')
    with np.load(folder/'meteo.npz', allow_pickle=False) as history:
        ids, last = list(history['stations'].astype(str)), pd.Timestamp(str(history['dates'][-1]))
    stations = stations.loc[ids]
    print(f'Reconstitution du FWI pour {len(ids)} stations jusqu’au {last.date()}…', flush=True)
    meteo = read_meteo(args.meteo, depts=set(stations.dept.astype(str)))
    indices = station_indices(meteo[meteo.station.isin(ids)], stations)
    print(save_state(folder, indices, ids, last), flush=True)


if __name__ == '__main__':
    main()
