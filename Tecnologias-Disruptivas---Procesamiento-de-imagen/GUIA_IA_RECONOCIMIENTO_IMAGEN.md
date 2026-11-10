# Guía para IA: crear un proyecto de reconocimiento de imagen con ML

Instrucciones para un agente de IA que deba construir un sistema que clasifique lo que ve una cámara y actúe en vivo. El proyecto de referencia es **RoboCachipun**, donde una webcam captura la mano del jugador, MediaPipe extrae sus puntos, una red neuronal clasifica el gesto y un Arduino mueve una mano robótica.

Sigue las fases en orden. No pases a la siguiente sin cumplir la **puerta de salida** de la fase actual.

## 1. Reglas de trabajo

1. **No inventes datos ni resultados.** Nunca generes muestras sintéticas para cumplir una puerta ni declares validado algo que no se ejecutó.
2. **Lo físico lo hace una persona.** Si no puedes usar la cámara o el hardware, entrega el script y un plan de captura, y luego **detente y espera**. Marca la prueba en vivo como pendiente hasta tener sus resultados.
3. **Informa cada métrica con su forma de medirla.** "99 % de accuracy" no dice nada sin indicar el tipo de división, el número de sesiones y el número de personas.
4. **Una sola implementación del preprocesamiento.** Captura, entrenamiento y uso en vivo importan las mismas funciones; nunca las copies.
5. **No sobrescribas el modelo en uso.** Entrena en `artifacts/candidate/` y reemplaza `artifacts/current/` solo si el candidato gana con los mismos datos de prueba.
6. **Nombra bien lo que construyes.** Una red solo con capas `Dense` es un MLP, no una CNN.

## 2. Definir el proyecto

Antes de escribir código, deja por escrito lo siguiente y pregunta a la persona solo lo que no puedas deducir:

- **Clases**, incluida una clase de rechazo (`ninguno`) si el sistema puede ver algo que no es ninguna de ellas.
- **Decisión y acción:** qué se decide, cuándo y qué ocurre después. Puede ser continuo o en un instante, como al terminar una cuenta regresiva.
- **Hardware:** cámara, CPU o GPU, actuadores.
- **Criterios de aceptación.** Usa estos valores si nadie indica otros:
  - macro-F1 ≥ 0,95 con sesiones no vistas;
  - ≥ 90 % de aciertos por clase en vivo, con una persona que no aportó datos de entrenamiento;
  - latencia p95 ≤ 100 ms por cuadro.

### Elegir el enfoque

| Situación | Enfoque | Datos que guardar |
|---|---|---|
| Manos, cuerpo o rostro, con un detector de puntos existente | **Puntos clave + clasificador pequeño** (este proyecto) | Coordenadas |
| Objetos, texturas o defectos sin puntos clave | **Transfer learning** con una CNN preentrenada, como MobileNetV3 | Imágenes |
| Hay que localizar varios objetos en el cuadro | **Detector de objetos**, como YOLO | Imágenes con cajas |
| El gesto depende del movimiento | **Secuencias de puntos clave** (LSTM o 1D-CNN) | Series temporales |

Prefiere puntos clave cuando apliquen: requieren pocos datos, entrenan en segundos en CPU y dependen menos del fondo y la iluminación.

El resto de esta guía desarrolla ese enfoque. En los demás, sustituye `features.py` y el modelo, y aplica igual las reglas sobre sesiones, artefactos y uso en vivo.

**Puerta de salida:** clases, acción, criterios y enfoque escritos en el README.

## 3. Preparar el entorno

```text
proyecto/
├── README.md
├── requirements.txt       # versiones exactas
├── data/dataset.csv
├── models/hand_landmarker.task
├── artifacts/
│   ├── candidate/         # salida del último entrenamiento
│   └── current/           # modelo aprobado que usa live.py
└── src/
    ├── features.py        # preprocesamiento único
    ├── vision.py          # cámara y detector
    ├── collect.py
    ├── train.py
    └── live.py
```

Combinación usada en RoboCachipun, con **Python 3.11**:

```text
numpy==2.4.4
pandas==3.0.2
scikit-learn==1.8.0
tensorflow==2.21.0
opencv-python==4.13.0.92
mediapipe==0.10.35
joblib==1.5.3
pyserial==3.5        # solo con Arduino
```

- Descarga el detector de manos desde `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`.
- Construye las rutas desde `__file__`, no desde el directorio actual.
- Excluye el entorno virtual de git y comprueba que no quede ya rastreado.
- No uses Docker en Windows si necesitas la webcam o puertos COM: Docker Desktop corre en una VM sin acceso directo a ellos.

Crea primero los dos módulos compartidos:

```python
# src/features.py
import numpy as np

FEATURE_VERSION = "wrist-origin-v1"
N_LANDMARKS = 21
N_RAW = N_LANDMARKS * 3
RAW_COLUMNS = [f"f{i}" for i in range(N_RAW)]


def landmarks_to_raw(hand):
    return np.array(
        [value for point in hand for value in (point.x, point.y, point.z)],
        dtype=np.float32,
    )


def normalize_landmarks(raw):
    """Vuelve los puntos independientes de la posición y el tamaño de la mano."""
    points = np.asarray(raw, dtype=np.float32).reshape(-1, N_LANDMARKS, 3)
    points = points - points[:, [0], :]  # origen en la muñeca
    scale = np.linalg.norm(points[:, 9, :], axis=1).reshape(-1, 1, 1)
    return (points / np.maximum(scale, 1e-6)).reshape(len(points), -1)
```

```python
# src/vision.py
import time

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


def read_frame(cap):
    """Único punto de lectura de la cámara: todo el sistema ve el mismo espejado."""
    ok, frame = cap.read()
    return cv2.flip(frame, 1) if ok else None


class HandTracker:

    def __init__(self, model_path):
        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
        )
        self.detector = vision.HandLandmarker.create_from_options(options)
        self.last_timestamp = -1

    def detect(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        # El modo VIDEO exige marcas de tiempo estrictamente crecientes
        timestamp = max(self.last_timestamp + 1, int(time.monotonic() * 1000))
        self.last_timestamp = timestamp
        result = self.detector.detect_for_video(image, timestamp)
        return result.hand_landmarks[0] if result.hand_landmarks else None


def draw_hand(frame, hand):
    height, width = frame.shape[:2]
    for point in hand:
        cv2.circle(frame, (int(point.x * width), int(point.y * height)), 4, (0, 255, 0), -1)
```

**Puerta de salida:** el detector dibuja los puntos sobre la cámara en vivo, confirmado por la persona.

## 4. Recolectar datos

El modelo solo será fiable en condiciones parecidas a las que vio. La diversidad importa más que la cantidad de filas: mil cuadros seguidos de una misma pose casi no aportan información.

### Plan de captura

Entrega este plan a la persona que grabará:

- **Personas:** al menos 3, y más si el sistema será usado por público general.
- **Sesiones:** al menos 6, con al menos una persona reservada solo para prueba. Una **sesión** es una misma combinación de persona, lugar y luz, y debe **contener todas las clases**.
- **Variación dentro de cada sesión:** mano izquierda y derecha, distancia, posición en el cuadro, rotación y fondo.
- **Volumen orientativo:** 300 a 500 muestras por clase y sesión.
- **Clase `ninguno`:** poses intermedias y otros gestos.

### Formato

Guarda **coordenadas crudas** e identificadores en un CSV con encabezado: `session_id,subject_id,label,f0…f62`. Así podrás cambiar la normalización sin volver a grabar, y dividir los datos correctamente.

```python
# src/collect.py
"""Uso: python src/collect.py --session s01 --subject p01 --labels rock paper scissors ninguno

Teclas: 1-9 eligen clase y empiezan a grabar, 0 pausa, ESC sale.
"""
import argparse
import csv
import time
from pathlib import Path

import cv2

from features import RAW_COLUMNS, landmarks_to_raw
from vision import HandTracker, draw_hand, read_frame

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "dataset.csv"
MAX_FPS = 10  # los cuadros seguidos son casi idénticos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--labels", nargs="+", required=True)
    args = parser.parse_args()

    tracker = HandTracker(ROOT / "models" / "hand_landmarker.task")
    cap = cv2.VideoCapture(0)
    OUTPUT.parent.mkdir(exist_ok=True)
    is_new = not OUTPUT.exists()
    label = None
    last_saved = 0.0
    counts = dict.fromkeys(args.labels, 0)

    with OUTPUT.open("a", newline="") as file:
        writer = csv.writer(file)
        if is_new:
            writer.writerow(["session_id", "subject_id", "label", *RAW_COLUMNS])

        while True:
            frame = read_frame(cap)
            if frame is None:
                break

            hand = tracker.detect(frame)
            now = time.monotonic()
            if hand:
                draw_hand(frame, hand)
                if label and now - last_saved >= 1 / MAX_FPS:
                    writer.writerow([args.session, args.subject, label, *landmarks_to_raw(hand).tolist()])
                    counts[label] += 1
                    last_saved = now

            cv2.putText(frame, f"{label or 'PAUSA'} | {counts}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imshow("Captura", frame)

            key = cv2.waitKey(1)
            if key == 27:
                break
            if key == ord("0"):
                label = None
            elif ord("1") <= key < ord("1") + len(args.labels):
                label = args.labels[key - ord("1")]

    cap.release()
    cv2.destroyAllWindows()
    print(counts)


if __name__ == "__main__":
    main()
```

### Validar el dataset

Antes de entrenar, comprueba e informa:

- que no haya nulos ni columnas de más o de menos;
- que no haya etiquetas mal escritas;
- las muestras por clase, sesión y persona;
- el porcentaje de duplicados exactos;
- que toda sesión contenga todas las clases.

Agrega al CSV solo tras revisar lo grabado. Una sesión con una etiqueta equivocada se elimina completa por su `session_id`.

**Puerta de salida:** plan cumplido, validación sin errores, resumen entregado a la persona.

## 5. Entrenar

Reglas no negociables:

1. **Divide por sesión o persona, nunca por fila.** Los cuadros consecutivos son casi iguales, así que una división aleatoria pone el mismo momento en entrenamiento y prueba e infla el resultado.
2. **Ajusta el `StandardScaler` solo con entrenamiento.**
3. **Deriva el número de clases de los datos**; no lo dejes fijo en el código.
4. **Empieza con una línea base.** Entrena también un `RandomForestClassifier`. Si el MLP no lo supera con claridad, usa el más simple.
5. **Guarda juntos todos los artefactos**, con los metadatos necesarios para reproducirlos.

```python
# src/train.py
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import tensorflow as tf
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler

from features import FEATURE_VERSION, RAW_COLUMNS, normalize_landmarks

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "candidate"
SEED = 42


def split_by_group(indices, groups, test_size):
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=SEED)
    train, test = next(splitter.split(indices, groups=groups[indices]))
    return indices[train], indices[test]


def main():
    tf.keras.utils.set_random_seed(SEED)
    df = pd.read_csv(ROOT / "data" / "dataset.csv")
    X = normalize_landmarks(df[RAW_COLUMNS].to_numpy())
    classes = sorted(df["label"].unique().tolist())
    y = np.searchsorted(classes, df["label"].to_numpy())
    groups = df["session_id"].to_numpy()

    train, test = split_by_group(np.arange(len(df)), groups, 0.2)
    train, val = split_by_group(train, groups, 0.2)
    for name, part in (("train", train), ("val", val), ("test", test)):
        if len(np.unique(y[part])) != len(classes):
            raise SystemExit(f"Faltan clases en {name}: graba más sesiones completas.")

    scaler = StandardScaler().fit(X[train])
    X_train, X_val, X_test = (scaler.transform(X[part]) for part in (train, val, test))

    model = tf.keras.Sequential([
        tf.keras.layers.Input((X.shape[1],)),
        tf.keras.layers.Dense(128, activation="relu"),
        tf.keras.layers.Dense(64, activation="relu"),
        tf.keras.layers.Dense(32, activation="relu"),
        tf.keras.layers.Dense(len(classes), activation="softmax"),
    ])
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    model.fit(
        X_train, y[train],
        validation_data=(X_val, y[val]),
        epochs=100,
        batch_size=32,
        verbose=2,
        callbacks=[tf.keras.callbacks.EarlyStopping(patience=8, restore_best_weights=True)],
    )

    predicted = model.predict(X_test, verbose=0).argmax(axis=1)
    macro_f1 = f1_score(y[test], predicted, average="macro")
    print(classification_report(y[test], predicted, target_names=classes))
    print(confusion_matrix(y[test], predicted))

    OUTPUT.mkdir(parents=True, exist_ok=True)
    model.save(OUTPUT / "model.keras")
    joblib.dump(scaler, OUTPUT / "scaler.pkl")
    metadata = {
        "classes": classes,
        "feature_version": FEATURE_VERSION,
        "n_rows": len(df),
        "test_sessions": sorted(set(groups[test].tolist())),
        "test_macro_f1": round(float(macro_f1), 4),
        "versions": {"tensorflow": tf.__version__, "sklearn": sklearn.__version__},
    }
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(metadata)


if __name__ == "__main__":
    main()
```

### Evaluar

- Reporta macro-F1 y la matriz de confusión con sesiones no vistas. Si el proyecto va a ser usado por personas nuevas, evalúa también dejando fuera a una persona completa.
- Si la nota cae mucho respecto de una división aleatoria, faltan datos variados. Graba más sesiones antes de complicar el modelo.
- Compara candidato y modelo actual **con los mismos datos de prueba**.
- Toca el conjunto de prueba al final. Ajusta los hiperparámetros con validación.
- Los `.pkl` y `.keras` dependen de las versiones instaladas. Si cambian, reentrena y actualiza `requirements.txt`. Carga `.pkl` solo de fuentes propias, porque pueden ejecutar código.

**Puerta de salida:** el candidato cumple el criterio de la sección 2 con sesiones no vistas, supera a la línea base o la reemplaza, y se copia a `artifacts/current/`.

## 6. Usar el modelo en vivo

Un cuadro aislado no es confiable: la mano puede estar en movimiento. Tampoco basta la confianza del softmax, que puede ser alta en predicciones erróneas. Por eso:

- **Decide con una ventana de cuadros**, por mayoría y con confianza mínima.
- **Permite no decidir.** "Sin mano" e "indeciso" son resultados válidos, no se fuerzan a una clase.
- **Comprueba al arrancar** que `feature_version` coincida con `features.py`. Si no coincide, termina con un error claro.
- **Usa `model(x, training=False)`** por cuadro: `model.predict` es más lento para muestras individuales.
- **Mantén la acción fuera de la inferencia:** el clasificador devuelve una etiqueta y otro componente decide.

```python
# src/live.py
import json
import time
from collections import Counter, deque
from pathlib import Path

import cv2
import joblib
import numpy as np
import tensorflow as tf

from features import FEATURE_VERSION, landmarks_to_raw, normalize_landmarks
from vision import HandTracker, draw_hand, read_frame

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "current"


class LiveClassifier:

    def __init__(self, min_confidence=0.8, window=7, min_votes=5):
        metadata = json.loads((ARTIFACTS / "metadata.json").read_text())
        if metadata["feature_version"] != FEATURE_VERSION:
            raise SystemExit("El modelo y features.py usan preprocesamientos distintos: reentrena.")
        self.classes = metadata["classes"]
        self.model = tf.keras.models.load_model(ARTIFACTS / "model.keras")
        self.scaler = joblib.load(ARTIFACTS / "scaler.pkl")
        self.min_confidence = min_confidence
        self.min_votes = min_votes
        self.votes = deque(maxlen=window)

    def update(self, hand):
        """Devuelve una clase estable, o None mientras no haya una decisión segura."""
        if hand is None:
            self.votes.clear()
            return None
        features = self.scaler.transform(normalize_landmarks(landmarks_to_raw(hand)))
        probabilities = self.model(features, training=False).numpy()[0]
        best = int(np.argmax(probabilities))
        confident = probabilities[best] >= self.min_confidence
        self.votes.append(self.classes[best] if confident else None)
        label, count = Counter(self.votes).most_common(1)[0]
        return label if label is not None and count >= self.min_votes else None


def main():
    tracker = HandTracker(ROOT / "models" / "hand_landmarker.task")
    classifier = LiveClassifier()
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise SystemExit("No se pudo abrir la cámara.")
    latencies = deque(maxlen=200)

    while True:
        frame = read_frame(cap)
        if frame is None:
            break

        start = time.perf_counter()
        hand = tracker.detect(frame)
        label = classifier.update(hand)
        latencies.append((time.perf_counter() - start) * 1000)

        if hand:
            draw_hand(frame, hand)
        p95 = np.percentile(latencies, 95)
        cv2.putText(frame, f"{label or '-'} | p95 {p95:.0f} ms", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("En vivo", frame)
        if cv2.waitKey(1) == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
```

La primera inferencia suele tardar más: mide la latencia ya en régimen. Ajusta `min_confidence`, `window` y `min_votes` con pruebas reales, porque una ventana mayor es más estable pero responde más tarde.

### Integrar con la aplicación

- **Decisión en un instante:** sigue leyendo cuadros durante la ventana previa y toma el último valor estable. Si no hay ninguno, informa "no detectado"; no adivines.
- **Máquina de estados:** separa los estados (por ejemplo `MENU → COUNTDOWN → RESULT → ASK_CONTINUE`) y haz que cada evento produzca **una sola** acción.
- **Hardware opcional:** el programa debe funcionar sin el actuador.
- **Arduino por serie:** detecta el puerto con `serial.tools.list_ports`, espera 2 s tras abrirlo porque la placa se reinicia, y define el protocolo en un solo lugar.
- **Cierre limpio:** libera cámara, puerto y ventanas también si ocurre un error.

### Prueba en vivo

Cada prueba la hace una persona frente a la cámara. Pídele que:

1. Haga al menos 30 intentos por clase, incluyendo a alguien que no aportó datos y otra iluminación.
2. Registre en una tabla la clase esperada, la clase obtenida y si el sistema no decidió.
3. Muestre gestos ajenos para confirmar que `ninguno` o la falta de decisión funcionan.
4. Pruebe sin mano y sin el actuador conectado.

Si una condición falla, graba una sesión nueva en esa condición y vuelve a la fase 5. No ajustes el modelo a los datos de prueba.

**Puerta de salida:** criterios de la sección 2 cumplidos, tabla de resultados guardada y README con los comandos para recolectar, entrenar y ejecutar.

## 7. Errores ya cometidos en RoboCachipun

Son hallazgos sobre el código y los datos del proyecto, medidos el 2026-11-02. No los repitas.

| Hallazgo | Evidencia | Qué hacer |
|---|---|---|
| Artefactos desactualizados sin aviso | `scaler.pkl` se ajustó con 10.758 filas y el dataset tiene 20.797. `gesture_model.keras` acierta **58,5 %** sobre el CSV actual. La misma arquitectura reentrenada logra 99,5 % con división aleatoria | Guardar metadatos y evaluar el modelo en uso antes de confiar en él |
| Confianza engañosa | El modelo con 58,5 % de aciertos promedia 97 % de confianza | No usar el softmax como único filtro |
| División aleatoria por filas | Random Forest con coordenadas crudas: 99,1 % en aleatorio y 94,4 % al separar bloques de 300 cuadros | Dividir por sesión. El CSV no registra sesiones, así que los bloques solo aproximan el efecto |
| Coordenadas sin normalizar | Con bloques separados: 94,4 % crudo y 97,4 % normalizado | Normalizar respecto de la muñeca y del tamaño de la mano |
| Espejado inconsistente | `collect_dataset.py` y el bucle principal aplican `cv2.flip`, pero `resolve_round` en `main.py` clasifica sin él | Leer siempre la cámara mediante una sola función |
| Doble lectura y comando duplicado | `resolve_round` clasifica dos veces y envía dos veces el comando al robot | Un evento, una acción |
| `flip` antes de comprobar `ret` | `main.py` y `collect_dataset.py` fallan si la cámara no entrega cuadro | Validar la lectura primero |
| Decisión con un solo cuadro | `resolve_round` usa un único cuadro, justo al terminar la cuenta | Usar una ventana de cuadros |
| Sin clase de rechazo ni identificadores | Cualquier mano se fuerza a piedra, papel o tijeras, y no se puede dividir por sesión | Agregar `ninguno`, `session_id` y `subject_id` |
| Número de clases fijo y etiqueta editada a mano | `Dense(3)` y `LABEL = "rock"` en el código | Derivar las clases de los datos y elegirlas por argumentos |
| Rutas e importaciones frágiles | `collect_dataset.py` importa `Codigo.vision.detector`, mientras los demás usan `vision.detector`, y las rutas dependen del directorio actual | Rutas desde `__file__` e importaciones uniformes |

## 8. Lista final

Antes de declarar el proyecto terminado, confirma:

- [ ] Clases, acción y criterios de aceptación documentados.
- [ ] Dataset con `session_id` y `subject_id`, y validación sin errores.
- [ ] Métricas obtenidas con sesiones no vistas, indicando cómo se midieron.
- [ ] Modelo, scaler y metadatos generados juntos, con versiones fijadas.
- [ ] Captura, entrenamiento y uso en vivo comparten el mismo preprocesamiento.
- [ ] La aplicación maneja la falta de mano, de cámara y de actuador.
- [ ] Prueba en vivo hecha por una persona, con resultados guardados.
- [ ] README con los comandos para repetir todo el proceso.
- [ ] Lo que no se pudo verificar está informado de forma explícita.
