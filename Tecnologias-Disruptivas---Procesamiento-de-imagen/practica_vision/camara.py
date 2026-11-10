"""
camara.py - Abre una cámara y entrega una función leer() que devuelve un frame BGR (OpenCV) o None.

Fuentes aceptadas (el parámetro "fuente" o el argumento en la terminal):
    (nada)                      -> webcam por defecto (o la cámara de la Raspberry Pi si existe)
    0, 1, 2 ...                 -> otra webcam USB / integrada
    http://IP:81/stream         -> ESP32-CAM (ejemplo CameraWebServer)
    http://IP:8080/video        -> celular usado como cámara (app "IP Webcam" u otra similar)
    video.mp4                   -> un archivo de video (si no tienes cámara)
    picam                       -> Camera Module de la Raspberry Pi

Ejemplo desde otro script:   from camara import abrir_camara
                             leer = abrir_camara("http://192.168.1.60:81/stream")
"""
import platform
import cv2


def _picamera(ancho, alto):
    from picamera2 import Picamera2
    cam = Picamera2()
    cam.configure(cam.create_preview_configuration(
        main={"format": "RGB888", "size": (ancho, alto)}))
    cam.start()
    print("Cámara: Raspberry Pi Camera Module")
    # Con RGB888, Picamera2 entrega los bytes en orden BGR: listo para OpenCV
    return lambda: cam.capture_array()


def abrir_camara(fuente=None, ancho=640, alto=480):
    if fuente == "picam":
        return _picamera(ancho, alto)

    if fuente is None:
        try:                                    # en una Raspberry Pi con cámara CSI
            return _picamera(ancho, alto)
        except Exception:
            fuente = 0                          # en un PC: webcam por defecto

    if isinstance(fuente, str) and fuente.isdigit():
        fuente = int(fuente)

    if isinstance(fuente, int) and platform.system() == "Windows":
        cap = cv2.VideoCapture(fuente, cv2.CAP_DSHOW)   # en Windows abre más rápido
    else:
        cap = cv2.VideoCapture(fuente)

    if isinstance(fuente, int):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)         # menos retraso con cámaras por WiFi

    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir la cámara: {fuente}")
    print("Cámara:", fuente)

    def leer():
        ok, frame = cap.read()
        return frame if ok else None
    return leer


def fuente_desde_argumentos(argv, posicion=1):
    """Devuelve la fuente escrita en la terminal o None si no se indicó."""
    return argv[posicion] if len(argv) > posicion else None
