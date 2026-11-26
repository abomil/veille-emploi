"""Production des livrables : tableau de bord HTML autonome, export CSV, note des nouveautés."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from . import site

LIBELLES_STATUT = {"nouveau": "Nouveau", "a_etudier": "À étudier", "a_postuler": "À postuler",
                   "candidature_envoyee": "Candidature envoyée", "entretien": "Entretien", "ecarte": "Écarté"}


def produire(dossier: Path, profil: dict, lignes: list[dict], nouveaux: set[str],
             sante: list[str] | None = None, racine_site: Path | None = None) -> dict:
    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%d/%m/%Y à %H:%M")
    for l in lignes:
        l["nouveau"] = l["uid"] in nouveaux
        l["statut_libelle"] = LIBELLES_STATUT.get(l.get("statut", "nouveau"), l.get("statut", ""))
        l["extrait"] = (l.get("description") or "")[:600]
        l.pop("description", None)

    # CSV (s'ouvre dans Excel : séparateur point-virgule, encodage UTF-8 avec BOM)
    csv_p = dossier / "offres.csv"
    with csv_p.open("w", newline="", encoding="utf-8-sig") as f:
        brut = csv.writer(f, delimiter=";")

        class w:  # neutralise l'injection de formules Excel (=, +, -, @ en début de cellule)
            @staticmethod
            def writerow(r):
                brut.writerow(["'" + c if isinstance(c, str) and c[:1] in ("=", "+", "-", "@", "\t", "\r") else c
                               for c in r])
        w.writerow(["Score", "Nouveau", "Statut", "Intitulé", "Organisation", "Lieu", "Grade", "Rémunération",
                    "Français", "Télétravail", "Consultance", "Date limite", "Écarts ATS", "Lien", "Identifiant"])
        for l in lignes:
            w.writerow([l["score"], "oui" if l["nouveau"] else "", l["statut_libelle"], l["titre"], l["organisation"],
                        l["lieu"], l["grade"], l["remuneration"], "oui" if l["francais"] else "",
                        "oui" if l["teletravail"] else "", "oui" if l["consultance"] else "", l["limite"],
                        ", ".join(l["ecarts_ats"]), l["url"], l["uid"]])

    # Note des nouveautés prioritaires
    prio = sorted((l for l in lignes if l["nouveau"] and l["score"] >= profil.get("seuil_alerte", 60)),
                  key=lambda l: -l["score"])
    md_p = dossier / "nouveautes.md"
    md = [f"# Nouveautés prioritaires — {horodatage}", "",
          f"{len(prio)} nouvelle(s) offre(s) au-dessus du seuil d'alerte ({profil.get('seuil_alerte', 60)}).", ""]
    for l in prio:
        md += [f"## {l['score']}/100 — {l['titre']}", f"- {l['organisation']} · {l['lieu']}",
               f"- Grade : {l['grade'] or 'non indiqué'} · rémunération {l['remuneration']} · date limite : {l['limite'] or 'non indiquée'}",
               f"- Pourquoi : {', '.join(l['detail'])}",
               f"- À reprendre dans le CV (si maîtrisé) : {', '.join(l['ecarts_ats']) or 'rien'}",
               f"- {l['url']}", ""]
    md_p.write_text("\n".join(md), encoding="utf-8")

    html_p = dossier / "tableau-de-bord.html"
    gabarit = (Path(__file__).parent / "gabarit.html").read_text(encoding="utf-8")
    contenu = {"identifiant": profil["identifiant"], "profil": profil.get("nom", ""),
               "cible": profil.get("titre_cible", ""), "horodatage": horodatage,
               "seuil_alerte": profil.get("seuil_alerte", 60), "sante": sante or [], "offres": lignes}
    # « </ » et les séparateurs de ligne Unicode sont neutralisés : aucune offre ne peut casser le script
    donnees = (json.dumps(contenu, ensure_ascii=False).replace("</", "<\\/")
               .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    html_p.write_text(gabarit.replace("/*__DONNEES__*/null", donnees, 1), encoding="utf-8")
    site_p = site.construire(racine_site, profil, contenu) if racine_site else None
    return {"html": html_p, "csv": csv_p, "nouveautes": md_p, "nb_prioritaires": len(prio), "site": site_p}
