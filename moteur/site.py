"""Construction de l'application web installable (PWA) : dossier site/<profil>/ prêt à être hébergé.

Sécurité :
  - les données (offres, analyses, dossiers de candidature) sont chiffrées en AES-256-GCM ;
  - la clé est dérivée de la phrase secrète du profil (PBKDF2-SHA-256, 310 000 itérations, recommandation OWASP) ;
  - la phrase secrète n'est jamais écrite sur disque : elle vient d'une variable d'environnement
    VEILLE_PHRASE_<IDENTIFIANT> (ou VEILLE_PHRASE), fournie par un secret GitHub ou par la session locale ;
  - sans phrase secrète, aucun site n'est produit : rien n'est publié en clair.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from pathlib import Path

ITERATIONS = 310_000
ICI = Path(__file__).parent


def phrase_de(identifiant: str) -> str | None:
    return os.environ.get(f"VEILLE_PHRASE_{identifiant.upper()}") or os.environ.get("VEILLE_PHRASE")


def chiffrer(donnees: dict, phrase: str, identifiant: str) -> dict:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    # sel stable par profil (la clé mémorisée sur l'appareil reste valable d'un jour à l'autre),
    # vecteur d'initialisation aléatoire à chaque publication
    sel = hashlib.sha256(f"veille-emploi:{identifiant}".encode()).digest()[:16]
    cle = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sel, iterations=ITERATIONS).derive(phrase.encode())
    iv = secrets.token_bytes(12)
    clair = json.dumps(donnees, ensure_ascii=False).encode()
    b = lambda x: base64.b64encode(x).decode()
    return {"chiffre": 1, "algo": "AES-256-GCM/PBKDF2-SHA256", "iter": ITERATIONS, "sel": b(sel), "iv": b(iv),
            "donnees": b(AESGCM(cle).encrypt(iv, clair, None))}


def dechiffrer(paquet: dict, phrase: str) -> dict:
    """Utilisé par les tests : vérifie que ce qui est publié se relit avec la bonne phrase."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    d = lambda x: base64.b64decode(x)
    cle = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=d(paquet["sel"]),
                     iterations=paquet["iter"]).derive(phrase.encode())
    return json.loads(AESGCM(cle).decrypt(d(paquet["iv"]), d(paquet["donnees"]), None))


MANIFESTE = {
    "name": "Veille emploi santé", "short_name": "Veille emploi", "lang": "fr",
    "description": "Offres en supply chain santé, data et aide à la décision, notées et accompagnées.",
    "start_url": "./", "scope": "./", "display": "standalone",
    "background_color": "#f6f7f5", "theme_color": "#0f6b57",
    "icons": [{"src": "icone-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
              {"src": "icone-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}],
}

SERVICE_WORKER = """// Service worker : réseau d'abord (données fraîches), cache en secours (hors ligne).
const CACHE = "veille-v2";
const BASE = ["./", "index.html", "manifest.webmanifest", "icone-192.png", "icone-512.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(BASE))); self.skipWaiting(); });
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(k =>
  Promise.all(k.filter(n => n !== CACHE).map(n => caches.delete(n)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok) { const copie = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copie)); }
    return r;
  }).catch(() => caches.match(e.request, {ignoreSearch: true})));
});
"""


def _icones(dossier: Path) -> None:
    from PIL import Image, ImageDraw
    for taille in (192, 512):
        f = taille / 512
        im = Image.new("RGB", (taille, taille), "#0f6b57")
        d = ImageDraw.Draw(im)
        # loupe (veille) contenant une croix (santé), tracée dans la zone sûre des icônes adaptatives
        d.ellipse([int(150 * f), int(130 * f), int(330 * f), int(310 * f)], outline="white", width=max(4, int(26 * f)))
        d.line([int(310 * f), int(290 * f), int(385 * f), int(365 * f)], fill="white", width=max(5, int(34 * f)))
        d.rectangle([int(225 * f), int(170 * f), int(255 * f), int(270 * f)], fill="white")
        d.rectangle([int(190 * f), int(205 * f), int(290 * f), int(235 * f)], fill="white")
        im.save(dossier / f"icone-{taille}.png", optimize=True)


def construire(racine_site: Path, profil: dict, donnees: dict) -> Path | None:
    """Écrit site/<identifiant>/ ; renvoie None (et ne publie rien) si aucune phrase secrète n'est fournie."""
    ident = profil["identifiant"]
    phrase = phrase_de(ident)
    if not phrase:
        return None
    if len(phrase) < 12:
        raise ValueError("Phrase secrète trop courte : 12 caractères minimum (idéalement 4 mots).")
    d = racine_site / ident
    d.mkdir(parents=True, exist_ok=True)
    gabarit = (ICI / "gabarit.html").read_text(encoding="utf-8")
    (d / "index.html").write_text(gabarit, encoding="utf-8")  # données absentes : chargées et déchiffrées
    (d / "donnees.json").write_text(json.dumps(chiffrer(donnees, phrase, ident)), encoding="utf-8")
    (d / "manifest.webmanifest").write_text(json.dumps(MANIFESTE, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "sw.js").write_text(SERVICE_WORKER, encoding="utf-8")
    _icones(d)
    # page d'accueil du site : renvoie vers le profil (sans révéler de nom)
    (racine_site / "index.html").write_text(
        f'<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex">'
        f'<meta http-equiv="refresh" content="0;url={ident}/"><title>Veille emploi</title>', encoding="utf-8")
    (racine_site / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (racine_site / ".nojekyll").write_text("", encoding="utf-8")
    return d
