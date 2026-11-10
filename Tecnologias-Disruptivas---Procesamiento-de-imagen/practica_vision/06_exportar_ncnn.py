"""
06 - Exporta el modelo a formato NCNN, optimizado para procesadores ARM (Raspberry Pi).
También funciona en un PC, pero donde más se nota la diferencia es en la Raspberry Pi.
Uso:  python 06_exportar_ncnn.py      (se ejecuta una sola vez; crea la carpeta yolo26n_ncnn_model)
"""
from ultralytics import YOLO

YOLO("yolo26n.pt").export(format="ncnn", imgsz=320)
print("Listo. Ahora 05_yolo_camara.py y 07_yolo_esp32.py usarán yolo26n_ncnn_model automáticamente.")
