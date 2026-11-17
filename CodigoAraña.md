# CodigoAraña.md — Guía Maestra e Instrucciones para la IA del Robot Araña (ESP32 + Visión YOLO)

> **PROPÓSITO DE ESTE DOCUMENTO:**  
> Este archivo sirve como **contexto maestro e instrucciones de orientación** para cualquier modelo o asistente de Inteligencia Artificial que trabaje en el proyecto del **Robot Araña Hexápodo/Cuadrúpedo con ESP32 y Visión por Computadora (YOLO + OpenCV)**.  
> Cada vez que la IA asista al usuario en este repositorio, debe seguir las directrices, arquitecturas, protocolos de telemetría y reglas de seguridad descritas a continuación.

---

## 1. Arquitectura General del Sistema

El proyecto integra dos capas principales que cooperan en tiempo real:

```
┌────────────────────────────────────────────────────────┐
│             CEREBRO DE VISIÓN Y TELEMETRÍA             │
│        (PC / Raspberry Pi / Servidor Python)           │
│                                                        │
│  [Cámara / ESP32-CAM / IP Stream celular]              │
│                     │                                  │
│                     ▼                                  │
│      [Pipeline de Visión por Computadora]              │
│       ├─ Detector YOLO (Objetos conocidos)             │
│       └─ Detector OpenCV (Objetos no identificados     │
│           con caracterización de forma geométrica)     │
│                     │                                  │
│                     ▼                                  │
│      [Módulo de Navegación y Virtual Bumper]           │
│       └─ Evalúa si el pasillo frontal está libre       │
│                     │                                  │
│                     ▼                                  │
│        Telemetría JSON + Flag de Bloqueo               │
└─────────────────────┬──────────────────────────────────┘
                      │  (WiFi / HTTP / WebSocket / Serial)
                      ▼
┌────────────────────────────────────────────────────────┐
│             CEREBRO DE CONTROL Y ACTUACIÓN             │
│                     (ESP32 / Arduino)                  │
│                                                        │
│  [Recepción de Comandos del Humano (Joystick / Web)]   │
│                     │                                  │
│                     ▼                                  │
│  [Árbitro de Seguridad / Override Antichoque]          │
│       ¿Humano pide AVANZAR?                            │
│       ¿IA indica BLOQUEO_AVANCE == TRUE?               │
│          ├─ SÍ ➔ FRENO FORZADO (IGNORAR AVANCE)        │
│          └─ NO ➔ EJECUTAR MOVIMIENTO SOLICITADO        │
│                     │                                  │
│                     ▼                                  │
│       [Generador de Marcha y Servomotores]             │
│       (caminar.h, control.h, estabilizador.h)          │
└────────────────────────────────────────────────────────┘
```

---

## 2. Requerimientos Funcionales Esenciales

El sistema de visión e inteligencia debe cumplir obligatoriamente dos pasos fundamentales:

### PASO 1: Detección y Envío de Telemetría Ambiental (Objetos y Formas)
1. **Objetos conocidos:** Detección en tiempo real mediante **YOLO** (personas, sillas, botellas, paredes, etc.) extrayendo:
   - Clase y nivel de confianza.
   - Bounding Box normalizado `[x1, y1, x2, y2]`.
   - Posición espacial relativa respecto al robot (`izquierda`, `centro`, `derecha`) y distancia estimada (por tamaño/área relativa y posición `y` del contacto con el suelo).
2. **Objetos NO identificados / desconocidos:** 
   - Si una masa, obstáculo o perturbación no pertenece a las clases del modelo o su confianza es inferior al umbral, el sistema **no debe descartarlo**.
   - Se debe aislar el contorno y **asociarle una forma geométrica** aproximada (`rectangular/caja`, `circular/cilíndrica`, `triangular/rampa`, o `polígono_irregular`), calculada mediante aproximación poligonal (`cv2.approxPolyDP`) y relaciones de aspecto / circularidad.
3. **Envío de Telemetría:** Transmitir toda la información estructurada en formato JSON al ESP32 o a la interfaz de monitoreo.

#### Formato estándar de Telemetría JSON:
```json
{
  "timestamp": 1731872100.12,
  "fps": 24.5,
  "camino_estado": "BLOQUEADO",
  "bloqueo_avance": true,
  "distancia_minima_m": 0.35,
  "objetos": [
    {
      "id": 1,
      "tipo": "identificado",
      "clase": "chair",
      "confianza": 0.82,
      "forma": "caja_compleja",
      "posicion": "centro",
      "caja": [210, 180, 150, 220],
      "amenaza_colision": true
    },
    {
      "id": 2,
      "tipo": "no_identificado",
      "clase": "desconocido",
      "forma_asociada": "rectangular",
      "vertices": 4,
      "posicion": "centro_bajo",
      "caja": [260, 320, 110, 80],
      "amenaza_colision": true
    }
  ]
}
```

---

### PASO 2: Análisis de Camino y Prevención Activa de Colisión (Virtual Bumper)
1. **Región Crítica de Avance (ROI de Trayectoria):**
   - Se define una zona de paso frontal (trapezoide o rectángulo inferior-central de la cámara) que corresponde al espacio físico que ocupará la araña al dar sus siguientes pasos.
2. **Evaluación de Obstáculos en el Camino:**
   - Si cualquier objeto (conocido o desconocido) penetra en la zona crítica y su tamaño en pantalla indica proximidad peligrosa, se dispara de inmediato el flag:
     $$\text{bloqueo\_avance} = \text{true}$$
3. **Árbitro de Seguridad (Human-in-the-loop Override):**
   - **Regla Inquebrantable:** *Aunque el usuario humano mantenga presionado el botón o joystick de "AVANZAR" (adelante), el robot bloquea mecánicamente el avance para evitar el choque*.
   - El robot se detiene (`STOP`) o emite alerta auditiva/visual.
   - El robot **SÍ permite** maniobras de escape solicitadas por el humano: `RETROCEDER`, `GIRAR_IZQUIERDA` o `GIRAR_DERECHA`.
   - Cuando el giro o retroceso saque el obstáculo de la zona crítica, el bloqueo se libera automáticamente (`bloqueo_avance = false`).

---

## 3. Instrucciones Directas para Asistentes de IA (Guía de Comportamiento)

Al interactuar con el usuario o modificar el código de este repositorio, la IA debe seguir estas pautas:

1. **Mantener la separación de responsabilidades:**
   - La visión pesada (YOLO, OpenCV, redes neuronales) se ejecuta en la máquina anfitriona (PC, Raspberry Pi o servidor local en Python). El ESP32 no tiene suficiente RAM ni potencia para ejecutar YOLO nativo a alta tasa de cuadros; el ESP32 se encarga del control cinemático, servos y la seguridad reactiva.
2. **Robustez ante objetos desconocidos:**
   - Nunca asumas que el mundo solo contiene las 80 clases del dataset COCO. Si la araña tiene enfrente una caja de cartón sin textura, una piedra o una pared lisa, el análisis de contornos y varianza espacial debe detectarla como obstáculo geométrico.
3. **Prioridad de Seguridad Cero:**
   - El código del ESP32 debe tener el bloqueo por hardware/software en su nivel más bajo. Si el flag de bloqueo está activo, ninguna función de paso hacia adelante (`avanzar()`) debe energizar los servos en dirección frontal.
4. **Respuesta en Español:**
   - Comunicarse con el usuario en español, con explicaciones paso a paso, comentarios claros en el código y ejemplos de prueba sencillos.

---

## 4. Estructura de Archivos del Proyecto

```text
arana/
├── CodigoAraña.md                          <-- Este archivo de orientación
├── ara-a-esp32/
│   ├── AranaCode/                          <-- Firmware ESP32
│   │   ├── main.ino                        <-- Loop principal y servidor de control
│   │   ├── control.h                       <-- Árbitro de comandos y seguridad antichoque
│   │   ├── caminar.h                       <-- Cinemática de marcha (patas, servos)
│   │   └── estabilizador.h                 <-- Postura estable y reposo
│   └── Tecnologias-Disruptivas---Procesamiento-de-imagen/
│       └── practica_vision/
│           ├── vision_arana_obstaculos.py  <-- Cerebro de visión: YOLO + Formas + Virtual Bumper
│           ├── camara.py                   <-- Manejo unificado de cámara/stream
│           ├── 05_yolo_camara.py           <-- Prueba base de YOLO
│           └── esp32_actuador/             <-- Pruebas de integración ESP32
```

---

## 5. Algoritmo de Identificación de Formas Geométricas para No Identificados

Para objetos que YOLO no reconozca, el módulo de visión ejecuta:

```python
# Extracción de contornos en región de interés
gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
desenfoque = cv2.GaussianBlur(gris, (5, 5), 0)
bordes = cv2.Canny(desenfoque, 50, 150)
contornos, _ = cv2.findContours(bordes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

for c in contornos:
    area = cv2.contourArea(c)
    if area < UMBRAL_AREA_MIN:
        continue
    
    # Aproximación poligonal
    perimetro = cv2.arcLength(c, True)
    poligono = cv2.approxPolyDP(c, 0.04 * perimetro, True)
    num_vertices = len(poligono)
    x, y, w, h = cv2.boundingRect(poligono)
    aspect_ratio = float(w) / h
    
    # Clasificación de la forma
    if num_vertices == 3:
        forma = "triangulo"
    elif num_vertices == 4:
        forma = "cuadrado" if 0.9 <= aspect_ratio <= 1.1 else "rectangulo"
    elif num_vertices > 4:
        circularidad = 4 * np.pi * (area / (perimetro * perimetro))
        forma = "circulo" if circularidad > 0.75 else "poligono_irregular"
    else:
        forma = "obstaculo_irregular"
```

---

## 6. Lógica del Árbitro Antichoque (Virtual Bumper)

```cpp
// En control.h (ESP32)
void procesarComandoHumano(String comando) {
    if (comando == "ADELANTE") {
        if (bloqueoObstaculoActivo) {
            // El humano insiste en avanzar, pero hay obstáculo detectado por la IA
            detenerMarcha();
            alertaSonoraVisualColision();
            Serial.println("[SEGURIDAD ACTIVA] Bloqueo de avance: Obstáculo en camino.");
            return; // Rechazar orden de avance
        } else {
            ejecutarPasoAdelante();
        }
    } else if (comando == "ATRAS") {
        ejecutarPasoAtras(); // Siempre permitido
    } else if (comando == "GIRAR_IZQ") {
        ejecutarGiroIzquierda(); // Permitido para maniobra evasiva
    } else if (comando == "GIRAR_DER") {
        ejecutarGiroDerecha();   // Permitido para maniobra evasiva
    } else if (comando == "STOP") {
        detenerMarcha();
    }
}
```

---

## 7. Instrucciones para Ejecutar y Probar

1. **Instalar dependencias en Python:**
   ```bash
   python -m pip install ultralytics opencv-python requests numpy
   ```
2. **Iniciar la visión con detección de obstáculos:**
   ```bash
   python vision_arana_obstaculos.py --ip-esp32 192.168.1.50
   ```
3. **Cargar firmware en el ESP32:**
   - Abrir `ara-a-esp32/AranaCode` en Arduino IDE o VS Code PlatformIO.
   - Configurar red WiFi e IP.
   - Compilar y subir a la placa ESP32.
