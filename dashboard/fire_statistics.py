"""Departmental observed fire counts, independent of map coordinates and burned area."""
import csv
import io
from pathlib import Path


def history_signature(folder):
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size)
                 for p in sorted(Path(folder).glob('*.csv')))


def department_fire_statistics(signature, first=2006, last=2024):
    counts, years, seen = {}, set(), set()
    for filename, *_ in signature:
        lines = Path(filename).read_text(encoding='utf-8-sig').splitlines()
        start = next((i for i, line in enumerate(lines)
                      if line.startswith('Année;') and 'Département' in line), None)
        if start is None:
            raise ValueError(f'En-tête BDIFF introuvable : {filename}')
        for row in csv.DictReader(io.StringIO('\n'.join(lines[start:])), delimiter=';'):
            try:
                year = int(row['Année'])
            except (ValueError, TypeError):
                continue
            if not first <= year <= last:
                continue
            years.add(year)
            number = (row.get('Numéro') or '').strip()
            if number:
                key = (year, number)
                if key in seen:
                    continue
                seen.add(key)
            dept = (row.get('Département') or '').strip().upper().zfill(2)
            if dept in ('', '00'):
                code = (row.get('Code INSEE') or '').strip()
                dept = code[:3] if code.startswith(('97', '98')) else code[:2]
            if dept:
                counts[dept] = counts.get(dept, 0) + 1
    years = sorted(years)
    complete = bool(years) and years == list(range(first, last + 1))
    return {'years': years, 'complete': complete,
            'departments': {dept: {'count': count, 'annual_mean': count / len(years)}
                            for dept, count in counts.items()}}
