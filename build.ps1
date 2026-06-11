$ErrorActionPreference = "Stop"

python -m PyInstaller `
  --onedir `
  --windowed `
  --name "API CoolImport V6.2.0" `
  --add-data "img;img" `
  --icon "logo_apì_ico.ico" `
  generar_qr_pdf.py

$distDir = Join-Path $PSScriptRoot "dist\API CoolImport V6.2.0"
$distCredentialsDir = Join-Path $distDir "credentials"

New-Item -ItemType Directory -Force -Path $distCredentialsDir | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README.md") -Destination $distDir -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "config.example.py") -Destination $distDir -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot ".env.example") -Destination $distDir -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "credentials\README.md") -Destination $distCredentialsDir -Force
