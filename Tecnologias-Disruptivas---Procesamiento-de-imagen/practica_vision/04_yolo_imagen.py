"""
04 - Detección de objetos con YOLO sobre una imagen.
Uso:  python 04_yolo_imagen.py imagenes/calle.jpg
La primera vez descarga el modelo pre-entrenado yolo26n.pt (~5 MB, 80 clases del dataset COCO).
"""
import sys, os
import cv2
from ultralytics import YOLO

ruta = sys.argv[1] if len(sys.argv) > 1 else "imagenes/calle.jpg"
modelo = YOLO("yolo26n.pt")                     # n = nano, el más liviano

resultados = modelo(ruta, conf=0.5)             # solo detecciones con confianza >= 50 %
r = resultados[0]

for caja in r.boxes:
    clase = modelo.names[int(caja.cls)]         # nombre de la clase: person, bus, car...
    confianza = float(caja.conf)
    x1, y1, x2, y2 = map(int, caja.xyxy[0])     # esquinas de la caja (bounding box)
    print(f"{clase:12s} {confianza:.2f}  caja=({x1},{y1})-({x2},{y2})")

os.makedirs("resultados", exist_ok=True)
cv2.imwrite("resultados/04_yolo.jpg", r.plot())  # imagen con cajas y etiquetas dibujadas
print("Listo: resultados/04_yolo.jpg")
