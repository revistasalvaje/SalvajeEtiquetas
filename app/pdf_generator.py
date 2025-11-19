# app/pdf_generator.py - PDF generation functionality
import pandas as pd
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code128
import logging
import functools
import os
import time
from datetime import datetime, timedelta
from flask import current_app
from reportlab.lib.colors import cyan

logger = logging.getLogger(__name__)

# Simple caching mechanism
_pdf_cache = {}
_cache_timeout = 300  # 5 minutes

def _get_from_cache(key):
    """Get item from cache if valid"""
    if key in _pdf_cache:
        timestamp, data = _pdf_cache[key]
        if time.time() - timestamp < _cache_timeout:
            return data
    return None

def _add_to_cache(key, data):
    """Add item to cache"""
    _pdf_cache[key] = (time.time(), data)

def _get_data_file_timestamp():
    """Get timestamp of data file for cache invalidation"""
    try:
        data_file_path = os.path.join('app', 'data', 'datos_hoja.csv')
        if not os.path.exists(data_file_path):
            data_file_path = 'datos_hoja.csv'  # Fallback a la ubicación antigua

        return os.path.getmtime(data_file_path)
    except OSError:
        logger.warning("No se encontró el archivo de datos")
        return 0

def pdf_cache(func):
    """Decorator for caching PDF generation"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        cache_key = f"{func.__name__}_{_get_data_file_timestamp()}"
        cached_data = _get_from_cache(cache_key)

        if cached_data:
            logger.info(f"Using cached PDF for {func.__name__}")
            # Return a new BytesIO with the same content
            buffer = BytesIO()
            buffer.write(cached_data.getvalue())
            buffer.seek(0)
            return buffer

        # Generate new PDF
        buffer = func(*args, **kwargs)

        # Cache a copy
        buffer_copy = BytesIO()
        buffer_copy.write(buffer.getvalue())
        buffer_copy.seek(0)
        _add_to_cache(cache_key, buffer_copy)

        return buffer
    return wrapper

def _intentar_cargar_sello(internacional=False):
    """Try to load stamp image from static files"""
    sello_file = "sello_extranjero.png" if internacional else "sello_nacional.png"

    # Lista de posibles ubicaciones para los sellos
    rutas = [
        os.path.join('app', 'static', 'sellos', sello_file),
        os.path.join('static', 'sellos', sello_file),
        os.path.join('sellos', sello_file),
        os.path.join('/tmp', 'sellos', sello_file)
    ]

    for ruta in rutas:
        if os.path.exists(ruta):
            logger.info(f"Sello encontrado en: {ruta}")
            return ruta

    logger.warning(f"No se encontró el archivo de sello: {sello_file}")
    return None

def _read_data_file():
    """Read data from CSV file handling different locations"""
    posibles_rutas = [
        os.path.join('app', 'data', 'datos_hoja.csv'),
        'datos_hoja.csv'
    ]

    for ruta in posibles_rutas:
        if os.path.exists(ruta):
            logger.info(f"Leyendo datos desde: {ruta}")
            return pd.read_csv(ruta, encoding="utf-8-sig", dtype=str).fillna("")

    raise FileNotFoundError("No se encontró el archivo datos_hoja.csv")

@pdf_cache
def generate_address_labels(show_guides=False):
    """Generate address labels PDF with optional calibration guides"""
    try:
        # Read and filter data
        df = _read_data_file()
        df = df[df["Enviar"].astype(str).str.lower().isin(["true", "1", "sí", "si"])
                & df["Nombre"].fillna("").str.strip().ne("")
                & df["Dirección"].fillna("").str.strip().ne("")
                & df["Ciudad"].fillna("").str.strip().ne("")].reset_index(drop=True)

        # Permitir generar PDF vacío si estamos en modo calibración (para ver solo las líneas)
        if df.empty and not show_guides:
            logger.warning("No valid data for labels")
            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=A4)
            c.drawString(50, 800, "No hay datos válidos para generar etiquetas")
            c.save()
            buffer.seek(0)
            return buffer

        # Create PDF
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)

        # --- CONFIGURACIÓN DE MEDIDAS (AJUSTADO A TUS NECESIDADES) ---
        COLS, ROWS = 3, 8
        WIDTH, HEIGHT = A4

        # MÁRGENES: He puesto 0 porque decías que se montaban. 
        # Si tu papel tiene borde, cambia el 0 por la medida en mm (ej: 5 * mm)
        SIDE_MARGIN = 0 * mm      
        TOP_MARGIN = 0 * mm       

        # ESPACIADO: Si hay hueco entre etiquetas, ponlo aquí.
        HORIZ_GAP = 0 * mm
        VERT_GAP = 0 * mm

        # Cálculos automáticos
        usable_width = WIDTH - (2 * SIDE_MARGIN) - (HORIZ_GAP * (COLS - 1))
        LABEL_W = usable_width / COLS
        # Calculamos el alto para que ocupen toda la página equitativamente
        LABEL_H = (HEIGHT - (2 * TOP_MARGIN) - (VERT_GAP * (ROWS - 1))) / ROWS

        SELLO_SIZE = 52
        # -------------------------------------------------------------

        # --- MODO CALIBRACIÓN: DIBUJAR LÍNEAS CIAN ---
        if show_guides:
            c.setStrokeColor(cyan)
            c.setLineWidth(1)
            c.setDash(3, 3) # Línea discontinua

            # Dibujar la cuadrícula completa
            for r in range(ROWS):
                for col in range(COLS):
                    x = SIDE_MARGIN + (col * (LABEL_W + HORIZ_GAP))
                    y = HEIGHT - TOP_MARGIN - ((r + 1) * LABEL_H) - (r * VERT_GAP)
                    c.rect(x, y, LABEL_W, LABEL_H)

            # Texto informativo
            c.setFillColor(cyan)
            c.setFont("Helvetica-Bold", 14)
            c.drawCentredString(WIDTH/2, HEIGHT/2, "MODO CALIBRACIÓN: LÍNEAS CIAN DE PRUEBA")
            c.setFont("Helvetica", 10)
            c.drawCentredString(WIDTH/2, HEIGHT/2 - 20, f"Márgenes actuales: Lateral={SIDE_MARGIN/mm}mm, Superior={TOP_MARGIN/mm}mm")

            # Restaurar colores normales
            c.setDash([]) 
            c.setStrokeColor('black')
            c.setFillColor('black')

        # --- DIBUJAR DATOS DE ETIQUETAS ---
        if not df.empty:
            for i, row in df.iterrows():
                col = i % COLS
                fila = (i // COLS) % ROWS

                # Nueva página si se llena
                if i > 0 and i % (COLS * ROWS) == 0:
                    c.showPage()
                    # Si es calibración, volver a dibujar líneas en la página nueva
                    if show_guides:
                        c.setStrokeColor(cyan)
                        c.setLineWidth(1)
                        c.setDash(3, 3)
                        for r in range(ROWS):
                            for cl in range(COLS):
                                rx = SIDE_MARGIN + (cl * (LABEL_W + HORIZ_GAP))
                                ry = HEIGHT - TOP_MARGIN - ((r + 1) * LABEL_H) - (r * VERT_GAP)
                                c.rect(rx, ry, LABEL_W, LABEL_H)
                        c.setDash([])
                        c.setStrokeColor('black')

                x = SIDE_MARGIN + (col * (LABEL_W + HORIZ_GAP))
                y = HEIGHT - TOP_MARGIN - ((fila + 1) * LABEL_H) - (fila * VERT_GAP)

                # Extraer datos
                nombre = str(row.get("Nombre", "")).strip()
                empresa = str(row.get("Empresa", "")).strip()
                direccion = str(row.get("Dirección", "")).strip()
                cp = str(row.get("CP", "")).split(".")[0].strip()
                ciudad = str(row.get("Ciudad", "")).strip()
                zona = str(row.get("Zona", "")).strip()
                producto = str(row.get("Producto", "")).split(".")[0].strip()
                pais = str(row.get("País", "")).strip()

                # Formatear líneas
                lineas = [nombre]
                if empresa: lineas.append(empresa)
                lineas.append(direccion)
                bloque_final = " ".join(part for part in [cp, ciudad, zona, producto] if part.strip())
                lineas.append(bloque_final)
                if pais: lineas.append(pais) # Añadir país si existe

                lineas = [l for l in lineas if l and l.lower() != "nan"]

                # Tamaño fuente dinámico
                max_chars = max((len(l) for l in lineas), default=0)
                font_size = 10 if max_chars <= 35 else 9 if max_chars <= 42 else 8
                c.setFont("Helvetica", font_size)

                # Dibujar texto (calculando posición desde abajo hacia arriba)
                line_height = font_size + 2
                text_y_base = y + 12 * mm 

                for idx, l in enumerate(reversed(lineas)):
                    c.drawString(x + 5 * mm, text_y_base + (idx * line_height), l)

                # Línea separadora y remitente
                c.setLineWidth(0.4)
                c.line(x + 2 * mm, y + 8 * mm, x + LABEL_W - 2 * mm, y + 8 * mm)
                c.setFont("Helvetica", 6)
                c.drawString(x + 5 * mm, y + 5 * mm, "Rte: Revista Salvaje | Apdo. Correos 15024 CP 28080")

                # Dibujar Sello
                internacional = str(row.get("Internacional", "")).strip().lower() in ["true", "1", "sí", "si"]
                sello = _intentar_cargar_sello(internacional)

                sello_x = x + LABEL_W - SELLO_SIZE - 2
                sello_y = y + LABEL_H - SELLO_SIZE + 2 

                try:
                    if sello:
                        c.drawImage(sello, sello_x, sello_y, width=SELLO_SIZE, height=SELLO_SIZE, preserveAspectRatio=True, mask='auto')
                    else:
                        c.rect(sello_x, sello_y, SELLO_SIZE, SELLO_SIZE)
                        c.setFont("Helvetica", 8)
                        c.drawString(sello_x + 5, sello_y + SELLO_SIZE/2, "INT." if internacional else "NAC.")
                except Exception:
                    c.rect(sello_x, sello_y, SELLO_SIZE, SELLO_SIZE)

        c.save()
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"Error generating address labels: {str(e)}", exc_info=True)
        raise
        
@pdf_cache
def generate_or_labels():
    """Generate OR-type labels with barcodes"""
    try:
        # Read and filter data
        df = _read_data_file()
        df = df[df["Enviar"].astype(str).str.lower().isin(["true", "1", "sí", "si"])]
        df = df[(df["Nombre"].str.strip() != "")
                & (df["Dirección"].str.strip() != "") 
                & (df["Ciudad"].str.strip() != "")]

        if df.empty:
            logger.warning("No valid data for OR labels")
            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=A4)
            c.drawString(50, 800, "No hay datos válidos para generar etiquetas OR")
            c.save()
            buffer.seek(0)
            return buffer

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)

        # Label dimensions
        COLS, ROWS = 2, 5
        WIDTH, HEIGHT = A4
        LABEL_W = WIDTH / COLS
        LABEL_H = HEIGHT / ROWS
        MARGIN = 6 * mm

        # Base ID for numbering
        id_base = 921

        # Generate label data
        etiquetas = []
        for i, (_, row) in enumerate(df.iterrows()):
            cp = str(row["CP"]).zfill(5)
            id_envio = str(id_base + i).zfill(9)
            codigo = f"OR6BNA93{id_envio}{cp}X"
            etiquetas.append((cp, codigo))

        # Draw labels
        for i, (cp, codigo) in enumerate(etiquetas):
            col = i % COLS
            fila = (i // COLS) % ROWS
            if i > 0 and i % (COLS * ROWS) == 0:
                c.showPage()

            x = col * LABEL_W + MARGIN / 2
            y = HEIGHT - ((fila + 1) * LABEL_H) + MARGIN / 2
            w = LABEL_W - MARGIN
            h = LABEL_H - MARGIN

            # Draw border
            c.setLineWidth(1)
            c.rect(x, y, w, h)

            # Draw header with product type and postal code
            c.setFont("Helvetica-Bold", 14)
            c.drawString(x + 10, y + h - 24, "Libros (Ordinario)")
            c.drawRightString(x + w - 10, y + h - 24, f"CP {cp}")

            # Generate and draw barcode
            try:
                barcode = code128.Code128(codigo, barHeight=h - 70, barWidth=1)
                bw, bh = barcode.wrapOn(c, w - 16, h)
                barcode.drawOn(c, x + 8, y + 36)
            except Exception as e:
                logger.error(f"Error drawing barcode: {str(e)}")
                # Draw placeholder for barcode
                c.rect(x + 8, y + 36, w - 16, h - 70)
                c.setFont("Helvetica", 8)
                c.drawCentredString(x + w/2, y + 36 + (h-70)/2, "ERROR BARCODE")

            # Draw tracking code
            c.setFont("Helvetica-Bold", 12)
            c.drawCentredString(x + w / 2, y + 18, codigo)

        c.save()
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"Error generating OR labels: {str(e)}", exc_info=True)
        raise