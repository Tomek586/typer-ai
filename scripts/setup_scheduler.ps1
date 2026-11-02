# Zakłada (lub usuwa) zadanie w Harmonogramie zadań Windows, które uruchamia harmonogram Typer AI
# przy każdym zalogowaniu użytkownika i restartuje go po awarii.
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler.ps1           # załóż zadanie
#   powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler.ps1 -DryRun   # tylko pokaż, co zostanie założone
#   powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler.ps1 -Remove   # usuń zadanie

param(
    [switch]$Remove,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$TaskName = "TyperAI_Scheduler"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Usunieto zadanie $TaskName."
    } else {
        Write-Host "Zadanie $TaskName nie istnieje."
    }
    exit 0
}

if (-not (Test-Path $Python)) {
    Write-Error "Nie znaleziono $Python. Najpierw utworz srodowisko: python -m venv .venv oraz pip install -e ."
}

# pythonw.exe = Python bez okna konsoli; wyjscie harmonogram zapisuje do data\scheduler.log
$Action = New-ScheduledTaskAction -Execute $Python -Argument "-m typerai.scheduler" -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Write-Host "Zadanie:      $TaskName"
Write-Host "Program:      $Python -m typerai.scheduler"
Write-Host "Katalog:      $ProjectDir"
Write-Host "Wyzwalacz:    przy zalogowaniu uzytkownika $env:USERDOMAIN\$env:USERNAME"
Write-Host "Ustawienia:   bez limitu czasu, restart co 5 min po awarii, jedna instancja, praca na baterii"
Write-Host "Log:          $ProjectDir\data\scheduler.log"

if ($DryRun) {
    Write-Host "`nTryb proby (-DryRun): niczego nie zmieniono."
    exit 0
}

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Principal $Principal -Description "Typer AI: etap 1, etap 2 i rozliczenia typow (python -m typerai.scheduler)" -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "`nZalozono i uruchomiono zadanie $TaskName. Sprawdz log: data\scheduler.log"
