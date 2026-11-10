# Práctica: procesamiento de imágenes, OCR y YOLO — Tecnologías Disruptivas (UNAB)

Todo funciona en **tu propio computador** con una **webcam** (integrada, USB o el celular como cámara).
Más adelante, la misma carpeta sirve con la **ESP32-CAM** como cámara.

## 1. Instalación (una sola vez)

Necesitas **Python 3.10 o superior**.

```bash
python -m venv vision
vision\Scripts\activate          # Windows
# source vision/bin/activate     # macOS / Linux
pip install ultralytics pytesseract requests
```
Cada vez que abras una terminal nueva, vuelve a activar el entorno (`vision\Scripts\activate`).

**Tesseract** (para el OCR) se instala aparte:
- **Windows:** instalador de UB Mannheim (github.com/UB-Mannheim/tesseract/wiki). En "Additional language data" marca *Spanish*. Agrega `C:\Program Files\Tesseract-OCR` al PATH y reinicia la terminal (ver abajo).
- **macOS:** `brew install tesseract tesseract-lang`
- **Linux:** `sudo apt install tesseract-ocr tesseract-ocr-spa`

**Agregar Tesseract al PATH en Windows desde la terminal**

Permanente (recomendado), en PowerShell y sin permisos de administrador:
```powershell
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";C:\Program Files\Tesseract-OCR", "User")
```
Luego **cierra y vuelve a abrir la terminal** (y VS Code, si usas su terminal). No uses `setx PATH "%PATH%;..."`: puede cortar el PATH si supera 1024 caracteres.

Solo para la terminal actual (se pierde al cerrarla):
```powershell
$env:Path += ";C:\Program Files\Tesseract-OCR"            # PowerShell
```
```bash
export PATH="$PATH:/c/Program Files/Tesseract-OCR"         # Git Bash / MSYS2
```

Comprueba que funciona:
```powershell
tesseract --version
tesseract --list-langs     # debe aparecer "spa"
```

Alternativa sin tocar el PATH: en `03_ocr.py`, después de `import pytesseract`, agrega
```python
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Comprueba todo con:
```bash
python 00_verificar_entorno.py
```

## 2. ¿Qué cámara uso?

Todos los scripts que usan cámara aceptan la fuente como argumento:

| Cámara | Cómo se indica |
|---|---|
| Webcam integrada o USB | nada (`python 05_yolo_camara.py`) o un número: `1`, `2` |
| Celular como cámara (app tipo "IP Webcam") | `http://IP_DEL_CELULAR:8080/video` |
| ESP32-CAM (ejemplo CameraWebServer) | `http://IP_DE_LA_ESP32CAM:81/stream` |
| Un video grabado | `mi_video.mp4` |
| Camera Module de Raspberry Pi | `picam` |

El celular y el computador (o la ESP32-CAM) deben estar en la **misma red WiFi**.

## 3. Archivos y orden sugerido (≈10 min cada uno)

| Archivo | Qué hace | Ejemplo |
|---|---|---|
| `00_verificar_entorno.py` | Revisa Python, OpenCV, Tesseract, Ultralytics y la cámara | `python 00_verificar_entorno.py` |
| `01_ver_camara.py` | Muestra la cámara en vivo; tecla **f** guarda una foto en `imagenes/` | `python 01_ver_camara.py` |
| `02_procesamiento.py` | Grises, umbral, bordes y contornos (OpenCV, sin IA) | `python 02_procesamiento.py imagenes/etiqueta.jpg` |
| `03_ocr.py` | Lee texto con Tesseract (imagen o foto de la cámara) | `python 03_ocr.py imagenes/etiqueta.jpg` |
| `04_yolo_imagen.py` | Detecta objetos en una imagen con YOLO26n | `python 04_yolo_imagen.py imagenes/calle.jpg` |
| `05_yolo_camara.py` | YOLO en tiempo real, cuenta objetos y muestra FPS | `python 05_yolo_camara.py` |
| `06_exportar_ncnn.py` | Optimiza el modelo (sobre todo para Raspberry Pi) | `python 06_exportar_ncnn.py` |
| `07_yolo_esp32.py` | Si detecta un objeto, envía una orden HTTP al ESP32 | `python 07_yolo_esp32.py` |
| `08.1_recolectar_datos.py` | Graba los puntos de tu mano para cada clase (sección 6) | `python 08.1_recolectar_datos.py --sesion s01 --persona p01 --clases piedra papel tijera ninguno` |
| `08.2_entrenar_modelo.py` | Valida los datos, entrena y evalúa el clasificador | `python 08.2_entrenar_modelo.py` |
| `08.3_probar_modelo.py` | Prueba el modelo en vivo y registra los aciertos | `python 08.3_probar_modelo.py --persona p09` |
| `esp32_actuador/esp32_actuador.ino` | Servidor web en el ESP32 que enciende/apaga un LED | Arduino IDE |
| `yolo_api.py` | Extensión: YOLO como API con FastAPI | `uvicorn yolo_api:app --port 8000` |
| `gestos.py` | Módulo de apoyo de 08.1, 08.2 y 08.3 (no se ejecuta solo) | — |
| `camara.py` | Módulo de apoyo que abre cualquier cámara (no se ejecuta solo) | — |

Los resultados quedan en la carpeta `resultados/`. Para la API: `pip install fastapi uvicorn python-multipart`.

## 4. ESP32-CAM (cuando llegue)

1. Arduino IDE → *Archivo → Ejemplos → ESP32 → Camera → CameraWebServer*.
2. Descomenta el modelo de tu placa (normalmente `CAMERA_MODEL_AI_THINKER`) y escribe tu red WiFi.
3. Carga el programa y copia la IP del Monitor Serie (115200 baudios).
4. Pruébala en el navegador (`http://IP`) y luego en Python: `python 05_yolo_camara.py http://IP:81/stream`

La ESP32-CAM **solo envía la imagen**: YOLO se ejecuta en el computador o en la Raspberry Pi.

## 5. Problemas frecuentes
- **`TesseractNotFoundError`**: Tesseract no está instalado o no está en el PATH (reinicia la terminal).
- **La webcam no abre**: ciérrala en otras apps (Teams, Zoom, navegador) o prueba con `1` en vez de `0`.
- **Muy lento**: baja `TAMANO` a 320 en `05_yolo_camara.py`; en la Pi usa `06_exportar_ncnn.py`.
- **La cámara por WiFi se congela**: acerca el equipo al router y baja la resolución en la página de la ESP32-CAM.
- **`pip` dice "externally-managed-environment"**: falta activar el entorno virtual.

## 6. Entrena tu propio modelo (08.1, 08.2 y 08.3)

YOLO reconoce las clases con las que otros lo entrenaron. Aquí entrenas un modelo para reconocer **tus** clases: gestos de la mano, como piedra, papel o tijera. MediaPipe encuentra 21 puntos de la mano y una red pequeña (un MLP) aprende a clasificarlos. Por eso bastan pocos datos y se entrena en alrededor de un minuto, sin GPU.

**Instalación:** con el entorno activo, ejecuta `python -m pip install -r requirements.txt`. Ocupa cerca de 1,7 GB más en disco (TensorFlow es lo más pesado). Usa Python 3.11 a 3.13. El detector de manos (~8 MB) se descarga solo la primera vez.

**Paso 1: recolectar.** Graba una sesión por cada combinación de persona, lugar y luz. Cada sesión debe incluir todas las clases.
```bash
python 08.1_recolectar_datos.py --sesion s01 --persona p01 --clases piedra papel tijera ninguno
```
Con las teclas **1-9** eliges la clase y empiezas a grabar, con **0** pausas y con **q** sales. La meta es de 300 a 500 muestras por clase y sesión, en **al menos 6 sesiones de 3 personas**. Importa más la variedad que la cantidad: cambia de mano, distancia, posición y rotación. En `ninguno` muestra poses intermedias y otros gestos.

Si te equivocas, borra `datos/sesion_s01.csv` y graba de nuevo.

**Paso 2: entrenar.**
```bash
python 08.2_entrenar_modelo.py --solo-validar    # revisa los datos
python 08.2_entrenar_modelo.py                   # entrena
```
Entrena un MLP y un Random Forest (la línea base), y se queda con el MLP solo si es claramente mejor. La nota se mide con **sesiones que el modelo nunca vio**. Si mezclaras las filas al azar, los cuadros casi iguales quedarían en entrenamiento y en prueba, y la nota saldría inflada.

El resultado queda en `modelos/candidato/` y pasa a `modelos/actual/` solo si alcanza macro-F1 ≥ 0,95 y supera al modelo actual con las mismas sesiones de prueba. Para empezar un proyecto con otras clases, borra `datos/` y `modelos/actual/`.

**Paso 3: probar en vivo.**
```bash
python 08.3_probar_modelo.py --persona p09       # --candidato prueba un modelo aún sin aprobar
```
Elige con **1-9** la clase que vas a mostrar y registra cada intento con **espacio**. Haz al menos 30 intentos por clase, con alguien que no aportó datos y con otra luz. El sistema decide con varios cuadros seguidos y puede responder `indeciso`: es mejor no decidir que adivinar. Los intentos quedan en `resultados/08_prueba_en_vivo.csv`.

**El modelo cumple si:**
- alcanza macro-F1 ≥ 0,95 con sesiones no vistas;
- acierta ≥ 90 % por clase en vivo, con una persona que no aportó datos;
- tiene una latencia p95 ≤ 100 ms por cuadro.

¿Falla en alguna condición? Graba una sesión nueva en esa condición y vuelve a entrenar, antes de complicar el modelo.

La guía completa, con la metodología y los errores que conviene evitar, está en [`GUIA_IA_RECONOCIMIENTO_IMAGEN.md`](../GUIA_IA_RECONOCIMIENTO_IMAGEN.md).
