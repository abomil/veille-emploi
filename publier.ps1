# Met l'application en ligne sur GitHub (une seule fois) : elle tournera ensuite seule, chaque matin.
#   1. crée le dépôt PUBLIC « veille-emploi » (code seulement : profils, données et rapports sont exclus par .gitignore)
#   2. enregistre votre profil comme secret chiffré GitHub (PROFIL_MARCELLIN)
#   3. active GitHub Pages et lance un premier passage
# La phrase secrète n'est PAS gérée ici : saisissez-la vous-même avec
#   gh secret set VEILLE_PHRASE --repo <compte>/veille-emploi
param([string]$Depot = "veille-emploi")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw "Tests en échec : publication annulée." }

$compte = gh api user --jq .login
if (-not (Test-Path .git)) { git init -b main | Out-Null }
git add -A
$suivis = git ls-files --cached
foreach ($interdit in @("profils/marcellin.yaml", "donnees/", "rapports/", "site/")) {
    if ($suivis | Where-Object { $_ -like "$interdit*" }) { throw "« $interdit » serait publié : arrêt." }
}
git commit -m "Veille emploi : application autonome chiffrée" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" | Out-Null

if (-not (gh repo view "$compte/$Depot" 2>$null)) {
    gh repo create $Depot --public --source . --push --description "Veille emploi santé mondiale (code ; données chiffrées)"
} else { git push -u origin main }

Get-Content profils/marcellin.yaml -Raw | gh secret set PROFIL_MARCELLIN --repo "$compte/$Depot"
gh api -X POST "repos/$compte/$Depot/pages" -f build_type=workflow 2>$null | Out-Null
Write-Host "Dépôt prêt : https://github.com/$compte/$Depot"
Write-Host "Étape suivante (vous seul) : gh secret set VEILLE_PHRASE --repo $compte/$Depot"
Write-Host "Puis : gh workflow run veille.yml --repo $compte/$Depot"
Write-Host "Application : https://$compte.github.io/$Depot/marcellin/"
