"""Dernier verrou avant publication : le dossier site/ ne doit contenir aucune donnée personnelle en clair.

Usage : python tests/verifier_publication.py site profils/marcellin.yaml
Code de sortie 1 (publication bloquée) si un élément sensible est trouvé ou si les données ne sont pas chiffrées.
"""
import json
import re
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
site, profil = Path(sys.argv[1]), yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8"))
# nom complet, chaque partie du nom, et des extraits de 30 caractères de chaque ligne du CV et des réalisations
sensibles = {profil.get("nom", ""), profil.get("signature", "")}
sensibles |= {m for m in re.findall(r"[\wÀ-ÿ]+", profil.get("nom", "")) if len(m) >= 4}
textes = (profil.get("cv_texte", "") + "\n" + profil.get("cv_texte_en", "")).splitlines()
textes += [r.get("fr", "") for r in profil.get("realisations", [])]
sensibles |= {t.strip()[:30] for t in textes if len(t.strip()) >= 30}
sensibles = {s for s in sensibles if len(s) >= 4}

erreurs = []
fichiers = [f for f in site.rglob("*") if f.is_file()]
if not any(f.name == "donnees.json" for f in fichiers):
    erreurs.append("aucun fichier donnees.json : la construction du site a échoué")
for f in fichiers:
    if f.suffix == ".png":
        continue
    texte = f.read_text(encoding="utf-8", errors="ignore")
    if f.name == "donnees.json" and json.loads(texte).get("chiffre") != 1:
        erreurs.append(f"{f} n'est pas chiffré")
    for s in sensibles:
        if s in texte:
            erreurs.append(f"« {s} » apparaît en clair dans {f}")

if erreurs:
    print("PUBLICATION BLOQUÉE :\n- " + "\n- ".join(erreurs))
    sys.exit(1)
print(f"Contrôle réussi : {len(fichiers)} fichiers, aucune donnée personnelle en clair.")
