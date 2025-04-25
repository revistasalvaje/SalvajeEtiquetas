# app/data_processor.py - Data processing functions
import pandas as pd
from urllib.parse import urlparse
import requests
from io import StringIO
import unicodedata
import re
import logging
import os
from app.utils import extract_id_from_url, normalize_text, find_column

logger = logging.getLogger(__name__)

def clean_data(df):
    """Process and normalize input data"""
    logger.info(f"Columnas originales: {list(df.columns)}")

    # Normalize column names for matching
    normalized_columns = {col: normalize_text(col) for col in df.columns}
    logger.info(f"Columnas normalizadas: {normalized_columns}")

    data = pd.DataFrame()

    # Process name fields
    col_full_name = find_column(["nombre y apellidos", "nombre completo"], normalized_columns)
    col_first_name = find_column(["nombre"], normalized_columns)
    col_last_name = find_column(["apellidos"], normalized_columns)

    if col_full_name:
        data["Nombre"] = df[col_full_name].fillna("").astype(str).str.strip()
    elif col_first_name and col_last_name:
        data["Nombre"] = (df[col_first_name].fillna("").astype(str).str.strip() + 
                         " " + df[col_last_name].fillna("").astype(str).str.strip())
    else:
        raise ValueError("Falta columna: Nombre y Apellidos (o Nombre + Apellidos)")

    # Define field mappings for the remaining columns
    field_mappings = {
        "Empresa": ["empresa", "compañía", "negocio"],
        "Dirección": ["Dirección", "direccion", "direccion de envio", "calle", "domicilio"],
        "CP": ["cp", "codigo postal"],
        "Ciudad": ["ciudad", "poblacion", "localidad"],
        "Zona": ["zona", "sector", "area", "z"],
        "Producto": ["Envío", "producto", "env"],
        "País": ["pais"],
        "Internacional": ["internacional", "extranjero", "es extranjero", "int"]
    }

    # Process each field according to its type
    for field, aliases in field_mappings.items():
        col = find_column(aliases, normalized_columns)

        if field in ["Empresa", "País"] and not col:
            data[field] = ""
        elif field == "Internacional":
            data[field] = df[col].astype(str).str.lower().isin(["sí", "si", "true", "1"]) if col else False
        elif field == "CP" and col:
            # Extract digits only for postal codes
            data[field] = df[col].fillna("").astype(str).str.extract(r"(\d+)")[0].fillna("")
        else:
            if not col and field not in ["Empresa", "País"]:
                raise ValueError(f"Falta columna: {field}")
            data[field] = df[col].fillna("").astype(str).str.strip() if col else ""

    # Add "Enviar" field (always True by default)
    data.insert(0, "Enviar", True)

    return data

def process_sheet_data(url):
    """Process data from Google Sheets URL"""
    sheet_id = extract_id_from_url(url)

    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

    try:
        response = requests.get(sheet_url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise Exception("No se pudo acceder al documento. ¿Está compartido correctamente?") from e

    try:
        df_raw = pd.read_csv(StringIO(response.content.decode("utf-8", errors="replace")))
        df = clean_data(df_raw)

        # Filter out rows with empty required fields
        df = df[df["Nombre"].fillna("").str.strip().ne("") & 
                df["Dirección"].fillna("").str.strip().ne("") & 
                df["Ciudad"].fillna("").str.strip().ne("")].reset_index(drop=True)

        # Process numeric fields
        df["Producto"] = df["Producto"].astype(str).str.replace(".0", "", regex=False)
        df["Zona"] = df["Zona"].astype(str)

        # Sort by product and zone
        df = df.sort_values(by=["Producto", "Zona"], na_position="last")

        # Save to CSV
        # Ensure data directory exists
        data_dir = os.path.join('app', 'data')
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        # Save to new location
        csv_path = os.path.join(data_dir, 'datos_hoja.csv')
        df.to_csv(csv_path, index=False)
        logger.info(f"Datos guardados en {csv_path}")

        return df.to_dict(orient="records")
    except Exception as e:
        logger.error(f"Error processing sheet data: {str(e)}", exc_info=True)
        raise

def save_edited_data(data):
    """Save edited data back to CSV"""
    required_fields = [
        "Enviar", "Nombre", "Empresa", "Dirección", "CP", 
        "Ciudad", "Zona", "Producto", "País", "Internacional"
    ]

    # Ensure all required fields are present
    for row in data:
        for field in required_fields:
            if field not in row:
                if field in ["Enviar", "Internacional"]:
                    row[field] = False
                else:
                    row[field] = ""

    # Validate data has required fields
    if not data or not all(field in data[0] for field in required_fields):
        missing = [f for f in required_fields if f not in data[0]]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")

    # Convert to DataFrame and save
    df = pd.DataFrame(data)[required_fields]

    # Ensure boolean fields are properly converted
    df["Internacional"] = df["Internacional"].astype(bool)
    df["Enviar"] = df["Enviar"].astype(bool)

    # Ensure data directory exists
    data_dir = os.path.join('app', 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    # Save to new location
    csv_path = os.path.join(data_dir, 'datos_hoja.csv')
    df.to_csv(csv_path, index=False)
    logger.info(f"Datos editados guardados en {csv_path}")

    return True