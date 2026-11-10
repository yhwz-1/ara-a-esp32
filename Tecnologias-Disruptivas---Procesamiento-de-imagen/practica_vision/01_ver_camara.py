"""
01 - Ver la cámara en vivo y tomar fotos.
Uso:  python 01_ver_camara.py                          (webcam por defecto)
      python 01_ver_camara.py 1                        (otra webcam)
      python 01_ver_camara.py http://IP:81/stream      (ESP32-CAM o celular)
Teclas:  f = guardar foto en imagenes/   ·   q = salir
"""
import sys, os, time
import cv2
from camara import abrir_camara, fuente_desde_argumentos

leer = abrir_camara(fuente_desde_argumentos(sys.argv))
os.makedirs("imagenes", exist_ok=True)
fotos = 0

while True:
    t0 = time.time()
    frame = leer()
    if frame is None:
        print("La cámara no entregó imagen")
        break
    fps = 1 / max(time.time() - t0, 1e-6)
    alto, ancho = frame.shape[:2]

    vista = frame.copy()
    cv2.putText(vista, f"{ancho}x{alto}  FPS: {fps:.0f}  [f] foto  [q] salir", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.imshow("Mi camara", vista)

    tecla = cv2.waitKey(1) & 0xFF
    if tecla == ord("f"):
        fotos += 1
        nombre = f"imagenes/foto_{fotos}.jpg"
        cv2.imwrite(nombre, frame)              # se guarda sin el texto
        print("Guardada:", nombre)
    elif tecla == ord("q"):
        break

cv2.destroyAllWindows()
