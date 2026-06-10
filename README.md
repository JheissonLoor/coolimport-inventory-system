# API CoolImport V6.2.0

Servidor local de impresion para CoolImport. Es una aplicacion Flask + PyQt5 que recibe datos desde la app movil, genera una etiqueta `sticker.pdf` con QR y texto, y la envia a una impresora Zebra.

La aplicacion trabaja con Google Sheets y Supabase. No genera archivos Excel locales.

## Requisitos

- Python 3.11 recomendado.
- Windows, porque la impresion usa `pywin32`.
- Credenciales de Google Sheets en formato JSON.
- Variables de Supabase y Google Sheets en `config.py`.

## Instalacion

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuracion

1. Copia `config.example.py` como `config.py`.
2. Copia `.env.example` como referencia si prefieres manejar los valores como variables de entorno.
3. Completa estos valores en `config.py`:

```python
SUPABASE_URL = ""
SUPABASE_KEY = ""
SUPABASE_SERVICE_KEY = ""

GOOGLE_CREDENTIALS_FILE = "credentials/your-service-account.json"

STOCK_SPREADSHEET_ID = ""
AUXILIARY_SPREADSHEET_ID = ""

WORKSHEET_STOCK = "STOCK"
WORKSHEET_ALMACEN_MOVIMIENTOS = "Movimientos del almacen"
WORKSHEET_DATOS_KARDEX = "datosKardex"
WORKSHEET_STOCK_ACTUAL = "Stock Actual"
```

4. Coloca los JSON de Google dentro de `credentials/`.
5. Verifica que `GOOGLE_CREDENTIALS_FILE` apunte al JSON correcto.

`config.py`, `.env` y los JSON de `credentials/` estan ignorados por git porque contienen llaves privadas o datos de entorno.

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

Compila con el script incluido:

```powershell
.\build.ps1
```

El script usa modo `onedir`, ventana sin consola, `--add-data` para `credentials` e `img`, y el icono `logo_apì_ico.ico`.

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
- `.env`
- archivos JSON dentro de `credentials/`

El repositorio debe contener codigo fuente, assets necesarios y documentacion; los artefactos compilados se regeneran localmente.

## Propuestas de mejora

- Rotar las llaves de Google y Supabase que hayan estado en builds o historiales antiguos antes de volver a publicar releases.
- Crear un endpoint `/health` que valide conexion a Supabase, Google Sheets e impresora sin generar etiquetas.
- Mover los nombres de impresora, IPs conocidas y parametros de etiqueta a `config.py` para no editar codigo por cada equipo.
- Agregar un modo `DRY_RUN_PRINT=True` para generar `sticker.pdf` sin mandar a la Zebra durante pruebas.
- Crear pruebas simples para `/generar_kardex` y `/consulta_pcp` usando mocks de Google Sheets.
- Crear un release de GitHub solo con el `.exe` compilado, manteniendo el repo principal solo con codigo fuente.
