"""
08.3 - Probar en vivo el clasificador de gestos y registrar los aciertos.

Uso:  python 08.3_probar_modelo.py --persona p09
      python 08.3_probar_modelo.py --persona p09 --fuente http://IP:8080/video
      python 08.3_probar_modelo.py --candidato          (usa modelos/candidato en vez de modelos/actual)
Teclas:  1-9 = clase que vas a mostrar   ·   espacio = registrar el intento   ·   q = salir

Prueba: haz al menos 30 intentos por clase, con alguien que no aportó datos y con otra luz.
En "ninguno", muestra gestos ajenos o ninguna mano: también vale que el sistema no decida.
Los intentos quedan en resultados/08_prueba_en_vivo.csv.
"""
import argparse, csv, time
from collections import Counter, deque
from datetime import datetime
import cv2
import numpy as np
from camara import abrir_camara
from gestos import ACTUAL, CANDIDATO, RESULTADOS, DetectorManos, cargar_modelo, dibujar_mano, leer_espejado, mano_a_fila, normalizar

ACIERTOS_MINIMOS = 0.90          # criterio de aceptación por clase
INTENTOS_MINIMOS = 30            # por clase
LATENCIA_MAXIMA = 100            # ms, percentil 95
CUADROS_DE_CALENTAMIENTO = 10    # la primera inferencia es más lenta y no representa el uso normal


class ClasificadorEnVivo:
    """Decide con varios cuadros seguidos: un cuadro suelto puede ser la mano en movimiento."""

    def __init__(self, clases, predecir, confianza, ventana, votos):
        self.clases, self.predecir = clases, predecir
        self.confianza, self.votos_minimos = confianza, votos
        self.votos = deque(maxlen=ventana)

    def actualizar(self, mano):
        """Devuelve una clase estable, o None mientras no haya una decisión segura."""
        if mano is None:
            self.votos.clear()
            return None
        probabilidades = self.predecir(normalizar(mano_a_fila(mano)))[0]
        mejor = int(np.argmax(probabilidades))
        self.votos.append(self.clases[mejor] if probabilidades[mejor] >= self.confianza else None)
        conteo = Counter(v for v in self.votos if v is not None).most_common(1)
        return conteo[0][0] if conteo and conteo[0][1] >= self.votos_minimos else None


parser = argparse.ArgumentParser(description="Prueba en vivo del clasificador de gestos")
parser.add_argument("--persona", default="sin_nombre", help="código de quien prueba, por ejemplo p09")
parser.add_argument("--candidato", action="store_true", help="usa modelos/candidato en vez de modelos/actual")
parser.add_argument("--fuente", help="cámara: 0, 1, http://IP:8080/video... (ver camara.py)")
parser.add_argument("--confianza", type=float, default=0.8, help="confianza mínima para que un cuadro vote")
parser.add_argument("--ventana", type=int, default=7, help="cuántos cuadros seguidos se consideran")
parser.add_argument("--votos", type=int, default=5, help="votos necesarios para decidir")
args = parser.parse_args()

meta, predecir = cargar_modelo(CANDIDATO if args.candidato else ACTUAL)
print(f"Modelo: {'candidato (sin aprobar)' if args.candidato else 'actual'} · tipo {meta['tipo']} · clases {meta['clases']}")
print(f"macro-F1 {meta['macro_f1_prueba']} con las sesiones no vistas {meta['sesiones_prueba']}")
if args.persona in meta["personas_entrenamiento"]:
    print(f"AVISO: {args.persona} aportó datos de entrenamiento; esta prueba no mide a una persona nueva")

clasificador = ClasificadorEnVivo(meta["clases"], predecir, args.confianza, args.ventana, args.votos)
detector = DetectorManos()
leer = abrir_camara(args.fuente)

# Sin clase "ninguno" en el modelo, igual se prueba qué hace con gestos ajenos
esperables = meta["clases"] if "ninguno" in meta["clases"] else [*meta["clases"], "ninguno"]
esperables = esperables[:9]
esperada = None
intentos = []
latencias = deque(maxlen=200)
cuadros = 0

while True:
    frame = leer_espejado(leer)
    if frame is None:
        print("La cámara no entregó imagen")
        break

    t0 = time.perf_counter()
    mano = detector.detectar(frame)
    etiqueta = clasificador.actualizar(mano)
    cuadros += 1
    if cuadros > CUADROS_DE_CALENTAMIENTO:
        latencias.append((time.perf_counter() - t0) * 1000)

    if mano:
        dibujar_mano(frame, mano)
    obtenida = etiqueta or ("indeciso" if mano else "sin mano")   # no decidir es un resultado válido
    p95 = np.percentile(latencias, 95) if latencias else 0
    cv2.putText(frame, f"{obtenida}  (p95 {p95:.0f} ms)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(frame, f"Muestro: {esperada or '-'}  [espacio] registrar  [q] salir", (10, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    hechos = Counter(i["esperada"] for i in intentos)
    for i, nombre in enumerate(esperables):
        cv2.putText(frame, f"[{i + 1}] {nombre}: {hechos[nombre]}", (10, 85 + 22 * i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    cv2.imshow("Probar modelo", frame)

    tecla = cv2.waitKey(1) & 0xFF
    if tecla == ord("q"):
        break
    if ord("1") <= tecla < ord("1") + len(esperables):
        esperada = esperables[tecla - ord("1")]
    elif tecla == ord(" "):
        if esperada is None:
            print("Primero elige con 1-9 la clase que vas a mostrar")
            continue
        correcto = obtenida == esperada or (esperada == "ninguno" and etiqueta is None)
        intentos.append({"fecha": datetime.now().isoformat(timespec="seconds"), "persona": args.persona,
                         "modelo": meta["tipo"], "esperada": esperada, "obtenida": obtenida, "correcto": correcto})
        print(f"{len(intentos):3d}. esperada {esperada:12s} obtenida {obtenida:12s} {'OK' if correcto else 'ERROR'}")

cv2.destroyAllWindows()
detector.cerrar()

if latencias:
    p95 = np.percentile(latencias, 95)
    print(f"\nLatencia p95: {p95:.0f} ms por cuadro ({'cumple' if p95 <= LATENCIA_MAXIMA else 'NO cumple'} {LATENCIA_MAXIMA} ms)")

if intentos:
    RESULTADOS.mkdir(exist_ok=True)
    ruta = RESULTADOS / "08_prueba_en_vivo.csv"
    es_nuevo = not ruta.exists()
    with ruta.open("a", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(intentos[0]))
        if es_nuevo:
            escritor.writeheader()
        escritor.writerows(intentos)

    print(f"\nResultados de esta prueba (criterio: {ACIERTOS_MINIMOS:.0%} por clase, {INTENTOS_MINIMOS}+ intentos):")
    for nombre in esperables:
        de_clase = [i for i in intentos if i["esperada"] == nombre]
        if de_clase:
            tasa = sum(i["correcto"] for i in de_clase) / len(de_clase)
            cumple = tasa >= ACIERTOS_MINIMOS and len(de_clase) >= INTENTOS_MINIMOS
            print(f"  {nombre:12s} {tasa:5.0%} de {len(de_clase):3d} intentos  {'cumple' if cumple else 'NO cumple'}")
        else:
            print(f"  {nombre:12s} sin intentos  NO cumple")
    print("Guardados en:", ruta)
