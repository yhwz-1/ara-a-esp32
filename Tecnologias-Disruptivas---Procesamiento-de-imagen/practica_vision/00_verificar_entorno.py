"""00 - Verifica que todo lo necesario para la práctica está instalado.
Uso:  python 00_verificar_entorno.py        (o con una fuente: python 00_verificar_entorno.py http://IP:81/stream)
"""
import sys, platform

print("Python      :", platform.python_version(), "|", platform.system(), platform.machine())

try:
    import cv2
    print("OpenCV      :", cv2.__version__)
except ImportError:
    print("OpenCV      : FALTA  ->  pip install ultralytics   (instala OpenCV)")

try:
    import pytesseract
    print("Tesseract   :", pytesseract.get_tesseract_version())
    print("Idiomas OCR :", ", ".join(pytesseract.get_languages()))
except ImportError:
    print("pytesseract : FALTA  ->  pip install pytesseract")
except Exception:
    print("Tesseract   : FALTA  ->  instalar el programa Tesseract (ver README) y reiniciar la terminal")

try:
    import ultralytics
    print("Ultralytics :", ultralytics.__version__)
except ImportError:
    print("Ultralytics : FALTA  ->  pip install ultralytics")

try:
    from camara import abrir_camara, fuente_desde_argumentos
    frame = abrir_camara(fuente_desde_argumentos(sys.argv))()
    print("Cámara      : OK", frame.shape if frame is not None else "(abrió, pero sin imagen)")
except Exception as e:
    print("Cámara      : no disponible ->", e)
    print("              Puedes trabajar con las imágenes de la carpeta imagenes/ o usar el celular como cámara")
