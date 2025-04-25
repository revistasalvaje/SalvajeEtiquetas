# app/routes/admin.py
import os
import json
import logging
from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for

logger = logging.getLogger(__name__)
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route("/productos", methods=["GET", "POST"])
def configurar_productos():
    mensaje = None

    if request.method == "POST":
        try:
            # Guardar la configuración
            nuevo_mapeo = {}

            # Productos individuales
            productos = request.form.getlist("producto_id[]")
            codigos = request.form.getlist("codigo[]")

            for i in range(len(productos)):
                if productos[i] and codigos[i]:
                    nuevo_mapeo[productos[i]] = codigos[i]

            # Combos/packs
            combos = request.form.getlist("combo_id[]")
            combo_contenidos = request.form.getlist("combo_contenido[]")

            for i in range(len(combos)):
                if combos[i] and combo_contenidos[i]:
                    # Convertir la cadena separada por comas en una lista
                    nuevo_mapeo[combos[i]] = [c.strip() for c in combo_contenidos[i].split(",")]

            # Guardar en la integración de WooCommerce si existe
            if hasattr(current_app, "woo_integration"):
                success = current_app.woo_integration.update_product_mapping(nuevo_mapeo)
                if success:
                    mensaje = "Configuración guardada correctamente"
                else:
                    mensaje = "Error al guardar la configuración en WooCommerce"
            else:
                # Guardar directamente en un archivo si no hay integración
                config_path = os.path.join('app', 'data', 'product_mapping.json')
                os.makedirs(os.path.dirname(config_path), exist_ok=True)

                with open(config_path, 'w') as f:
                    json.dump(nuevo_mapeo, f)

                mensaje = "Configuración guardada correctamente"

        except Exception as e:
            logger.error(f"Error al guardar configuración de productos: {str(e)}")
            mensaje = f"Error al guardar la configuración: {str(e)}"

    # Cargar la configuración actual
    mapeo_actual = {}
    try:
        config_path = os.path.join('app', 'data', 'product_mapping.json')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                mapeo_actual = json.load(f)
        elif hasattr(current_app, "woo_integration"):
            mapeo_actual = current_app.woo_integration.product_mapping
    except Exception as e:
        logger.error(f"Error al cargar configuración de productos: {str(e)}")

    # Separar productos individuales de combos
    productos_individuales = {}
    combos = {}

    for producto_id, codigo in mapeo_actual.items():
        if isinstance(codigo, list):
            combos[producto_id] = codigo
        else:
            productos_individuales[producto_id] = codigo

    return render_template("admin/configurar_productos.html", 
                          productos=productos_individuales,
                          combos=combos,
                          mensaje=mensaje)

@admin_bp.route("/woocommerce/test", methods=["GET"])
def test_woocommerce():
    """Prueba la conexión con WooCommerce"""
    if not hasattr(current_app, "woo_integration"):
        return jsonify({"status": "error", "message": "Integración de WooCommerce no configurada"})

    try:
        # Intentar obtener 1 pedido para probar la conexión
        orders = current_app.woo_integration.get_recent_orders(days=30, status="any")

        if orders:
            return jsonify({
                "status": "success", 
                "message": f"Conexión exitosa. Se encontraron {len(orders)} pedidos.",
                "orders_sample": orders[0:1] if orders else []
            })
        else:
            return jsonify({
                "status": "warning", 
                "message": "Conexión exitosa pero no se encontraron pedidos."
            })

    except Exception as e:
        logger.error(f"Error probando conexión con WooCommerce: {str(e)}")
        return jsonify({"status": "error", "message": f"Error: {str(e)}"})