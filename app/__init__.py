# app/__init__.py - Application factory
import logging
import os
import json
from flask import Flask
from dotenv import load_dotenv

def create_app(test_config=None):
    """Create and configure the Flask application"""
    # Cargar variables de entorno
    load_dotenv()

    # Definir correctamente la ubicación de las carpetas estáticas y plantillas
    app = Flask(__name__,
                instance_relative_config=True,
                static_folder='static',
                template_folder='templates')

    # Configure logging
    logging.basicConfig(level=logging.INFO, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    # Configure the app
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev_key_change_in_production'),
        DEBUG=os.environ.get('DEBUG', 'False').lower() in ['true', 't', '1'],
        PDF_CACHE_TIMEOUT=int(os.environ.get('PDF_CACHE_TIMEOUT', 300)),
        # Configuración WooCommerce
        WOO_URL=os.environ.get('WOO_URL', ''),
        WOO_KEY=os.environ.get('WOO_KEY', ''),
        WOO_SECRET=os.environ.get('WOO_SECRET', ''),
        STAMP_PATHS=[
            os.path.join('app', 'static', 'sellos'),
            'sellos',
            'static/sellos',
            '/tmp/sellos'
        ]
    )

    if test_config is None:
        # Load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # Load the test config if passed in
        app.config.from_mapping(test_config)

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        os.makedirs(os.path.join('app', 'data'), exist_ok=True)
    except OSError:
        pass

    # Inicializar WooCommerce si está configurado
    if all([app.config['WOO_URL'], app.config['WOO_KEY'], app.config['WOO_SECRET']]):
        try:
            from app.integrations.woocommerce import WooCommerceIntegration
            app.woo_integration = WooCommerceIntegration(
                app.config['WOO_URL'],
                app.config['WOO_KEY'],
                app.config['WOO_SECRET']
            )
            logger.info("Integración WooCommerce inicializada correctamente")
        except Exception as e:
            logger.error(f"Error al inicializar WooCommerce: {str(e)}")

    # Register blueprints
    from app.routes.main import main_bp
    app.register_blueprint(main_bp)

    from app.routes.admin import admin_bp
    app.register_blueprint(admin_bp)

    from app.routes.woocommerce import woo_bp
    app.register_blueprint(woo_bp)

    # Imprimir rutas registradas para depuración
    logger.debug("Rutas registradas:")
    for rule in app.url_map.iter_rules():
        logger.debug(f"{rule.endpoint}: {rule}")

    return app