# Veille emploi — supply chain santé, data, aide à la décision

Collecte chaque jour les offres d'organisations internationales et d'ONG de santé mondiale, les
note sur 100 contre un profil (à la manière d'un ATS), et produit un tableau de bord.

## Démarrer

```powershell
pip install -r requirements.txt
python veille.py
```

Puis ouvrir `rapports/marcellin/tableau-de-bord.html`.

La première collecte lit toutes les descriptions (15 à 20 minutes) ; les suivantes ne lisent que
les nouvelles offres.

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `profils/marcellin.yaml` | votre profil : familles de compétences, poids, exclusions, préférences. **C'est ici qu'on règle le tir.** |
| `sources.yaml` | les portails interrogés et les mots-clés envoyés |
| `rapports/<profil>/tableau-de-bord.html` | le tableau de bord filtrable |
| `rapports/<profil>/offres.csv` | la même liste pour Excel |
| `rapports/<profil>/nouveautes.md` | les nouvelles offres prioritaires du jour |
| `donnees/veille.sqlite` | la mémoire (offres vues, scores, statuts) |
| `donnees/journal.log` | le journal des collectes |
| `GUIDE-STRATEGIE.md` | plateformes, requêtes booléennes, méthode ATS, routine |
| `planifier.ps1` | installe l'exécution quotidienne automatique (Planificateur de tâches Windows) |

## Comment le score est calculé (sur 100)

| Composante | Points |
| --- | --- |
| Couverture de vos familles de compétences dans l'offre | jusqu'à 55 |
| Vos termes présents dans l'intitulé | jusqu'à 12 |
| Séniorité (manager, conseiller, expert, P3-P5, NOC/NOD…) | +8 ; junior ou assistant −15 ; hors cible −40 |
| Français demandé ou offre rédigée en français | +15 |
| Pays francophone | +8 |
| Anglais courant exigé sans le français | −10 |
| Télétravail / consultance | +10 / +6 |
| Grade bien rémunéré (P3+, NOC+, GL D+, IPSA 9+) | +5 ; grade local (G, NPSA) −10 |

Chaque offre affiche le détail de sa note et la liste des termes de l'offre absents de votre CV.

## Suivi des candidatures

Dans le tableau de bord, le menu de chaque offre (Nouveau, À étudier, À postuler…) est mémorisé
par le navigateur. Pour l'inscrire dans la base :

```powershell
python veille.py statut "wd:theglobalfund:JR4768" a_postuler --note "CV envoyé le 2/12"
```

## Accompagnement des candidatures (module coach)

Pour chaque offre prioritaire (score ≥ seuil d'alerte), l'application produit un **dossier de candidature** dans `rapports/<profil>/candidatures/`. On l'ouvre depuis le bouton « Préparer ma candidature » du tableau de bord. Il croise quatre regards :

- docteur en ressources humaines : éligibilité, niveau, surqualification, langues ;
- détecteur de talents : requête booléenne du sourceur et vérification de votre CV terme par terme ;
- personal branding : titre de CV, profil en 3 lignes, titre LinkedIn ;
- coach : réalisations choisies dans votre banque, brouillon de lettre (FR, ou EN + FR), questions d'entretien, check-list.

Dossier pour n'importe quelle offre : `python veille.py dossier <identifiant>`. L'identifiant se trouve dans la dernière colonne de `offres.csv`.
La stratégie générale est décrite dans `GUIDE-CANDIDATURE.md`. Les réalisations se règlent dans la rubrique `realisations` du profil.

## Application autonome (Android, web, ordinateur)

- **Raccourci « Veille emploi » sur le bureau** : ouvre l'application en ligne dans sa propre fenêtre. Hors ligne, il ouvre la version locale.
- **Dans le cloud** : `.github/workflows/veille.yml` lance chaque matin, sur les serveurs de GitHub, les tests de contrôle, la collecte, les dossiers et le chiffrement, puis publie le site sur GitHub Pages. Tout fonctionne ordinateur éteint.
- **Sur Android** : ouvrir l'adresse dans Chrome, puis menu ⋮ → « Installer l'application ». Elle apparaît alors comme une application, avec son icône, et reste consultable hors ligne.
- **Mise en ligne initiale** : `.\publier.ps1`, puis définir la phrase secrète (voir le script).
- **Contrôles** : `CONFORMITE.md` et `python -m unittest discover -s tests -v`.
