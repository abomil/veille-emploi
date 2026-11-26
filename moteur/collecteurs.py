"""Collecteurs : chaque fonction renvoie une liste d'offres au format commun.

Format commun d'une offre (dict) :
    uid, source, organisation, titre, lieu, url, publiee, limite, description, contrat
Seuls des points d'accès publics, servis par les sites à leurs propres pages carrières, sont utilisés.
"""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from typing import Callable, Iterable

import requests

ENTETES = {"User-Agent": "VeilleEmploi/1.1 (veille personnelle d'offres publiques; non commercial)",
           "Accept": "application/json, text/xml, */*"}
PAUSE = 0.4  # secondes entre deux appels : on reste courtois avec les serveurs


def texte_brut(h: str | None) -> str:
    """Retire les balises HTML et normalise les espaces."""
    if not h:
        return ""
    h = re.sub(r"<(br|/p|/div|/li|/h\d)[^>]*>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    h = html.unescape(h)
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", h)).strip()


TAILLE_MAX = 15_000_000  # octets : une réponse anormalement grosse est refusée


class Refus(Exception):
    """Accès refusé par la politique du site (robots.txt) : la source est ignorée, jamais contournée."""


def _session() -> requests.Session:
    """Session avec reprises automatiques : 4 essais espacés (2, 4, 8 s) sur erreurs passagères,
    en respectant l'en-tête Retry-After des serveurs qui demandent de patienter."""
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    s = requests.Session()
    reprise = Retry(total=4, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                    allowed_methods=("GET", "POST"), respect_retry_after_header=True, raise_on_status=False)
    s.mount("https://", HTTPAdapter(max_retries=reprise))
    s.headers.update(ENTETES)
    return s


SESSION = _session()
_ROBOTS: dict[str, object] = {}


def autorise(url: str) -> bool:
    """Contrôle de conformité : le fichier robots.txt du site autorise-t-il cette adresse ?"""
    from urllib import robotparser
    from urllib.parse import urlsplit
    hote = "{0.scheme}://{0.netloc}".format(urlsplit(url))
    if hote not in _ROBOTS:
        rp = robotparser.RobotFileParser()
        try:
            r = SESSION.get(hote + "/robots.txt", timeout=20)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])  # absent = tout autorisé (norme RFC 9309)
        except requests.RequestException:
            rp.parse([])
        _ROBOTS[hote] = rp
    return _ROBOTS[hote].can_fetch(ENTETES["User-Agent"], url)


def _verifier(url: str, r: requests.Response) -> requests.Response:
    if not url.startswith("https://"):
        raise Refus(f"adresse non chiffrée refusée : {url}")
    r.raise_for_status()
    if len(r.content) > TAILLE_MAX:
        raise ValueError(f"réponse trop volumineuse ({len(r.content)} octets)")
    time.sleep(PAUSE)
    return r


def _get(url: str, **kw):
    if not autorise(url):
        raise Refus(f"robots.txt interdit {url}")
    return _verifier(url, SESSION.get(url, timeout=40, **kw))


def _post(url: str, payload: dict):
    if not autorise(url):
        raise Refus(f"robots.txt interdit {url}")
    return _verifier(url, SESSION.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=40))


# --------------------------------------------------------------------------- Nations unies
def nations_unies(_requetes: list[str], journal: Callable[[str], None]) -> list[dict]:
    """careers.un.org : toutes les offres ouvertes (le moteur filtre ensuite localement)."""
    url = "https://careers.un.org/api/public/opening/jo/list/filteredV2/en"
    offres, page = [], 0
    while page < 15:
        data = _post(url, {"filterConfig": {}, "pagination": {
            "page": page, "itemPerPage": 100, "sortBy": "startDate", "sortDirection": -1}}).json()["data"]
        lot = data.get("list") or []
        for j in lot:
            lieux = ", ".join(d.get("description", "").title() for d in (j.get("dutyStation") or []))
            dept = (j.get("dept") or {}).get("name", "Nations unies")
            offres.append({
                "uid": f"un:{j['jobId']}", "source": "Nations unies (careers.un.org)",
                "organisation": dept, "titre": j.get("postingTitle") or j.get("jobTitle", ""),
                "lieu": lieux, "url": f"https://careers.un.org/jobSearchDescription/{j['jobId']}?language=en",
                "publiee": (j.get("startDate") or "")[:10], "limite": (j.get("endDate") or "")[:10],
                "description": texte_brut(j.get("jobDescription")),
                "contrat": (j.get("recrttype") or {}).get("name", "") + " " + (j.get("jl") or {}).get("name", ""),
            })
        if len(lot) < 100:
            break
        page += 1
    journal(f"  Nations unies : {len(offres)} offres ouvertes lues")
    return offres


# --------------------------------------------------------------------------- PNUD (Oracle)
PNUD = "https://estm.fa.em2.oraclecloud.com/hcmRestApi/resources/latest/"


def pnud(requetes: list[str], journal: Callable[[str], None], deja_connus: set[str]) -> list[dict]:
    vus: dict[str, dict] = {}
    for q in requetes:
        url = (PNUD + "recruitingCEJobRequisitions?onlyData=true&expand=requisitionList&finder=findReqs;"
               f"siteNumber=CX_1,keyword=%22{requests.utils.quote(q)}%22,limit=100,sortBy=POSTING_DATES_DESC")
        try:
            items = _get(url).json().get("items") or []
        except Exception as e:  # une requête en échec ne bloque pas les autres
            journal(f"  PNUD « {q} » : échec ({e})")
            continue
        for r in (items[0].get("requisitionList") or []) if items else []:
            vus[r["Id"]] = r
    offres = []
    for rid, r in vus.items():
        uid = f"pnud:{rid}"
        desc = ""
        if uid not in deja_connus:
            try:
                d = _get(PNUD + "recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;"
                         f"Id=%22{rid}%22,siteNumber=CX_1").json().get("items") or []
                if d:
                    desc = texte_brut(" ".join(str(d[0].get(k) or "") for k in (
                        "ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr",
                        "CorporateDescriptionStr", "OrganizationDescriptionStr")))
            except Exception:
                pass
        offres.append({
            "uid": uid, "source": "PNUD", "organisation": "PNUD / UNDP", "titre": r.get("Title", ""),
            "lieu": r.get("PrimaryLocation") or "",
            "url": f"https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/{rid}",
            "publiee": r.get("PostedDate") or "", "limite": r.get("PostingEndDate") or "",
            "description": desc, "contrat": "",
        })
    journal(f"  PNUD : {len(offres)} offres pertinentes aux requêtes")
    return offres


# --------------------------------------------------------------------------- Workday
def workday(cfg: dict, requetes: list[str], journal: Callable[[str], None], deja_connus: set[str]) -> list[dict]:
    t, s, site = cfg["tenant"], cfg["serveur"], cfg["site"]
    base = f"https://{t}.{s}.myworkdayjobs.com/wday/cxs/{t}/{site}"
    vus: dict[str, dict] = {}
    for q in requetes:
        for offset in (0, 20, 40):
            try:
                data = _post(base + "/jobs", {"appliedFacets": {}, "limit": 20, "offset": offset,
                                              "searchText": q}).json()
            except Exception as e:
                journal(f"  {cfg['nom']} « {q} » : échec ({e})")
                break
            lot = data.get("jobPostings") or []
            for p in lot:
                if p.get("externalPath"):
                    vus[p["externalPath"]] = p
            if len(lot) < 20:
                break
    offres = []
    for chemin, p in vus.items():
        uid = f"wd:{t}:{chemin.rsplit('_', 1)[-1]}"
        desc, lieu, publiee = "", p.get("locationsText", ""), ""
        if uid not in deja_connus:
            try:
                info = _get(base + chemin).json().get("jobPostingInfo", {})
                desc = texte_brut(info.get("jobDescription"))
                lieu = info.get("location") or lieu
                if info.get("additionalLocations"):
                    lieu += " · " + ", ".join(info["additionalLocations"])
                publiee = info.get("startDate", "")
            except Exception:
                pass
        offres.append({
            "uid": uid, "source": f"{cfg['nom']} (Workday)", "organisation": cfg["nom"],
            "titre": p.get("title", ""), "lieu": lieu,
            "url": f"https://{t}.{s}.myworkdayjobs.com/en-US/{site}{chemin}",
            "publiee": publiee, "limite": "", "description": desc, "contrat": p.get("postedOn", ""),
        })
    journal(f"  {cfg['nom']} : {len(offres)} offres pertinentes aux requêtes")
    return offres


# --------------------------------------------------------------------------- ReliefWeb
def reliefweb(cfg: dict, requetes: list[str], journal: Callable[[str], None]) -> list[dict]:
    if not cfg.get("appname"):
        journal("  ReliefWeb : inactif (appname à demander sur apidoc.reliefweb.int)")
        return []
    url = f"https://api.reliefweb.int/v2/jobs?appname={cfg['appname']}"
    offres = {}
    for q in requetes:
        try:
            data = _post(url, {"query": {"value": q}, "limit": 100, "sort": ["date.created:desc"],
                               "fields": {"include": ["title", "body", "url", "source.name", "country.name",
                                                      "date.created", "date.closing", "type.name"]}}).json()
        except Exception as e:
            journal(f"  ReliefWeb « {q} » : échec ({e})")
            continue
        for it in data.get("data", []):
            f = it.get("fields", {})
            offres[it["id"]] = {
                "uid": f"rw:{it['id']}", "source": "ReliefWeb",
                "organisation": ", ".join(x["name"] for x in f.get("source", [])),
                "titre": f.get("title", ""), "lieu": ", ".join(x["name"] for x in f.get("country", [])),
                "url": f.get("url", ""), "publiee": (f.get("date", {}).get("created") or "")[:10],
                "limite": (f.get("date", {}).get("closing") or "")[:10],
                "description": texte_brut(f.get("body")),
                "contrat": ", ".join(x["name"] for x in f.get("type", [])),
            }
    journal(f"  ReliefWeb : {len(offres)} offres")
    return list(offres.values())


# --------------------------------------------------------------------------- RSS
def rss(cfg: dict, journal: Callable[[str], None]) -> list[dict]:
    try:
        racine = ET.fromstring(_get(cfg["url"]).content)
    except Exception as e:
        journal(f"  RSS {cfg['nom']} : échec ({e})")
        return []
    offres = []
    for it in racine.iter("item"):
        lien = (it.findtext("link") or "").strip()
        offres.append({
            "uid": f"rss:{lien}", "source": cfg["nom"], "organisation": cfg["nom"],
            "titre": (it.findtext("title") or "").strip(), "lieu": "", "url": lien,
            "publiee": (it.findtext("pubDate") or "")[:16], "limite": "",
            "description": texte_brut(it.findtext("description")), "contrat": "",
        })
    journal(f"  RSS {cfg['nom']} : {len(offres)} offres")
    return offres


def tout_collecter(sources: dict, deja_connus: set[str], journal: Callable[[str], None]) -> Iterable[dict]:
    req = sources.get("requetes", [])
    if sources.get("nations_unies", {}).get("actif"):
        try:
            yield from nations_unies(req, journal)
        except Exception as e:
            journal(f"  Nations unies : échec ({e})")
    if sources.get("pnud", {}).get("actif"):
        yield from pnud(req, journal, deja_connus)
    for cfg in sources.get("workday", []) or []:
        yield from workday(cfg, req, journal, deja_connus)
    if sources.get("reliefweb", {}).get("actif"):
        yield from reliefweb(sources["reliefweb"], req, journal)
    for cfg in sources.get("rss", []) or []:
        yield from rss(cfg, journal)
