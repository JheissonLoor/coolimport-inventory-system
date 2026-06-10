# API CoolImport V6.2.0

Servidor local de impresion para CoolImport. Es una aplicacion Flask + PyQt5 que recibe datos desde la app movil, genera una etiqueta `sticker.pdf` con QR y texto, y la envia a una impresora Zebra.

La aplicacion trabaja con Google Sheets y Supabase. No genera archivos Excel locales.

## Requisitos

- Python 3.11 recomendado.
- Windows, porque la impresion usa `pywin32`.
- Credenciales de Google Sheets en formato JSON.
- Variables de Supabase en `config.py`.

## Instalacion

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuracion

1. Copia `config.example.py` como `config.py`.
2. Completa las variables:

```python
SUPABASE_URL = ""
SUPABASE_KEY = ""
SUPABASE_SERVICE_KEY = ""
```

3. Coloca los JSON de Google dentro de `credentials/`.
4. Verifica que los nombres de los JSON coincidan con los que usa `generar_qr_pdf.py`.

`config.py` y los JSON de `credentials/` estan ignorados por git porque contienen llaves privadas.

## Ejecutar en desarrollo

```powershell
python generar_qr_pdf.py
```

La app abre una interfaz PyQt5 y expone los endpoints Flask usados por el sistema movil.

## Compilar EXE

Instala PyInstaller solo en el entorno de build:

```powershell
pip install pyinstaller
```

Compila en modo `onedir` y sin consola:

```powershell
pyinstaller --onedir --windowed --name "API CoolImport V6.2.0" --add-data "credentials;credentials" --add-data "img;img" --icon "logo_apì_ico.ico" generar_qr_pdf.py
```

En Windows, `--add-data` usa punto y coma (`;`) para separar origen y destino.

## Archivos que no se suben

No subas al repositorio:

- `build/`
- `dist/`
- `*.spec`
- `_internal/`
- `*.exe`
- `sticker.pdf`
- `temp_qr*.png`
- `logs_consola.pdf`
- `config.py`
- archivos JSON dentro de `credentials/`

El repositorio debe contener codigo fuente, assets necesarios y documentacion; los artefactos compilados se regeneran localmente.
