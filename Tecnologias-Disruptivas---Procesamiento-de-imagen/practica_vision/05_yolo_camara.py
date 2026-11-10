"""
05 - YOLO en tiempo real + conteo de objetos + FPS.
Uso:  python 05_yolo_camara.py                          (webcam por defecto)
      python 05_yolo_camara.py http://IP:81/stream      (ESP32-CAM o celular)
Tecla q para salir. Si existe la carpeta yolo26n_ncnn_model (ver 06_exportar_ncnn.py) la usa.
"""
import sys, os, time
import cv2
from ultralytics import YOLO
from camara import abrir_camara, fuente_desde_argumentos

CLASE_A_CONTAR = "person"        # prueba: cell phone, bottle, cup, book, laptop...
TAMANO = 320                     # 320 = más rápido · 640 = más preciso

ruta = "yolo26n_ncnn_model" if os.path.isdir("yolo26n_ncnn_model") else "yolo26n.pt"
modelo = YOLO(ruta)
leer = abrir_camara(fuente_desde_argumentos(sys.argv))
print("Modelo:", ruta)

while True:
    frame = leer()
    if frame is None:
        break
    t0 = time.time()
    r = modelo(frame, imgsz=TAMANO, conf=0.5, verbose=False)[0]
    fps = 1 / (time.time() - t0)

    cantidad = sum(1 for c in r.boxes if modelo.names[int(c.cls)] == CLASE_A_CONTAR)
    vista = r.plot()
    cv2.putText(vista, f"{CLASE_A_CONTAR}: {cantidad}   FPS: {fps:.1f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    cv2.imshow("YOLO en tiempo real", vista)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cv2.destroyAllWindows()
