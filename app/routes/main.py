# app/routes/main.py
import logging
import os
import pandas as pd
from flask import Blueprint, render_template, request, send_file, jsonify, current_app, flash, redirect, url_for
from app.utils.data_processor import process_sheet_data, save_edited_data, read_data_file
from app.pdf_generator import generate_address_labels, generate_or_labels

logger = logging.getLogger(__name__)
main_bp = Blueprint('main', __name__, url_prefix='')

@main_bp.route("/", methods=["GET"])
def index():
    """Página principal de la aplicación"""
    preview = None

    # Verificar si hay datos cargados
    try:
        df = read_data_file()
        if not df.empty:
            preview = df.to_dict(orient="records")
    except Exception as e:
        logger.warning(f"No hay datos cargados: {str(e)}")

    return render_template("index.html", preview=preview)

@main_bp.route("/cargar-google-sheets", methods=["POST"])
def cargar_google_sheets():
    """Carga datos desde Google Sheets"""
    if request.method == "POST":
        url = request.form.get("sheet_url")

        try:
            # Process the spreadsheet data
            preview = process_sheet_data(url)
            flash("Datos cargados correctamente desde Google Sheets", "success")
            return redirect(url_for("main.index"))
        except Exception as e:
            logger.error(f"Error processing sheet: {str(e)}", exc_info=True)
            flash(f"Error al procesar la hoja: {str(e)}", "error")
            return redirect(url_for("main.index"))

@main_bp.route("/editar", methods=["POST"])
def editar():
    """Guarda datos editados"""
    datos = request.get_json().get("data", [])
    if not datos:
        return jsonify({"ok": False, "error": "No se recibieron datos"}), 400

    try:
        save_edited_data(datos)
        return jsonify({"ok": True})
    except Exception as e:
        