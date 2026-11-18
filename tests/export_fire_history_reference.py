"""Run in dashboard and redirect stdout to a JSON file for JS parity tests."""
import sys,json
sys.path.insert(0,'/app')
import fire_history as h
paths=sorted(set(([h.FIRE_DATA_PATH] if h.FIRE_DATA_PATH.is_file() else [])+list(h.BDIFF_DIR.glob('*.csv'))))
records,_=h.load_fire_records(tuple(map(str,paths)),str(h.CENTROID_PATH),0,0)
records=records[records.zone=='France métropolitaine']
cases=[]
for year in sorted(records[h.DATE_COLUMN].dt.year.unique()):
    states=[('year',12,'Toutes les saisons','Toutes les causes')]+[('month',m,'Toutes les saisons','Toutes les causes') for m in range(1,13)]
    if year==2022:
        states += [('month',7,s,c) for s in ['Toutes les saisons',*h.SEASON_MONTHS] for c in ['Toutes les causes',*h.CAUSE_VALUES]]
    for period,month,season,cause in states:
        subset=h.filter_fire_records(records,season,cause,year=int(year))
        if period=='month':subset=h.fire_records_for_month(subset,f'{year}-{month:02d}')
        located=subset.dropna(subset=['latitude','longitude'])
        points=h.build_map_points(located).drop(columns='zone').to_dict('records')
        cases.append({'state':{'year':int(year),'month':month,'period':period,'season':'all' if season=='Toutes les saisons' else season,'cause':'all' if cause=='Toutes les causes' else h.CAUSE_VALUES[cause].casefold()},
                      'expected':{'count':len(subset),'unmapped':len(subset)-len(located),'approximate':int(located.precision.eq('département').sum()),'points':points}})
print(json.dumps({'records':h.history_records_payload(records),'cases':cases},ensure_ascii=False,allow_nan=False))
