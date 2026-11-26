# Ouvre la veille emploi dans sa propre fenêtre d'application.
# Priorité à la version en ligne (à jour même si cet ordinateur était éteint) ; sinon, version locale.
param([string]$Adresse = "https://abomil.github.io/veille-emploi/marcellin/")

$local = Join-Path $PSScriptRoot "rapports\marcellin\tableau-de-bord.html"
$cible = $local
try {
    $r = Invoke-WebRequest -Uri $Adresse -Method Head -TimeoutSec 6 -UseBasicParsing
    if ($r.StatusCode -eq 200) { $cible = $Adresse }
} catch { }

$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
          "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($edge -and $cible -like "https://*") {
    Start-Process $edge "--app=$cible"          # fenêtre d'application, sans barre de navigation
} else {
    Start-Process $cible
}
