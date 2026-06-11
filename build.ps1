$ErrorActionPreference = "Stop"

$iconPath = (Get-ChildItem -LiteralPath $PSScriptRoot -Filter "logo_ap*_ico.ico" | Select-Object -First 1).FullName
if (-not $iconPath) {
  throw "No se encontro el icono logo_ap*_ico.ico"
}

$buildIcon = Join-Path $env:TEMP "coolimport-build-icon.ico"
Copy-Item -LiteralPath $iconPath -Destination $buildIcon -Force

python -m PyInstaller `
  --clean `
  --onedir `
  --windowed `
  --name "API CoolImport V6.2.0" `
  --add-data "img;img" `
  --icon $buildIcon `
  generar_qr_pdf.py

$distDir = Join-Path $PSScriptRoot "dist\API CoolImport V6.2.0"
$distCredentialsDir = Join-Path $distDir "credentials"

New-Item -ItemType Directory -Force -Path $distCredentialsDir | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README.md") -Destination $distDir -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "config.example.py") -Destination $distDir -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot ".env.example") -Destination $distDir -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "credentials\README.md") -Destination $distCredentialsDir -Force
