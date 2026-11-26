"""Contrôles automatiques : fiabilité, conformité, sécurité (non-intrusion), qualité des dossiers.

Lancement : python -m unittest discover -s tests -v
Ces tests tournent aussi dans le cloud avant chaque publication : si l'un échoue, rien n'est publié.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

import yaml  # noqa: E402

from moteur import coach, collecteurs, rapport, site  # noqa: E402
from moteur.score import evaluer, motif, norm  # noqa: E402


def profil_test() -> dict:
    f = RACINE / "profils" / "marcellin.yaml"
    if not f.exists():
        f = RACINE / "profils" / "exemple.yaml"
    return yaml.safe_load(f.read_text(encoding="utf-8"))


OFFRE = {
    "uid": "test:1", "source": "Test", "organisation": "Fonds mondial", "lieu": "Dakar, Sénégal",
    "titre": "Spécialiste supply chain et gestion des données - GL D",
    "url": "https://exemple.org/offre/1", "publiee": "", "limite": "2026-12-31", "contrat": "",
    "description": ("Le poste assure la quantification, la prévision et le suivi des stocks des produits de santé. "
                    "Il conçoit les tableaux de bord et contrôle la qualité des données. "
                    "Maîtrise du français exigée. Master requis et 7 ans d'expérience. ") * 3,
}


class Fiabilite(unittest.TestCase):
    def test_pluriel_reconnu(self):
        self.assertTrue(motif("stock").search(norm("gestion des stocks")))
        self.assertTrue(motif("indicateur").search(norm("les indicateurs")))
        self.assertFalse(motif("stock").search(norm("stockholm")))

    def test_score_borne_et_explique(self):
        ev = evaluer(OFFRE, profil_test())
        self.assertTrue(0 <= ev["score"] <= 100)
        self.assertTrue(ev["detail"], "chaque score doit être justifié")
        self.assertTrue(ev["francais"])

    def test_exclusion_appliquee(self):
        o = {**OFFRE, "titre": "Comptable senior (accountant)"}
        self.assertLess(evaluer(o, profil_test())["score"], evaluer(OFFRE, profil_test())["score"])

    def test_offre_vide_ne_plante_pas(self):
        ev = evaluer({"uid": "x", "titre": "", "description": ""}, profil_test())
        self.assertEqual(ev["score"], 0)

    def test_coupe_circuit_apres_refus_429(self):
        r = mock.Mock(status_code=429, content=b"")
        r.raise_for_status.side_effect = collecteurs.requests.HTTPError("429")
        for _ in range(2):
            with self.assertRaises(collecteurs.requests.HTTPError):
                collecteurs._verifier("https://sature.test/jobs", r)
        self.assertIn("sature.test", collecteurs.SATURES)
        with self.assertRaises(collecteurs.Refus):
            collecteurs._get("https://sature.test/jobs")
        collecteurs.SATURES.discard("sature.test")

    def test_budget_de_temps_respecte(self):
        ancien = collecteurs.FIN
        try:
            collecteurs.demarrer_chrono(-1)
            with self.assertRaises(collecteurs.Refus):
                collecteurs._get("https://exemple.org/emplois")
        finally:
            collecteurs.FIN = ancien

    def test_reprises_configurees(self):
        a = collecteurs.SESSION.get_adapter("https://exemple.org")
        self.assertGreaterEqual(a.max_retries.total, 3)
        self.assertIn(429, a.max_retries.status_forcelist)


class Conformite(unittest.TestCase):
    def test_robots_respecte(self):
        rp = __import__("urllib.robotparser", fromlist=["x"]).RobotFileParser()
        rp.parse(["User-agent: *", "Disallow: /prive"])
        collecteurs._ROBOTS["https://interdit.test"] = rp
        self.assertFalse(collecteurs.autorise("https://interdit.test/prive/emplois"))
        self.assertTrue(collecteurs.autorise("https://interdit.test/emplois"))
        with self.assertRaises(collecteurs.Refus):
            collecteurs._get("https://interdit.test/prive/emplois")

    def test_aucune_source_linkedin_ni_privee(self):
        s = (RACINE / "sources.yaml").read_text(encoding="utf-8").lower()
        actif = [l for l in s.splitlines() if not l.strip().startswith("#")]
        self.assertFalse(any("linkedin" in l or "devex" in l or "impactpool" in l for l in actif),
                         "LinkedIn, Devex et Impactpool interdisent la lecture automatique")

    def test_agent_identifie_honnetement(self):
        self.assertIn("VeilleEmploi", collecteurs.ENTETES["User-Agent"])

    def test_http_non_chiffre_refuse(self):
        with self.assertRaises(collecteurs.Refus):
            collecteurs._verifier("http://exemple.org", mock.Mock())

    def test_aucun_envoi_automatique(self):
        code = "\n".join(p.read_text(encoding="utf-8") for p in (RACINE / "moteur").glob("*.py"))
        self.assertNotRegex(code, r"smtplib|sendmail|apply_now|submitApplication")


class Securite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_chiffrement_aller_retour(self):
        paquet = site.chiffrer({"profil": "Personne Test", "offres": [1, 2]}, "phrase secrete de test", "t")
        self.assertNotIn("Personne", json.dumps(paquet))
        self.assertEqual(site.dechiffrer(paquet, "phrase secrete de test")["offres"], [1, 2])
        with self.assertRaises(Exception):
            site.dechiffrer(paquet, "mauvaise phrase secrete")

    def test_rien_publie_sans_phrase(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(site.construire(self.dir, {"identifiant": "t"}, {}))
        self.assertFalse((self.dir / "t").exists())

    def test_phrase_trop_courte_refusee(self):
        with mock.patch.dict(os.environ, {"VEILLE_PHRASE": "court"}, clear=True):
            with self.assertRaises(ValueError):
                site.construire(self.dir, {"identifiant": "t"}, {})

    def test_site_publie_sans_donnee_en_clair(self):
        p = profil_test()
        lignes = [{**OFFRE, **evaluer(OFFRE, p), "statut": "nouveau", "dossier_md": coach.construire(OFFRE, evaluer(OFFRE, p), p)}]
        with mock.patch.dict(os.environ, {"VEILLE_PHRASE": "une phrase secrete solide"}):
            r = rapport.produire(self.dir / "rapports", p, lignes, set(), racine_site=self.dir / "site")
        publie = "".join(f.read_text(encoding="utf-8", errors="ignore") for f in (self.dir / "site").rglob("*")
                         if f.is_file() and f.suffix != ".png")
        for secret in (p.get("nom", "Prénom NOM"), "Dakar", "quantification", p["cv_texte"][:40]):
            self.assertNotIn(secret, publie, f"« {secret} » apparaît en clair dans le site publié")
        self.assertIn("noindex", publie)
        self.assertTrue((r["site"] / "sw.js").exists() and (r["site"] / "icone-512.png").exists())

    def test_injection_html_neutralisee(self):
        p = profil_test()
        piege = {**OFFRE, "titre": "</script><script>alert(1)</script>"}
        lignes = [{**piege, **evaluer(piege, p), "statut": "nouveau"}]
        r = rapport.produire(self.dir, p, lignes, set())
        h = r["html"].read_text(encoding="utf-8")
        self.assertEqual(h.count("</script>"), 1, "le titre piégé ne doit pas fermer le script")
        self.assertIn("Content-Security-Policy", h)

    def test_injection_formule_excel_neutralisee(self):
        p = profil_test()
        piege = {**OFFRE, "titre": "=HYPERLINK(\"http://pirate\")"}
        r = rapport.produire(self.dir, p, [{**piege, **evaluer(piege, p), "statut": "nouveau"}], set())
        with r["csv"].open(encoding="utf-8-sig") as f:
            ligne = list(csv.reader(f, delimiter=";"))[1]
        self.assertTrue(ligne[3].startswith("'="))

    def test_aucun_secret_dans_le_code(self):
        motifs = re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_|-----BEGIN [A-Z ]*PRIVATE KEY|"
                            r"VEILLE_PHRASE\w*\s*[:=]\s*['\"][^'\"]{6,})")
        for f in RACINE.rglob("*"):
            if f.is_file() and f.suffix in {".py", ".yaml", ".yml", ".md", ".html", ".ps1", ".json", ".txt"} \
                    and "rapports" not in f.parts and "site" not in f.parts and "tests" not in f.parts:
                self.assertIsNone(motifs.search(f.read_text(encoding="utf-8", errors="ignore")), str(f))

    def test_aucune_donnee_personnelle_dans_le_depot(self):
        import subprocess
        try:
            sortie = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=RACINE,
                                    capture_output=True, text=True, check=True).stdout.split("\n")
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("git indisponible")
        p = profil_test()
        if p["identifiant"] == "exemple":
            self.skipTest("profil réel absent")
        nom = p.get("nom", "")
        sensibles = {m for m in re.findall(r"[\wÀ-ÿ]+", nom) if len(m) >= 5}  # parties du nom (sauf prénom court)
        sensibles |= {p["marque"].get("formation_fr", "")[:40], p["marque"].get("contexte_fr", "")[:40]}
        sensibles |= {r["fr"][:40] for r in p.get("realisations", [])}
        sensibles |= {l.strip()[:40] for l in p.get("cv_texte", "").splitlines() if len(l.strip()) >= 40}
        sensibles = {s for s in sensibles if s}
        for f in filter(None, sortie):
            if f.endswith((".png", ".ico")):
                continue
            texte = (RACINE / f).read_text(encoding="utf-8", errors="ignore")
            for s in sensibles:
                self.assertNotIn(s, texte, f"« {s} » serait publié dans {f}")

    def test_profil_personnel_jamais_versionne(self):
        gi = (RACINE / ".gitignore").read_text(encoding="utf-8")
        for m in ("profils/*.yaml", "donnees/", "rapports/", "site/"):
            self.assertIn(m, gi)
        self.assertIn("!profils/exemple.yaml", gi)


class QualiteDossiers(unittest.TestCase):
    def test_dossier_complet_et_exact(self):
        p = profil_test()
        md = coach.construire(OFFRE, evaluer(OFFRE, p), p)
        for section in ("ressources humaines", "détecteur de talents", "personal branding", "coach",
                        "Lettre de motivation", "entretien", "Check-list"):
            self.assertIn(section, md)
        self.assertNotRegex(md.lower(), r"ing[ée]nieur statisticien|statistician economist engineer")
        self.assertNotIn("de améliorer", md)
        self.assertNotIn("- GL D", md.split("## 3.")[1].split("## 4.")[0])  # intitulé nettoyé

    def test_aucune_realisation_inventee(self):
        p = profil_test()
        md = coach.construire(OFFRE, evaluer(OFFRE, p), p)
        banque = " ".join(r["fr"] + r["en"] for r in p.get("realisations", []))
        for puce in re.findall(r"^- \*\*(.+?)\*\*$", md, re.M):
            self.assertIn(puce, banque, "une réalisation citée doit venir de la banque du profil")


if __name__ == "__main__":
    unittest.main(verbosity=2)
