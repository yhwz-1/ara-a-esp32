"""
03 - OCR: leer texto de una imagen con Tesseract.
Uso:  python 03_ocr.py imagenes/etiqueta.jpg        (una imagen)
      python 03_ocr.py                              (en vivo con la webcam)
      python 03_ocr.py http://IP:81/stream          (en vivo con la ESP32-CAM)
En vivo: lee el texto cada ESPERA segundos y lo muestra en la terminal.
Teclas:  f = guardar resultado en resultados/   ·   q = salir
Requiere Tesseract instalado (ver README) y  pip install pytesseract
"""
import sys, os, time
import cv2
import pytesseract

IDIOMA = "spa" if "spa" in pytesseract.get_languages() else "eng"
ESPERA = 1.0        # segundos entre lecturas en vivo
ESCALA = 1.5        # agrandar ayuda con letras pequeñas


def leer_texto(img):
    """Devuelve el texto completo y las palabras confiables como (x, y, w, h, conf) en la imagen original."""
    # Preprocesamiento: el OCR funciona mucho mejor con texto negro sobre fondo blanco
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gris = cv2.resize(gris, None, fx=ESCALA, fy=ESCALA)
    _, limpia = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 1) Texto completo
    texto = pytesseract.image_to_string(limpia, lang=IDIOMA, config="--psm 6").strip()

    # 2) Palabra por palabra, con posición y confianza
    datos = pytesseract.image_to_data(limpia, lang=IDIOMA, config="--psm 6",
                                      output_type=pytesseract.Output.DICT)
    cajas = []
    for i, palabra in enumerate(datos["text"]):
        conf = float(datos["conf"][i])
        if palabra.strip() and conf > 60:
            x, y, w, h = (int(datos[k][i] / ESCALA) for k in ("left", "top", "width", "height"))
            cajas.append((x, y, w, h, conf))
    return texto, cajas


def dibujar(img, cajas):
    salida = img.copy()
    for x, y, w, h, conf in cajas:
        cv2.rectangle(salida, (x, y), (x + w, y + h), (0, 160, 0), 2)
        cv2.putText(salida, f"{conf:.0f}", (x, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    return salida


os.makedirs("resultados", exist_ok=True)
arg = sys.argv[1] if len(sys.argv) > 1 else None
img = cv2.imread(arg) if arg and os.path.isfile(arg) else None   # ¿es una imagen?

if img is not None:                         # una sola imagen
    texto, cajas = leer_texto(img)
    print("----- TEXTO LEÍDO -----")
    print(texto)
    cv2.imwrite("resultados/03_ocr.jpg", dibujar(img, cajas))
    print("Listo: resultados/03_ocr.jpg")
    sys.exit()

# Si no es una imagen, es una cámara o un video: lectura en vivo
from camara import abrir_camara
leer = abrir_camara(arg, 1280, 720)
cajas, ultima = [], 0.0
print(f"Leyendo en vivo cada {ESPERA:.0f} s  ·  [f] guardar  ·  [q] salir")

while True:
    frame = leer()                          # se lee siempre, para no acumular cuadros atrasados
    if frame is None:
        print("La cámara no entregó imagen")
        break

    if time.time() - ultima >= ESPERA:
        texto, cajas = leer_texto(frame)
        ultima = time.time()
        print(f"----- {time.strftime('%H:%M:%S')} -----")
        print(texto if texto else "(sin texto)")

    vista = dibujar(frame, cajas)
    cv2.putText(vista, "[f] guardar  [q] salir", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.imshow("OCR en vivo", vista)

    tecla = cv2.waitKey(1) & 0xFF
    if tecla == ord("f"):
        cv2.imwrite("resultados/03_ocr.jpg", dibujar(frame, cajas))
        print("Guardado: resultados/03_ocr.jpg")
    elif tecla == ord("q"):
        break

cv2.destroyAllWindows()
