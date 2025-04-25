# app/utils/product_coder.py
from collections import Counter
import logging

logger = logging.getLogger(__name__)

class ProductCoder:
    def __init__(self, product_mapping=None):
        """
        Inicializa el codificador con un mapeo opcional de productos.

        Args:
            product_mapping (dict): Diccionario que mapea IDs de productos a sus códigos cortos
        """
        # Mapeo por defecto (puedes personalizarlo según tus productos)
        self.product_mapping = product_mapping or {
            "revista-salvaje-24": "24",
            "revista-salvaje-23": "23",
            "revista-salvaje-22": "22",
            "pack-revistas-23-24": ["23", "24"],
            "camiseta-salvaje": "CS",
            "poster-edicion-limitada": "PEL",
            # Combos predefinidos
            "pack-completo": ["23", "24", "CS"],
        }

        # Mapeo inverso para búsquedas por nombre de producto
        self.name_mapping = {}
        for product_id, code in self.product_mapping.items():
            name_parts = product_id.replace('-', ' ').lower().split()
            for i in range(len(name_parts)):
                for j in range(i+1, len(name_parts)+1):
                    key = ' '.join(name_parts[i:j])
                    if key not in self.name_mapping:
                        self.name_mapping[key] = product_id

        logger.info(f"ProductCoder inicializado con {len(self.product_mapping)} productos")

    def match_product(self, product_name):
        """
        Intenta hacer coincidir un nombre de producto con un ID conocido.

        Args:
            product_name (str): Nombre del producto de WooCommerce

        Returns:
            str: ID del producto si se encuentra, o None si no
        """
        product_name_lower = product_name.lower()

        # Intentar coincidencia exacta primero
        if product_name_lower in self.name_mapping:
            return self.name_mapping[product_name_lower]

        # Intentar coincidencia parcial
        best_match = None
        max_match_length = 0

        for keyword in self.name_mapping:
            if keyword in product_name_lower and len(keyword) > max_match_length:
                max_match_length = len(keyword)
                best_match = self.name_mapping[keyword]

        return best_match

    def encode_order_items(self, items):
        """
        Codifica una lista de artículos de pedido en un código conciso.

        Args:
            items (list): Lista de artículos (diccionarios con 'name' y 'quantity')

        Returns:
            str: Código conciso para la etiqueta
        """
        # Contador para acumular códigos de producto
        code_counter = Counter()

        for item in items:
            product_name = item.get('name', '')
            product_id = self.match_product(product_name)
            quantity = item.get('quantity', 1)

            if product_id:
                codes = self.product_mapping.get(product_id)

                # Si el valor es una lista, es un combo
                if isinstance(codes, list):
                    for code in codes:
                        code_counter[code] += quantity
                else:
                    code_counter[codes] += quantity
            else:
                logger.warning(f"No se encontró coincidencia para producto: {product_name}")

        # Generar el código final
        result = []
        for code, count in sorted(code_counter.items()):
            if count > 1:
                result.append(f"{count}{code}")
            else:
                result.append(code)

        final_code = "+".join(result) if result else "?"
        logger.debug(f"Código generado: {final_code} para items: {items}")
        return final_code

    def process_woocommerce_orders(self, orders):
        """
        Procesa órdenes de WooCommerce y añade códigos de producto.

        Args:
            orders (list): Lista de órdenes de WooCommerce

        Returns:
            list: Las mismas órdenes con códigos de producto añadidos
        """
        for order in orders:
            items = []
            for item in order.get('line_items', []):
                items.append({
                    'name': item.get('name', ''),
                    'quantity': item.get('quantity', 1)
                })

            product_code = self.encode_order_items(items)
            order['product_code'] = product_code

        return orders

    def enhance_dataframe(self, df, items_column=None):
        """
        Mejora un DataFrame con códigos de producto.

        Args:
            df (pandas.DataFrame): DataFrame con datos de pedidos
            items_column (str): Nombre de la columna que contiene JSON con los items

        Returns:
            pandas.DataFrame: DataFrame mejorado con códigos de producto
        """
        import json
        import pandas as pd

        # Copia para no modificar el original
        enhanced_df = df.copy()

        if items_column and items_column in df.columns:
            # Si tenemos una columna con items en JSON
            enhanced_df['Producto'] = enhanced_df[items_column].apply(
                lambda x: self.encode_order_items(json.loads(x)) if isinstance(x, str) else ""
            )
        else:
            # Si no tenemos información detallada, intentamos inferir
            product_names = {}
            for col in df.columns:
                if "producto" in col.lower() or "producto" in col.lower():
                    product_names[col] = df[col]

            if product_names:
                # Crear ítems simulados a partir de columnas de producto
                def create_items(row):
                    items = []
                    for col, values in product_names.items():
                        value = row[col]
                        if pd.notnull(value) and value:
                            items.append({
                                'name': str(value),
                                'quantity': 1
                            })
                    return self.encode_order_items(items)

                enhanced_df['Producto'] = df.apply(create_items, axis=1)

        return enhanced_df