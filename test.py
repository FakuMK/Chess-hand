import serial
import time

PUERTO_SERIE = "/dev/ttyACM0"
BAUDIOS = 9600

ser = serial.Serial(PUERTO_SERIE, BAUDIOS, timeout=1)
time.sleep(2)

ser.write(b"e2 e3\n")
ser.flush()

print("Enviado: e2 e3")
ser.close()
