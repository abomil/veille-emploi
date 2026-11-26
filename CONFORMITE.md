# Contrôles de fiabilité, de conformité et de sécurité

Ce document décrit les contrôles intégrés à l'application et la manière de les vérifier soi-même.
La commande `python -m unittest discover -s tests -v` lance les 23 tests automatiques. Les mêmes tests tournent dans le cloud avant chaque publication : **si un seul échoue, rien n'est publié** et GitHub envoie un courriel d'échec.

## 1. Fiabilité

| Contrôle | Mise en œuvre | Test |
|---|---|---|
| Reprise sur erreur réseau | 4 essais espacés de 2, 4 puis 8 s (erreurs 429 et 5xx), en respectant le délai `Retry-After` demandé par le serveur | `test_reprises_configurees` |
| Coupe-circuit | Un serveur qui renvoie deux refus « trop de requêtes » (429) est laissé tranquille jusqu'au lendemain ; un budget de temps (50 min) borne la collecte ; au plus 60 descriptions par source et par jour, la suite les jours suivants | `test_coupe_circuit_*`, `test_budget_*` |
| Panne d'une source sans effet sur les autres | Chaque source est isolée ; un échec est journalisé et la collecte continue | journal `donnees/journal.log` |
| Santé des sources | Une source muette, ou en baisse de plus de 70 % par rapport au passage précédent, est signalée dans l'application (bandeau orange) | `donnees/sante.json` |
| Intégrité des offres | Une offre sans identifiant, sans titre ou sans lien https est rejetée | `valide()` |
| Aucune perte de données | Enregistrement toutes les 25 offres ; une description vide n'écrase jamais une description connue | `base.enregistrer` |
| Notation explicable et bornée | Score entre 0 et 100, chaque point justifié ; une offre vide ne bloque rien | `test_score_*`, `test_offre_vide_*` |
| Dossiers exacts | Chaque réalisation citée vient de votre banque, rien n'est inventé ; les chiffres manquants restent marqués [à chiffrer] | `test_aucune_realisation_inventee` |

## 2. Conformité

| Exigence | Mise en œuvre |
|---|---|
| Conditions d'utilisation des sites | Seuls les points d'accès publics que les sites servent à leurs propres pages carrières sont utilisés. Aucun identifiant, aucun contournement de connexion ni de CAPTCHA. |
| robots.txt (norme RFC 9309) | Vérifié avant chaque appel ; une adresse interdite n'est jamais lue (`test_robots_respecte`). |
| Sites interdisant la lecture automatique | LinkedIn, Devex et Impactpool sont exclus. Un test bloque leur ajout par erreur. Le guide stratégique donne pour eux les alertes à créer à la main. |
| Courtoisie envers les serveurs | 0,4 s entre deux appels, une collecte par jour. L'application se présente sous son vrai nom (`VeilleEmploi/1.1`) et ne se fait pas passer pour un navigateur. |
| Protection des données personnelles (loi ivoirienne n° 2013-450, RGPD) | Minimisation : seules les offres publiques sont collectées. Le profil (CV, réalisations) n'est jamais versionné ni publié en clair. Les statuts de suivi restent sur l'appareil. Aucun traceur, aucune statistique, aucun service tiers. |
| Pas d'action à votre place | Aucune candidature n'est envoyée et aucun courriel n'est écrit automatiquement (`test_aucun_envoi_automatique`). |
| Données de l'employeur actuel | Aucune donnée interne de votre employeur n'est utilisée : seulement votre parcours, tel que vous le décrivez publiquement. |

## 3. Sécurité et non-intrusion

| Risque | Protection |
|---|---|
| Lecture de vos données sur le site public | Chiffrement AES-256-GCM. La clé est dérivée de votre phrase secrète par PBKDF2-SHA-256 (310 000 itérations, recommandation OWASP). Sans la phrase, le site ne montre qu'un écran de verrouillage. |
| Fuite avant publication | Un dernier verrou (`tests/verifier_publication.py`) bloque la publication si votre nom ou un terme de votre CV apparaît en clair. |
| Phrase secrète | Jamais écrite dans un fichier : elle est fournie par un secret chiffré de GitHub, refusée sous 12 caractères, et un test vérifie qu'aucun secret ne figure dans le code. |
| Injection de code par une offre piégée | Tout texte est échappé, seuls les liens https sont actifs, et une politique de sécurité du contenu (CSP) interdit les scripts et connexions extérieurs (`test_injection_html_neutralisee`). |
| Injection de formule dans Excel | Les cellules commençant par `=`, `+`, `-` ou `@` sont neutralisées (`test_injection_formule_excel_neutralisee`). |
| Réponse réseau malveillante | https obligatoire, taille limitée à 15 Mo, délai maximal de 40 s. |
| Robot du cloud | Droits minimaux : lecture du code seulement, sans pouvoir le modifier. Les identifiants Git ne sont pas conservés. |
| Indexation par les moteurs de recherche | `noindex` et `robots.txt` interdisent l'indexation du site ; aucun en-tête Referer n'est transmis. |
| Appareil perdu | La clé mémorisée est supprimable (« Effacer les données du site » dans le navigateur). Changer la phrase secrète dans GitHub invalide toutes les clés mémorisées. |

## 4. Limites connues, dites franchement

- Les **statuts de suivi** (« À postuler », « Entretien »…) sont gardés sur chaque appareil : ils ne se synchronisent pas encore entre le téléphone et l'ordinateur.
- Le **code** de l'application est public (le dépôt doit être public pour un hébergement gratuit). Il ne contient aucune donnée personnelle, ce que vérifient les tests.
- La **solidité du chiffrement dépend de la phrase secrète**. Choisissez 4 ou 5 mots sans lien entre eux, utilisés nulle part ailleurs.
