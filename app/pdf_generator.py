        # app/pdf_generator.py - PDF generation functionality
        import pandas as pd
        from io import BytesIO
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.graphics.barcode import code128
        import logging
        import functools
        import os
        import time
        from datetime import datetime, timedelta
        from flask import current_app

        logger = logging.getLogger(__name__)

        # Simple caching mechanism
        _pdf_cache = {}
        _cache_timeout = 300  # 5 minutes

        def _get_from_cache(key):
            """Get item from cache if valid"""
            if key in _pdf_cache:
                timestamp, data = _pdf_cache[key]
                if time.time() - timestamp < _cache_timeout:
                    return data
            return None

        def _add_to_cache(key, data):
            """Add item to cache"""
            _pdf_cache[key] = (time.time(), data)

        def _get_data_file_timestamp():
            """Get timestamp of data file for cache invalidation"""
            try:
                data_file_path = os.path.join('app', 'data', 'datos_hoja.csv')
                if not os.path.exists(data_file_path):
                    data_file_path = 'datos_hoja.csv'  # Fallback a la ubicación antigua

                return os.path.getmtime(data_file_path)
            except OSError:
                logger.warning("No se encontró el archivo de datos")
                return 0

        def pdf_cache(func):
            """Decorator for caching PDF generation"""
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Include offsets in cache key to regenerate if offsets change
                offsets_key = f"{kwargs.get('offset_x', 0)}_{kwargs.get('offset_y', 0)}"
                cache_key = f"{func.__name__}_{_get_data_file_timestamp()}_{offsets_key}"
                cached_data = _get_from_cache(cache_key)

                if cached_data:
                    logger.info(f"Using cached PDF for {func.__name__}")
                    # Return a new BytesIO with the same content
                    buffer = BytesIO()
                    buffer.write(cached_data.getvalue())
                    buffer.seek(0)
                    return buffer

                # Generate new PDF
                buffer = func(*args, **kwargs)

                # Cache a copy
                buffer_copy = BytesIO()
                buffer_copy.write(buffer.getvalue())
                buffer_copy.seek(0)
                _add_to_cache(cache_key, buffer_copy)

                return buffer
            return wrapper

        def _intentar_cargar_sello(internacional=False):
            """Try to load stamp image from static files"""
            sello_file = "sello_extranjero.png" if internacional else "sello_nacional.png"

            # Lista de posibles ubicaciones para los sellos
            rutas = [
                os.path.join('app', 'static', 'sellos', sello_file),
                os.path.join('static', 'sellos', sello_file),
                os.path.join('sellos', sello_file),
                os.path.join('/tmp', 'sellos', sello_file)
            ]

            for ruta in rutas:
                if os.path.exists(ruta):
                    logger.info(f"Sello encontrado en: {ruta}")
                    return ruta

            logger.warning(f"No se encontró el archivo de sello: {sello_file}")
            return None

        def _read_data_file():
            """Read data from CSV file handling different locations"""
            posibles_rutas = [
                os.path.join('app', 'data', 'datos_hoja.csv'),
                'datos_hoja.csv'
            ]

            for ruta in posibles_rutas:
                if os.path.exists(ruta):
                    logger.info(f"Leyendo datos desde: {ruta}")
                    # Ensure dtype=str to preserve CPs with leading zeros
                    return pd.read_csv(ruta, encoding="utf-8-sig", dtype=str).fillna("")

            raise FileNotFoundError("No se encontró el archivo datos_hoja.csv")

        @pdf_cache
        def generate_address_labels(offset_x=0, offset_y=0):
            """Generate address labels PDF with manual offsets (in mm)"""
            try:
                # Read and filter data
                df = _read_data_file()
                df = df[df["Enviar"].astype(str).str.lower().isin(["true", "1", "sí", "si"])
                        & df["Nombre"].fillna("").str.strip().ne("")
                        & df["Dirección"].fillna("").str.strip().ne("")
                        & df["Ciudad"].fillna("").str.strip().ne("")].reset_index(drop=True)

                if df.empty:
                    logger.warning("No valid data for labels")
                    buffer = BytesIO()
                    c = canvas.Canvas(buffer, pagesize=A4)
                    c.drawString(50, 800, "No hay datos válidos para generar etiquetas")
                    c.save()
                    buffer.seek(0)
                    return buffer

                # Create PDF
                buffer = BytesIO()
                c = canvas.Canvas(buffer, pagesize=A4)

                # Label dimensions
                COLS, ROWS = 3, 8
                WIDTH, HEIGHT = A4
                LABEL_H = 36 * mm
                SIDE_MARGIN = 2 * mm
                MARGIN = 6 * mm
                top_margin = MARGIN / 2
                usable_width = WIDTH - 2 * SIDE_MARGIN
                LABEL_W = usable_width / COLS
                SELLO_SIZE = 52

                # Apply user offsets (convert mm to points)
                u_off_x = offset_x * mm
                u_off_y = offset_y * mm

                # Draw labels
                for i, row in df.iterrows():
                    col = i % COLS
                    fila = (i // COLS) % ROWS
                    if i > 0 and i % (COLS * ROWS) == 0:
                        c.showPage()

                    # Base coordinates + user offsets
                    x = SIDE_MARGIN + col * LABEL_W + u_off_x
                    y = HEIGHT - top_margin - ((fila + 1) * LABEL_H) + MARGIN / 2 + u_off_y

                    # Extract data
                    nombre = str(row.get("Nombre", "")).strip()
                    empresa = str(row.get("Empresa", "")).strip()
                    direccion = str(row.get("Dirección", "")).strip()
                    cp = str(row.get("CP", "")).strip() # CP should already be clean from data_processor
                    ciudad = str(row.get("Ciudad", "")).strip()
                    zona = str(row.get("Zona", "")).strip()
                    producto = str(row.get("Producto", "")).split(".")[0].strip()
                    pais = str(row.get("País", "")).strip()

                    # Format address lines
                    lineas = [nombre]
                    if empresa:
                        lineas.append(empresa)
                    lineas.append(direccion)
                    bloque_final = " ".join(part for part in [cp, ciudad, zona, producto] if part.strip())
                    lineas.append(bloque_final)

                    # Filter out empty lines
                    lineas = [l for l in lineas if l and l.lower() != "nan"]

                    # Determine font size based on text length
                    max_chars = max((len(l) for l in lineas), default=0)
                    font_size = 10 if max_chars <= 35 else 9 if max_chars <= 42 else 8
                    c.setFont("Helvetica", font_size)

                    # Draw address lines
                    line_height = font_size + 1
                    offset_text_y = 12 * mm

                    for l in reversed(lineas):
                        offset_text_y += line_height
                        c.drawString(x + 2 * mm, y + offset_text_y, l)

                    # Draw separator line and return address
                    c.setLineWidth(0.4)
                    c.line(x + 1 * mm, y + 8 * mm, x + LABEL_W - 1 * mm, y + 8 * mm)
                    c.setFont("Helvetica", 7)
                    c.drawString(x + 2 * mm, y + 4.2 * mm,
                                "Rte: Revista Salvaje | Apdo. Correos 15024 CP 28080")

                    # Draw appropriate stamp image
                    internacional = str(row.get("Internacional", "")).strip().lower() in ["true", "1", "sí", "si"]
                    sello = _intentar_cargar_sello(internacional)
                    sello_x = x + LABEL_W - SELLO_SIZE - 1
                    sello_y = y + LABEL_H - SELLO_SIZE + 4

                    # Error handling for stamp images
                    try:
                        if sello:
                            c.drawImage(sello,
                                        sello_x,
                                        sello_y,
                                        width=SELLO_SIZE,
                                        height=SELLO_SIZE,
                                        preserveAspectRatio=True,
                                        mask='auto')
                        else:
                            # Draw placeholder rectangle
                            c.rect(sello_x, sello_y, SELLO_SIZE, SELLO_SIZE)
                            c.setFont("Helvetica", 8)
                            c.drawString(sello_x + 5, sello_y + SELLO_SIZE/2, 
                                        "NACIONAL" if not internacional else "INTERNACIONAL")
                    except Exception as e:
                        logger.error(f"Error drawing stamp image: {str(e)}")
                        # Draw placeholder rectangle
                        c.rect(sello_x, sello_y, SELLO_SIZE, SELLO_SIZE)
                        c.setFont("Helvetica-Bold", 9)
                        c.drawCentredString(sello_x + SELLO_SIZE/2, sello_y + SELLO_SIZE/2, "LIBROS")

                c.save()
                buffer.seek(0)
                return buffer
            except Exception as e:
                logger.error(f"Error generating address labels: {str(e)}", exc_info=True)
                raise

        @pdf_cache
        def generate_or_labels(offset_x=0, offset_y=0):
            """Generate OR-type labels with barcodes and manual offsets"""
            try:
                # Read and filter data
                df = _read_data_file()
                df = df[df["Enviar"].astype(str).str.lower().isin(["true", "1", "sí", "si"])]
                df = df[(df["Nombre"].str.strip() != "")
                        & (df["Dirección"].str.strip() != "") 
                        & (df["Ciudad"].str.strip() != "")]

                if df.empty:
                    logger.warning("No valid data for OR labels")
                    buffer = BytesIO()
                    c = canvas.Canvas(buffer, pagesize=A4)
                    c.drawString(50, 800, "No hay datos válidos para generar etiquetas OR")
                    c.save()
                    buffer.seek(0)
                    return buffer

                buffer = BytesIO()
                c = canvas.Canvas(buffer, pagesize=A4)

                # Label dimensions
                COLS, ROWS = 2, 5
                WIDTH, HEIGHT = A4
                LABEL_W = WIDTH / COLS
                LABEL_H = HEIGHT / ROWS
                MARGIN = 6 * mm

                # Apply user offsets (convert mm to points)
                u_off_x = offset_x * mm
                u_off_y = offset_y * mm

                # Base ID for numbering
                id_base = 921

                # Generate label data
                etiquetas = []
                for i, (_, row) in enumerate(df.iterrows()):
                    cp = str(row["CP"]).strip().zfill(5)
                    id_envio = str(id_base + i).zfill(9)
                    codigo = f"OR6BNA93{id_envio}{cp}X"
                    etiquetas.append((cp, codigo))

                # Draw labels
                for i, (cp, codigo) in enumerate(etiquetas):
                    col = i % COLS
                    fila = (i // COLS) % ROWS
                    if i > 0 and i % (COLS * ROWS) == 0:
                        c.showPage()

                    # Base coordinates + user offsets
                    x = col * LABEL_W + MARGIN / 2 + u_off_x
                    y = HEIGHT - ((fila + 1) * LABEL_H) + MARGIN / 2 + u_off_y
                    w = LABEL_W - MARGIN
                    h = LABEL_H - MARGIN

                    # Draw border
                    c.setLineWidth(1)
                    c.rect(x, y, w, h)

                    # Draw header with product type and postal code
                    c.setFont("Helvetica-Bold", 14)
                    c.drawString(x + 10, y + h - 24, "Libros (Ordinario)")
                    c.drawRightString(x + w - 10, y + h - 24, f"CP {cp}")

                    # Generate and draw barcode
                    try:
                        barcode = code128.Code128(codigo, barHeight=h - 70, barWidth=1)
                        bw, bh = barcode.wrapOn(c, w - 16, h)
                        barcode.drawOn(c, x + 8, y + 36)
                    except Exception as e:
                        logger.error(f"Error drawing barcode: {str(e)}")
                        # Draw placeholder for barcode
                        c.rect(x + 8, y + 36, w - 16, h - 70)
                        c.setFont("Helvetica", 8)
                        c.drawCentredString(x + w/2, y + 36 + (h-70)/2, "ERROR BARCODE")

                    # Draw tracking code
                    c.setFont("Helvetica-Bold", 12)
                    c.drawCentredString(x + w / 2, y + 18, codigo)

                c.save()
                buffer.seek(0)
                return buffer
            except Exception as e:
                logger.error(f"Error generating OR labels: {str(e)}", exc_info=True)
                raise