"""
08.2 - Validar los datos de datos/ y entrenar el clasificador de gestos.
Compara una red MLP con una línea base (Random Forest) y mide con sesiones que el modelo nunca vio.
El resultado queda en modelos/candidato/ y reemplaza a modelos/actual/ solo si lo merece.

Uso:  python 08.2_entrenar_modelo.py
      python 08.2_entrenar_modelo.py --solo-validar          (solo revisa los datos)
      python 08.2_entrenar_modelo.py --prueba s05 s06        (elige las sesiones de prueba)
Se necesitan al menos 3 sesiones; se recomiendan 6 o más, de 3 o más personas.

Se divide por sesión y no por fila: los cuadros seguidos son casi iguales, y con una división
por filas el modelo "rinde el examen" con preguntas que ya vio, lo que infla la nota.
"""
import argparse, json, platform, shutil
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.preprocessing import StandardScaler
from gestos import ACTUAL, CANDIDATO, COLUMNAS, DATOS, VERSION_PREPROCESO, cargar_modelo, normalizar

SEMILLA = 42
F1_MINIMO = 0.95                 # criterio de aceptación con sesiones no vistas
VENTAJA_MLP = 0.01               # el MLP debe superar al Random Forest por este margen; si no, se usa el más simple
MUESTRAS_SUGERIDAS = 300         # por clase y sesión

parser = argparse.ArgumentParser(description="Valida los datos y entrena el clasificador")
parser.add_argument("--solo-validar", action="store_true", help="revisa los datos sin entrenar")
parser.add_argument("--prueba", nargs="+", help="sesiones reservadas para la prueba final")
args = parser.parse_args()


def cargar_y_validar():
    """Lee datos/sesion_*.csv, informa qué contienen y termina si hay errores."""
    archivos = sorted(DATOS.glob("sesion_*.csv"))
    if not archivos:
        raise SystemExit("No hay datos: graba sesiones con 08.1_recolectar_datos.py")

    errores, tablas = [], []
    identificadores = ["sesion", "persona", "clase"]
    for archivo in archivos:
        tabla = pd.read_csv(archivo, dtype={c: str for c in identificadores})
        if list(tabla.columns) != identificadores + COLUMNAS:
            errores.append(f"{archivo.name}: las columnas no son las esperadas")
            continue
        numeros = tabla[COLUMNAS].apply(pd.to_numeric, errors="coerce")
        if tabla[identificadores].isna().any(axis=None) or numeros.isna().any(axis=None):
            errores.append(f"{archivo.name}: tiene valores vacíos o que no son números")
        if set(tabla["sesion"]) - {archivo.stem.removeprefix("sesion_")}:
            errores.append(f"{archivo.name}: contiene filas de otra sesión")
        if tabla["persona"].nunique() > 1:
            errores.append(f"{archivo.name}: tiene más de una persona; cada persona es una sesión distinta")
        tablas.append(tabla)
    if not tablas or all(t.empty for t in tablas):
        raise SystemExit("\n".join(["ERROR: " + e for e in errores] or ["ERROR: los archivos no tienen muestras"]))

    datos = pd.concat([t for t in tablas if not t.empty], ignore_index=True)
    conteo = pd.crosstab(datos["sesion"], datos["clase"])
    print("Muestras por sesión y clase:")
    print(conteo.to_string(), "\n")
    print("Muestras por clase  :", datos["clase"].value_counts().to_dict())
    print("Muestras por persona:", datos["persona"].value_counts().to_dict())
    duplicados = datos.duplicated(subset=["clase", *COLUMNAS]).mean()
    print(f"Duplicados exactos  : {duplicados:.1%}\n")

    # Una clase que falta suele ser un error de escritura: "tijera" y "tijeras" son dos clases
    for sesion, fila in conteo.iterrows():
        faltan = fila.index[fila == 0].tolist()
        if faltan:
            errores.append(f"la sesión {sesion} no tiene: {', '.join(faltan)}")
    if errores:
        raise SystemExit("\n".join("ERROR: " + e for e in errores))

    if conteo.to_numpy().min() < MUESTRAS_SUGERIDAS:
        print(f"AVISO: hay clases con menos de {MUESTRAS_SUGERIDAS} muestras en alguna sesión")
    if len(conteo) < 6 or datos["persona"].nunique() < 3:
        print("AVISO: se recomiendan al menos 6 sesiones y 3 personas para que el modelo generalice")
    return datos


def separar(sesiones, proporcion):
    """Separa sesiones completas al azar. Devuelve (resto, separadas)."""
    cantidad = max(1, round(len(sesiones) * proporcion))
    separadas = np.random.default_rng(SEMILLA).choice(sorted(sesiones), cantidad, replace=False).tolist()
    return [s for s in sorted(sesiones) if s not in separadas], sorted(separadas)


def entrenar_mlp(X_ent, y_ent, X_val, y_val, n_clases):
    """Red de capas Dense, es decir un MLP (no una CNN: no recibe imágenes, sino 63 números)."""
    import tensorflow as tf
    tf.keras.utils.set_random_seed(SEMILLA)
    red = tf.keras.Sequential([
        tf.keras.layers.Input((X_ent.shape[1],)),
        tf.keras.layers.Dense(128, activation="relu"),
        tf.keras.layers.Dense(64, activation="relu"),
        tf.keras.layers.Dense(32, activation="relu"),
        tf.keras.layers.Dense(n_clases, activation="softmax"),
    ])
    red.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    red.fit(X_ent, y_ent, validation_data=(X_val, y_val), epochs=100, batch_size=32, verbose=0,
            callbacks=[tf.keras.callbacks.EarlyStopping(patience=8, restore_best_weights=True)])
    return red


def entrenar_bosque(X_ent, y_ent):
    return RandomForestClassifier(n_estimators=100, random_state=SEMILLA, n_jobs=-1).fit(X_ent, y_ent)


def macro_f1(y_real, probabilidades):
    return f1_score(y_real, probabilidades.argmax(axis=1), average="macro")


datos = cargar_y_validar()
if args.solo_validar:
    print("Datos sin errores.")
    raise SystemExit

X = normalizar(datos[COLUMNAS].to_numpy(dtype=np.float32))
clases = sorted(datos["clase"].unique().tolist())       # el número de clases sale de los datos
y = np.searchsorted(clases, datos["clase"].to_numpy())
sesion = datos["sesion"].to_numpy()
sesiones = sorted(set(sesion))
if len(sesiones) < 3:
    raise SystemExit(f"Hay {len(sesiones)} sesiones y se necesitan al menos 3: entrenamiento, validación y prueba.")

# Sesiones de prueba: las indicadas, o las del modelo actual para comparar con los mismos datos
meta_actual = None
if (ACTUAL / "metadatos.json").exists():
    meta_actual = json.loads((ACTUAL / "metadatos.json").read_text(encoding="utf-8"))
if args.prueba:
    if set(args.prueba) - set(sesiones):
        raise SystemExit(f"Estas sesiones no existen: {sorted(set(args.prueba) - set(sesiones))}")
    prueba = sorted(args.prueba)
elif meta_actual and set(meta_actual["sesiones_prueba"]) <= set(sesiones):
    prueba = meta_actual["sesiones_prueba"]
else:
    _, prueba = separar(sesiones, 0.2)
resto = [s for s in sesiones if s not in prueba]
if len(resto) < 2:
    raise SystemExit("Deben quedar al menos 2 sesiones para entrenar y validar.")
entrenamiento, validacion = separar(resto, 0.2)
print(f"Entrenamiento: {entrenamiento}\nValidación   : {validacion}\nPrueba       : {prueba}\n")

en_ent, en_val, en_prueba = (np.isin(sesion, s) for s in (entrenamiento, validacion, prueba))

escalador = StandardScaler().fit(X[en_ent])             # se ajusta solo con entrenamiento
X_ent, X_val = escalador.transform(X[en_ent]), escalador.transform(X[en_val])

# El ganador se elige con validación; la prueba se usa una sola vez, al final
print("Entrenando Random Forest (línea base)...")
bosque = entrenar_bosque(X_ent, y[en_ent])
f1_bosque = macro_f1(y[en_val], bosque.predict_proba(X_val))
print("Entrenando MLP...")
red = entrenar_mlp(X_ent, y[en_ent], X_val, y[en_val], len(clases))
f1_mlp = macro_f1(y[en_val], red.predict(X_val, verbose=0))
tipo = "mlp" if f1_mlp >= f1_bosque + VENTAJA_MLP else "bosque"
print(f"macro-F1 en validación: Random Forest {f1_bosque:.3f} · MLP {f1_mlp:.3f} -> se usa {tipo}\n")

personas_ent = sorted(set(datos.loc[en_ent | en_val, "persona"]))
meta = {
    "tipo": tipo,
    "clases": clases,
    "version_preproceso": VERSION_PREPROCESO,
    "filas": len(datos),
    "personas_entrenamiento": personas_ent,
    "sesiones_entrenamiento": entrenamiento,
    "sesiones_validacion": validacion,
    "sesiones_prueba": prueba,
    "macro_f1_validacion": {"bosque": round(f1_bosque, 4), "mlp": round(f1_mlp, 4)},
    "versiones": {"python": platform.python_version(), "scikit-learn": sklearn.__version__},
}
if tipo == "mlp":
    import tensorflow as tf
    meta["versiones"]["tensorflow"] = tf.__version__

# Modelo, escalador y metadatos se guardan juntos
shutil.rmtree(CANDIDATO, ignore_errors=True)
CANDIDATO.mkdir(parents=True)
joblib.dump(escalador, CANDIDATO / "escalador.pkl")
if tipo == "mlp":
    red.save(CANDIDATO / "modelo.keras")
else:
    joblib.dump(bosque, CANDIDATO / "modelo.pkl")
(CANDIDATO / "metadatos.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

# Se evalúa lo que quedó guardado, para probar también que se puede volver a cargar
_, predecir = cargar_modelo(CANDIDATO)
probabilidades = predecir(X[en_prueba])
f1_prueba = macro_f1(y[en_prueba], probabilidades)
predichas = probabilidades.argmax(axis=1)
matriz = confusion_matrix(y[en_prueba], predichas, labels=range(len(clases)))
personas_prueba = sorted(set(datos.loc[en_prueba, "persona"]))
nuevas = [p for p in personas_prueba if p not in personas_ent]

print(classification_report(y[en_prueba], predichas, labels=range(len(clases)), target_names=clases, zero_division=0))
print("Matriz de confusión (filas = real, columnas = predicho):")
print(pd.DataFrame(matriz, index=clases, columns=clases).to_string(), "\n")
print(f"macro-F1 = {f1_prueba:.3f}, medido con {len(prueba)} sesión(es) no vista(s) {prueba}; "
      f"de {len(personas_prueba)} persona(s), {len(nuevas)} ausente(s) del entrenamiento; "
      f"{len(sesiones)} sesiones y {datos['persona'].nunique()} personas en total.")

# Persona fuera: ¿funciona con alguien cuyos datos no conoce? Es el caso real de un usuario nuevo
fuera = {}
for persona in sorted(set(datos["persona"])):
    otras = sorted(set(datos.loc[datos["persona"] != persona, "sesion"]))
    if len(otras) < 2:
        continue
    ent_p, val_p = separar(otras, 0.2)
    en_e, en_v, en_p = np.isin(sesion, ent_p), np.isin(sesion, val_p), (datos["persona"] == persona).to_numpy()
    esc = StandardScaler().fit(X[en_e])
    if tipo == "mlp":
        modelo_p = entrenar_mlp(esc.transform(X[en_e]), y[en_e], esc.transform(X[en_v]), y[en_v], len(clases))
        proba_p = modelo_p.predict(esc.transform(X[en_p]), verbose=0)
    else:
        proba_p = entrenar_bosque(esc.transform(X[en_e]), y[en_e]).predict_proba(esc.transform(X[en_p]))
    fuera[persona] = round(float(macro_f1(y[en_p], proba_p)), 4)
if fuera:
    print("macro-F1 dejando fuera a cada persona (entrenando con las demás):", fuera)

meta.update({
    "macro_f1_prueba": round(float(f1_prueba), 4),
    "macro_f1_persona_fuera": fuera,
    "personas_prueba": personas_prueba,
    "matriz_confusion": matriz.tolist(),
})
(CANDIDATO / "metadatos.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

# Promoción: el candidato reemplaza al actual solo si gana con los mismos datos de prueba
motivo = None
if f1_prueba < F1_MINIMO:
    motivo = f"no alcanza macro-F1 {F1_MINIMO}. Graba más sesiones variadas antes de complicar el modelo"
elif meta_actual:
    vistas = set(meta_actual["sesiones_entrenamiento"] + meta_actual["sesiones_validacion"])
    if meta_actual["clases"] != clases:
        motivo = "el modelo actual tiene otras clases. Si es un proyecto nuevo, borra modelos/actual y entrena de nuevo"
    elif vistas & set(prueba):
        motivo = (f"el modelo actual ya vio {sorted(vistas & set(prueba))}, así que no es una comparación justa. "
                  f"Usa --prueba con sesiones que no haya visto: {sorted(set(sesiones) - vistas) or 'graba sesiones nuevas'}")
    else:
        _, predecir_actual = cargar_modelo(ACTUAL)
        f1_actual = macro_f1(y[en_prueba], predecir_actual(X[en_prueba]))
        print(f"Con las mismas sesiones de prueba: actual {f1_actual:.3f} · candidato {f1_prueba:.3f}")
        if f1_prueba <= f1_actual:
            motivo = "no supera al modelo actual"

if motivo:
    print(f"\nEl candidato NO se aprueba: {motivo}.")
    print("Queda en modelos/candidato/. Puedes probarlo con:  python 08.3_probar_modelo.py --candidato")
else:
    temporal = ACTUAL.with_name("actual_nuevo")
    shutil.rmtree(temporal, ignore_errors=True)
    shutil.copytree(CANDIDATO, temporal)
    shutil.rmtree(ACTUAL, ignore_errors=True)
    temporal.rename(ACTUAL)
    print("\nCandidato aprobado: ahora es modelos/actual/. Pruébalo con:  python 08.3_probar_modelo.py")
