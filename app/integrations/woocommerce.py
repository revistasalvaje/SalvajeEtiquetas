# app/integrations/woocommerce.py
from woocommerce import API
import pandas as pd
import json
import os
import logging
from datetime import datetime, timedelta
from app.utils.product_coder import ProductCoder

logger = logging.getLogger(__name__)

class WooCommerceIntegration:
    def __init__(self, url, consumer_key, consumer_secret, config_path=None):
        self.wcapi = API(
            url=url,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            version="wc/v3"
        )

        # Cargar mapeo de productos desde archivo de configuración
        self.config_path = config_path or os.path.join('app', 'data', 'product_mapping.json')
        self.product_mapping = {}
        self.load_product_mapping()

        self.product_coder = ProductCoder(self.product_mapping)

    def load_product_mapping(self):
        """Carga el mapeo de productos desde un archivo JSON"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    self.product_mapping = json.load(f)
                logger.info(f"Mapeo de productos cargado: {len(self.product_mapping)} productos")
            else:
                logger.warning(f"No se encontró archivo de mapeo de productos en {self.config_path}")
        except Exception as e:
            logger.error(f"Error al cargar mapeo de productos: {str(e)}")

    def save_product_mapping(self, mapping):
        """Guarda el mapeo de productos en un archivo JSON"""
        try:
            # Asegurar que existe el directorio
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

            with open(self.config_path, 'w') as f:
                json.dump(mapping, f)

            # Actualizar el mapeo interno
            self.product_mapping = mapping
            self.product_coder = ProductCoder(mapping)

            logger.info(f"Mapeo de productos guardado: {len(mapping)} productos")
            return True
        except Exception as e:
            logger.error(f"Error al guardar mapeo de productos: {str(e)}")
            return False

    def get_recent_orders(self, days=7, status="processing"):
        """Obtiene pedidos recientes de WooCommerce según estado y periodo"""
        try:
            # Calcular fecha desde cuando buscar
            date_from = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # Parámetros de la consulta
            params = {
                'status': status,
                'after': date_from,
                'per_page': 100,  # Ajusta según necesidades
            }

            # Realizar la consulta a la API
            response = self.wcapi.get("orders", params=params)

            if response.status_code != 200:
                logger.error(f"Error en API de WooCommerce: {response.status_code} - {response.text}")
                return []

            orders = response.json()
            logger.info(f"Obtenidos {len(orders)} pedidos de WooCommerce")
            return orders

        except Exception as e:
            logger.error(f"Error obteniendo pedidos de WooCommerce: {str(e)}")
            return []

    def convert_orders_to_dataframe(self, orders):
        """Convierte los pedidos de WooCommerce al formato necesario para las etiquetas"""
        data = []

        for order in orders:
            try:
                # Extraer datos del cliente y envío
                shipping = order.get('shipping', {})

                # Determinar si es internacional
                pais = shipping.get('country', 'ES')
                es_internacional = pais != 'ES'

                # Extraer líneas de productos para codificación
                items = []
                for item in order.get('line_items', []):
                    items.append({
                        'name': item.get('name', ''),
                        'quantity': item.get('quantity', 1)
                    })

                # Generar código de producto conciso
                product_code = self.product_coder.encode_order_items(items)

                # Crear registro para la tabla
                row = {
                    'Enviar': True,
                    'Nombre': f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}".strip(),
                    'Empresa': shipping.get('company', ''),
                    'Dirección': shipping.get('address_1', ''),
                    'CP': shipping.get('postcode', ''),
                    'Ciudad': shipping.get('city', ''),
                    'Zona': self._determine_zone(shipping),
                    'Producto': product_code,  # Código generado automáticamente
                    'País': pais,
                    'Internacional': es_internacional
                }

                data.append(row)
            except Exception as e:
                order_id = order.get('id', 'desconocido')
                logger.error(f"Error procesando pedido {order_id}: {str(e)}")

        # Convertir a DataFrame
        df = pd.DataFrame(data)
        logger.info(f"Creado DataFrame con {len(df)} pedidos")

        return df

    def _determine_zone(self, shipping):
        """Determina la zona según la dirección"""
        direccion = shipping.get('address_1', '').lower()

        # Comprobar si hay apartado de correos o similar en la dirección
        if any(term in direccion for term in ['apartado', 'apdo', 'p.o. box', 'pobox']):
            return 'B'  # Marcar como zona especial
        else:
            return 'A'  # Zona normal

    def save_to_csv(self, df, filename=None):
        """Guarda el DataFrame en un archivo CSV"""
        if filename is None:
            filename = os.path.join('app', 'data', 'datos_hoja.csv')

        # Asegurar que existe el directorio
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        df.to_csv(filename, index=False)
        logger.info(f"Datos guardados en {filename}")
        return filename

    def get_orders_as_csv(self, days=7, status="processing", filename=None):
        """Proceso completo: obtiene pedidos y genera CSV"""
        orders = self.get_recent_orders(days, status)

        if not orders:
            logger.warning("No se encontraron pedidos para procesar")
            return None

        df = self.convert_orders_to_dataframe(orders)

        if df.empty:
            logger.warning("No se pudo crear DataFrame con los pedidos")
            return None

        return self.save_to_csv(df, filename)

    def update_product_mapping(self, mapping):
        """Actualiza el mapeo de productos en el codificador"""
        success = self.save_product_mapping(mapping)
        if success:
            self.product_coder = ProductCoder(mapping)
        return success