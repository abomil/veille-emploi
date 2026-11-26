"""Veille emploi — supply chain santé, data management, aide à la décision.

Utilisation :
    python veille.py                      collecte + évaluation + rapports, pour tous les profils
    python veille.py --profil marcellin   un seul profil
    python veille.py --sans-collecte      ré-évalue la base existante (après avoir modifié un profil)
    python veille.py statut <identifiant> <statut> [--note "..."] [--profil marcellin]
        statuts : nouveau, a_etudier, a_postuler, candidature_envoyee, entretien, ecarte
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml

from moteur import coach, collecteurs, rapport
from moteur.base import STATUTS, Base
from moteur.score import evaluer

for flux in (sys.stdout, sys.stderr):  # console Windows : éviter les erreurs d'accents
    try:
        flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RACINE = Path(__file__).resolve().parent
JOURNAL = RACINE / "donnees" / "journal.log"


def journal(msg: str) -> None:
    ligne = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(ligne, flush=True)
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(ligne + "\n")


SANTE: list[str] = []  # alertes sur l'état des sources, affichées dans le tableau de bord
CHAMPS = ("uid", "source", "organisation", "titre", "url")


def valide(o: dict) -> bool:
    """Contrôle d'intégrité : une offre sans identifiant, sans titre ou avec un lien non https est rejetée."""
    ok = all(isinstance(o.get(c), str) and o[c].strip() for c in CHAMPS) and o["url"].startswith("https://")
    if not ok:
        journal(f"  offre rejetée (données incomplètes) : {str(o.get('uid'))[:60]}")
    return ok


def controler_sources(sources: dict, par_source: dict[str, int]) -> None:
    """Compare chaque source à son dernier passage : silence ou chute de plus de 70 % = alerte."""
    import json
    fichier = RACINE / "donnees" / "sante.json"
    avant = {}
    try:
        avant = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    attendues = [f'{c["nom"]} (Workday)' for c in sources.get("workday", []) or []]
    attendues += ["Nations unies (careers.un.org)"] if sources.get("nations_unies", {}).get("actif") else []
    attendues += ["PNUD"] if sources.get("pnud", {}).get("actif") else []
    for nom in attendues:
        n, p = par_source.get(nom, 0), avant.get(nom, 0)
        if n == 0:
            SANTE.append(f"{nom} : aucune offre lue")
        elif p >= 10 and n < 0.3 * p:
            SANTE.append(f"{nom} : {n} offres contre {p} au passage précédent")
    for a in SANTE:
        journal(f"  ALERTE source — {a}")
    fichier.write_text(json.dumps({**avant, **par_source}, ensure_ascii=False, indent=1), encoding="utf-8")


def charger_profils(nom: str | None) -> list[dict]:
    fichiers = [f for f in sorted((RACINE / "profils").glob("*.yaml")) if f.stem != "exemple"]
    profils = [yaml.safe_load(f.read_text(encoding="utf-8")) for f in fichiers]
    if nom:
        profils = [p for p in profils if p["identifiant"] == nom]
        if not profils:
            sys.exit(f"Profil « {nom} » introuvable dans profils/.")
    return profils


def executer(args) -> None:
    base = Base(RACINE / "donnees" / "veille.sqlite")
    nouveaux: set[str] = set()
    if not args.sans_collecte:
        sources = yaml.safe_load((RACINE / "sources.yaml").read_text(encoding="utf-8"))
        journal("Collecte : début")
        connus = base.uids_avec_description()
        n, par_source = 0, {}
        for o in collecteurs.tout_collecter(sources, connus, journal):
            if not valide(o):
                continue
            par_source[o["source"]] = par_source.get(o["source"], 0) + 1
            if base.enregistrer(o):
                nouveaux.add(o["uid"])
            n += 1
            if n % 25 == 0:  # sauvegarde régulière : une coupure ne fait rien perdre
                base.valider()
        base.valider()
        journal(f"Collecte : {n} offres lues, {len(nouveaux)} nouvelles")
        controler_sources(sources, par_source)

    nouveaux |= base.uids_recents()
    offres = base.offres_actives()
    for p in charger_profils(args.profil):
        suivi = base.suivi(p["identifiant"])
        lignes = []
        for o in offres:
            ev = evaluer(o, p)
            base.enregistrer_evaluation(p["identifiant"], o["uid"], ev)
            if ev["score"] >= p.get("seuil_affichage", 35):
                lignes.append({**o, **ev, **{k: v for k, v in suivi.get(o["uid"], {}).items() if k != "uid"}})
        base.valider()
        # Dossier de candidature (coach) pour chaque offre au-dessus du seuil d'alerte
        for l in sorted(lignes, key=lambda l: -l["score"])[: p.get("dossiers_max", 40)]:
            if l["score"] >= p.get("seuil_alerte", 60):
                l["dossier_md"] = coach.construire(l, l, p)
        sortie = rapport.produire(RACINE / "rapports" / p["identifiant"], p, lignes, nouveaux,
                                  sante=SANTE, racine_site=RACINE / "site")
        if sortie["site"]:
            journal(f"Application web chiffrée prête : {sortie['site']}")
        journal(f"Profil {p['identifiant']} : {len(lignes)} offres retenues, "
                f"{sortie['nb_prioritaires']} nouvelles prioritaires → {sortie['html']}")


def dossier(uid: str, nom: str) -> None:
    """Produit le dossier de candidature d'une offre précise, quel que soit son score."""
    p = charger_profils(nom)[0]
    o = next((o for o in Base(RACINE / "donnees" / "veille.sqlite").offres_actives(365) if o["uid"] == uid), None)
    if not o:
        sys.exit("Identifiant inconnu (voir la colonne Identifiant du fichier offres.csv).")
    chemin = coach.ecrire(RACINE / "rapports" / p["identifiant"] / "candidatures", o, evaluer(o, p), p)
    print(f"Dossier de candidature : {chemin}")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "dossier":
        ap = argparse.ArgumentParser(prog="veille.py dossier")
        ap.add_argument("_cmd")
        ap.add_argument("uid")
        ap.add_argument("--profil", default="marcellin")
        a = ap.parse_args()
        dossier(a.uid, a.profil)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "statut":
        ap = argparse.ArgumentParser(prog="veille.py statut")
        ap.add_argument("_cmd")
        ap.add_argument("uid")
        ap.add_argument("statut", choices=STATUTS)
        ap.add_argument("--note", default="")
        ap.add_argument("--profil", default="marcellin")
        a = ap.parse_args()
        ok = Base(RACINE / "donnees" / "veille.sqlite").changer_statut(a.profil, a.uid, a.statut, a.note)
        print("Statut enregistré." if ok else "Identifiant inconnu pour ce profil.")
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profil")
    ap.add_argument("--sans-collecte", action="store_true")
    executer(ap.parse_args())


if __name__ == "__main__":
    main()
