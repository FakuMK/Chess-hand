import cv2
import numpy as np
import os
import chess
import chess.engine
import serial
import time


# =========================
# CONFIGURACION GENERAL
# =========================
tamano_tablero = 8
tolerancia_fila = 50
area_minima = 1000
area_maxima = 5000
indice_camara = 1
nombre_foto = "fotoprev.png"

# Ajusta esta ruta a tu ejecutable real de Stockfish
ruta_stockfish = "/usr/bin/stockfish"

# Serie hacia el brazo (ajusta a tu puerto y baudios)
PUERTO_SERIE = "/dev/ttyACM0"  # Linux: /dev/ttyACM0 o /dev/ttyUSB0
# PUERTO_SERIE = "COM3"        # Windows
BAUDIOS = 9600

umbral_angulo_cuadrado = 20
umbral_aspecto_cuadrado = 0.4
umbral_llenado_cuadrado = 0.5

factor_visualizacion = 2.2

# Fichas rojas y azules en HSV
rojo1_bajo = np.array([0, 90, 50], dtype=np.uint8)
rojo1_alto = np.array([12, 255, 255], dtype=np.uint8)
rojo2_bajo = np.array([170, 90, 50], dtype=np.uint8)
rojo2_alto = np.array([180, 255, 255], dtype=np.uint8)

azul_bajo = np.array([90, 70, 40], dtype=np.uint8)
azul_alto = np.array([135, 255, 255], dtype=np.uint8)

umbral_porcentaje_color = 0.02
umbral_area_blob = 20


# =========================
# MOTOR DE AJEDREZ
# =========================
def iniciar_motor():
    if not os.path.exists(ruta_stockfish):
        raise FileNotFoundError(f"No existe Stockfish en: {ruta_stockfish}")
    if not os.access(ruta_stockfish, os.X_OK):
        raise PermissionError(f"El archivo no tiene permisos de ejecucion: {ruta_stockfish}")

    motor = chess.engine.SimpleEngine.popen_uci(
        ruta_stockfish,
        timeout=30.0
    )
    return motor


def indice_a_casilla(fila, col):
    archivo = "abcdefgh"[col]
    rango = str(8 - fila)
    return archivo + rango


def normalizar_matriz(m):
    arr = np.array(m, dtype=int)
    if arr.shape != (8, 8):
        raise ValueError("La matriz debe ser de 8x8")
    return arr


def construir_matriz_tablero(ocupacion, tamano_tablero):
    if len(ocupacion) != tamano_tablero * tamano_tablero:
        return None
    try:
        return np.array(ocupacion, dtype=int).reshape(tamano_tablero, tamano_tablero)
    except ValueError:
        return None


def matriz_ocupacion_desde_tablero(tablero):
    matriz = np.zeros((8, 8), dtype=int)
    for square, piece in tablero.piece_map().items():
        fila = 7 - chess.square_rank(square)
        col = chess.square_file(square)
        matriz[fila, col] = 1
    return matriz


def matriz_colores_desde_tablero(tablero):
    """Construye la matriz de colores usando el mismo orden que python-chess."""
    matriz = np.zeros((8, 8), dtype=int)
    for square, piece in tablero.piece_map().items():
        fila = 7 - chess.square_rank(square)
        col = chess.square_file(square)
        matriz[fila, col] = 1 if piece.color == chess.WHITE else 2
    return matriz


def aplicar_transformacion(matriz, transformacion):
    """Aplica una de las ocho orientaciones posibles al tablero detectado."""
    if transformacion == "normal":
        return matriz.copy()
    if transformacion == "flip_vertical":
        return np.flipud(matriz).copy()
    if transformacion == "flip_horizontal":
        return np.fliplr(matriz).copy()
    if transformacion == "rotacion_180":
        return np.rot90(matriz, 2).copy()
    if transformacion == "rotacion_90_cw":
        return np.rot90(matriz, -1).copy()
    if transformacion == "rotacion_90_ccw":
        return np.rot90(matriz, 1).copy()
    if transformacion == "transpuesta":
        return matriz.T.copy()
    if transformacion == "antitranspuesta":
        return np.rot90(matriz, 2).T.copy()
    raise ValueError(f"Transformación desconocida: {transformacion}")


def transformaciones_posibles():
    return [
        "normal",
        "flip_vertical",
        "flip_horizontal",
        "rotacion_180",
        "rotacion_90_cw",
        "rotacion_90_ccw",
        "transpuesta",
        "antitranspuesta",
    ]


def inferir_transformacion(matriz_ocupacion, matriz_colores, tablero):
    """
    Deduce how the camera matrix must be transformed to match python-chess.

    The detector can return the board rotated or mirrored depending on the
    camera position.  The previous code only handled a vertical flip, which
    made valid physical moves look illegal.
    """
    matriz_ocupacion = normalizar_matriz(matriz_ocupacion)
    matriz_colores = normalizar_matriz(matriz_colores)

    ocupacion_esperada = matriz_ocupacion_desde_tablero(tablero)
    colores_esperados = matriz_colores_desde_tablero(tablero)

    mejor_transformacion = None
    mejor_error_ocupacion = None
    mejor_error_color = None

    for transformacion in transformaciones_posibles():
        ocupacion_candidata = aplicar_transformacion(
            matriz_ocupacion, transformacion
        )
        colores_candidatos = aplicar_transformacion(
            matriz_colores, transformacion
        )

        error_ocupacion = int(
            np.count_nonzero(ocupacion_candidata != ocupacion_esperada)
        )
        mascara_fichas = (ocupacion_candidata != 0) | (ocupacion_esperada != 0)
        error_color = int(
            np.count_nonzero(
                colores_candidatos[mascara_fichas]
                != colores_esperados[mascara_fichas]
            )
        )

        if (
            mejor_transformacion is None
            or (error_ocupacion, error_color)
            < (mejor_error_ocupacion, mejor_error_color)
        ):
            mejor_transformacion = transformacion
            mejor_error_ocupacion = error_ocupacion
            mejor_error_color = error_color

    return mejor_transformacion, mejor_error_ocupacion, mejor_error_color


def detectar_cambios(matriz_anterior, matriz_actual):
    anterior = normalizar_matriz(matriz_anterior)
    actual = normalizar_matriz(matriz_actual)

    cambios = []
    for fila in range(8):
        for col in range(8):
            if anterior[fila, col] != actual[fila, col]:
                cambios.append({
                    "fila": fila,
                    "col": col,
                    "antes": int(anterior[fila, col]),
                    "despues": int(actual[fila, col]),
                    "casilla": indice_a_casilla(fila, col)
                })
    return cambios


def deducir_movimientos_candidatos_desde_ocupacion(matriz_anterior, matriz_actual):
    cambios = detectar_cambios(matriz_anterior, matriz_actual)

    salen = []
    entran = []

    for c in cambios:
        if c["antes"] == 1 and c["despues"] == 0:
            salen.append(c["casilla"])
        elif c["antes"] == 0 and c["despues"] == 1:
            entran.append(c["casilla"])

    candidatos = []

    if len(salen) == 1 and len(entran) == 1:
        candidatos.append(salen[0] + entran[0])

    if len(salen) == 1 and len(entran) == 0:
        origen = salen[0]
        candidatos.extend([origen + indice_a_casilla(f, c) for f in range(8) for c in range(8)])

    return candidatos, cambios


def movimiento_legal_desde_matrices(tablero, matriz_anterior, matriz_actual):
    candidatos_base, cambios = deducir_movimientos_candidatos_desde_ocupacion(
        matriz_anterior, matriz_actual
    )

    legales = list(tablero.legal_moves)

    # Coincidencia directa con candidatos base
    for uci_base in candidatos_base:
        for mov in legales:
            if mov.uci() == uci_base:
                return mov, cambios

    # Probar promociones
    for uci_base in candidatos_base:
        for promo in ["q", "r", "b", "n"]:
            uci_promo = uci_base + promo
            for mov in legales:
                if mov.uci() == uci_promo:
                    return mov, cambios

    # Fallback: probar todas las legales contra la matriz actual
    actual = normalizar_matriz(matriz_actual)
    coincidencias = []

    for mov in legales:
        tablero_tmp = tablero.copy()
        tablero_tmp.push(mov)
        matriz_esperada = matriz_ocupacion_desde_tablero(tablero_tmp)
        if np.array_equal(matriz_esperada, actual):
            coincidencias.append(mov)

    if len(coincidencias) == 1:
        return coincidencias[0], cambios

    if len(coincidencias) > 1:
        if candidatos_base:
            for mov in coincidencias:
                for base in candidatos_base:
                    if mov.uci().startswith(base):
                        return mov, cambios
        return coincidencias[0], cambios

    return None, cambios


# =========================
# SERIAL
# =========================
def abrir_serial():
    try:
        ser = serial.Serial(
            port=PUERTO_SERIE,
            baudrate=BAUDIOS,
            timeout=1,
            write_timeout=2
        )
        time.sleep(2)
        print(f"Puerto serial abierto: {PUERTO_SERIE} a {BAUDIOS} baudios")
        return ser
    except serial.SerialException as e:
        print(f"No se pudo abrir el puerto serial {PUERTO_SERIE}: {e}")
        raise


def convertir_uci_a_formato_serial(movimiento_uci: str) -> str:
    texto = movimiento_uci.strip()
    if not texto:
        return texto

    if len(texto) >= 4:
        origen = texto[0:2]
        destino = texto[2:4]
        promocion = texto[4:]
        if promocion:
            return f"{origen} {destino} {promocion}"
        return f"{origen} {destino}"

    return texto


def enviar_movimiento_serial(ser, movimiento_uci: str):
    linea = convertir_uci_a_formato_serial(movimiento_uci)
    if ser is None or not ser.is_open:
        raise RuntimeError("El puerto serial no está abierto")

    mensaje = (linea + "\n").encode("ascii")
    ser.write(mensaje)
    ser.flush()

    print(f"[SERIAL] Movimiento enviado: {linea}")

    try:
        with open("movimientos_stockfish.log", "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError as e:
        print(f"No se pudo escribir el log de movimientos: {e}")


# =========================
# VISION: DETECCION DE FICHAS
# =========================
def detectar_color_ficha(region_color):
    if region_color.size == 0:
        return 0, None, 0.0

    alto, ancho = region_color.shape[:2]
    if alto < 10 or ancho < 10:
        return 0, None, 0.0

    mx1 = int(ancho * 0.2)
    mx2 = int(ancho * 0.8)
    my1 = int(alto * 0.2)
    my2 = int(alto * 0.8)
    roi = region_color[my1:my2, mx1:mx2]

    if roi.size == 0:
        return 0, None, 0.0

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    mask_rojo_1 = cv2.inRange(hsv, rojo1_bajo, rojo1_alto)
    mask_rojo_2 = cv2.inRange(hsv, rojo2_bajo, rojo2_alto)
    mask_rojo = cv2.bitwise_or(mask_rojo_1, mask_rojo_2)
    mask_azul = cv2.inRange(hsv, azul_bajo, azul_alto)

    kernel = np.ones((3, 3), np.uint8)
    mask_rojo = cv2.morphologyEx(mask_rojo, cv2.MORPH_OPEN, kernel, iterations=1)
    mask_rojo = cv2.morphologyEx(mask_rojo, cv2.MORPH_CLOSE, kernel, iterations=1)
    mask_azul = cv2.morphologyEx(mask_azul, cv2.MORPH_OPEN, kernel, iterations=1)
    mask_azul = cv2.morphologyEx(mask_azul, cv2.MORPH_CLOSE, kernel, iterations=1)

    area_total = float(roi.shape[0] * roi.shape[1])
    porc_rojo = float(np.count_nonzero(mask_rojo)) / area_total
    porc_azul = float(np.count_nonzero(mask_azul)) / area_total

    contornos_rojo, _ = cv2.findContours(mask_rojo, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contornos_azul, _ = cv2.findContours(mask_azul, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    area_max_rojo = max([cv2.contourArea(c) for c in contornos_rojo], default=0.0)
    area_max_azul = max([cv2.contourArea(c) for c in contornos_azul], default=0.0)

    presente_rojo = porc_rojo > umbral_porcentaje_color and area_max_rojo > umbral_area_blob
    presente_azul = porc_azul > umbral_porcentaje_color and area_max_azul > umbral_area_blob

    if presente_rojo and porc_rojo >= porc_azul:
        return 1, "rojo", porc_rojo
    if presente_azul:
        return 1, "azul", porc_azul

    return 0, None, max(porc_rojo, porc_azul)


def es_casi_cuadrado(aproximacion, angle_tol=umbral_angulo_cuadrado, aspect_tol=umbral_aspecto_cuadrado, fill_ratio=umbral_llenado_cuadrado):
    pts = np.asarray(aproximacion).reshape(-1, 2)
    if pts.shape[0] != 4:
        return False

    if not cv2.isContourConvex(aproximacion):
        return False

    x, y, w, h = cv2.boundingRect(aproximacion)
    if h == 0:
        return False

    aspect = float(w) / float(h)
    if abs(aspect - 1.0) > aspect_tol:
        return False

    area = cv2.contourArea(aproximacion)
    rect_area = float(w * h)
    if rect_area <= 0 or (area / rect_area) < fill_ratio:
        return False

    def angle_between(a, b, c):
        ba = a - b
        bc = c - b
        cosang = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-9)
        ang = np.degrees(np.arccos(np.clip(cosang, -1.0, 1.0)))
        return ang

    for i in range(4):
        prev_pt = pts[(i - 1) % 4]
        cur_pt = pts[i]
        next_pt = pts[(i + 1) % 4]
        ang = angle_between(prev_pt, cur_pt, next_pt)
        if abs(ang - 90) > angle_tol:
            return False

    return True


def estimar_tamano_casilla(centros_casillas=None, esquinas=None, columnas_patron=None, filas_patron=None, tamano_predeterminado=(50, 50)):
    if esquinas is not None and columnas_patron is not None and filas_patron is not None:
        puntos = esquinas.reshape(-1, 2)
        anchos = []
        altos = []

        for r in range(filas_patron):
            for c in range(columnas_patron - 1):
                p1 = puntos[r * columnas_patron + c]
                p2 = puntos[r * columnas_patron + c + 1]
                anchos.append(np.linalg.norm(p2 - p1))

        for c in range(columnas_patron):
            for r in range(filas_patron - 1):
                p1 = puntos[r * columnas_patron + c]
                p2 = puntos[(r + 1) * columnas_patron + c]
                altos.append(np.linalg.norm(p2 - p1))

        if anchos and altos:
            return float(np.median(anchos)), float(np.median(altos))

    if centros_casillas is not None:
        sizes = []
        for _, _, puntos in centros_casillas:
            if puntos is None:
                continue
            pts = np.asarray(puntos).reshape(-1, 2)
            x, y, w, h = cv2.boundingRect(pts.astype(int))
            sizes.append((w, h))

        if sizes:
            ws, hs = zip(*sizes)
            return float(np.median(ws)), float(np.median(hs))

    return tamano_predeterminado


def encontrar_esquinas_tablero(fuentes, tamano_patron):
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE

    for fuente in fuentes:
        if hasattr(cv2, "findChessboardCornersSB"):
            try:
                encontrado, esquinas = cv2.findChessboardCornersSB(fuente, tamano_patron, flags)
                if encontrado:
                    return encontrado, esquinas
            except cv2.error:
                pass

        try:
            encontrado, esquinas = cv2.findChessboardCorners(fuente, tamano_patron, flags)
            if encontrado:
                return encontrado, esquinas
        except cv2.error:
            pass

    return False, None


def detectar_centros_casillas_desde_umbral(gris, laplaciano_abs, area_minima, area_maxima):
    mascaras = []
    adaptativo = cv2.adaptiveThreshold(gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    adaptativo_inv = cv2.adaptiveThreshold(gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
    _, lap_umbral = cv2.threshold(laplaciano_abs, 20, 255, cv2.THRESH_BINARY)
    mascaras.extend([adaptativo, adaptativo_inv, lap_umbral])

    nucleo = np.ones((5, 5), np.uint8)
    centros = []
    vistos = set()

    for mascara in mascaras:
        procesado_mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, nucleo, iterations=2)
        procesado_mascara = cv2.morphologyEx(procesado_mascara, cv2.MORPH_OPEN, nucleo, iterations=1)
        contornos, _ = cv2.findContours(procesado_mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contorno in contornos:
            area = cv2.contourArea(contorno)
            if area_minima < area < area_maxima:
                epsilon = 0.05 * cv2.arcLength(contorno, True)
                aproximacion = cv2.approxPolyDP(contorno, epsilon, True)

                if len(aproximacion) == 4 and es_casi_cuadrado(aproximacion):
                    x, y, w, h = cv2.boundingRect(contorno)
                    centro_x = x + w // 2
                    centro_y = y + h // 2
                    clave = (int(centro_x), int(centro_y), int(w), int(h))
                    if clave not in vistos:
                        vistos.add(clave)
                        centros.append([centro_x, centro_y, aproximacion.reshape(4, 2)])

    return centros


def ordenar_casillas(centros_casillas, tolerancia_fila):
    if not centros_casillas:
        return []

    ordenadas_por_y = sorted(centros_casillas, key=lambda x: (x[1], x[0]))

    filas = []
    fila_actual = [ordenadas_por_y[0]]

    for coordenada in ordenadas_por_y[1:]:
        if abs(coordenada[1] - fila_actual[-1][1]) < tolerancia_fila:
            fila_actual.append(coordenada)
        else:
            filas.append(fila_actual)
            fila_actual = [coordenada]

    filas.append(fila_actual)

    filas = sorted(filas, key=lambda fila: np.mean([p[1] for p in fila]))
    for fila in filas:
        fila.sort(key=lambda x: x[0])

    return [coordenada for fila in filas for coordenada in fila]


def centros_completos_casillas_desde_esquinas(esquinas, filas_patron, columnas_patron):
    malla = esquinas.reshape(filas_patron, columnas_patron, 2).astype(np.float32)

    filas_ext = []
    for fila in malla:
        paso_izquierda = fila[1] - fila[0]
        paso_derecha = fila[-1] - fila[-2]
        extendida = np.vstack([
            fila[0] - paso_izquierda,
            fila,
            fila[-1] + paso_derecha
        ])
        filas_ext.append(extendida)

    malla_extendida = np.stack(filas_ext, axis=0)

    fila_superior = malla_extendida[0] - (malla_extendida[1] - malla_extendida[0])
    fila_inferior = malla_extendida[-1] + (malla_extendida[-1] - malla_extendida[-2])

    malla_completa = np.vstack([
        fila_superior[np.newaxis, :, :],
        malla_extendida,
        fila_inferior[np.newaxis, :, :]
    ])

    centros_matriz = []
    for r in range(8):
        fila_centros = []
        for c in range(8):
            bloque = malla_completa[r:r + 2, c:c + 2]
            cx = float(np.mean(bloque[:, :, 0]))
            cy = float(np.mean(bloque[:, :, 1]))
            fila_centros.append([cx, cy, None])
        centros_matriz.append(fila_centros)

    centros_matriz.reverse()
    return [casilla for fila in centros_matriz for casilla in fila]


def dibujar_texto_con_fondo(imagen, texto, org, escala=0.45, color_texto=(255, 255, 255), color_fondo=(0, 0, 0)):
    font = cv2.FONT_HERSHEY_SIMPLEX
    grosor = 1
    (w, h), baseline = cv2.getTextSize(texto, font, escala, grosor)
    x, y = org
    cv2.rectangle(imagen, (x - 2, y - h - 2), (x + w + 2, y + baseline + 2), color_fondo, -1)
    cv2.putText(imagen, texto, (x, y), font, escala, color_texto, grosor, cv2.LINE_AA)


def determinar_orientacion(matriz_colores):
    # fila 7 = rank 1 (abajo), fila 0 = rank 8 (arriba)
    fila_abajo = matriz_colores[7, :]
    fila_arriba = matriz_colores[0, :]

    rojas_abajo = np.count_nonzero(fila_abajo == 1)
    azules_abajo = np.count_nonzero(fila_abajo == 2)
    rojas_arriba = np.count_nonzero(fila_arriba == 1)
    azules_arriba = np.count_nonzero(fila_arriba == 2)

    if rojas_abajo >= rojas_arriba and azules_arriba >= azules_abajo:
        return "normal"
    else:
        return "invertida"


def analizar_imagen_tablero(imagen):
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    desenfoque_gaussiano = cv2.GaussianBlur(gris, (5, 5), 0)
    _, binaria_otsu = cv2.threshold(
        desenfoque_gaussiano, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    laplaciano = cv2.Laplacian(desenfoque_gaussiano, cv2.CV_64F)
    laplaciano_abs = cv2.convertScaleAbs(laplaciano)

    columnas_patron = tamano_tablero - 1
    filas_patron = tamano_tablero - 1
    usar_esquinas = False
    esquinas = None

    if columnas_patron > 2 and filas_patron > 2:
        ecualizado = cv2.equalizeHist(gris)
        invertido = cv2.bitwise_not(binaria_otsu)
        fuentes = [gris, ecualizado, desenfoque_gaussiano, binaria_otsu, invertido, laplaciano_abs]
        encontrado, esquinas = encontrar_esquinas_tablero(fuentes, (columnas_patron, filas_patron))
        if encontrado:
            criterios = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            cv2.cornerSubPix(desenfoque_gaussiano, esquinas, (11, 11), (-1, -1), criterios)
            usar_esquinas = True

    procesado = laplaciano_abs if usar_esquinas else binaria_otsu
    tablero_marcado = cv2.cvtColor(procesado, cv2.COLOR_GRAY2BGR)
    centros_casillas = []

    if not usar_esquinas:
        centros_casillas = detectar_centros_casillas_desde_umbral(gris, laplaciano_abs, area_minima, area_maxima)

    if usar_esquinas and esquinas is not None:
        cv2.drawChessboardCorners(tablero_marcado, (columnas_patron, filas_patron), esquinas, True)
        coordenadas_ordenadas = centros_completos_casillas_desde_esquinas(esquinas, filas_patron, columnas_patron)
        modo = "esquinas"
    else:
        coordenadas_ordenadas = ordenar_casillas(centros_casillas, tolerancia_fila)
        modo = "contornos"

    if len(coordenadas_ordenadas) != 64:
        return None, None, None, "No se detectaron correctamente las 64 casillas"

    ancho_casilla, alto_casilla = estimar_tamano_casilla(
        centros_casillas=centros_casillas if not usar_esquinas else None,
        esquinas=esquinas if usar_esquinas else None,
        columnas_patron=columnas_patron if usar_esquinas else None,
        filas_patron=filas_patron if usar_esquinas else None,
        tamano_predeterminado=(50, 50)
    )

    ocupacion = []
    colores_capa = []

    alto_img, ancho_img = gris.shape
    ancho_region = max(10, int(ancho_casilla * 0.72))
    alto_region = max(10, int(alto_casilla * 0.72))

    for i, casilla in enumerate(coordenadas_ordenadas, start=1):
        cx, cy, _ = casilla
        cx_i, cy_i = int(cx), int(cy)

        x1 = max(0, cx_i - ancho_region // 2)
        x2 = min(ancho_img, cx_i + ancho_region // 2)
        y1 = max(0, cy_i - alto_region // 2)
        y2 = min(alto_img, cy_i + alto_region // 2)

        if x2 <= x1 or y2 <= y1:
            ocupacion.append(0)
            colores_capa.append(0)
            continue

        region_color = imagen[y1:y2, x1:x2]
        esta_ocupada, color_detectado, confianza = detectar_color_ficha(region_color)

        if not esta_ocupada:
            valor_color = 0
        elif color_detectado == "rojo":
            valor_color = 1  # blancas
        elif color_detectado == "azul":
            valor_color = 2  # negras
        else:
            valor_color = 0

        ocupacion.append(1 if esta_ocupada else 0)
        colores_capa.append(valor_color)

        if esta_ocupada:
            color_rect = (0, 0, 255) if color_detectado == "rojo" else (255, 0, 0)
        else:
            color_rect = (80, 80, 80)

        cv2.rectangle(tablero_marcado, (x1, y1), (x2, y2), color_rect, 1)
        cv2.circle(tablero_marcado, (cx_i, cy_i), 3, (0, 255, 255), -1)

        color_num = (255, 255, 255)
        if color_detectado == "rojo":
            color_num = (0, 0, 255)
        elif color_detectado == "azul":
            color_num = (255, 0, 0)

        dibujar_texto_con_fondo(
            tablero_marcado,
            str(i),
            (cx_i - 8, cy_i - 6),
            escala=0.38,
            color_texto=color_num,
            color_fondo=(0, 0, 0)
        )

    texto_modo = f"Modo: {modo} | Detectadas: {len(coordenadas_ordenadas)}"
    cv2.putText(tablero_marcado, texto_modo, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    matriz_ocupacion = construir_matriz_tablero(ocupacion, tamano_tablero)
    if matriz_ocupacion is None:
        return None, None, None, "No se pudo construir la matriz 8x8"

    matriz_colores = np.array(colores_capa, dtype=int).reshape(tamano_tablero, tamano_tablero)

    return matriz_ocupacion, matriz_colores, tablero_marcado, None


def capturar_y_analizar(camara):
    leido, cuadro = camara.read()
    if not leido:
        return None, None, None, "No se pudo leer el frame de la camara"

    cv2.imwrite(nombre_foto, cuadro)
    imagen = cv2.imread(nombre_foto)
    if imagen is None:
        return None, None, None, "No se pudo cargar la foto capturada"

    return analizar_imagen_tablero(imagen)


def mostrar_tablero(nombre_ventana, imagen):
    if imagen is None:
        return
    tablero_grande = cv2.resize(
        imagen, None, fx=factor_visualizacion, fy=factor_visualizacion, interpolation=cv2.INTER_CUBIC
    )
    cv2.imshow(nombre_ventana, tablero_grande)


# =========================
# LOOP PRINCIPAL
# =========================
def jugar_con_camara_y_stockfish():
    tablero = chess.Board()
    motor = iniciar_motor()
    ser = abrir_serial()

    camara = cv2.VideoCapture(indice_camara)
    camara.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    camara.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

    matriz_base = None
    matriz_colores_base = None
    imagen_base = None
    transformacion_base = None

    if not camara.isOpened():
        print("No se pudo abrir la camara")
        motor.quit()
        if ser is not None:
            ser.close()
        return

    print("Controles:")
    print("s = capturar estado base (despues de la jugada de Stockfish)")
    print("m = capturar estado despues de tu jugada y procesar")
    print("r = reiniciar partida")
    print("q = salir")
    print("")

    try:
        while True:
            leido, frame = camara.read()
            if not leido:
                print("No se pudo leer el frame")
                break

            preview = frame.copy()
            cv2.putText(preview, "s=base  m=movimiento  r=reiniciar  q=salir", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(preview, f"Turno: {'blancas' if tablero.turn == chess.WHITE else 'negras'}", (10, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

            if matriz_base is not None:
                cv2.putText(preview, "BASE: cargada", (10, 75),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            else:
                cv2.putText(preview, "BASE: no cargada", (10, 75),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            cv2.imshow("camara", preview)
            tecla = cv2.waitKey(1) & 0xFF

            if tecla == ord('q'):
                break

            elif tecla == ord('r'):
                tablero = chess.Board()
                matriz_base = None
                matriz_colores_base = None
                imagen_base = None
                transformacion_base = None
                print("")
                print("Partida reiniciada")
                print(tablero)
                print("")

            elif tecla == ord('s'):
                matriz_base_nueva, matriz_colores_nueva, imagen_base_nueva, error = capturar_y_analizar(camara)
                if error is not None:
                    print("Error capturando base:", error)
                    continue

                # Deducir la orientación completa (giro/reflejo) comparando
                # la captura con la posición conocida de python-chess.
                (
                    transformacion_nueva,
                    error_ocupacion,
                    error_color,
                ) = inferir_transformacion(
                    matriz_base_nueva,
                    matriz_colores_nueva,
                    tablero,
                )
                print(
                    f"Transformacion detectada: {transformacion_nueva} "
                    f"(errores ocupacion={error_ocupacion}, color={error_color})"
                )

                if error_ocupacion > 0:
                    print(
                        "Aviso: la captura no coincide exactamente con el tablero interno; "
                        "revisa que las 64 casillas y las piezas sean visibles."
                    )

                matriz_base_nueva = aplicar_transformacion(
                    matriz_base_nueva, transformacion_nueva
                )
                matriz_colores_nueva = aplicar_transformacion(
                    matriz_colores_nueva, transformacion_nueva
                )

                matriz_base = matriz_base_nueva
                matriz_colores_base = matriz_colores_nueva
                imagen_base = imagen_base_nueva
                transformacion_base = transformacion_nueva

                print("")
                print("Estado base capturado")
                print("Matriz base (ocupacion):")
                print(matriz_base)
                print("Matriz colores (0 vacio, 1 blancas/rojas, 2 negras/azules):")
                print(matriz_colores_base)
                print("Tablero python-chess actual:")
                print(tablero)
                print("")

                mostrar_tablero("tablero_base", imagen_base)

            elif tecla == ord('m'):
                if matriz_base is None:
                    print("Primero debes capturar el estado base con la tecla 's'")
                    continue

                matriz_actual, matriz_colores_actual, imagen_actual, error = capturar_y_analizar(camara)
                if error is not None:
                    print("Error capturando movimiento:", error)
                    continue

                # Aplicar exactamente la misma orientación usada en la base.
                # No se vuelve a decidir aquí: si no, un cambio de iluminación
                # o una detección de color imperfecta puede invertir el tablero.
                matriz_actual = aplicar_transformacion(
                    matriz_actual, transformacion_base
                )
                matriz_colores_actual = aplicar_transformacion(
                    matriz_colores_actual, transformacion_base
                )

                mostrar_tablero("tablero_actual", imagen_actual)

                print("")
                print("Matriz base (ocupacion):")
                print(matriz_base)
                print("Matriz actual (ocupacion):")
                print(matriz_actual)

                mov, cambios = movimiento_legal_desde_matrices(tablero, matriz_base, matriz_actual)

                print("Cambios detectados:", cambios)

                if mov is None:
                    print("No pude deducir una jugada legal")
                    print("Vuelve a capturar base con 's' y luego movimiento con 'm'")
                    print("")
                    continue

                print("Jugada detectada del jugador:", mov.uci())
                tablero.push(mov)

                if tablero.is_game_over():
                    print("Partida terminada")
                    print("Resultado:", tablero.result())
                    matriz_base = None
                    matriz_colores_base = None
                    transformacion_base = None
                    continue

                respuesta = motor.play(tablero, chess.engine.Limit(time=0.1, depth=10, nodes=1000))
                mov_stockfish = respuesta.move.uci()
                print("Stockfish juega:", mov_stockfish)

                enviar_movimiento_serial(ser, mov_stockfish)

                tablero.push(respuesta.move)

                print("Aplica en el tablero real la jugada de Stockfish y luego presiona 's' para guardar la nueva base")
                print("")
                print(tablero)
                print("")

                matriz_base = None
                matriz_colores_base = None
                imagen_base = None
                transformacion_base = None

    finally:
        print("")
        print("Partida terminada")
        print(tablero)
        print("Resultado:", tablero.result())
        motor.quit()
        if ser is not None:
            ser.close()
        camara.release()
        cv2.destroyAllWindows()

        if os.path.exists(nombre_foto):
            os.remove(nombre_foto)


if __name__ == "__main__":
    jugar_con_camara_y_stockfish()
