# app/routes/woocommerce.py
import logging
from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, flash
import os

logger = logging.getLogger(__name__)
woo_bp = Blueprint('woocommerce', __name__, url_prefix='/woocommerce')

@woo_bp.route("/importar", methods=["GET", "POST"])
def importar_pedidos():
    """Importación de pedidos desde WooCommerce"""

    if request.method == "POST":
        try:
            # Verificar si la integración está configurada
            if not hasattr(current_app, "woo_integration"):
                flash("Error: La integración con WooCommerce no está configurada", "error")
                return redirect(url_for("main.index"))

            # Obtener parámetros
            days = int(request.form.get("woo_days", 7))
            status = request.form.get("woo_status", "processing")

            # Obtener pedidos y guardar en CSV
            csv_path = current_app.woo_integration.get_orders_as_csv(days=days, status=status)

            if csv_path and os.path.exists(csv_path):
                # Redirigir a la página principal con los datos cargados
                flash(f"Datos importados correctamente desde WooCommerce", "success")
                return redirect(url_for("main.index"))
            else:
                flash("No se encontraron pedidos para importar", "warning")
                return redirect(url_for("main.index"))

        except Exception as e:
            logger.error(f"Error al importar pedidos de WooCommerce: {str(e)}")
            flash(f"Error al importar: {str(e)}", "error")
            return redirect(url_for("main.index"))

    # GET - Mostrar formulario
    return render_template("woocommerce/importar.html")

@woo_bp.route("/pedidos", methods=["GET"])
def listar_pedidos():
    """Lista los pedidos recientes de WooCommerce"""

    if not hasattr(current_app, "woo_integration"):
        flash("Error: La integración con WooCommerce no está configurada", "error")
        return redirect(url_for("main.index"))

    try:
        # Parámetros de búsqueda
        days = int(request.args.get("days", 30))
        status = request.args.get("status", "any")

        # Obtener pedidos
        orders = current_app.woo_integration.get_recent_orders(days=days, status=status)

        # Procesar pedidos para mostrar
        processed_orders = []
        for order in orders:
            processed_orders.append({
                'id': order.get('id'),
                'order_number': order.get('number'),
                'status': order.get('status'),
                'date': order.get('date_created'),
                'customer': f"{order.get('shipping', {}).get('first_name', '')} {order.get('shipping', {}).get('last_name', '')}".strip(),
                'total': order.get('total'),
                'items_count': len(order.get('line_items', [])),
                'product_codes': current_app.woo_integration.product_coder.encode_order_items([
                    {'name': item.get('name', ''), 'quantity': item.get('quantity', 1)} 
                    for item in order.get('line_items', [])
                ])
            })

        return render_template(
            "woocommerce/pedidos.html", 
            orders=processed_orders,
            days=days,
            status=status
        )

    except Exception as e:
        logger.error(f"Error al listar pedidos de WooCommerce: {str(e)}")
        flash(f"Error al obtener pedidos: {str(e)}", "error")
        return redirect(url_for("main.index"))