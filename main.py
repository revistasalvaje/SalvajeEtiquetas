# main.py - Main Flask application
from flask import Flask, render_template, request, send_file, jsonify, url_for
import logging
from data_processor import process_sheet_data, save_edited_data
from pdf_generator import generate_address_labels, generate_or_labels

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    preview = None
    if request.method == "POST":
        url = request.form.get("sheet_url")
        try:
            preview = process_sheet_data(url)
            return render_template("index.html", 
                                   success="Datos cargados correctamente",
                                   preview=preview)
        except Exception as e:
            logger.error(f"Error processing sheet: {str(e)}", exc_info=True)
            return render_template("index.html", 
                                   error=f"Error al procesar la hoja: {str(e)}")

    return render_template("index.html")

@app.route("/editar", methods=["POST"])
def editar():
    datos = request.get_json().get("data", [])
    if not datos:
        return "No se recibieron datos", 400

    try:
        save_edited_data(datos)
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Error saving data: {str(e)}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/etiquetas.pdf")
def generar_pdf():
    try:
        buffer = generate_address_labels()
        return send_file(buffer,
                        mimetype="application/pdf",
                        download_name="etiquetas.pdf")
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}", exc_info=True)
        return f"Error generando PDF: {str(e)}", 500

@app.route("/etiquetas_or.pdf")
def generar_etiquetas_or():
    try:
        buffer = generate_or_labels()
        return send_file(buffer,
                        mimetype="application/pdf",
                        download_name="etiquetas_or.pdf")
    except Exception as e:
        logger.error(f"Error generating OR labels: {str(e)}", exc_info=True)
        return f"Error generando etiquetas OR: {str(e)}", 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)