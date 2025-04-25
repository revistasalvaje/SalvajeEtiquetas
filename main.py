# main.py - Entry point for the application
import os
import sys
import logging

# Configurar logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Asegurarse de que el directorio actual está en el path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
    logger.debug(f"Añadido {current_dir} al sys.path")

# Importar después de configurar el path
from app import create_app

# Create application instance
app = create_app()

# Para depuración - mostrar carpetas importantes
logger.debug(f"Directorio actual: {os.getcwd()}")
logger.debug(f"Directorio de la aplicación: {os.path.dirname(os.path.abspath(__file__))}")
logger.debug(f"Static folder: {app.static_folder}")
logger.debug(f"Template folder: {app.template_folder}")

if __name__ == "__main__":
    # Get port from environment or use default
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting application on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)