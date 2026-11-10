"""
gestos.py - Módulo de apoyo de 08.1, 08.2 y 08.3 (no se ejecuta solo).

Los tres scripts usan estas mismas funciones: si la captura y el uso en vivo prepararan
los datos de forma distinta, el modelo fallaría sin avisar.
"""
import json, os, time, urllib.request
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")      # menos mensajes de TensorFlow en la terminal

import cv2
import joblib
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

RAIZ = Path(__file__).resolve().parent
DATOS = RAIZ / "datos"
MODELOS = RAIZ / "modelos"
CANDIDATO = MODELOS / "candidato"                       # salida del último entrenamiento
ACTUAL = MODELOS / "actual"                             # modelo aprobado
RESULTADOS = RAIZ / "resultados"

RUTA_DETECTOR = MODELOS / "hand_landmarker.task"
URL_DETECTOR = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                "hand_landmarker/float16/1/hand_landmarker.task")

VERSION_PREPROCESO = "muneca-origen-v1"                 # cámbiala si modificas normalizar()
N_PUNTOS = 21                                           # MediaPipe entrega 21 puntos por mano
COLUMNAS = [f"f{i}" for i in range(N_PUNTOS * 3)]       # x, y, z de cada punto


def mano_a_fila(mano):
    """Convierte los 21 puntos de MediaPipe en una fila de 63 números."""
    return np.array([v for p in mano for v in (p.x, p.y, p.z)], dtype=np.float32)


def normalizar(filas):
    """Hace los puntos independientes de la posición y del tamaño de la mano en la imagen."""
    puntos = np.asarray(filas, dtype=np.float32).reshape(-1, N_PUNTOS, 3)
    puntos = puntos - puntos[:, [0], :]                 # el origen pasa a ser la muñeca (punto 0)
    escala = np.linalg.norm(puntos[:, 9, :], axis=1).reshape(-1, 1, 1)  # muñeca -> base del dedo medio
    return (puntos / np.maximum(escala, 1e-6)).reshape(len(puntos), -1)


def leer_espejado(leer):
    """Único punto de lectura de la cámara: captura y uso en vivo ven el mismo espejado."""
    frame = leer()
    return cv2.flip(frame, 1) if frame is not None else None


class DetectorManos:
    def __init__(self):
        if not RUTA_DETECTOR.exists():
            print("Descargando el detector de manos (~8 MB)...")
            MODELOS.mkdir(exist_ok=True)
            temporal = RUTA_DETECTOR.with_suffix(".parcial")    # si se corta, no queda un archivo a medias
            urllib.request.urlretrieve(URL_DETECTOR, temporal)
            temporal.replace(RUTA_DETECTOR)
        # Se entrega en bytes: en Windows, MediaPipe no abre rutas con tildes o eñes
        opciones = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_buffer=RUTA_DETECTOR.read_bytes()),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
        )
        self.detector = vision.HandLandmarker.create_from_options(opciones)
        self.ultimo = -1

    def detectar(self, frame):
        """Devuelve los puntos de la mano, o None si no hay ninguna."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        # El modo VIDEO exige marcas de tiempo estrictamente crecientes
        self.ultimo = max(self.ultimo + 1, int(time.monotonic() * 1000))
        resultado = self.detector.detect_for_video(imagen, self.ultimo)
        return resultado.hand_landmarks[0] if resultado.hand_landmarks else None

    def cerrar(self):
        self.detector.close()


def dibujar_mano(frame, mano):
    alto, ancho = frame.shape[:2]
    for p in mano:
        cv2.circle(frame, (int(p.x * ancho), int(p.y * alto)), 4, (0, 255, 0), -1)


def cargar_modelo(carpeta):
    """Lee un modelo guardado por 08.2. Devuelve sus metadatos y una función X -> probabilidades."""
    if not (carpeta / "metadatos.json").exists():
        raise SystemExit(f"No hay un modelo en {carpeta}: ejecuta primero 08.2_entrenar_modelo.py")
    meta = json.loads((carpeta / "metadatos.json").read_text(encoding="utf-8"))
    if meta["version_preproceso"] != VERSION_PREPROCESO:
        raise SystemExit(f"El modelo de {carpeta} usa otro preprocesamiento: vuelve a entrenar.")
    escalador = joblib.load(carpeta / "escalador.pkl")

    if meta["tipo"] == "mlp":
        import tensorflow as tf
        red = tf.keras.models.load_model(carpeta / "modelo.keras")
        # red(x) es más rápido que red.predict(x) para un cuadro a la vez
        return meta, lambda X: red(escalador.transform(X), training=False).numpy()

    bosque = joblib.load(carpeta / "modelo.pkl")
    bosque.n_jobs = 1                                   # con un cuadro a la vez, un solo hilo es más rápido
    return meta, lambda X: bosque.predict_proba(escalador.transform(X))
