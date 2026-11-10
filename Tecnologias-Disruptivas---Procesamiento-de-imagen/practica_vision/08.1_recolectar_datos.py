"""
08.1 - Recolectar datos para entrenar un clasificador de gestos de la mano.
Guarda los puntos de la mano (no las fotos) en datos/sesion_<nombre>.csv.

Uso:  python 08.1_recolectar_datos.py --sesion s01 --persona p01 --clases piedra papel tijera ninguno
      python 08.1_recolectar_datos.py --sesion s02 --persona p01 --clases piedra papel tijera ninguno --fuente 1
Teclas:  1-9 = elegir clase y grabar   ·   0 = pausa   ·   q = salir

Una sesión es una misma combinación de persona, lugar y luz, y debe incluir TODAS las clases.
Dentro de cada una, varía la mano (izquierda y derecha), la distancia, la posición y la rotación.
En la clase "ninguno" muestra poses intermedias y otros gestos.
¿Te equivocaste de clase? Borra el archivo de esa sesión y grábala de nuevo.
"""
import argparse, csv, re, time
import cv2
from camara import abrir_camara
from gestos import COLUMNAS, DATOS, DetectorManos, dibujar_mano, leer_espejado, mano_a_fila

MUESTRAS_POR_SEGUNDO = 10        # los cuadros seguidos son casi idénticos: guardar más no aporta

parser = argparse.ArgumentParser(description="Graba los puntos de la mano para cada clase")
parser.add_argument("--sesion", required=True, help="nombre de la sesión, por ejemplo s01")
parser.add_argument("--persona", required=True, help="código de quien graba, por ejemplo p01")
parser.add_argument("--clases", nargs="+", required=True, help="clases a grabar, separadas por espacios")
parser.add_argument("--fuente", help="cámara: 0, 1, http://IP:8080/video... (ver camara.py)")
args = parser.parse_args()

for valor in (args.sesion, args.persona, *args.clases):
    if not re.fullmatch(r"[\w-]+", valor):
        parser.error(f"'{valor}' solo puede tener letras, números, guion y guion bajo")
if not 2 <= len(set(args.clases)) == len(args.clases) <= 9:
    parser.error("indica entre 2 y 9 clases, sin repetirlas")
if "ninguno" not in args.clases:
    print('AVISO: sin una clase "ninguno", cualquier otro gesto se confundirá con una de tus clases')

detector = DetectorManos()
leer = abrir_camara(args.fuente)
DATOS.mkdir(exist_ok=True)
ruta = DATOS / f"sesion_{args.sesion}.csv"
es_nuevo = not ruta.exists()

clase = None                     # None = en pausa
ultima_muestra = 0.0
conteo = dict.fromkeys(args.clases, 0)

with ruta.open("a", newline="", encoding="utf-8") as archivo:
    escritor = csv.writer(archivo)
    if es_nuevo:
        escritor.writerow(["sesion", "persona", "clase", *COLUMNAS])

    while True:
        frame = leer_espejado(leer)
        if frame is None:
            print("La cámara no entregó imagen")
            break

        mano = detector.detectar(frame)
        ahora = time.monotonic()
        if mano:
            dibujar_mano(frame, mano)
            if clase and ahora - ultima_muestra >= 1 / MUESTRAS_POR_SEGUNDO:
                escritor.writerow([args.sesion, args.persona, clase, *mano_a_fila(mano).tolist()])
                conteo[clase] += 1
                ultima_muestra = ahora

        estado = f"GRABANDO: {clase}" if clase else "PAUSA"
        color = (0, 0, 255) if clase else (0, 255, 0)
        cv2.putText(frame, f"{estado}  [q] salir", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        for i, nombre in enumerate(args.clases):
            cv2.putText(frame, f"[{i + 1}] {nombre}: {conteo[nombre]}", (10, 60 + 25 * i),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imshow("Recolectar datos", frame)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord("q"):
            break
        if tecla == ord("0"):
            clase = None
        elif ord("1") <= tecla < ord("1") + len(args.clases):
            clase = args.clases[tecla - ord("1")]

cv2.destroyAllWindows()
detector.cerrar()
print("Muestras nuevas:", conteo)
print("Guardadas en:", ruta)
print("Revísalas con:  python 08.2_entrenar_modelo.py --solo-validar")
