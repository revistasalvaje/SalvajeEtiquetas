# app/__init__.py - Application factory
import logging
import os
from flask import Flask

def create_app(test_config=None):
    """Create and configure the Flask application"""
    # Definir correctamente la ubicación de las carpetas estáticas y plantillas
    app = Flask(__name__,
                instance_relative_config=True,
                static_folder='static',
                template_folder='templates')

    # Configure logging
    logging.basicConfig(level=logging.INFO, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Configure the app
    app.config.from_mapping(
        SECRET_KEY='dev',  # Change this in production!
        DEBUG=True
    )

    if test_config is None:
        # Load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # Load the test config if passed in
        app.config.from_mapping(test_config)

    # Register blueprints
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    # Imprimir rutas registradas para depuración
    print("Rutas registradas:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule}")

    return app