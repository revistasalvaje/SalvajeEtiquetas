from flask import Flask, render_template, request, send_file, jsonify
import pandas as pd
from urllib.parse import urlparse
import requests
from io import StringIO, BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import unicodedata
import re
import os

app = Flask(__name__)

# === FUNCIONES AUXILIARES ===

def extraer_id_desde_url(url):
    if "/d/" in url:
        try:
            return url.split("/d/")[1].split("/")[0]
        except IndexError:
            return None
    return None


def normalizar(texto):
    texto = str(texto).encode("latin1",
                              errors="ignore").decode("utf-8", errors="ignore")
    texto = texto.lower()
    texto = unicodedata.normalize('NFKD',
                                  texto).encode('ascii',
                                                'ignore').decode('utf-8')
    texto = re.sub(r"[^a-z0-9]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def buscar_col(posibles, columnas_norm):
    for posible in posibles:
        posible_norm = normalizar(posible)
        for col_real, col_norm in columnas_norm.items():
            if posible_norm in col_norm:
                print(f"✔ Campo '{posible}' detectado como → '{col_real}'")
                return col_real
    return None


def limpiar_datos(df):
    print("Columnas crudas:", list(df.columns))
    columnas_norm = {col: normalizar(col) for col in df.columns}
    print("Columnas normalizadas:", columnas_norm)

    data = pd.DataFrame()

    col_nombre_y_apellidos = buscar_col(
        ["nombre y apellidos", "nombre completo"], columnas_norm)
    col_nombre = buscar_col(["nombre"], columnas_norm)
    col_apellidos = buscar_col(["apellidos"], columnas_norm)

    if col_nombre_y_apellidos:
        data["Nombre"] = df[col_nombre_y_apellidos].fillna("").astype(
            str).str.strip()
    elif col_nombre and col_apellidos:
        data["Nombre"] = df[col_nombre].fillna("").astype(str).str.strip(
        ) + " " + df[col_apellidos].fillna("").astype(str).str.strip()
    else:
        raise ValueError(
            "Falta columna: Nombre y Apellidos (o Nombre + Apellidos)")

    campos = {
        "Empresa": ["empresa", "compañía", "negocio"],
        "Dirección":
        ["Dirección", "direccion", "direccion de envio", "calle", "domicilio"],
        "CP": ["cp", "codigo postal"],
        "Ciudad": ["ciudad", "poblacion", "localidad"],
        "Zona": ["zona", "sector", "area"],
        "Producto": ["Envío"],
        "País": ["pais"],
        "Internacional": ["internacional", "extranjero", "es extranjero"]
    }

    for campo, aliases in campos.items():
        col = buscar_col(aliases, columnas_norm)
        if campo in ["Empresa", "País"] and not col:
            data[campo] = ""
        elif campo == "Internacional":
            data[campo] = df[col].astype(str).str.lower().isin(
                ["sí", "true", "1"]) if col else False
        elif campo == "CP" and col:
            data[campo] = df[col].fillna("").astype(str).str.extract(
                r"(\d+)")[0].fillna("")
        else:
            if not col:
                raise ValueError(f"Falta columna: {campo}")
            data[campo] = df[col].fillna("").astype(str).str.strip()

    data.insert(0, "Enviar", True)
    return data


def intentar_cargar_sello(internacional=False):
    """Intenta cargar el sello desde archivos estáticos"""
    try:
        sello_file = "sello_extranjero.png" if internacional else "sello_nacional.png"
        # Buscar el archivo en varias ubicaciones posibles
        for ruta in ["sellos/", "./sellos/", "../sellos/", "/tmp/sellos/"]:
            path = ruta + sello_file
            if os.path.exists(path):
                return path
    except:
        pass
    return None


# === RUTAS PRINCIPALES ===


@app.route("/", methods=["GET", "POST"])
def index():
    preview = None
    if request.method == "POST":
        url = request.form.get("sheet_url")
        sheet_id = extraer_id_desde_url(url)

        if not sheet_id:
            return render_template("index.html",
                                   error="URL no válida o no reconocida.")

        try:
            sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
            response = requests.get(sheet_url)
            if response.status_code != 200:
                raise Exception(
                    "No se pudo acceder al documento (compartido correctamente?)"
                )

            df_raw = pd.read_csv(
                StringIO(response.content.decode("utf-8", errors="replace")))
            df = limpiar_datos(df_raw)

            df = df[df["Nombre"].fillna("").str.strip().ne("")
                    & df["Dirección"].fillna("").str.strip().ne("")
                    & df["Ciudad"].fillna("").str.strip().ne("")].reset_index(
                        drop=True)

            df["Producto"] = df["Producto"].astype(str).str.replace(
                ".0", "", regex=False)
            df["Zona"] = df["Zona"].astype(str)

            df = df.sort_values(by=["Producto", "Zona"], na_position="last")
            df.to_csv("datos_hoja.csv", index=False)
            preview = df.to_dict(orient="records")

            return render_template("index.html",
                                   success="Datos cargados correctamente",
                                   preview=preview)

        except Exception as e:
            return render_template(
                "index.html", error=f"Error al procesar la hoja: {str(e)}")

    return render_template("index.html")


@app.route("/editar", methods=["POST"])
def editar():
    datos = request.get_json().get("data", [])
    if not datos:
        return "No se recibieron datos", 400

    campos = [
        "Enviar", "Nombre", "Empresa", "Dirección", "CP", "Ciudad", "Zona",
        "Producto", "País", "Internacional"
    ]
    df = pd.DataFrame(datos)[campos]
    df["Internacional"] = df["Internacional"].astype(bool)
    df["Enviar"] = df["Enviar"].astype(bool)
    df.to_csv("datos_hoja.csv", index=False)
    return jsonify({"ok": True})


# === RUTA PARA PDF DE DIRECCIONES ===

@app.route("/etiquetas.pdf")
def generar_pdf():
    df = pd.read_csv("datos_hoja.csv", encoding="utf-8-sig",
                     dtype=str).fillna("")
    df = df[df["Enviar"].astype(str).str.lower().isin(["true", "1", "sí"])
            & df["Nombre"].fillna("").str.strip().ne("")
            & df["Dirección"].fillna("").str.strip().ne("")
            & df["Ciudad"].fillna("").str.strip().ne("")].reset_index(
                drop=True)

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    # Configuración exacta con medidas obtenidas con regla
    A4_WIDTH, A4_HEIGHT = A4
    COLS, ROWS = 3, 8

    # Márgenes superiores e inferiores reducidos
    MARGIN_TOP = 6 * mm        # Reducido de 8mm a 6mm
    MARGIN_BOTTOM = 6 * mm     # Reducido de 8mm a 6mm

    # Sin márgenes laterales para alinear con bordes de página
    MARGIN_LEFT = 0 * mm
    MARGIN_RIGHT = 0 * mm

    # Cálculo de dimensiones de etiquetas
    USABLE_HEIGHT = A4_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    LABEL_HEIGHT = USABLE_HEIGHT / ROWS  # Altura calculada automáticamente
    LABEL_WIDTH = A4_WIDTH / COLS

    # Medidas internas de la etiqueta
    PADDING_LATERAL = 4 * mm    # Padding lateral aumentado a 4mm
    PADDING_VERTICAL = 2 * mm   # Padding vertical básico
    REMITE_HEIGHT = 4 * mm      # Altura para el remitente
    DIVIDER_Y = 8 * mm          # Posición Y de la línea divisoria reducida

    # Tamaño y posición del sello - ahora justo en la esquina superior derecha
    SELLO_SIZE = 16 * mm
    SELLO_MARGIN = 0.8 * mm  # Margen mínimo

    for i, row in df.iterrows():
        # Determinar posición de la etiqueta en la rejilla
        col = i % COLS
        fila = (i // COLS) % ROWS

        # Nueva página si es necesario
        if i > 0 and i % (COLS * ROWS) == 0:
            c.showPage()

        # Coordenadas base de la etiqueta (sin separación entre columnas)
        x_base = MARGIN_LEFT + (col * LABEL_WIDTH)
        y_base = A4_HEIGHT - MARGIN_TOP - ((fila + 1) * LABEL_HEIGHT)

        # ---- Dibujar primero el remitente y línea divisoria ----
        # Línea divisoria
        c.setLineWidth(0.4)
        c.line(x_base + PADDING_LATERAL, 
               y_base + DIVIDER_Y, 
               x_base + LABEL_WIDTH - PADDING_LATERAL, 
               y_base + DIVIDER_Y)

        # Remitente (más cerca a la línea)
        c.setFont("Helvetica", 7)
        c.drawString(x_base + PADDING_LATERAL, 
                     y_base + DIVIDER_Y - REMITE_HEIGHT, 
                     "Rte: Revista Salvaje | Apdo. Correos 15024 CP 28080")

        # ---- Espacio para el sello ----
        internacional = str(row.get("Internacional", "")).strip().lower() in ["true", "1", "sí"]

        # Posición del sello - alineado con el borde derecho de la línea
        sello_x = x_base + LABEL_WIDTH - PADDING_LATERAL - SELLO_SIZE
        sello_y = y_base + LABEL_HEIGHT - SELLO_SIZE - SELLO_MARGIN

        # Intentar cargar sello desde archivo
        sello_path = intentar_cargar_sello(internacional)

        # ---- Datos del destinatario ----
        # Extraer información de la fila
        nombre = str(row.get("Nombre", "")).strip()
        empresa = str(row.get("Empresa", "")).strip()
        direccion = str(row.get("Dirección", "")).strip()
        cp = str(row.get("CP", "")).split(".")[0].strip()
        ciudad = str(row.get("Ciudad", "")).strip()
        zona = str(row.get("Zona", "")).strip()
        producto = str(row.get("Producto", "")).split(".")[0].strip()
        pais = str(row.get("País", "")).strip()

        # Construir líneas de dirección
        lineas = []
        if nombre: lineas.append(nombre)
        if empresa: lineas.append(empresa)
        if direccion: lineas.append(direccion)

        # Línea CP+Ciudad+Zona+Producto
        location_parts = []
        if cp: location_parts.append(cp)
        if ciudad: location_parts.append(ciudad)
        if zona: location_parts.append(zona)
        if producto: location_parts.append(producto)

        if location_parts:
            lineas.append(" ".join(location_parts))

        if pais:
            lineas.append(pais)

        # Calcular el área disponible para texto
        text_width = LABEL_WIDTH - (2 * PADDING_LATERAL)
        text_height = LABEL_HEIGHT - DIVIDER_Y - (2 * PADDING_VERTICAL)

        # Calcular tamaño óptimo de fuente - para evitar cortes
        max_chars = max((len(line) for line in lineas), default=0)
        num_lines = len(lineas)

        # Iniciar con fuente más pequeña para todos los casos
        if max_chars > 30 or num_lines > 3:
            font_size = 8
        elif max_chars > 25 or num_lines > 2:
            font_size = 9
        else:
            font_size = 10

        # Calcular espaciado de líneas
        line_height = font_size * 1.1  # Interlineado reducido

        # Posicionamiento vertical mejorado
        # 1. Comenzar con menos espacio desde arriba (reducido 5mm)
        top_margin = 1 * mm  # Margen superior muy reducido
        # 2. Distribuir el espacio disponible
        available_height = LABEL_HEIGHT - DIVIDER_Y - top_margin
        # 3. Centrar las líneas en el espacio restante
        spacing = (available_height - (num_lines * line_height)) / (num_lines + 1)
        spacing = max(spacing, 1 * mm)  # Mínimo espaciado

        # Establecer fuente
        c.setFont("Helvetica", font_size)

        # Posición inicial más abajo
        y_pos = y_base + LABEL_HEIGHT - top_margin

        # Dibujar cada línea
        for idx, line in enumerate(lineas):
            # Aplicar espaciado entre líneas
            y_pos = y_pos - spacing - line_height

            # Garantizar que no se corte ninguna línea
            # Si la línea es muy larga, reducir el tamaño de la fuente solo para esa línea
            current_font_size = font_size
            line_width = len(line) * current_font_size * 0.6

            while line_width > (LABEL_WIDTH - 2 * PADDING_LATERAL) and current_font_size > 5:
                current_font_size -= 0.5
                line_width = len(line) * current_font_size * 0.6

            # Usar tamaño de fuente específico para esta línea si fue necesario reducirla
            if current_font_size != font_size:
                c.setFont("Helvetica", current_font_size)
                c.drawString(x_base + PADDING_LATERAL, y_pos, line)
                c.setFont("Helvetica", font_size)  # Restaurar fuente original
            else:
                c.drawString(x_base + PADDING_LATERAL, y_pos, line)

        # Dibujar sello al final (para que quede encima)
        if sello_path:
            try:
                c.saveState()
                c.drawImage(sello_path, 
                           sello_x, 
                           sello_y,
                           width=SELLO_SIZE, 
                           height=SELLO_SIZE,
                           preserveAspectRatio=True,
                           mask='auto')
                c.restoreState()
            except:
                # Si falla, dibujar un rectángulo con palabra "LIBROS"
                c.saveState()
                c.setFillColorRGB(1, 1, 1)  # Fondo blanco
                c.rect(sello_x, sello_y, SELLO_SIZE, SELLO_SIZE, fill=1, stroke=1)
                c.setFillColorRGB(0, 0, 0)  # Texto negro
                c.setFont("Helvetica-Bold", 9)
                c.drawCentredString(sello_x + SELLO_SIZE/2, sello_y + SELLO_SIZE/2, "LIBROS")
                c.restoreState()
        else:
            # Dibujar un rectángulo simple con "LIBROS"
            c.saveState()
            c.setFillColorRGB(1, 1, 1)
            c.rect(sello_x, sello_y, SELLO_SIZE, SELLO_SIZE, fill=1, stroke=1)
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(sello_x + SELLO_SIZE/2, sello_y + SELLO_SIZE/2, "LIBROS")
            c.restoreState()

    c.save()
    buffer.seek(0)
    return send_file(buffer,
                     mimetype="application/pdf",
                     download_name="etiquetas.pdf")


# === RUTA PARA PDF DE ETIQUETAS OR ===


@app.route("/etiquetas_or.pdf")
def generar_etiquetas_or():
    from reportlab.graphics.barcode import code128
    df = pd.read_csv("datos_hoja.csv", encoding="utf-8-sig",
                     dtype=str).fillna("")
    df = df[df["Enviar"].astype(str).str.lower().isin(["true", "1", "sí"])]
    df = df[(df["Nombre"].str.strip() != "")
            & (df["Dirección"].str.strip() != "") &
            (df["Ciudad"].str.strip() != "")]

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    COLS, ROWS = 2, 5
    WIDTH, HEIGHT = A4
    LABEL_W = WIDTH / COLS
    LABEL_H = HEIGHT / ROWS
    MARGIN = 6 * mm
    id_base = 921
    etiquetas = []

    for i, (_, row) in enumerate(df.iterrows()):
        cp = str(row["CP"]).zfill(5)
        id_envio = str(id_base + i).zfill(9)
        codigo = f"OR6BNA93{id_envio}{cp}X"
        etiquetas.append((cp, codigo))

    for i, (cp, codigo) in enumerate(etiquetas):
        col = i % COLS
        fila = (i // COLS) % ROWS
        if i > 0 and i % (COLS * ROWS) == 0:
            c.showPage()

        x = col * LABEL_W + MARGIN / 2
        y = HEIGHT - ((fila + 1) * LABEL_H) + MARGIN / 2
        w = LABEL_W - MARGIN
        h = LABEL_H - MARGIN

        c.setLineWidth(1)
        c.rect(x, y, w, h)

        c.setFont("Helvetica-Bold", 14)
        c.drawString(x + 10, y + h - 24, "Libros (Ordinario)")
        c.drawRightString(x + w - 10, y + h - 24, f"CP {cp}")

        barcode = code128.Code128(codigo, barHeight=h - 70, barWidth=1)
        bw, bh = barcode.wrapOn(c, w - 16, h)
        barcode.drawOn(c, x + 8, y + 36)

        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(x + w / 2, y + 18, codigo)

    c.save()
    buffer.seek(0)
    return send_file(buffer,
                     mimetype="application/pdf",
                     download_name="etiquetas_or.pdf")


# === EJECUCIÓN ===

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)