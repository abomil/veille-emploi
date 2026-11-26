"""Mémoire de la veille : SQLite. Une offre n'est stockée qu'une fois, même vue sur plusieurs requêtes."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS offres (
  uid TEXT PRIMARY KEY, source TEXT, organisation TEXT, titre TEXT, lieu TEXT, url TEXT,
  publiee TEXT, limite TEXT, description TEXT, contrat TEXT,
  premiere_vue TEXT, derniere_vue TEXT
);
CREATE TABLE IF NOT EXISTS evaluations (
  profil TEXT, uid TEXT, score INTEGER, analyse TEXT, statut TEXT DEFAULT 'nouveau',
  note TEXT DEFAULT '', evaluee_le TEXT, PRIMARY KEY (profil, uid)
);
"""
STATUTS = ["nouveau", "a_etudier", "a_postuler", "candidature_envoyee", "entretien", "ecarte"]


class Base:
    def __init__(self, chemin: Path):
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self.cx = sqlite3.connect(chemin)
        self.cx.row_factory = sqlite3.Row
        self.cx.executescript(SCHEMA)

    def uids_avec_description(self) -> set[str]:
        return {r[0] for r in self.cx.execute("SELECT uid FROM offres WHERE description <> ''")}

    def enregistrer(self, o: dict) -> bool:
        """Insère ou met à jour ; renvoie True si l'offre est nouvelle. Ne remplace jamais une description par du vide."""
        maintenant = datetime.now().isoformat(timespec="seconds")
        existe = self.cx.execute("SELECT 1 FROM offres WHERE uid=?", (o["uid"],)).fetchone()
        if existe:
            self.cx.execute(
                """UPDATE offres SET titre=?, lieu=COALESCE(NULLIF(?,''),lieu), url=?, limite=COALESCE(NULLIF(?,''),limite),
                   description=COALESCE(NULLIF(?,''),description), derniere_vue=? WHERE uid=?""",
                (o["titre"], o["lieu"], o["url"], o["limite"], o["description"], maintenant, o["uid"]))
        else:
            self.cx.execute(
                "INSERT INTO offres VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (o["uid"], o["source"], o["organisation"], o["titre"], o["lieu"], o["url"], o["publiee"],
                 o["limite"], o["description"], o["contrat"], maintenant, maintenant))
        return not existe

    def offres_actives(self, jours: int = 45) -> list[dict]:
        """Offres revues lors d'une collecte récente (les autres sont considérées comme closes)."""
        q = "SELECT * FROM offres WHERE derniere_vue >= datetime('now', 'localtime', ?)"
        return [dict(r) for r in self.cx.execute(q, (f"-{jours} days",))]

    def uids_recents(self, heures: int = 24) -> set[str]:
        return {r[0] for r in self.cx.execute(
            "SELECT uid FROM offres WHERE premiere_vue >= datetime('now','localtime',?)", (f"-{heures} hours",))}

    def enregistrer_evaluation(self, profil: str, uid: str, ev: dict) -> None:
        self.cx.execute(
            """INSERT INTO evaluations (profil, uid, score, analyse, evaluee_le) VALUES (?,?,?,?,datetime('now','localtime'))
               ON CONFLICT(profil, uid) DO UPDATE SET score=excluded.score, analyse=excluded.analyse,
               evaluee_le=excluded.evaluee_le""",
            (profil, uid, ev["score"], json.dumps(ev, ensure_ascii=False)))

    def suivi(self, profil: str) -> dict[str, dict]:
        return {r["uid"]: dict(r) for r in self.cx.execute(
            "SELECT uid, statut, note FROM evaluations WHERE profil=?", (profil,))}

    def changer_statut(self, profil: str, uid: str, statut: str, note: str = "") -> bool:
        cur = self.cx.execute("UPDATE evaluations SET statut=?, note=? WHERE profil=? AND uid=?",
                              (statut, note, profil, uid))
        self.cx.commit()
        return cur.rowcount > 0

    def valider(self):
        self.cx.commit()
