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

    COLS, ROWS = 3, 8
    WIDTH, HEIGHT = A4
    LABEL_H = 36 * mm
    SIDE_MARGIN = 2 * mm
    MARGIN = 6 * mm
    top_margin = MARGIN / 2
    usable_width = WIDTH - 2 * SIDE_MARGIN
    LABEL_W = usable_width / COLS
    SELLO_SIZE = 52

    for i, row in df.iterrows():
        col = i % COLS
        fila = (i // COLS) % ROWS
        if i > 0 and i % (COLS * ROWS) == 0:
            c.showPage()

        x = SIDE_MARGIN + col * LABEL_W
        y = HEIGHT - top_margin - ((fila + 1) * LABEL_H) + MARGIN / 2

        nombre = str(row.get("Nombre", "")).strip()
        empresa = str(row.get("Empresa", "")).strip()
        direccion = str(row.get("Dirección", "")).strip()
        cp = str(row.get("CP", "")).split(".")[0].strip()
        ciudad = str(row.get("Ciudad", "")).strip()
        zona = str(row.get("Zona", "")).strip()
        producto = str(row.get("Producto", "")).split(".")[0].strip()
        pais = str(row.get("País", "")).strip()

        lineas = [nombre]
        if empresa:
            lineas.append(empresa)
        lineas.append(direccion)
        bloque_final = " ".join(part for part in [cp, ciudad, zona, producto]
                                if part.strip())
        lineas.append(bloque_final)

        lineas = [l for l in lineas if l and l.lower() != "nan"]
        max_chars = max((len(l) for l in lineas), default=0)
        font_size = 10 if max_chars <= 35 else 9 if max_chars <= 42 else 8
        c.setFont("Helvetica", font_size)

        line_height = font_size + 1
        offset_y = 12 * mm

        for l in reversed(lineas):
            offset_y += line_height
            c.drawString(x + 2 * mm, y + offset_y, l)

        c.setLineWidth(0.4)
        c.line(x + 1 * mm, y + 8 * mm, x + LABEL_W - 1 * mm, y + 8 * mm)
        c.setFont("Helvetica", 7)
        c.drawString(x + 2 * mm, y + 4.2 * mm,
                     "Rte: Revista Salvaje | Apdo. Correos 15024 CP 28080")

        internacional = str(row.get(
            "Internacional", "")).strip().lower() in ["true", "1", "sí"]
        sello = "sellos/sello_extranjero.png" if internacional else "sellos/sello_nacional.png"
        sello_x = x + LABEL_W - SELLO_SIZE - 1
        sello_y = y + LABEL_H - SELLO_SIZE + 4
        c.drawImage(sello,
                    sello_x,
                    sello_y,
                    width=SELLO_SIZE,
                    height=SELLO_SIZE,
                    preserveAspectRatio=True,
                    mask='auto')

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
