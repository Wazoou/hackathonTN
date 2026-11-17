"""Export de la BDIFF (Base de Données sur les Incendies de Forêts en France).

Le portail https://bdiff.agriculture.gouv.fr/ n'a pas d'API : on reproduit la
recherche du formulaire (France entière, feux de forêt) puis le bouton « CSV »
(``/incendies/zip``), limité à 30 000 lignes par export, d'où le découpage
par tranches d'années. Licence Ouverte 2.0.

Le serveur envoie une chaîne de certificats incomplète (intermédiaire HARICA
« GEANT TLS RSA 1 » absent) : on télécharge cet intermédiaire depuis l'adresse
indiquée dans le certificat et on l'ajoute aux autorités de ``certifi``, sans
désactiver la vérification TLS.

    python ml/download_bdiff.py --out ifm_plus/data/raw/manual/bdiff --debut 2006 --fin 2024
"""
import argparse
import base64
import io
import re
import tempfile
import time
import zipfile
from pathlib import Path

import certifi
import requests

PORTAL = "https://bdiff.agriculture.gouv.fr"
INTERMEDIATE = "http://crt.harica.gr/HARICA-GEANT-TLS-R1.cer"
MAX_ROWS = 30_000


def ca_bundle() -> str:
    der = requests.get(INTERMEDIATE, timeout=30).content  # DER -> PEM : base64 en lignes de 64
    b64 = base64.b64encode(der).decode()
    pem = ("-----BEGIN CERTIFICATE-----\n" + "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64))
           + "\n-----END CERTIFICATE-----\n").encode()
    bundle = Path(tempfile.gettempdir()) / "bdiff-ca-bundle.pem"
    bundle.write_bytes(Path(certifi.where()).read_bytes() + b"\n" + pem)
    return str(bundle)


def export(session: requests.Session, first: int, last: int) -> tuple[int, bytes]:
    params = {"if[dateAlerteDeb][date]": f"01/01/{first}", "if[dateAlerteFin][date]": f"31/12/{last}",
              "if[fr]": "1"}
    page = session.get(f"{PORTAL}/incendies", params=params, timeout=120)
    page.raise_for_status()
    found = re.search(r"(\d+)\s+incendies", page.text)
    if not found:
        raise RuntimeError("Nombre d'incendies introuvable : la page du portail a changé")
    count = int(found.group(1))
    if count > MAX_ROWS:
        return count, b""
    archive = session.get(f"{PORTAL}/incendies/zip", timeout=300)
    if archive.headers.get("content-type") != "application/zip":
        raise RuntimeError(f"Export {first}-{last} refusé par le portail")
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        return count, z.read("Incendies.csv")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--debut", type=int, default=2006)
    parser.add_argument("--fin", type=int, default=2024)
    parser.add_argument("--tranche", type=int, default=6, help="Années par export (≤ 30 000 lignes)")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    verify = ca_bundle()
    first = args.debut
    while first <= args.fin:
        last = min(args.fin, first + args.tranche - 1)
        with requests.Session() as session:  # une session par recherche : l'export suit la dernière recherche
            session.verify = verify
            count, data = export(session, first, last)
        if not data:
            if first == last:
                raise RuntimeError(f"{first} : {count} feux, au-delà de la limite d'export")
            args.tranche = max(1, (last - first + 1) // 2)
            continue
        target = args.out / f"incendies_{first}_{last}.csv"
        target.write_bytes(data)
        print(f"{first}-{last} : {count} feux -> {target}")
        first = last + 1
        time.sleep(2)


if __name__ == "__main__":
    main()
