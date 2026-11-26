# Installe (ou retire) l'exécution automatique quotidienne de la veille emploi.
#   .\planifier.ps1                                   -> tâche « VeilleEmploi » chaque jour à 07:00
#   .\planifier.ps1 -Heure 06:30
#   .\planifier.ps1 -Dossier C:\Applications\Veille-Emploi   -> dossier où chercher veille.py
#   .\planifier.ps1 -Retirer                          -> supprime la tâche
param([string]$Heure = "07:00", [string]$Dossier = $PSScriptRoot, [switch]$Retirer)

$nom = "VeilleEmploi"
if ($Retirer) {
    Unregister-ScheduledTask -TaskName $nom -Confirm:$false
    Write-Host "Tâche $nom supprimée."
    return
}
$python = (Get-Command python).Source
# veille.py est recherché à chaque lancement : la tâche continue de marcher si le dossier est réorganisé.
$commande = "`$v = Get-ChildItem -LiteralPath '$Dossier' -Filter veille.py -Recurse -Depth 3 | Select-Object -First 1; " +
            "if (`$v) { Set-Location `$v.DirectoryName; & '$python' `$v.FullName --apport }"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"$commande`""
$declencheur = New-ScheduledTaskTrigger -Daily -At $Heure
# Rattrape l'exécution si l'ordinateur était éteint à l'heure prévue ; ne tourne que sur réseau.
$reglages = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $nom -Action $action -Trigger $declencheur -Settings $reglages `
    -Description "Collecte, notation et dossiers de candidature quotidiens (veille emploi santé mondiale)" -Force | Out-Null
Write-Host "Tâche $nom créée : chaque jour à $Heure, dans $Dossier."
