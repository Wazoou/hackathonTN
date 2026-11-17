"""Import ciblé et reproductible de 29 images publiques, sans collecte continue.

python ml/import_webcam_demo.py --out archives-data
Les coordonnées et créneaux proviennent des catalogues/lecteurs publics.
L'accès technique ne constitue pas une licence de redistribution.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path

import requests
from PIL import Image


ATMO = "https://www.atmosud.org/actualite/incendie-frejus-le-7-juillet-2025"
MARTIGUES = "https://www.gendarmerie.interieur.gouv.fr/gendinfo/actualites/2020/martigues-mobilisation-des-forces-de-l-etat-face-aux-incendies"
CATALOG = "https://www.infoclimat.fr/cartes/webcams.php"


def catalog():
    cameras = {
        "frejus": dict(name="Fréjus · panorama du centre-ville", lat=43.43294786, lon=6.73731744,
            source="Skaping / Estérel Côte d’Azur", credit="Skaping · Estérel Côte d’Azur",
            source_url="https://www.skaping.com/esterel/frejus?archives=MTc1MTg4NDI2MA-YQ",
            coordinate_source="Métadonnées du lecteur public Skaping", coordinate_precision="Position publiée de la webcam",
            episode="Fréjus · 7 juillet 2025", evidence="Incendie et panache documentés par AtmoSud",
            evidence_url=ATMO, focus="2025-07-07T11:31:00",
            description="Incendie près du domaine du Colombier. À 11 h 31, examiner l’horizon à droite du clocher. Le panorama montre aussi des nuages naturels."),
        "samena": dict(name="Marseille · Saména", lat=43.27083, lon=5.3821,
            source="Infoclimat / Météo Calanques Marseille", credit="Infoclimat · Météo Calanques Marseille",
            source_url=CATALOG, coordinate_source="Catalogue public Infoclimat, webcam 355",
            coordinate_precision="Position publiée ; implantation historique non vérifiée",
            episode="Martigues · 4–5 août 2020", evidence="Panache candidat ; attribution au feu de Martigues à confirmer",
            evidence_url=MARTIGUES, focus="2020-08-04T18:00:00",
            description="Un panache sombre apparaît à droite de l’horizon au créneau de 18 h. La Gendarmerie documente un départ de feu à Martigues peu avant 17 h ; le lien précis avec cette image reste une hypothèse."),
        "saint-martin": dict(name="Saint-Martin-de-Londres · Pic Saint-Loup", lat=43.7904, lon=3.73066,
            source="Infoclimat / webcam de Saint-Martin-de-Londres", credit="Infoclimat · webcam de Saint-Martin-de-Londres",
            source_url=CATALOG, coordinate_source="Catalogue public Infoclimat, webcam 474",
            coordinate_precision="Position publiée de la webcam", episode="Paysage de comparaison · 7 juillet 2025",
            evidence="Vues de comparaison ; pas de label incendie", focus="2025-07-07T12:00:00",
            description="Paysage et ciel pour comparer les sorties futures du détecteur. Une image sans panache visible ne prouve pas l’absence d’incendie dans la région."),
        "canejan": dict(name="Canéjan · lisière de pins", lat=44.7666667, lon=-0.6333333,
            source="Infoclimat / webcam de Canéjan", credit="Infoclimat · webcam de Canéjan",
            source_url=CATALOG, coordinate_source="Catalogue public Infoclimat, webcam 93",
            coordinate_precision="Position publiée ; implantation historique non vérifiée",
            episode="Vues de comparaison · 13 juillet 2022", evidence="Vues de comparaison pendant un épisode régional de feux",
            evidence_url="https://www.gironde.gouv.fr/Actualites/Communiques-de-presse/Communiques-de-presse-2022/Juillet-2022/Incendies-en-cours-en-Gironde-point-le-14-juillet-a-9h00",
            focus="2022-07-13T18:00:00",
            description="Le champ de cette caméra sert de comparaison, même si des incendies sont documentés ailleurs en Gironde à cette date. Aucun label négatif de référence n’est fourni."),
    }
    specs = []
    for slot in ["09-01", "09-31", "10-01", "10-31", "11-01", "11-31", "12-01", "12-31", "13-01"]:
        specs.append(("frejus", "2025-07-07", slot.replace("-", ":"),
            f"https://skaping.s3.gra.io.cloud.ovh.net/esterel/3/2025/07/07/large/{slot}.jpg", "Heure du lecteur · Europe/Paris"))
    for key, cam, dates in [
        ("samena", 355, [("2020-08-04", [8, 10, 12, 14, 16, 18]), ("2020-08-05", [8, 10])]),
        ("saint-martin", 474, [("2025-07-07", [8, 10, 12, 14, 16, 18])]),
        ("canejan", 93, [("2022-07-13", [8, 10, 12, 14, 16, 18])]),
    ]:
        for day, hours in dates:
            for hour in hours:
                specs.append((key, day, f"{hour:02}:00",
                    f"https://www.infoclimat.fr/multimedia/webcams/{day.replace('-', '/')}/{hour:02}/{cam}.jpg",
                    "Créneau d’archive Infoclimat ; heure exacte incrustée dans l’image, fuseau non vérifié"))
    return cameras, specs


def import_demo(out):
    out = Path(out)
    directory = out / "webcam-demo"
    directory.mkdir(parents=True, exist_ok=True)
    cameras, specs = catalog()
    frames = []
    for key, day, hour, url, basis in specs:
        relative = Path("webcam-demo") / f"{key}-{day}-{hour.replace(':', '-')}.jpg"
        path = out / relative
        if not path.exists():
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.content
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            temporary = path.with_suffix(".part")
            temporary.write_bytes(data)
            temporary.replace(path)
        with Image.open(path) as image:
            size = list(image.size)
        frames.append(dict(camera_id=key, department=key, sequence_id=key,
            timestamp=f"{day}T{hour}:00", image=str(relative), boxes=[], annotated=False,
            source_url=url, time_basis=basis, image_size=size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        print(f"{key} {day} {hour} : OK", flush=True)
    manifest = dict(kind="webcam_demo", source="Échantillon de webcams publiques · Infoclimat et Skaping",
        revision="webcam-demo-v1", timezone="Heures locales affichées ; créneaux Infoclimat non convertis",
        license_note="Conditions de réutilisation non établies. Les crédits et liens originaux sont conservés ; aucune licence ouverte n’est présumée.",
        default_camera="frejus", default_cursor=cameras["frejus"]["focus"],
        departments=cameras, frames=frames)
    destination = out / "manifest-webcams.json"
    temporary = destination.with_suffix(".part")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    print(f"{len(frames)} images / {len(cameras)} caméras → {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="archives-data")
    import_demo(parser.parse_args().out)
