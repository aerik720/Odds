$ErrorActionPreference = "Stop"

function Write-Log($Message, $Color = "Gray") {
  $stamp = Get-Date -Format "HH:mm:ss"
  Write-Host "[$stamp] $Message" -ForegroundColor $Color
}

function Import-DotEnv($Path) {
  if (-not (Test-Path $Path)) {
    return
  }
  foreach ($rawLine in Get-Content $Path) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith("#")) {
      continue
    }
    $parts = $line.Split("=", 2)
    if ($parts.Length -ne 2) {
      continue
    }
    $name = $parts[0].Trim()
    $value = $parts[1].Trim()
    if (-not $name) {
      continue
    }
    if ($value.StartsWith('"') -and $value.EndsWith('"')) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    if (-not ${env:$name}) {
      Set-Item -Path "env:$name" -Value $value
    }
  }
}

Push-Location (Split-Path $PSScriptRoot -Parent)

Import-DotEnv ".env"

Write-Log "Step 1/2: Fetch value bets (no Smarkets match)" "Cyan"
python -m scripts.fetch_valuebets_smarkets --auto-reset-bookmakers --valuebets-only

Write-Log "Step 2/2: Done" "Green"

Pop-Location
