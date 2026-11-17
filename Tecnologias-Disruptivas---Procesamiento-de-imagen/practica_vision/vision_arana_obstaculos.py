"""
vision_arana_obstaculos.py - Sistema de Visión e Inteligencia para el Robot Araña ESP32

Cumple con los 2 pasos clave:
1. DETECTAR Y MANDAR INFORMACIÓN:
   - Objetos conocidos detectados con YOLO (clase, confianza, coordenadas, posición).
   - Objetos NO identificados detectados por análisis de contornos y clasificados
     con una forma geométrica asociada (caja/rectángulo, cilindro/círculo, triángulo, polígono irregular).
   - Empaqueta y transmite la telemetría en formato JSON hacia el ESP32 o consola.
2. ANÁLISIS DE CAMINO Y PARACHOQUES VIRTUAL (PREVENCIÓN DE CHOQUES):
   - Monitorea la zona crítica de avance frontal (pasillo de los próximos pasos).
   - Si detecta cualquier estructura u obstáculo que impida el paso, activa el flag
     de bloqueo de colisión y envía la orden de veto al ESP32 para anular el avance humano.

Uso:
    python vision_arana_obstaculos.py                     # webcam por defecto
    python vision_arana_obstaculos.py --esp32 192.168.1.50 # IP del ESP32
    python vision_arana_obstaculos.py http://IP:81/stream # ESP32-CAM
"""

import sys
import os
import time
import json
import argparse
import numpy as np
import cv2
import requests
from ultralytics import YOLO

# Módulo de cámara unificado del proyecto
try:
    from camara import abrir_camara, fuente_desde_argumentos
except ImportError:
    # Fallback si se ejecuta de forma independiente
    def abrir_camara(fuente=0):
        cap = cv2.VideoCapture(int(fuente) if str(fuente).isdigit() else fuente)
        return lambda: (cap.read()[1] if cap.isOpened() else None)
    def fuente_desde_argumentos(argv):
        return argv[1] if len(argv) > 1 else 0


class DetectorObstaculosArana:
    def __init__(self, ip_esp32=None, modelo_yolo="yolo26n.pt", conf_min=0.45):
        self.ip_esp32 = ip_esp32
        self.conf_min = conf_min
        
        # Cargar modelo YOLO
        ruta_modelo = "yolo26n_ncnn_model" if os.path.isdir("yolo26n_ncnn_model") else modelo_yolo
        print(f"[*] Cargando modelo YOLO ({ruta_modelo})...")
        self.modelo = YOLO(ruta_modelo)
        
        # Estado de seguridad
        self.bloqueo_anterior = None
        self.bloqueo_activo = False
        self.ultimo_envio_telemetria = 0
        self.intervalo_telemetria = 0.2  # 5 veces por segundo
        
    def clasificar_forma_geometrica(self, contorno):
        """Analiza un contorno y devuelve su forma geométrica aproximada."""
        perimetro = cv2.arcLength(contorno, True)
        if perimetro == 0:
            return "indefinido", 0
            
        poligono = cv2.approxPolyDP(contorno, 0.04 * perimetro, True)
        vertices = len(poligono)
        area = cv2.contourArea(contorno)
        x, y, w, h = cv2.boundingRect(poligono)
        aspect_ratio = float(w) / max(h, 1)

        if vertices == 3:
            forma = "triangulo"
        elif vertices == 4:
            forma = "cuadrado" if 0.88 <= aspect_ratio <= 1.12 else "rectangulo"
        elif vertices > 4:
            # Calcular índice de circularidad: 4 * pi * Area / Perimetro^2
            circularidad = 4 * np.pi * (area / (perimetro * perimetro))
            if circularidad > 0.72:
                forma = "circulo"
            else:
                forma = f"poligono_{vertices}_lados"
        else:
            forma = "obstaculo_irregular"
            
        return forma, vertices

    def detectar_objetos_no_identificados(self, frame, cajas_yolo, roi_piso):
        """
        Detecta objetos que YOLO no reconoció mediante segmentación de bordes y contornos.
        Ignora las regiones ya cubiertas por YOLO para evitar duplicados.
        """
        alto, ancho = frame.shape[:2]
        
        # Crear máscara binaria de las cajas YOLO existentes
        mascara_yolo = np.zeros((alto, ancho), dtype=np.uint8)
        for (x1, y1, x2, y2) in cajas_yolo:
            cv2.rectangle(mascara_yolo, (x1, y1), (x2, y2), 255, -1)
            
        # Filtrado y detección de bordes en el frame
        gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        suavizado = cv2.GaussianBlur(gris, (7, 7), 0)
        
        # Binarización adaptativa para capturar obstáculos incluso con baja luz
        bordes = cv2.Canny(suavizado, 40, 120)
        
        # Eliminar las zonas que ya corresponden a objetos reconocidos por YOLO
        bordes_desconocidos = cv2.bitwise_and(bordes, bordes, mask=cv2.bitwise_not(mascara_yolo))
        
        # Dilatar para unir contornos rotos
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilatado = cv2.dilate(bordes_desconocidos, kernel, iterations=2)
        
        contornos, _ = cv2.findContours(dilatado, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        desconocidos = []
        area_minima = (ancho * alto) * 0.003  # Al menos 0.3% del frame para ignorar ruido
        
        for c in contornos:
            area = cv2.contourArea(c)
            if area < area_minima:
                continue
                
            x, y, w, h = cv2.boundingRect(c)
            
            # Solo considerar objetos cuyo punto inferior esté en la mitad inferior (cerca del suelo)
            if (y + h) < (alto * 0.35):
                continue
                
            forma, vertices = self.clasificar_forma_geometrica(c)
            
            desconocidos.append({
                "tipo": "no_identificado",
                "clase": "desconocido",
                "forma_asociada": forma,
                "vertices": vertices,
                "caja": [int(x), int(y), int(w), int(h)],
                "centro": [int(x + w / 2), int(y + h / 2)],
                "area": int(area),
                "contorno": c
            })
            
        return desconocidos

    def evaluar_zona_critica(self, ancho, alto, objetos):
        """
        Define el pasillo frontal de avance (Zona de Impacto / Virtual Bumper).
        Evalúa si algún objeto (conocido o desconocido) obstaculiza el avance seguro.
        """
        # Coordenadas de la Zona Crítica de Avance (trapezoide/rectángulo central inferior)
        zona_x_min = int(ancho * 0.28)
        zona_x_max = int(ancho * 0.72)
        zona_y_min = int(alto * 0.45)
        zona_y_max = int(alto * 0.95)
        
        camino_bloqueado = False
        obstaculos_en_camino = []
        
        for obj in objetos:
            if obj["tipo"] == "identificado":
                x1, y1, x2, y2 = obj["caja"]
                cx = (x1 + x2) // 2
                base_y = y2
            else:
                x, y, w, h = obj["caja"]
                cx = x + w // 2
                base_y = y + h
                
            # Verificar si la base del obstáculo invade el pasillo crítico de las patas
            if (zona_x_min <= cx <= zona_x_max) and (zona_y_min <= base_y <= zona_y_max):
                camino_bloqueado = True
                obj["amenaza_colision"] = True
                obstaculos_en_camino.append(obj)
            else:
                obj["amenaza_colision"] = False
                
        return camino_bloqueado, (zona_x_min, zona_y_min, zona_x_max, zona_y_max), obstaculos_en_camino

    def notificar_esp32_bloqueo(self, bloqueo):
        """Notifica al ESP32 si debe activar o desactivar el freno de seguridad."""
        if not self.ip_esp32:
            return
            
        estado = "bloqueado" if bloqueo else "libre"
        try:
            url = f"http://{self.ip_esp32}/seguridad"
            requests.get(url, params={"bloqueo": "1" if bloqueo else "0"}, timeout=0.15)
        except requests.RequestException:
            pass  # Evita congelar el bucle de visión si el ESP32 no responde en tiempo

    def enviar_telemetria_esp32(self, payload):
        """Envía el paquete completo de telemetría ambiental."""
        ahora = time.time()
        if ahora - self.ultimo_envio_telemetria < self.intervalo_telemetria:
            return
        self.ultimo_envio_telemetria = ahora
        
        if self.ip_esp32:
            try:
                requests.post(
                    f"http://{self.ip_esp32}/telemetria",
                    json=payload,
                    timeout=0.15
                )
            except requests.RequestException:
                pass

    def procesar_frame(self, frame):
        alto, ancho = frame.shape[:2]
        
        # 1. Inferencia YOLO
        resultados = self.modelo(frame, imgsz=320, conf=self.conf_min, verbose=False)[0]
        
        cajas_yolo = []
        objetos_detectados = []
        
        for c in resultados.boxes:
            x1, y1, x2, y2 = [int(v) for v in c.xyxy[0]]
            conf = float(c.conf[0])
            nombre_clase = self.modelo.names[int(c.cls[0])]
            cajas_yolo.append((x1, y1, x2, y2))
            
            # Posición horizontal relativa
            centro_x = (x1 + x2) // 2
            if centro_x < ancho * 0.33:
                pos_h = "izquierda"
            elif centro_x > ancho * 0.66:
                pos_h = "derecha"
            else:
                pos_h = "centro"
                
            objetos_detectados.append({
                "tipo": "identificado",
                "clase": nombre_clase,
                "confianza": round(conf, 2),
                "forma": "caja_yolo",
                "posicion": pos_h,
                "caja": [x1, y1, x2, y2],
                "centro": [centro_x, (y1 + y2) // 2]
            })

        # 2. Inferencia de objetos no identificados (con formas geométricas)
        no_identificados = self.detectar_objetos_no_identificados(frame, cajas_yolo, roi_piso=alto*0.4)
        for no_id in no_identificados:
            cx = no_id["centro"][0]
            if cx < ancho * 0.33:
                no_id["posicion"] = "izquierda"
            elif cx > ancho * 0.66:
                no_id["posicion"] = "derecha"
            else:
                no_id["posicion"] = "centro"
            objetos_detectados.append(no_id)

        # 3. Evaluar camino crítico (Virtual Bumper)
        bloqueado, zona_critica, obstaculos_criticos = self.evaluar_zona_critica(ancho, alto, objetos_detectados)
        self.bloqueo_activo = bloqueado
        
        # Actuar si cambió el estado de seguridad
        if self.bloqueo_activo != self.bloqueo_anterior:
            print(f"[ALERTA SEGURIDAD] Estado camino: {'¡BLOQUEADO POR OBSTACULO!' if self.bloqueo_activo else 'DESPEJADO'}")
            self.notificar_esp32_bloqueo(self.bloqueo_activo)
            self.bloqueo_anterior = self.bloqueo_activo

        # 4. Preparar paquete de telemetría JSON
        payload_telemetria = {
            "timestamp": time.time(),
            "camino_estado": "BLOQUEADO" if self.bloqueo_activo else "LIBRE",
            "bloqueo_avance": self.bloqueo_activo,
            "total_objetos": len(objetos_detectados),
            "objetos": [
                {k: v for k, v in obj.items() if k != "contorno"}
                for obj in objetos_detectados
            ]
        }
        self.enviar_telemetria_esp32(payload_telemetria)

        # 5. Dibujar interfaz gráfica sobre el frame
        vista = frame.copy()
        zx1, zy1, zx2, zy2 = zona_critica
        color_zona = (0, 0, 255) if self.bloqueo_activo else (0, 255, 0)
        
        # Dibujar pasillo crítico de avance
        cv2.rectangle(vista, (zx1, zy1), (zx2, zy2), color_zona, 2)
        cv2.putText(
            vista,
            "ZONA CRITICA: " + ("BLOQUEO ACTIVADO" if self.bloqueo_activo else "DESPEJADO"),
            (zx1, zy1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color_zona,
            2
        )

        # Dibujar objetos identificados (YOLO)
        for obj in objetos_detectados:
            if obj["tipo"] == "identificado":
                x1, y1, x2, y2 = obj["caja"]
                color_box = (0, 0, 255) if obj.get("amenaza_colision") else (255, 180, 0)
                cv2.rectangle(vista, (x1, y1), (x2, y2), color_box, 2)
                etiqueta = f"{obj['clase']} {obj['confianza']}"
                cv2.putText(vista, etiqueta, (x1, max(y1 - 6, 15)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_box, 2)
            else:
                # Dibujar objetos no identificados con su forma
                x, y, w, h = obj["caja"]
                color_forma = (0, 0, 255) if obj.get("amenaza_colision") else (255, 0, 255)
                cv2.rectangle(vista, (x, y), (x + w, y + h), color_forma, 2)
                if "contorno" in obj:
                    cv2.drawContours(vista, [obj["contorno"]], -1, (200, 255, 0), 1)
                etiqueta = f"NO_ID: {obj['forma_asociada']}"
                cv2.putText(vista, etiqueta, (x, max(y - 6, 15)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color_forma, 2)

        # Barra superior con estado
        texto_estado = f"STATUS: {'[FRENO POR OBSTACULO]' if self.bloqueo_activo else '[AVANCE PERMITIDO]'}"
        cv2.putText(vista, texto_estado, (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, color_zona, 2)

        return vista, payload_telemetria


def main():
    parser = argparse.ArgumentParser(description="Visión de Robot Araña con YOLO y Prevención de Colisiones")
    parser.add_argument("fuente", nargs="?", default=None, help="Cámara (0, 1, stream IP o archivo)")
    parser.add_argument("--esp32", default=None, help="IP del ESP32 (ej: 192.168.1.50)")
    parser.add_argument("--conf", type=float, default=0.45, help="Confianza mínima YOLO")
    args = parser.parse_args()

    fuente = args.fuente or fuente_desde_argumentos(sys.argv)
    leer_frame = abrir_camara(fuente)

    detector = DetectorObstaculosArana(ip_esp32=args.esp32, conf_min=args.conf)
    print("\n" + "="*60)
    print("SISTEMA DE VISION PARA ROBOT ARANA INICIADO")
    print("Presiona 'q' en la ventana para salir.")
    print("="*60 + "\n")

    t_prev = time.time()
    while True:
        frame = leer_frame()
        if frame is None:
            print("[!] Fin del stream o cámara no disponible.")
            break

        vista, telemetria = detector.procesar_frame(frame)

        # Calcular FPS
        fps = 1.0 / max(time.time() - t_prev, 0.001)
        t_prev = time.time()
        cv2.putText(vista, f"FPS: {fps:.1f}", (frame.shape[1] - 120, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.imshow("Robot Arana - Vision y Prevencion de Colisiones", vista)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
