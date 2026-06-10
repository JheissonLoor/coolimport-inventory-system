from flask import Flask, request, send_file, jsonify
from fpdf import FPDF
import base64
from PIL import Image
import io
import sys
import threading
from PyQt5.QtWidgets import (QSystemTrayIcon, QHBoxLayout, QMenu, QApplication, QMainWindow, QTextEdit, QLabel, QVBoxLayout, QWidget, QPushButton, QComboBox,)
from PyQt5.QtCore import Qt, QEvent, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon
import socket
import win32print
import win32api
import os
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
from supabase import create_client, Client
import config as app_config


def require_config_value(name):
    value = getattr(app_config, name, "")
    if not value:
        raise RuntimeError(f"Configura {name} en config.py")
    return value


SUPABASE_URL = require_config_value("SUPABASE_URL")
SUPABASE_KEY = require_config_value("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = require_config_value("SUPABASE_SERVICE_KEY")
GOOGLE_CREDENTIALS_FILE = require_config_value("GOOGLE_CREDENTIALS_FILE")
STOCK_SPREADSHEET_ID = require_config_value("STOCK_SPREADSHEET_ID")
AUXILIARY_SPREADSHEET_ID = require_config_value("AUXILIARY_SPREADSHEET_ID")
WORKSHEET_STOCK = require_config_value("WORKSHEET_STOCK")
WORKSHEET_ALMACEN_MOVIMIENTOS = require_config_value("WORKSHEET_ALMACEN_MOVIMIENTOS")
WORKSHEET_DATOS_KARDEX = require_config_value("WORKSHEET_DATOS_KARDEX")
WORKSHEET_STOCK_ACTUAL = require_config_value("WORKSHEET_STOCK_ACTUAL")

# Cliente administrativo (para operaciones CRUD con service_role)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Cliente público (mantener compatibilidad temporal con anon key)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CACHÉ SIMPLE PARA DATOS TARA ---
TARA_CACHE = {}
TARA_CACHE_TTL = 60 * 60  # 1 hora de vida útil (en segundos)

#ALMACEN_UBICACION_CACHE = {}
#ALMACEN_UBICACION_CACHE_TTL = 60 * 60  # 1 hora, puedes ajustar el tiempo

# Al iniciar la app, carga toda la hoja en memoria
ALMACEN_CACHE = {
    "data": [],
    "last_update": 0
}
ALMACEN_UPDATE_INTERVAL = 60 * 12  # 20 minutos (en segundos)

DATOS_GENERALES_CACHE = {
    "articulos": {"data": [], "count": 0, "last_update": 0},
    "colores": {"data": [], "count": 0, "last_update": 0},
    "materiales": {"data": [], "last_update": 0},
    "titulo_materiales": {"data": [], "last_update": 0}
}
CACHE_TTL = 60 * 5  # 5 minutos

def get_almacen_data():
    now = time.time()
    if now - ALMACEN_CACHE["last_update"] > ALMACEN_UPDATE_INTERVAL:
        almacen_sheet = client.open_by_key(AUXILIARY_SPREADSHEET_ID).worksheet(WORKSHEET_ALMACEN_MOVIMIENTOS)
        ALMACEN_CACHE["data"] = almacen_sheet.get_all_values()
        ALMACEN_CACHE["last_update"] = now
    return ALMACEN_CACHE["data"]

# Diccionario de IPs con nombres descriptivos
IP_NAMES = {
    "192.168.1.46": "TabletPCP",
    "192.168.1.71": "PCAdmin",
    # Agrega más IPs y nombres según sea necesario
}

def get_client_name(ip):
    """Devuelve el nombre asociado a una IP o la IP si no está en el diccionario."""
    return IP_NAMES.get(ip, ip)


def get_resource_path(relative_path):
    """Obtiene la ruta del recurso, compatible con PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        # Si se ejecuta como un ejecutable empaquetado
        return os.path.join(getattr(sys, "_MEIPASS", ""), relative_path)
    # Si se ejecuta como un script normal
    return os.path.join(os.getcwd(), relative_path)


def get_local_ip():
    """Obtiene la IP local automáticamente."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    return ip


def connect_to_sheets():
    """Establece la conexión con Google Sheets usando las credenciales."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_path = get_resource_path(GOOGLE_CREDENTIALS_FILE)
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    return client


# Conectar con la hoja de Google Sheets
client = connect_to_sheets()
sheet = client.open_by_key(STOCK_SPREADSHEET_ID).worksheet(WORKSHEET_STOCK)

app = Flask(__name__)

# Variable global para la interfaz
log_widget = None
window = None  # Initialize the window variable to avoid using it before assignment


def log_message(message):
    """Función para registrar mensajes en la consola de la interfaz."""
    if window:  # Asegurarse de que la ventana esté inicializada
        window.log_signal.emit(message)  # Emitir la señal con el mensaje


# Dimensiones del PDF en mm
WIDTH_MM = 104
HEIGHT_MM = 50.8
MARGIN = 0.1  # Margen para evitar recortes
CONTAINER_WIDTH = WIDTH_MM - 90 * MARGIN
CONTAINER_HEIGHT = HEIGHT_MM - 60 * MARGIN  # Contenedor mas alto para que entre un QR grande
IMAGE_WIDTH = 43  # QR mas grande (antes 33). Vuelve al tamano del servidor anterior (~42mm)
IMAGE_HEIGHT = IMAGE_WIDTH  # QR cuadrado: mismo ancho y alto
TEXT_WIDTH = CONTAINER_WIDTH - IMAGE_WIDTH - 1 * MARGIN  # Ancho máximo del texto
MAX_TEXT_HEIGHT = (
    CONTAINER_HEIGHT - 1 * MARGIN
)  # Altura máxima disponible para el texto

@app.route('/generar_kardex', methods=['POST'])
def generar_kardex():
    """Generar un código Kardex basado en material, título y color."""
    try:
        # Obtener los datos enviados en la solicitud
        data = request.json
        material = data.get("material", "").strip()
        titulo = data.get("titulo", "").strip()
        color = data.get("color", "").strip()

        # Validar que todos los campos estén presentes
        if not material or not titulo or not color:
            return jsonify({"error": "Todos los campos ('material', 'titulo', 'color') son obligatorios."}), 400

        # Conectar con la hoja "datosKardex"
        kardex_sheet = client.open_by_key(AUXILIARY_SPREADSHEET_ID).worksheet(WORKSHEET_DATOS_KARDEX)

        # Obtener todas las filas de la hoja
        rows = kardex_sheet.get_all_values()

        # Buscar el índice del material en la columna 1
        material_indices = [i for i, row in enumerate(rows) if row[0].strip() == material]
        if not material_indices:
            return jsonify({"error": f"El material '{material}' no se encuentra en la hoja 'datosKardex'."}), 404
        material_index = material_indices[0]  # Tomar el primer índice encontrado

        # Buscar el índice del color en la columna 3
        color_indices = [i for i, row in enumerate(rows) if row[2].strip() == color]
        if not color_indices:
            return jsonify({"error": f"El color '{color}' no se encuentra en la hoja 'datosKardex'."}), 404
        color_index = color_indices[0]  # Tomar el primer índice encontrado

        # Obtener los valores de las columnas relevantes
        codigo_material = rows[material_index][3]  # Columna 4 (código material)
        codigo_color = rows[color_index][4]  # Columna 5 (código color)
        codigo_10 = rows[material_index][5]  # Columna 6 (código 10)

        # Procesar el título eliminando "." y espacios
        titulo_procesado = titulo.replace(".", "").replace(" ", "")

        # Generar el código Kardex
        kardex = f"{codigo_10}{codigo_material}{titulo_procesado}{codigo_color}"

        # Devolver el resultado como respuesta JSON
        return jsonify({"kardex": kardex}), 200

    except Exception as e:
        log_message(f"Error en /generar_kardex: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/consulta_pcp', methods=['POST'])
def consulta_stock_actual():
    """Buscar un código PCP en la hoja 'Stock Actual' y devolver los datos en el formato solicitado."""
    try:
        # Obtener el JSON enviado en la solicitud
        data = request.json
        codigopcp = data.get("codigopcp", "").strip()

        if not codigopcp:
            log_message("El campo 'codigopcp' está vacío.")
            return jsonify({"error": "El campo 'codigopcp' está vacío."}), 400

        log_message(f"Buscando el código PCP: {codigopcp}")

        # Conectar con la hoja "Stock Actual"
        stock_sheet = client.open_by_key(AUXILIARY_SPREADSHEET_ID).worksheet(WORKSHEET_STOCK_ACTUAL)

        # Buscar el código PCP en la columna 1 (CodigoPCP)
        cell = stock_sheet.find(codigopcp, in_column=1)

        if not cell:
            log_message(f"El código PCP '{codigopcp}' no se encuentra en la hoja 'Stock Actual'.")
            return jsonify({"message": f"El código PCP '{codigopcp}' no se encuentra en el Stock Actual."}), 404

        log_message(f"Código PCP encontrado en la fila {cell.row}")

        # Obtener la fila correspondiente al código PCP
        row_data = stock_sheet.row_values(cell.row)
        log_message(f"Datos de la fila: {row_data}")

        # Verificar que la fila tenga suficientes columnas
        if len(row_data) < 18:
            log_message(f"La fila encontrada no tiene suficientes columnas: {len(row_data)}")
            return jsonify({"error": "La fila encontrada no tiene suficientes columnas."}), 500

        # Extraer los datos específicos en el orden solicitado
        result = ",".join([
            row_data[0],  # CodigoPCP
            row_data[2],  # Material
            row_data[3],  # Titulo
            row_data[4],  # Color
            row_data[1],  # CodigoKardex
            row_data[5],  # Lote
            row_data[6],  # Caja
            row_data[7],  # Bobinas/Conos
            row_data[8],  # Reenconado
            row_data[9],  # Peso Bruto
            row_data[10],  # Peso Neto
            row_data[11],  # Proveedor
            row_data[12],  # Fecha de ingreso al almacen
            row_data[15],  # Almacen
            row_data[16],  # Ubicacion
            row_data[17]  # Servicio
        ])

        log_message(f"Resultado generado: {result}")

        # Devolver los datos como respuesta JSON
        return jsonify({"result": result}), 200

    except Exception as e:
        log_message(f"Error en '/consulta_stock_actual': {str(e)}")
        return jsonify({"error": str(e)}), 500

def crop_qr_image(image_b64, crop_size=53.5):
    """Recorta un margen en todos los lados de la imagen sin importar el contenido."""
    try:
        image_data = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(image_data))

        # Obtener dimensiones actuales
        width, height = image.size

        # Definir nuevas coordenadas de recorte
        left = crop_size
        top = crop_size
        right = width - crop_size
        bottom = height - crop_size

        # Asegurar que el recorte no sea inválido (mínimo de 1px)
        if right > left and bottom > top:
            image = image.crop((left, top, right, bottom))

        # Guardar la imagen recortada en un archivo temporal
        image_path = "temp_qr.png"
        image.save(image_path, format="PNG")
        return image_path

    except (ValueError, IOError) as e:
        raise ValueError(f"Error al procesar la imagen: {e}") from e


@app.route("/generate_pdf", methods=["POST"])
def generate_pdf():
    try:

        data = request.json
        image_b64 = data.get("image", "")  # Imagen en Base64
        text = data.get("text", "")  # Texto a incluir

        if not data.get("image") or not data.get("text"):
            log_message(
                f"Solicitud fallida desde {request.remote_addr} con código 400: Faltan datos en la solicitud."
            )
            return jsonify({"error": "Faltan datos en la solicitud."}), 400

        log_message(
            f"Imagen y Texto recibidos correctamente desde {request.remote_addr} con código 200. "
            f"Los datos son los siguientes: '{text}'"
        )

        # Procesar imagen para eliminar bordes blancos
        image_path = crop_qr_image(image_b64, crop_size=43)

        # Crear PDF con tamaño personalizado
        pdf = FPDF(unit="mm", format=(WIDTH_MM, HEIGHT_MM))
        pdf.add_page()

        # Calcular posición centrada del contenedor
        container_x = (WIDTH_MM - CONTAINER_WIDTH) / 2
        container_y = (HEIGHT_MM - CONTAINER_HEIGHT) / 2

        # Dibujar rectángulo contenedor centrado
        pdf.set_line_width(0.5)
        pdf.rect(container_x, container_y, CONTAINER_WIDTH, CONTAINER_HEIGHT)

        # Agregar imagen dentro del contenedor (ajustada al tamaño)
        pdf.image(
            image_path,
            x=container_x + MARGIN,
            y=container_y + MARGIN,
            w=IMAGE_WIDTH,
            h=IMAGE_HEIGHT,
        )

        # Configurar fuente inicial
        font_size = 9
        pdf.set_font("Arial", style="B", size=font_size)
        line_height = 4  # Altura de línea

        # Calcular altura del texto y ajustarlo
        num_lines = len(text.split("\n"))
        total_text_height = num_lines * line_height

        while total_text_height > MAX_TEXT_HEIGHT and font_size > 6:
            font_size -= 1
            line_height -= 0.5
            pdf.set_font("Arial", style="B", size=font_size)
            total_text_height = num_lines * line_height

        # Posición centrada del texto dentro del contenedor
        text_x_start = container_x + IMAGE_WIDTH + MARGIN
        text_y_start = container_y + (CONTAINER_HEIGHT - total_text_height) / 4.5
        pdf.set_xy(text_x_start, text_y_start)

        # Agregar texto sin desbordar
        pdf.multi_cell(TEXT_WIDTH, line_height, text, align="C")

        # Guardar PDF en una ruta absoluta
        pdf_path = os.path.join(os.getcwd(), "sticker.pdf")
        pdf.output(pdf_path)

        # Enviar PDF como respuesta
        return send_file(pdf_path, as_attachment=True)

    except (ValueError, KeyError, OSError) as e:  # Replace with specific exceptions
        log_message(f"Error desde {request.remote_addr} con código 500: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/imprimir", methods=["POST"])
def imprimir_pdf():
    """Imprimir el archivo PDF generado desde una solicitud POST."""
    try:
        # Verificar si se seleccionó una impresora en la interfaz
        if (
            not window.printer_combo
            or window.printer_combo.currentText() == "Seleccionar impresora..."
        ):
            log_message(
                "Por favor, selecciona una impresora antes de intentar imprimir."
            )
            return jsonify({"error": "No se ha seleccionado una impresora."}), 400

        # Obtener la impresora seleccionada
        selected_printer = window.printer_combo.currentText()

        # Ruta del archivo PDF generado
        pdf_path = os.path.join(os.getcwd(), "sticker.pdf")

        # Verificar si el archivo PDF existe
        if not os.path.exists(pdf_path):
            log_message(
                "El archivo PDF no existe. Genera el archivo antes de intentar imprimir."
            )
            return jsonify({"error": "El archivo PDF no existe."}), 404

        # Configurar la impresora seleccionada
        win32print.SetDefaultPrinter(selected_printer)

        # Ruta del ejecutable de Adobe Reader
        reader_path = r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe"
        if not os.path.exists(reader_path):
            log_message(
                "No se encontró Adobe Reader en la ruta especificada. Verifica la instalación."
            )
            return (
                jsonify(
                    {"error": "No se encontró Adobe Reader en la ruta especificada."}
                ),
                500,
            )

        # Comando para imprimir el archivo PDF
        win32api.ShellExecute(0, "open", reader_path, f'/p /h "{pdf_path}"', None, 0)
        log_message(
            f"Archivo '{pdf_path}' enviado a la impresora '{selected_printer}' utilizando Adobe Reader."
        )
        return (
            jsonify(
                {
                    "message": f"Archivo '{pdf_path}' enviado a la impresora '{selected_printer}'."
                }
            ),
            200,
        )

    except (OSError, RuntimeError) as e:  # Replace with specific exceptions
        log_message(f"Error al imprimir el archivo: {str(e)}")
        return jsonify({"error": f"Error al imprimir el archivo: {str(e)}"}), 500
    
class LoggerApp(QMainWindow):
    log_signal = pyqtSignal(str)  # Señal para manejar mensajes de log

    def __init__(self):
        super().__init__()
        icon_path = get_resource_path("img/logo_api.png")  # Nueva ruta para el ícono
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))  # Establecer el ícono de la ventana
        else:
            print("El archivo 'logo_api.png' no se encontró en la carpeta 'img'.")
        self.initUI()
        self.initTrayIcon()  # Inicializar el ícono de la bandeja del sistema
        self.log_signal.connect(self.update_log)

        # Ocultar la ventana al iniciar
        self.hide()

    def update_log(self, message):
        """Actualizar el contenido de log_widget desde el hilo principal."""
        if log_widget:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_widget.append(f"[{timestamp}] {message}")

    def initUI(self):
        global log_widget  # Declarar log_widget como global al inicio del método

        self.setGeometry(100, 100, 800, 500)
        self.setWindowTitle("API CoolImport")
        self.setFixedSize(800, 500)  # Establecer un tamaño fijo para la ventana
        self.setWindowFlags(
            Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint
        )  # Deshabilitar el botón de maximizar
        self.center()
        self.setStyleSheet(
            """
        QMainWindow {
            background-color: #00c6d1;  /* Fondo general */
        }
        QLabel {
            color: #000000;  /* Color del texto */
        }
        QComboBox {
            background-color: #ffffff;  /* Fondo de la lista desplegable */
            border: 1px solid #6ab8bd;  /* Borde de la lista desplegable */
            text-align: center;  /* Centrar el texto */
            font-size: 15px;  /* Tamaño de fuente */
        }
        QTextEdit {
            border: 10px solid #408b8f;  /* Borde de la consola */
        }
        QPushButton {
            background-color: #ffffff;  /* Fondo del botón */
            border: 1px solid #6ab8bd;  /* Borde del botón */
            font-size: 15px;  /* Tamaño de fuente */
            padding: 5px;  /* Espaciado interno */
        }
        """
        )

        # Layout principal
        layout = QVBoxLayout()

        # Título
        title = QLabel("API CoolImport- Logs de Solicitudes", self)
        title.setStyleSheet("font-size: 25px; font-weight: bold; text-align: center;")
        title.setAlignment(Qt.AlignCenter)  # Centrar el título
        layout.addWidget(title)

        # Logo
        logo_label = QLabel(self)
        logo_path = get_resource_path("img/logo2.png")  # Nueva ruta para el logo
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            pixmap = pixmap.scaled(300, 200)  # Escalar la imagen a 300x200
            logo_label.setPixmap(pixmap)
            logo_label.setAlignment(Qt.AlignCenter)  # Centrar el logo
            layout.addWidget(logo_label)
        else:
            print(
                "No se encontró el archivo 'logo2.png' en la carpeta 'img'."
            )  # Cambiar log_widget.append a print

        # Lista desplegable para seleccionar impresoras
        self.printer_combo = QComboBox(self)
        self.printer_combo.addItem("Seleccionar impresora...")  # Opción inicial
        self.printer_combo.setFixedWidth(300)  # Establecer un ancho fijo de 300 píxeles
        self.populate_printer_list()  # Poblar la lista con impresoras disponibles
        self.printer_combo.currentIndexChanged.connect(
            self.printer_selected
        )  # Conectar evento
        layout.addWidget(
            self.printer_combo, alignment=Qt.AlignCenter
        )  # Centrar la lista desplegable

        # Consola de logs
        log_widget = QTextEdit(self)  # Inicializar log_widget aquí
        log_widget.setReadOnly(True)
        layout.addWidget(log_widget)
        log_widget.setStyleSheet(
            "background-color: #000000; font-size: 20px; color: #13ff00"
        )  # Estilo de la consola

        # Botones para limpiar la consola y exportar a PDF
        button_layout = QHBoxLayout()  # Crear un layout horizontal para los botones

        # Botón para limpiar la consola
        clear_button = QPushButton("Limpiar", self)
        clear_button.setFixedWidth(150)  # Establecer un ancho fijo de 150px
        clear_button.clicked.connect(
            self.clear_logs
        )  # Conectar el botón a la función clear_logs
        button_layout.addWidget(clear_button)  # Agregar el botón al layout

        # Espaciado entre los botones
        button_layout.addSpacing(50)  # Agregar un espacio de 50px entre los botones

        # Botón para exportar la consola a PDF
        export_button = QPushButton("Exportar Consola", self)
        export_button.setFixedWidth(150)  # Establecer un ancho fijo de 150px
        export_button.clicked.connect(
            self.export_logs_to_pdf
        )  # Conectar el botón a la función export_logs_to_pdf
        button_layout.addWidget(export_button)  # Agregar el botón al layout

        # Agregar el layout de botones al layout principal
        layout.addLayout(button_layout)

        # Contenedor
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Iniciar minimizado
        self.hide()

    def clear_logs(self):
        """Limpia el contenido de la consola de logs."""
        log_widget.clear()

    def export_logs_to_pdf(self):
        """Exporta el contenido de la consola de logs a un archivo PDF."""

        try:
            # Obtener el contenido de la consola
            logs = log_widget.toPlainText()

            if not logs.strip():
                log_message("No hay contenido en la consola para exportar.")
                return

            # Crear un archivo PDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)

            # Dividir los logs en líneas y agregarlos al PDF usando multi_cell
            for line in logs.split("\n"):
                pdf.multi_cell(
                    0, 10, txt=line
                )  # Ajustar el texto automáticamente al ancho de la página

            # Guardar el PDF en el directorio actual
            pdf_path = os.path.join(os.getcwd(), "logs_consola.pdf")
            pdf.output(pdf_path)

            log_message(f"Consola exportada a PDF: {pdf_path}")

        except (OSError, RuntimeError) as e:
            log_message(f"Error al exportar la consola a PDF: {str(e)}")

    def initTrayIcon(self):
        """Inicializar el ícono de la bandeja del sistema."""
        tray_icon_path = get_resource_path(
            "img/logo_api.png"
        )  # Usar el mismo ícono para la bandeja
        self.tray_icon = QSystemTrayIcon(QIcon(tray_icon_path), self)

        # Menú contextual para el ícono de la bandeja
        tray_menu = QMenu()
        open_action = tray_menu.addAction("Abrir")
        open_action.triggered.connect(
            self.show_window
        )  # Mostrar la ventana al hacer clic en "Abrir"
        exit_action = tray_menu.addAction("Salir")
        exit_action.triggered.connect(self.close_application)  # Salir de la aplicación

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(
            self.on_tray_icon_click
        )  # Conectar clic en el ícono
        self.tray_icon.show()

    def changeEvent(self, event):
        """Manejar el evento de minimizar la ventana."""
        if event.type() == QEvent.WindowStateChange and self.isMinimized():
            self.hide()  # Ocultar la ventana principal
            self.tray_icon.showMessage(
                "API CoolImport",
                "La aplicación sigue ejecutándose en el área de notificación.",
                QSystemTrayIcon.Information,
                3000,  # Duración del mensaje en milisegundos
            )
            event.accept()

    def on_tray_icon_click(self, reason):
        """Manejar clics en el ícono de la bandeja."""
        if reason == QSystemTrayIcon.Trigger:  # Clic izquierdo
            self.show_window()

    def show_window(self):
        """Mostrar la ventana principal."""
        self.setWindowState(
            self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive
        )  # Restaurar la ventana si está minimizada
        self.show()
        self.raise_()
        self.activateWindow()

    def close_application(self):
        """Cerrar la aplicación."""
        self.tray_icon.hide()
        self.close()

    def center(self):
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def populate_printer_list(self):
        """Poblar la lista desplegable con las impresoras disponibles."""
        try:
            printers = win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )
            for printer in printers:
                self.printer_combo.addItem(
                    printer[2]
                )  # Agregar el nombre de la impresora al combo
        except (OSError, RuntimeError) as e:
            log_widget.append(f"Error al obtener la lista de impresoras: {str(e)}")

    def printer_selected(self, index):
        """Manejar la selección de una impresora en la lista desplegable."""
        if index > 0:  # Ignorar la opción inicial
            selected_printer = self.printer_combo.currentText()
            log_widget.append(f"Impresora seleccionada: {selected_printer}")


# Función para iniciar Flask en un hilo separado
def run_flask():
    local_ip = get_local_ip()
    print(
        f"Servidor corriendo en http://{local_ip}:5000"
    )  # Muestra la IP en la consola
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    # Iniciar Flask en un hilo separado
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Iniciar la aplicación PyQt
    app = QApplication(sys.argv)
    window = LoggerApp()
    sys.exit(app.exec_())
