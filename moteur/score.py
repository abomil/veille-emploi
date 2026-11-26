"""Évaluation d'une offre contre un profil, à la manière d'un ATS (Applicant Tracking System).

Les ATS (Workday, Oracle Taleo/Recruiting, Inspira, SuccessFactors, Greenhouse…) et les outils de
« talent sourcing » classent un dossier surtout par :
  1. la présence littérale des termes de l'offre dans le CV (titre de poste, compétences, outils) ;
  2. le poids accru des termes présents dans l'INTITULÉ ;
  3. les critères éliminatoires (langue, niveau, expérience).
Le score reproduit ces trois mécanismes, puis ajoute vos aspirations (français, télétravail,
consultance, rémunération). Il est explicable : chaque point est justifié dans le détail.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

PAYS_FRANCOPHONES = [
    "cote d'ivoire", "ivory coast", "abidjan", "senegal", "dakar", "mali", "bamako", "burkina", "ouagadougou",
    "niger", "niamey", "guinea", "guinee", "conakry", "benin", "cotonou", "togo", "lome", "cameroon",
    "cameroun", "yaounde", "douala", "chad", "tchad", "ndjamena", "n'djamena", "central african", "centrafrique",
    "bangui", "gabon", "libreville", "congo", "kinshasa", "brazzaville", "goma", "bukavu", "lubumbashi",
    "burundi", "bujumbura", "rwanda", "kigali", "madagascar", "antananarivo", "djibouti", "comoros", "comores",
    "mauritania", "mauritanie", "nouakchott", "haiti", "port-au-prince", "morocco", "maroc", "rabat",
    "tunisia", "tunisie", "tunis", "algeria", "algerie", "lebanon", "liban", "beirut", "france", "paris",
    "geneva", "geneve", "switzerland", "suisse", "belgium", "belgique", "brussels", "bruxelles",
    "luxembourg", "quebec", "montreal", "canada", "mauritius", "maurice", "seychelles", "vanuatu",
    "equatorial guinea", "cabo verde",
]
TELETRAVAIL = ["home-based", "home based", "homebased", "remote", "teletravail", "a distance", "work from home",
               "telework", "anywhere", "virtual"]
CONSULTANCE = ["consultant", "consultancy", "consultance", "individual contract", "ipsa", "nps a",
               "expert", "short-term", "court terme"]
MOTS_FR = [" le ", " la ", " les ", " des ", " et ", " pour ", " dans ", " avec ", " une ", " du "]


@lru_cache(maxsize=None)
def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower().replace("’", "'").replace("–", "-"))
    return "".join(c for c in t if not unicodedata.combining(c))


@lru_cache(maxsize=None)
def motif(terme: str) -> re.Pattern:
    # le pluriel est accepté (stock/stocks, indicateur/indicateurs), comme le font les ATS récents
    return re.compile(r"(?<![a-z0-9])" + re.escape(norm(terme)) + r"(?:s|x|es)?(?![a-z0-9])")


def trouve(termes, texte_norm: str) -> list[str]:
    return [t for t in termes if motif(t).search(texte_norm)]


GRADE = re.compile(r"\b(p-?[1-6]|d-?[12]|no-?[a-d]|noa|nob|noc|nod|g-?[1-7]|gl\s?[a-h]|ipsa-?\d{1,2}|"
                   r"npsa-?\d{1,2})\b")


def grade_et_remuneration(titre: str, contrat: str, texte: str) -> tuple[str, str]:
    m = GRADE.search(norm(f"{titre} {contrat}")) or GRADE.search(texte[:3000])
    g = m.group(1).upper().replace(" ", "") if m else ""
    n = norm(g)
    if re.match(r"(p-?[4-6]|d-?[12]|nod|gl[f-h]|ipsa-?1[2-9])", n):
        niveau = "très élevée"
    elif re.match(r"(p-?3|noc|gl[de]|ipsa-?(9|1[01]))", n):
        niveau = "élevée"
    elif re.match(r"(p-?[12]|no-?[ab]|noa|nob|ipsa|npsa-?1[0-1])", n):
        niveau = "moyenne"
    elif re.match(r"(g-?\d|npsa)", n):
        niveau = "locale"
    else:
        niveau = "à vérifier"
    return g, niveau


def evaluer(offre: dict, profil: dict) -> dict:
    titre_n = norm(offre.get("titre", ""))
    texte = f"{offre.get('titre','')}\n{offre.get('description','')}"
    tn = norm(texte)
    lieu_n = norm(f"{offre.get('lieu','')} {offre.get('organisation','')}")
    cv_n = norm(f"{profil.get('cv_texte', '')}\n{profil.get('cv_texte_en', '')}")
    detail, pts = [], 0.0

    # 1. Couverture des compétences (55 pts) + intitulé (12 pts)
    familles = profil["familles"]
    total_poids = sum(f["poids"] for f in familles.values()) or 1
    couverture, presents, absents_cv = {}, [], []
    pts_comp = pts_titre = 0.0
    for cle, f in familles.items():
        hits = trouve(f["termes"], tn)
        couverture[cle] = len(hits)
        pts_comp += 55 * f["poids"] / total_poids * min(1.0, len(hits) / 4)
        if trouve(f["termes"], titre_n):
            pts_titre += 12 * f["poids"] / total_poids * 2
        for h in hits:
            (presents if motif(h).search(cv_n) else absents_cv).append(h)
    pts_titre = min(12.0, pts_titre)
    pts += pts_comp + pts_titre
    detail.append(f"compétences +{pts_comp:.0f}")
    if pts_titre:
        detail.append(f"intitulé +{pts_titre:.0f}")

    # Domaine : ni supply chain ni santé dans l'offre → hors de votre terrain
    if not couverture.get("supply_sante") and not couverture.get("sante_mondiale"):
        pts -= 12
        detail.append("ni santé ni supply chain −12")

    # 2. Séniorité et exclusions
    if trouve(profil.get("exclusions", []), titre_n):
        pts -= 40
        detail.append("hors cible −40")
    if trouve(profil.get("seniorite_moins", []), titre_n):
        pts -= 15
        detail.append("niveau junior −15")
    elif trouve(profil.get("seniorite_plus", []), titre_n):
        pts += 8
        detail.append("séniorité +8")

    # 3. Langue
    L = profil.get("langue", {})
    redige_fr = sum(tn.count(m) for m in MOTS_FR) > 25
    fr_exige = fr_atout = en_exige = False
    for phrase in re.split(r"[.\n;•]", tn):  # chaque phrase qui parle de langue est classée
        atout = re.search(r"asset|advantage|desirable|preferred|a plus|an added|atout|souhait|apprecie", phrase)
        if re.search(r"french|francais", phrase):
            if atout:
                fr_atout = True
            elif re.search(r"requir|essential|mandatory|fluen|proficien|excellent|requis|exige|obligatoire|"
                           r"indispensable|maitrise|courant", phrase):
                fr_exige = True
        if re.search(r"english|anglais", phrase) and re.search(
                r"requir|essential|mandatory|fluen|proficien|excellent|requis|exige|obligatoire|courant", phrase) \
                and not re.search(r"english[^,]{0,25}(is an? )?(asset|advantage|desirable|atout)|anglais[^,]{0,25}atout", phrase):
            en_exige = True
    if re.search(r"francophone", tn):
        fr_exige = True
    francophone = bool(trouve(PAYS_FRANCOPHONES, lieu_n))
    bonus_fr = L.get("francais_obligatoire_bonus", 15)
    if redige_fr:
        niveau_fr = "offre en français"
        pts += bonus_fr
        detail.append(f"offre rédigée en français +{bonus_fr}")
    elif fr_exige:
        niveau_fr = "français exigé"
        pts += bonus_fr - 3
        detail.append(f"français exigé +{bonus_fr - 3}")
    elif fr_atout:
        niveau_fr = "français atout"
        pts += 5
        detail.append("français atout +5")
    else:
        niveau_fr = ""
    if francophone:
        pts += L.get("pays_francophone_bonus", 8)
        detail.append("pays francophone +%d" % L.get("pays_francophone_bonus", 8))
    if en_exige and not redige_fr:
        malus = L.get("anglais_courant_exige_malus", 10) // (2 if fr_exige else 1)
        pts -= malus
        detail.append(("bilingue anglais-français exigé −%d" if fr_exige else "anglais courant exigé −%d") % malus)
    fr_exige = redige_fr or fr_exige

    # 4. Modalités
    M = profil.get("modalites_bonus", {})
    remote = bool(trouve(TELETRAVAIL, f"{titre_n} {lieu_n} {tn[:4000]}"))
    consult = bool(trouve(CONSULTANCE, f"{titre_n} {norm(offre.get('contrat',''))}"))
    if remote:
        pts += M.get("remote", 10)
        detail.append("télétravail possible +%d" % M.get("remote", 10))
    if consult:
        pts += M.get("consultance", 6)
        detail.append("consultance +%d" % M.get("consultance", 6))

    grade, remu = grade_et_remuneration(offre.get("titre", ""), offre.get("contrat", ""), tn)
    if remu in ("très élevée", "élevée"):
        pts += 5
        detail.append("rémunération %s +5" % remu)
    elif remu == "locale":
        pts -= 10
        detail.append("grade local −10")

    if not offre.get("description"):
        detail.append("description non lue : score partiel")

    score = max(0, min(100, round(pts)))
    return {
        "score": score, "detail": detail, "couverture": couverture,
        "points_forts": sorted(set(presents)), "ecarts_ats": sorted(set(absents_cv)),
        "francais": fr_exige, "francais_niveau": niveau_fr, "francophone": francophone, "anglais_exige": en_exige,
        "teletravail": remote, "consultance": consult, "grade": grade, "remuneration": remu,
    }
