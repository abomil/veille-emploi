"""Dossier de candidature par offre : le regard croisé de quatre spécialistes.

  - le détecteur de talents (sourceur) : comment un recruteur cherche ce poste, et si le profil ressort ;
  - le docteur en ressources humaines : critères d'éligibilité, niveau, points de vigilance ;
  - le spécialiste du personal branding : titre, accroche, promesse alignés sur l'intitulé visé ;
  - le coach : réalisations à mettre en avant, lettre de motivation, préparation d'entretien.

Tout est produit à partir du profil (banque de réalisations) et du texte de l'offre ; rien n'est inventé :
les chiffres manquants restent signalés [à chiffrer]. Le dossier est un brouillon à relire et à adapter.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from .score import motif, norm, trouve

# Années d'expérience usuelles par grade (référentiel du système commun des Nations unies, master requis)
ANNEES_PAR_GRADE = {"P1": 0, "P2": 2, "P3": 5, "P4": 7, "P5": 10, "D1": 15, "D2": 15,
                    "NOA": 1, "NOB": 2, "NOC": 5, "NOD": 7}

MISSIONS = {
    "fonds mondial": ("mettre fin aux épidémies de sida, de tuberculose et de paludisme",
                      "ending AIDS, tuberculosis and malaria as epidemics"),
    "global fund": ("mettre fin aux épidémies de sida, de tuberculose et de paludisme",
                    "ending AIDS, tuberculosis and malaria as epidemics"),
    "pam": ("sauver des vies et changer des vies face à la faim", "saving lives and changing lives in the face of hunger"),
    "wfp": ("sauver des vies et changer des vies face à la faim", "saving lives and changing lives in the face of hunger"),
    "hcr": ("protéger et assister les personnes déracinées", "protecting and assisting forcibly displaced people"),
    "path": ("rendre l'innovation en santé accessible à tous", "advancing health equity through innovation"),
    "fhi 360": ("améliorer durablement la santé et le bien-être des populations",
                "improving lives in lasting ways through integrated, evidence-based solutions"),
    "msh": ("renforcer les systèmes de santé pour sauver des vies", "strengthening health systems to save lives"),
    "irc": ("aider les personnes touchées par les crises humanitaires à survivre et à se relever",
            "helping people affected by humanitarian crises to survive, recover and rebuild"),
    "world vision": ("améliorer durablement la vie des enfants les plus vulnérables",
                     "improving the lives of the most vulnerable children"),
    "pnud": ("accompagner les pays vers un développement durable", "helping countries achieve sustainable development"),
    "undp": ("accompagner les pays vers un développement durable", "helping countries achieve sustainable development"),
    "unicef": ("garantir à chaque enfant l'accès aux soins et aux produits essentiels",
               "ensuring every child has access to essential health supplies"),
    "oms": ("garantir le meilleur état de santé possible à tous", "achieving the highest attainable level of health for all"),
}
MISSION_DEFAUT = ("rendre les produits de santé disponibles pour les populations qui en ont besoin",
                  "making health products available to the people who need them")

VALEUR = {  # ce que vous apportez, par famille de compétences dominante de l'offre
    "supply_sante": ("sécuriser la disponibilité des produits de santé, de la quantification au dernier kilomètre",
                     "securing the availability of health products, from quantification to the last mile"),
    "data_decision": ("faire des données logistiques un outil de décision fiable pour les directions et les bailleurs",
                      "turning logistics data into a reliable decision tool for managers and donors"),
    "suivi_evaluation": ("piloter la performance par des indicateurs et un suivi-évaluation rigoureux",
                         "driving performance through indicators and rigorous monitoring and evaluation"),
    "achats_projet": ("conduire des achats internationaux transparents et performants",
                      "running transparent, high-performing international procurement"),
    "sante_mondiale": ("servir les programmes de santé publique financés par les grands bailleurs",
                       "serving donor-funded public health programmes"),
}

QUESTIONS = {  # questions comportementales probables par famille (FR, EN)
    "supply_sante": [("Racontez une rupture de stock que vous avez évitée ou résolue : comment l'avez-vous vue venir ?",
                      "Tell us about a stock-out you prevented or resolved: how did you see it coming?"),
                     ("Comment conduisez-vous un exercice de quantification avec des données incomplètes ?",
                      "How do you run a quantification exercise when data is incomplete?")],
    "data_decision": [("Donnez un exemple où une analyse de données a changé une décision de la direction.",
                       "Give an example where your data analysis changed a management decision."),
                      ("Comment améliorez-vous la qualité des données remontées par les sites ?",
                       "How do you improve the quality of data reported by facilities?")],
    "suivi_evaluation": [("Comment construisez-vous un cadre de suivi-évaluation et choisissez-vous les indicateurs ?",
                          "How do you build an M&E framework and choose indicators?"),
                         ("Parlez d'une évaluation dont les résultats ont été réellement utilisés.",
                          "Describe an evaluation whose findings were actually used.")],
    "achats_projet": [("Décrivez un appel d'offres international difficile et la manière dont vous l'avez mené.",
                       "Describe a difficult international tender and how you managed it."),
                      ("Comment gérez-vous un fournisseur qui ne respecte pas ses engagements ?",
                       "How do you handle a supplier that fails to meet its commitments?")],
    "sante_mondiale": [("Comment travaillez-vous avec le ministère de la Santé et plusieurs bailleurs aux attentes différentes ?",
                        "How do you work with the Ministry of Health and several donors with different expectations?")],
}
QUESTIONS_GENERALES = [
    ("Pourquoi ce poste, et pourquoi maintenant ?", "Why this role, and why now?"),
    ("Parlez-nous d'un désaccord avec un supérieur ou un partenaire et de sa résolution.",
     "Tell us about a disagreement with a manager or partner and how it was resolved."),
    ("Qu'apporterez-vous dans les 90 premiers jours ?", "What will you deliver in your first 90 days?"),
]

STOP = set("""a an the and or of for to in on with by at from as is are be this that will your our their its
           de la le les des du et ou pour dans sur avec par au aux en un une ce cette ses son leur nos vos""".split())


def _texte(offre: dict) -> str:
    return norm(f"{offre.get('titre', '')}\n{offre.get('description', '')}")


def _intitule_propre(titre: str) -> str:
    t = re.split(r"\s[-–|]\s(?=(?:GL|P-?\d|NO|G-?\d|Defined|Fixed|Temporary|IPSA|NPSA|Home|Remote))", titre)[0]
    t = t.split(" / ")[0]
    t = re.sub(r"(\s*-\s*[A-Z0-9]{2,}\b)+\s*$", "", t)  # codes de fin : « - AFGHS- PATH », « - GL D »
    return re.sub(r"\s{2,}", " ", t).strip(" ,-")


def _mission(offre: dict, fr: bool) -> str:
    org = norm(offre.get("organisation", ""))
    for cle, (m_fr, m_en) in MISSIONS.items():
        if motif(cle).search(org):
            return m_fr if fr else m_en
    return MISSION_DEFAUT[0 if fr else 1]


def _de(texte: str) -> str:
    """« de » ou « d' » selon la première lettre (élision française)."""
    return ("d'" if norm(texte[:1]) in "aeiouyh" else "de ") + texte


def _realisations(offre: dict, profil: dict, n: int = 4) -> list[dict]:
    tn = _texte(offre)
    titre_n = norm(offre.get("titre", ""))
    notes = []
    for r in profil.get("realisations", []):
        hits = trouve(r.get("tags", []), tn)
        s = len(hits) + 2 * len(trouve(r.get("tags", []), titre_n))
        if s:
            notes.append((s, r, hits))
    notes.sort(key=lambda x: -x[0])
    return [{**r, "_hits": h} for _, r, h in notes[:n]]


def _exigences(offre: dict) -> dict:
    tn = _texte(offre)
    ans = [int(x) for x in re.findall(r"(\d{1,2})\s*\+?\s*(?:years|yrs|ans|annees)", tn) if 1 <= int(x) <= 25]
    return {
        "annees": max(ans) if ans else None,
        "doctorat": bool(re.search(r"\b(phd|doctorat|doctorate)\b", tn)),
        "master": bool(re.search(r"\b(master|advanced (university )?degree|maitrise|bac\s?\+\s?5|graduate degree)", tn)),
        "pays_restreint": bool(re.search(r"(national|nationals|ressortissant)[^.]{0,40}(only|uniquement|seulement)|"
                                         r"open to [a-z ]{0,20}nationals", tn)),
    }


def _requete_sourceur(offre: dict, profil: dict, ev: dict) -> tuple[str, list[tuple[str, bool]]]:
    """Reconstitue la requête booléenne qu'un sourceur taperait, et vérifie chaque terme dans le CV."""
    titre = _intitule_propre(offre.get("titre", ""))
    cles = []
    for f in profil["familles"].values():
        for t in f["termes"]:
            if motif(t).search(_texte(offre)) and t not in cles:
                cles.append(t)
    cles = cles[:8]
    cv = norm(f"{profil.get('cv_texte', '')}\n{profil.get('cv_texte_en', '')}")
    # l'intitulé exact compte à part : les sourceurs filtrent d'abord sur le titre du poste
    controle = [(f"intitulé « {titre} »", bool(motif(titre).search(cv)))] + [(t, bool(motif(t).search(cv))) for t in cles]
    req = ("(" + " OR ".join(f'"{t}"' for t in [titre.lower(), *cles[:3]]) + ")"
           + (" AND (" + " OR ".join(f'"{t}"' for t in cles[3:8]) + ")" if len(cles) > 3 else "")
           + (' AND (French OR français)' if ev.get("francais") or ev.get("francophone") else ""))
    return req, controle


def _verdict(ev: dict, exig: dict, profil: dict) -> tuple[str, list[str], list[str]]:
    atouts, vigilance = [], []
    annees = profil.get("annees_experience", 0)
    grade = norm(ev.get("grade", "")).upper().replace("-", "").replace(" ", "")
    if exig["annees"]:
        (atouts if annees >= exig["annees"] else vigilance).append(
            f"Expérience demandée : {exig['annees']} ans ; vous en avez {annees}.")
    attendu = ANNEES_PAR_GRADE.get(grade)
    if attendu is not None:
        if annees >= attendu + 8:
            vigilance.append(f"Grade {ev['grade']} (≈ {attendu} ans attendus) : risque de surqualification. "
                             "Expliquez votre choix (terrain, thématique, mobilité) en une phrase dans la lettre.")
        elif annees >= attendu:
            atouts.append(f"Votre expérience couvre le niveau attendu pour le grade {ev['grade']} (≈ {attendu} ans).")
    if exig["doctorat"]:
        vigilance.append("Un doctorat est mentionné : vérifiez s'il est exigé ou seulement souhaité.")
    elif exig["master"]:
        atouts.append("Master exigé : " + profil.get("marque", {}).get("master_fr", "vérifiez que votre diplôme y répond."))
    if exig["pays_restreint"]:
        vigilance.append("L'offre semble réservée à certaines nationalités : vérifiez votre éligibilité avant tout.")
    if ev.get("anglais_exige"):
        vigilance.append("Anglais exigé : préparez une présentation de 2 minutes et vos 3 réalisations en anglais, "
                         "à voix haute. L'entretien technique peut se faire en anglais.")
    if ev.get("francais_niveau"):
        atouts.append(f"Langue : {ev['francais_niveau']}. Mettez « français langue maternelle » en tête de la rubrique Langues.")
    if ev.get("francophone"):
        atouts.append("Poste en pays francophone : votre connaissance des systèmes de santé d'Afrique francophone est un avantage direct.")
    s = ev["score"]
    if s >= 75 and not any("réservée" in v for v in vigilance):
        decision = "Postuler en priorité, dans les 5 jours (les premiers dossiers sont souvent lus en premier)."
    elif s >= 60:
        decision = "Postuler avec un CV adapté à cette offre."
    else:
        decision = "Candidature d'opportunité : seulement si vous avez un contact ou une recommandation dans l'organisation."
    return decision, atouts, vigilance


def construire(offre: dict, ev: dict, profil: dict) -> str:
    """Renvoie le dossier de candidature au format Markdown."""
    fr_offre = ev.get("francais_niveau") == "offre en français"
    titre = _intitule_propre(offre.get("titre", ""))
    exig = _exigences(offre)
    decision, atouts, vigilance = _verdict(ev, exig, profil)
    reals = _realisations(offre, profil)
    couv = ev.get("couverture", {})
    familles = sorted((k for k in couv if couv[k]), key=lambda k: -couv[k] * profil["familles"][k]["poids"])
    dom = familles[:2] or ["supply_sante"]
    annees = profil.get("annees_experience", 15)
    m = profil.get("marque", {})
    sig = profil.get("signature", profil.get("nom", ""))
    req, controle = _requete_sourceur(offre, profil, ev)

    L = [f"# Dossier de candidature — {offre.get('titre', '')}", "",
         f"**{offre.get('organisation', '')}** · {offre.get('lieu') or 'lieu non précisé'} · "
         f"date limite : {offre.get('limite') or 'non indiquée'} · [voir l'offre]({offre.get('url', '')})", "",
         f"> Score d'adéquation : **{ev['score']}/100**. {decision}", ""]

    # 1. Docteur RH
    L += ["## 1. Le regard du docteur en ressources humaines : éligibilité et niveau", ""]
    L += [f"- ✅ {a}" for a in atouts] + [f"- ⚠️ {v}" for v in vigilance]
    if not atouts and not vigilance:
        L.append("- Aucun critère éliminatoire détecté dans le texte ; lisez la rubrique « Qualifications » de l'offre.")
    L += ["", "Règle d'or : chaque critère « requis » de l'offre doit trouver sa réponse explicite, avec les mêmes mots, "
          "dans votre CV ou votre formulaire. Un critère non visible est considéré comme absent.", ""]

    # 2. Détecteur de talents
    L += ["## 2. Le regard du détecteur de talents : serez-vous trouvé ?", "",
          "Requête qu'un recruteur ou un sourceur taperait dans son ATS ou sur LinkedIn :", "",
          f"```\n{req}\n```", "",
          "Vérification de votre CV terme par terme :", ""]
    L += [f"- {'✅' if ok else '❌'} {t}" for t, ok in controle]
    manquants = [t for t, ok in controle if not ok]
    if manquants:
        L += ["", f"**À intégrer mot pour mot** (si vous le maîtrisez) : {', '.join(manquants)}. "
              "Placez l'intitulé exact du poste dans votre titre de CV, et les autres termes dans vos réalisations "
              "et votre rubrique Compétences. Les ATS ne reconnaissent pas toujours les synonymes."]
    if not fr_offre:
        L += ["", "Offre rédigée en anglais : l'ATS lira un **CV en anglais**. Les termes anglais ci-dessus doivent "
              "figurer dans cette version (base de départ : `cv_texte_en` de votre profil)."]
    L.append("")

    # 3. Personal branding
    accroche_fr = (f"Expert de la supply chain des produits de santé et de la donnée au service de la décision — {annees} ans en supply chain des produits de santé, data management et aide à la décision, "
                   f"{m.get('contexte_fr', '')}. {m.get('promesse_fr', '')}")
    accroche_en = (f"Health supply chain and data-for-decision expert — {annees} years in health supply chain, data management and decision support, "
                   f"{m.get('contexte_en', '')}. {m.get('promesse_en', '')}")
    L += ["## 3. Le regard du spécialiste en personal branding : votre positionnement pour cette offre", "",
          "**Titre de CV** (reprend l'intitulé visé, c'est ce que l'ATS compare en premier) :", "",
          f"> {titre} | {'Supply chain santé' if fr_offre else 'Health Supply Chain'} | "
          f"{'Data & aide à la décision' if fr_offre else 'Data for Decision-Making'} | {annees} {'ans' if fr_offre else 'yrs'}", "",
          "**Profil (3 lignes en haut du CV)**", ""]
    L += ([f"> {accroche_fr}"] if fr_offre else [f"> {accroche_en}", "", f"*En français :* {accroche_fr}"])
    L += ["", f"**Titre LinkedIn conseillé** : {m.get('titre_linkedin_fr' if fr_offre else 'titre_linkedin_en', '')}", ""]

    # 4. Coach : réalisations
    L += ["## 4. Le regard du coach : vos preuves pour ce poste", "",
          "Réalisations à placer en tête de votre expérience actuelle (choisies selon les mots de l'offre) :", ""]
    for r in reals:
        L.append(f"- **{r['fr'] if fr_offre else r['en']}**")
        if not fr_offre:
            L.append(f"  *({r['fr']})*")
        L.append(f"  Compétence démontrée : {r['competence']} · mots de l'offre couverts : {', '.join(r['_hits'][:6])}")
    if any("[" in (r["fr"]) for r in reals):
        L += ["", "Remplacez chaque crochet par un chiffre réel. Méthode : *verbe d'action + quoi + résultat chiffré + impact "
              "pour les patients ou le programme*. Exemple : « taux de disponibilité des antipaludiques porté de 82 % à 95 % »."]
    L.append("")

    # 5. Lettre de motivation
    preuves = reals[:3]
    v_fr = " et ".join(VALEUR[k][0] for k in dom)
    v_en = " and ".join(VALEUR[k][1] for k in dom)
    lettre_fr = [
        "Madame, Monsieur,", "",
        f"Votre organisation s'est donné pour mission {_de(_mission(offre, True))}. Depuis {annees} ans, je contribue "
        f"à cette même ambition {m.get('ancrage_fr', '')}. "
        f"C'est pourquoi le poste de « {titre} » a retenu toute mon attention.", "",
        f"Ce que je vous propose : {v_fr}. Trois exemples concrets :", "",
        *[f"- {r['fr']}" for r in preuves], "",
        m.get("formation_fr", ""), "",
        "Je serais heureux d'échanger avec vous sur la manière dont je peux contribuer aux résultats de votre équipe dès les "
        "premiers mois.", "", "Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.", "", sig]
    lettre_en = [
        "Dear Hiring Manager,", "",
        f"Your organization is committed to {_mission(offre, False)}. For {annees} years I have served that same goal {m.get('ancrage_en', '')}. This is why the {titre} position caught my attention.", "",
        f"What I bring: {v_en}. Three concrete examples:", "",
        *[f"- {r['en']}" for r in preuves], "",
        m.get("formation_en", ""), "",
        "I would welcome the opportunity to discuss how I can contribute to your team's results from the first months.", "",
        "Sincerely,", "", sig]
    L += ["## 5. Lettre de motivation (brouillon à personnaliser)", "",
          "Structure : mission de l'employeur → votre proposition de valeur → 3 preuves → double compétence → ouverture. "
          "Une page maximum. Ajoutez une phrase qui montre que vous connaissez un projet précis de l'organisation dans le pays.", ""]
    if fr_offre:
        L += ["```", *lettre_fr, "```", ""]
    else:
        L += ["**Version à envoyer (anglais)**", "", "```", *lettre_en, "```", "",
              "**Version française (pour vérifier le sens)**", "", "```", *lettre_fr, "```", ""]

    # 6. Entretien
    qs = [q for k in dom for q in QUESTIONS.get(k, [])] + QUESTIONS_GENERALES
    L += ["## 6. Préparation de l'entretien", "",
          "Méthode STAR pour chaque réponse : **S**ituation, **T**âche, **A**ctions (les vôtres, au « je »), **R**ésultat chiffré. "
          "Deux minutes par réponse. Les Nations unies et la plupart des ONG notent par compétence ; chaque réalisation "
          "ci-dessus indique celle qu'elle démontre.", ""]
    for q_fr, q_en in qs:
        L.append(f"- {q_fr}" + ("" if fr_offre else f"  \n  *{q_en}*"))
    L += ["", "Question à poser à la fin : « Quels seraient, pour vous, les résultats qui montreraient dans un an que "
          "la personne recrutée a réussi ? »", ""]

    # 7. Check-list
    L += ["## 7. Check-list avant envoi", "",
          "- [ ] Intitulé exact du poste dans le titre du CV et dans l'objet du courriel ou du formulaire",
          "- [ ] Chaque critère « requis » de l'offre visible dans le CV, avec les mêmes mots",
          "- [ ] Toutes les réalisations chiffrées (plus aucun crochet)",
          "- [ ] CV en format simple (Word ou PDF texte, sans tableau ni colonne) pour être lu par l'ATS",
          "- [ ] Rubrique Langues : français langue maternelle ; niveau d'anglais honnête et précis",
          "- [ ] Formulaire en ligne rempli entièrement : les ATS (Workday, Inspira, Oracle) notent souvent le formulaire, pas le CV joint",
          "- [ ] Statut mis à jour dans le tableau de bord (« Candidature envoyée »)", ""]
    return "\n".join(L)


# ── Conversion Markdown → page HTML lisible (sans dépendance) ────────────────────────────────────────────
def _inline(t: str) -> str:
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)
    return re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)


def en_html(md: str, titre: str) -> str:
    out, liste, code = [], False, False
    for ligne in md.split("\n"):
        if ligne.startswith("```"):
            out.append("</pre>" if code else "<pre>")
            code = not code
            continue
        if code:
            out.append(html.escape(ligne))
            continue
        if liste and not ligne.startswith(("- ", "  ")):
            out.append("</ul>")
            liste = False
        if ligne.startswith("# "):
            out.append(f"<h1>{_inline(ligne[2:])}</h1>")
        elif ligne.startswith("## "):
            out.append(f"<h2>{_inline(ligne[3:])}</h2>")
        elif ligne.startswith("> "):
            out.append(f"<blockquote>{_inline(ligne[2:])}</blockquote>")
        elif ligne.startswith("- "):
            if not liste:
                out.append("<ul>")
                liste = True
            item = ligne[2:].replace("[ ] ", "☐ ")
            out.append(f"<li>{_inline(item)}")
        elif ligne.startswith("  ") and liste:
            out.append(f"<br><span class='doux'>{_inline(ligne.strip())}</span>")
        elif ligne.strip():
            out.append(f"<p>{_inline(ligne)}</p>")
    if liste:
        out.append("</ul>")
    corps = "\n".join(out)
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(titre)}</title>
<style>
:root{{--fond:#f7f6f2;--carte:#fff;--texte:#1f2328;--doux:#5b6168;--accent:#0b6e5f;--trait:#e3e1da}}
@media (prefers-color-scheme:dark){{:root{{--fond:#15171a;--carte:#1e2125;--texte:#e8e6e1;--doux:#a3a8ae;--accent:#5cc9b5;--trait:#30343a}}}}
body{{background:var(--fond);color:var(--texte);font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}}
main{{max-width:820px;margin:0 auto;padding:24px 16px 60px}}
h1{{font-size:22px;line-height:1.3}} h2{{font-size:18px;margin-top:32px;color:var(--accent);border-bottom:1px solid var(--trait);padding-bottom:4px}}
blockquote{{background:var(--carte);border-left:4px solid var(--accent);margin:10px 0;padding:10px 14px;border-radius:6px}}
pre{{background:var(--carte);border:1px solid var(--trait);border-radius:8px;padding:14px;white-space:pre-wrap;font:14.5px/1.55 Georgia,serif}}
li{{margin:6px 0}} .doux{{color:var(--doux);font-size:14px}} a{{color:var(--accent)}}
@media print{{body{{background:#fff}} pre,blockquote{{border:1px solid #ccc}}}}
</style></head><body><main><p class="doux"><a href="../tableau-de-bord.html">← Tableau de bord</a></p>{corps}</main></body></html>"""


def fichier(uid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", uid).strip("_") + ".html"


def ecrire(dossier: Path, offre: dict, ev: dict, profil: dict) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    md = construire(offre, ev, profil)
    p = dossier / fichier(offre["uid"])
    p.write_text(en_html(md, f"Candidature — {offre.get('titre', '')}"), encoding="utf-8")
    return p
