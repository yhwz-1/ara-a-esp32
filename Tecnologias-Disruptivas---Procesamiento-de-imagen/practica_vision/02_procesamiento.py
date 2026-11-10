"""
02 - Procesamiento clásico de imágenes con OpenCV (sin IA).
Uso:  python 02_procesamiento.py imagenes/etiqueta.jpg
Genera resultados/02_procesamiento.jpg con los 4 pasos lado a lado.
"""
import sys, os
import cv2
import numpy as np

ruta = sys.argv[1] if len(sys.argv) > 1 else "imagenes/etiqueta.jpg"
img = cv2.imread(ruta)                                  # la imagen es una matriz alto x ancho x 3 (BGR)
print("Tamaño:", img.shape, "| píxel (0,0) en BGR:", img[0, 0])

gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)            # 1) a escala de grises (1 canal)
suave = cv2.GaussianBlur(gris, (5, 5), 0)               # 2) quitar ruido
binaria = cv2.adaptiveThreshold(suave, 255,             # 3) umbral adaptativo: blanco/negro
           cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15)  #    tolera luz dispareja
bordes = cv2.Canny(suave, 50, 150)                      # 4) detección de bordes

# 5) Unir letras vecinas (dilatación horizontal) y buscar contornos = zonas con texto
unidas = cv2.dilate(binaria, np.ones((3, 15), np.uint8))
contornos, _ = cv2.findContours(unidas, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
grandes = [c for c in contornos if 500 < cv2.contourArea(c) < 0.5 * gris.size]
print("Zonas de texto encontradas:", len(grandes))
salida = img.copy()
for c in grandes:
    x, y, w, h = cv2.boundingRect(c)
    cv2.rectangle(salida, (x, y), (x + w, y + h), (0, 0, 255), 2)

# Mosaico 2x2 para comparar
def a_color(m):
    return cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
fila1 = np.hstack([a_color(gris), a_color(binaria)])
fila2 = np.hstack([a_color(bordes), salida])
os.makedirs("resultados", exist_ok=True)
cv2.imwrite("resultados/02_procesamiento.jpg", np.vstack([fila1, fila2]))
print("Listo: resultados/02_procesamiento.jpg")
