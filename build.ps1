$ErrorActionPreference = "Stop"

python -m PyInstaller `
  --onedir `
  --windowed `
  --name "API CoolImport V6.2.0" `
  --add-data "credentials;credentials" `
  --add-data "img;img" `
  --icon "logo_apì_ico.ico" `
  generar_qr_pdf.py
