# app/routes.py - Routes and request handlers
import logging
from flask import Blueprint, render_template, request, send_file, jsonify
from app.data_processor import process_sheet_data, save_edited_data
from app.pdf_generator import generate_address_labels, generate_or_labels

logger = logging.getLogger(__name__)
main_bp = Blueprint('main', __name__, url_prefix='')

@main_bp.route("/", methods=["GET", "POST"])
def index():
    """Main route for the application"""
    preview = None
    if request.method == "POST":
        url = request.form.get("sheet_url")

        try:
            # Process the spreadsheet data
            preview = process_sheet_data(url)
            return render_template("index.html",
                                   success="Datos cargados correctamente",
                                   preview=preview)
        except Exception as e:
            logger.error(f"Error processing sheet: {str(e)}", exc_info=True)
            return render_template("index.html", 
                                  error=f"Error al procesar la hoja: {str(e)}")

    return render_template("index.html")

@main_bp.route("/editar", methods=["POST"])
def editar():
    """Route for editing data"""
    datos = request.get_json().get("data", [])
    if not datos:
        return jsonify({"ok": False, "error": "No se recibieron datos"}), 400

    try:
        save_edited_data(datos)
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Error saving data: {str(e)}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)})

@main_bp.route("/etiquetas.pdf")
def generar_pdf():
    """Generate address labels PDF"""
    try:
        buffer = generate_address_labels()
        return send_file(buffer,
                         mimetype="application/pdf",
                         as_attachment=False,
                         download_name="etiquetas.pdf")
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}", exc_info=True)
        return f"Error al generar PDF: {str(e)}", 500

@main_bp.route("/etiquetas_or.pdf")
def generar_etiquetas_or():
    """Generate OR labels PDF"""
    try:
        buffer = generate_or_labels()
        return send_file(buffer,
                         mimetype="application/pdf",
                         as_attachment=False,
                         download_name="etiquetas_or.pdf")
    except Exception as e:
        logger.error(f"Error generating OR labels: {str(e)}", exc_info=True)
        return f"Error al generar etiquetas OR: {str(e)}", 500