# config.py - Configuration settings
import os
from datetime import timedelta

# Flask settings
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_key_change_in_production')
DEBUG = os.environ.get('DEBUG', 'False').lower() in ['true', '1', 't']

# PDF generation settings
PDF_CACHE_TIMEOUT = int(os.environ.get('PDF_CACHE_TIMEOUT', 300))  # 5 minutes in seconds

# Google Sheets API settings (if needed)
# GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')

# Paths
STAMP_PATHS = [
    "sellos/",
    "./sellos/", 
    "../sellos/", 
    "/tmp/sellos/"
]