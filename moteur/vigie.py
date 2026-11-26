"""Envoi des offres collectées vers la plateforme Vigie (API /api/offres), après chaque collecte.

Seules les annonces publiques sont envoyées : aucune donnée de profil, aucune note, aucun dossier.
Variables : VIGIE_URL (https://…) et VIGIE_JETON_IMPORT. Sans elles, l'envoi est simplement ignoré.
Usage : python -m moteur.vigie [chemin/vers/veille.sqlite]
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import requests

LOT = 50          # offres par requête (le corps reste bien sous la limite de 4,5 Mo de l'hébergeur)
JOURS = 45        # seules les offres vues récemment sont envoyées
CHAMPS = ["uid", "source", "organisation", "titre", "lieu", "url", "publiee", "limite",
          "description", "contrat", "premiere_vue", "derniere_vue"]


def offres_recentes(chemin: Path) -> list[dict]:
    cx = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    cx.row_factory = sqlite3.Row
    lignes = cx.execute(
        f"SELECT {', '.join(CHAMPS)} FROM offres WHERE derniere_vue >= datetime('now','localtime',?)",
        (f"-{JOURS} days",)).fetchall()
    cx.close()
    return [{k: (r[k] or "")[:60_000] if isinstance(r[k], str) or r[k] is None else r[k] for k in CHAMPS} for r in lignes]


def envoyer(chemin: Path, url: str, jeton: str) -> tuple[int, int]:
    if not url.startswith("https://"):
        raise ValueError("VIGIE_URL doit commencer par https://")
    offres = offres_recentes(chemin)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {jeton}", "User-Agent": "VeilleEmploi/1.1 (import Vigie)"})
    retenues = rejetees = 0
    for i in range(0, len(offres), LOT):
        r = s.post(url.rstrip("/") + "/api/offres", json={"offres": offres[i:i + LOT]}, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"Vigie a refusé le lot {i // LOT + 1} : HTTP {r.status_code}")
        d = r.json()
        retenues += d.get("retenues", 0)
        rejetees += d.get("rejetees", 0)
    return retenues, rejetees


def main() -> int:
    url, jeton = os.environ.get("VIGIE_URL", ""), os.environ.get("VIGIE_JETON_IMPORT", "")
    if not url or not jeton:
        print("Vigie : VIGIE_URL ou VIGIE_JETON_IMPORT absent, envoi ignoré.")
        return 0
    chemin = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "donnees" / "veille.sqlite"
    retenues, rejetees = envoyer(chemin, url, jeton)
    print(f"Vigie : {retenues} offres envoyées, {rejetees} rejetée(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
