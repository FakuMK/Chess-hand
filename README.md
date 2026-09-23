# Sistema de ajedrez con cámara, visión por computadora y Stockfish

Este proyecto detecta jugadas sobre un tablero físico usando una cámara, analiza la ocupación de las 64 casillas con OpenCV, valida la jugada con python-chess y responde con una jugada generada por Stockfish. El código también deja preparado el envío del movimiento a un brazo robótico por serial, aunque en el estado actual usa una salida simulada por consola.

## Características

- Detección de casillas del tablero mediante esquinas internas del patrón o, como respaldo, por contornos.
- Detección de ocupación de casillas usando visión por computadora.
- Identificación de color de fichas usando HSV:
  - rojo = blancas
  - azul = negras
- Corrección automática de orientación del tablero.
- Reconstrucción de la matriz de ocupación 8x8.
- Deducción de jugadas legales comparando el estado anterior y el actual.
- Integración con Stockfish mediante UCI usando python-chess.
- Salida dummy por consola para simular el envío al brazo robótico.
- Visualización de capturas procesadas con etiquetas y regiones analizadas.

## Tecnologías usadas

- Python 3
- OpenCV (cv2)
- NumPy
- python-chess
- Stockfish
- Serial opcional (pyserial, actualmente comentado)

## Requisitos

### Dependencias de Python

Instala las librerías necesarias con:


pip install opencv-python numpy chess


Si luego quieres habilitar comunicación serial real:


pip install pyserial


### Motor Stockfish

Debes tener Stockfish instalado en tu sistema y ajustar esta variable en el código:

python
#linux# ruta_stockfish = "/usr/bin/stockfish"

en windows la ruta sera diferente, se muestra al instalar stockfish

En Linux puedes comprobar la ruta con:

which stockfish


## Configuración principal

Estas variables controlan el comportamiento general del sistema:

python
tamano_tablero = 8
tolerancia_fila = 50
area_minima = 1000
area_maxima = 5000
indice_camara = 1
nombre_foto = "fotoprev.png"
ruta_stockfish = "/usr/bin/stockfish"

PUERTO_SERIE = "/dev/ttyACM0"  # Linux: /dev/ttyACM0 o /dev/ttyUSB0
# PUERTO_SERIE = "COM3"        # Windows
BAUDIOS = 9600

### Parámetros importantes

- indice_camara: índice de la cámara usada por OpenCV.
- tolerancia_fila: margen para agrupar casillas detectadas en filas.
- area_minima y area_maxima: filtran contornos candidatos a casillas.
- factor_visualizacion: escala de la ventana mostrada.
- Umbrales HSV: permiten detectar fichas rojas y azules.
- umbral_porcentaje_color y umbral_area_blob: controlan cuándo una región se considera ocupada.

## Estructura lógica del programa

### 1. Inicialización del motor

La función iniciar_motor() verifica que Stockfish exista, tenga permisos de ejecución y luego lo abre como motor UCI.

### 2. Representación del tablero

El programa usa varias conversiones entre:

- matriz de ocupación de 8x8
- casillas algebraicas como e2, e4
- estado interno de python-chess

Funciones importantes:

- indice_a_casilla(fila, col)
- matriz_ocupacion_desde_tablero(tablero)
- construir_matriz_tablero(...)
- normalizar_matriz(m)

### 3. Detección de movimientos

El programa compara una matriz anterior con una actual para encontrar cambios:

- casillas que se vacían
- casillas que se ocupan
- posibles jugadas candidatas

Luego intenta validar la jugada contra la lista de jugadas legales del tablero actual.

Funciones clave:

- detectar_cambios(...)
- deducir_movimientos_candidatos_desde_ocupacion(...)
- movimiento_legal_desde_matrices(...)

También contempla promociones y un modo de respaldo que prueba todas las jugadas legales y compara la ocupación resultante.

### 4. Detección visual de fichas

Para cada casilla detectada, se recorta una región de interés y se analiza en HSV para decidir si contiene una ficha roja o azul.

Función principal:

- detectar_color_ficha(region_color)

Salida esperada:

- ocupada o vacía
- color detectado
- confianza aproximada basada en porcentaje de máscara

### 5. Detección del tablero

El sistema intenta primero detectar las esquinas internas del tablero como patrón de ajedrez usando:

- cv2.findChessboardCornersSB()
- cv2.findChessboardCorners()

Si eso falla, usa un enfoque por umbralado, contornos y validación geométrica de cuadrados.

Funciones relacionadas:

- encontrar_esquinas_tablero(...)
- detectar_centros_casillas_desde_umbral(...)
- ordenar_casillas(...)
- centros_completos_casillas_desde_esquinas(...)
- es_casi_cuadrado(...)

### 6. Orientación del tablero

La orientación se deduce observando si las fichas rojas están abajo y las azules arriba. Si está invertido, la matriz se invierte verticalmente antes de procesar la jugada.

Función usada:

- determinar_orientacion(matriz_colores)

### 7. Bucle principal

La función jugar_con_camara_y_stockfish() coordina todo el flujo:

1. Inicializa tablero, motor y cámara.
2. Espera comandos por teclado.
3. Captura un estado base.
4. Captura el estado tras la jugada del jugador.
5. Deduce la jugada legal.
6. Consulta a Stockfish.
7. Imprime el movimiento de Stockfish para aplicarlo en el tablero real.
8. Espera una nueva captura base.

## Controles del programa

Durante la ejecución:

- s: capturar estado base.
- m: capturar estado después de la jugada del jugador y procesar.
- r: reiniciar la partida.
- q: salir.

## Flujo de uso

1. Ejecuta el programa.
2. Coloca el tablero frente a la cámara.
3. Presiona s para capturar el estado base.
4. Realiza una jugada física en el tablero.
5. Presiona m para detectar tu jugada.
6. El programa valida la jugada y pide una respuesta a Stockfish.
7. Aplica físicamente la jugada de Stockfish.
8. Presiona s para guardar el nuevo estado base.
9. Repite el proceso.

## Ejecución

Guarda el script, por ejemplo como main.py, y ejecuta:


python main.py


## Comunicación serial

Actualmente la parte serial está simulada:

- abrir_serial() no abre un puerto real.
- enviar_movimiento_serial(...) imprime el movimiento en consola.
- Además guarda los movimientos en movimientos_stockfish.log.

Si quieres conectarlo a un brazo robótico real, debes:

1. descomentar import serial
2. definir puerto y baudios
3. implementar la apertura real del puerto
4. enviar la jugada en el formato esperado por tu microcontrolador

## Posibles mejoras

- Detectar tipos de piezas, no solo ocupación y color.
- Mejorar la robustez frente a iluminación variable.
- Integrar serial real con Arduino o un brazo robótico.
- Crear una interfaz gráfica más completa.

## Limitaciones actuales

- El sistema depende mucho de la iluminación y del color de las fichas.
- Asume una codificación por color fija: rojo para blancas y azul para negras.
- La detección puede fallar si no se reconocen correctamente las 64 casillas.
- No distingue el tipo de pieza, solo presencia y color.
- La comunicación serial real no está activa.


## Ejemplo de salida en consola

text
Controles:
s = capturar estado base (despues de la jugada de Stockfish)
m = capturar estado despues de tu jugada y procesar
r = reiniciar partida
q = salir

Orientacion detectada: normal
Estado base capturado
Jugada detectada del jugador: e2e4
Stockfish juega: c7c5
[DUMMY SERIAL] c7c5


