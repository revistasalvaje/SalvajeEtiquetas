# app/utils.py - Utility functions
import logging
from urllib.parse import urlparse
import re
import unicodedata

logger = logging.getLogger(__name__)

def extract_id_from_url(url):
    """Extract Google Sheet ID from URL"""
    if not url or "/d/" not in url:
        raise ValueError("URL no válida o no reconocida")

    try:
        return url.split("/d/")[1].split("/")[0]
    except IndexError:
        raise ValueError("No se pudo extraer ID de Google Sheets desde la URL")

def normalize_text(text):
    """Normalize text for comparison purposes"""
    text = str(text).encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r"[^a-z0-9]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def find_column(possible_names, normalized_columns):
    """Find column in dataframe by possible names"""
    for possible in possible_names:
        possible_norm = normalize_text(possible)
        for col_real, col_norm in normalized_columns.items():
            if possible_norm in col_norm:
                logger.info(f"Campo '{possible}' detectado como → '{col_real}'")
                return col_real
    return None