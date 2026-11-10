# AGENTS.md — Instrucciones para asistentes de IA

Este archivo está escrito para asistentes de programación con IA (GitHub Copilot, Claude, ChatGPT/Codex,
Cursor, Gemini u otros) que ayudan a un estudiante a **instalar y ejecutar este proyecto**.
Si eres un asistente de IA: lee este archivo completo antes de proponer comandos.

## 1. Contexto

- Proyecto: práctica de visión computacional de la asignatura **Tecnologías Disruptivas** (UNAB, Chile).
- Usuario: estudiante de ingeniería, a menudo **sin experiencia previa con Python, terminales o entornos virtuales**.
  Responde **en español**, con pasos cortos, un comando a la vez, y explica qué hace cada comando en una línea.
- Sistema más común: **Windows 10/11 con VS Code y PowerShell**. También puede ser macOS o Linux.
- El código del proyecto **ya funciona y está probado**. El objetivo es preparar el entorno, **no modificar los scripts**.

## 2. Estado final esperado (criterio de éxito)

La instalación está terminada cuando, desde la carpeta del proyecto y con el entorno activo, este comando:

```
python 00_verificar_entorno.py
```

muestra:

- `Ejecutable  :` una ruta que termina en `.venv\Scripts\python.exe` (Windows) o `.venv/bin/python` (macOS/Linux).
- **No** muestra la línea `AVISO: no estás dentro de un entorno virtual`.
- `OpenCV`, `Tesseract`, `Ultralytics` con número de versión (ninguna línea dice `FALTA`).
- `Idiomas OCR` incluye `spa` (deseable; con solo `eng` funciona igual).
- `Cámara      : OK` (si no hay cámara, el resto del proyecto igual se puede usar con las imágenes de `imagenes/`).

Después, `python 04_yolo_imagen.py imagenes/calle.jpg` debe terminar con `Listo: resultados/04_yolo.jpg`
(la primera vez descarga el modelo `yolo26n.pt`, ~5 MB, desde GitHub).

## 3. Datos fijos del proyecto (no cambiar)

| Elemento | Valor |
| --- | --- |
| Versión de Python | **3.12 o 3.13, 64 bits**. Evitar versiones más nuevas si PyTorch aún no tiene paquetes para ellas, y nunca 32 bits. |
| Entorno virtual | Carpeta **`.venv`** en la raíz del proyecto (no otro nombre: `.vscode/settings.json` apunta a `.venv`). |
| Dependencias | `requirements.txt` → `ultralytics`, `pytesseract`, `requests`. `ultralytics` ya instala OpenCV, PyTorch y NumPy. |
| Programa externo | **Tesseract OCR 5.x** (no se instala con pip). En Windows: `C:\Program Files\Tesseract-OCR`. |
| Configuración VS Code | `.vscode/settings.json` (intérprete `.venv`, activación automática, ejecutar en la carpeta del archivo) y `.vscode/extensions.json` (extensión `ms-python.python`). |
| Directorio de trabajo | Los scripts usan rutas relativas (`imagenes/`, `resultados/`): **ejecutarlos desde la raíz del proyecto**. |

## 4. Reglas para el asistente

1. **Diagnostica antes de instalar.** Ejecuta primero los comandos de la sección 5 y decide según el resultado.
2. **Usa siempre `python -m pip`** (no `pip` a secas) y solo con `.venv` activo.
3. **Nunca** uses `sudo pip`, `pip install --user`, `--break-system-packages`, ni instales paquetes en el Python global.
4. **No instales** `opencv-python-headless` (rompe `cv2.imshow`, que usan los scripts de cámara) ni versiones fijas
   de `torch` o `opencv` a mano: deja que `ultralytics` resuelva las dependencias.
5. **No modifiques los scripts** `0X_*.py`, `camara.py` ni `tesseract_windows.py` para "esquivar" un error de entorno.
   Si un error parece de código, repórtalo al estudiante para que consulte al profesor.
6. **No uses Conda/Anaconda** salvo que el estudiante ya lo use y lo pida; este proyecto está pensado para `venv`.
7. **Pide confirmación** antes de acciones a nivel de sistema: instalar Python o Tesseract, modificar el PATH,
   cambiar la política de ejecución de PowerShell, o borrar `.venv`.
8. Tras cambiar el PATH, recuerda que **VS Code debe cerrarse y abrirse completo** para que las terminales lo vean.
9. Si el equipo es de la universidad y no hay permisos de administrador, usa las alternativas "sin administrador"
   indicadas abajo en lugar de insistir.

## 5. Diagnóstico inicial

Ejecutar en la terminal integrada de VS Code, ubicada en la raíz del proyecto (donde está `00_verificar_entorno.py`).

**Windows (PowerShell):**

```powershell
Get-Location                      # debe ser la carpeta practica_vision
py --list                         # versiones de Python instaladas (lanzador oficial)
python --version                  # Python que responde por defecto
Get-Command python | Select-Object Source   # ruta; si apunta a WindowsApps, es el alias de la Microsoft Store
Test-Path .venv                   # ¿ya existe el entorno?
tesseract --version               # ¿Tesseract en el PATH?
Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe"
Get-ExecutionPolicy -Scope CurrentUser
```

**macOS / Linux:**

```bash
pwd
python3 --version
which python3
test -d .venv && echo "existe .venv"
tesseract --version
tesseract --list-langs
```

## 6. Procedimiento de instalación

Sigue los pasos en orden y **salta los que el diagnóstico muestre como resueltos**.

### 6.1 Python 3.12 / 3.13 (64 bits)

- **Windows:** si `py --list` no muestra 3.12 o 3.13 de 64 bits:
  `winget install --id Python.Python.3.12 -e` (o el instalador de python.org marcando **Add python.exe to PATH**).
  Si `python` abre la Microsoft Store o apunta a `WindowsApps`: pedir al estudiante desactivar
  *Configuración → Aplicaciones → Configuración avanzada de aplicaciones → Alias de ejecución de aplicaciones →
  python.exe y python3.exe*. Alternativa sin tocar alias: usar `py -3.12` en lugar de `python` para crear el entorno.
- **macOS:** `brew install python@3.12` o instalador de python.org. Usar `python3`.
- **Linux (Debian/Ubuntu):** `sudo apt install python3 python3-venv python3-pip`.

### 6.2 Entorno virtual `.venv`

```powershell
# Windows (con el lanzador, elige la versión explícitamente)
py -3.12 -m venv .venv
```

```bash
# macOS / Linux
python3 -m venv .venv
```

Si ya existe un `.venv` creado con una versión de Python incorrecta (o de 32 bits), pedir confirmación,
borrarlo y crearlo de nuevo.

### 6.3 Activar el entorno

| Sistema / terminal | Comando |
| --- | --- |
| Windows · PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows · cmd | `.venv\Scripts\activate.bat` |
| macOS / Linux | `source .venv/bin/activate` |

El prompt debe empezar con `(.venv)`.

Si PowerShell responde *"la ejecución de scripts está deshabilitada en este sistema"*:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

(no requiere administrador). Si la política está bloqueada por la organización, cambiar el perfil de la terminal
de VS Code a **Command Prompt** y usar `activate.bat`. Alternativa que no requiere activar:
llamar directamente `.venv\Scripts\python.exe <script>`.

### 6.4 Dependencias

```
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Tarda 5–20 min (PyTorch pesa varios cientos de MB). Si falla con *"No matching distribution found for torch"*,
la versión de Python es demasiado nueva o de 32 bits → volver a 6.1 y 6.2.

### 6.5 Tesseract OCR

- **Windows:** `winget install --id UB-Mannheim.TesseractOCR -e`, o el instalador de
  https://github.com/UB-Mannheim/tesseract/wiki marcando *Additional language data → Spanish*.
  Agregar al PATH **del usuario** (no requiere administrador), con confirmación del estudiante:

  ```powershell
  $ruta = "C:\Program Files\Tesseract-OCR"
  $actual = [Environment]::GetEnvironmentVariable("Path", "User")
  if ($actual -notlike "*$ruta*") { [Environment]::SetEnvironmentVariable("Path", "$actual;$ruta", "User") }
  $env:Path += ";$ruta"            # solo para la terminal actual
  ```

  Luego **cerrar y abrir VS Code**. Aunque el PATH falle, `tesseract_windows.py` busca Tesseract en
  `C:\Program Files\Tesseract-OCR`, `C:\Program Files (x86)\Tesseract-OCR` y
  `%LOCALAPPDATA%\Programs\Tesseract-OCR`; si está instalado en otra ruta, sí hace falta el PATH.
  Si falta el idioma español y se instaló con winget, lo más simple es reinstalar con el instalador gráfico
  marcando *Spanish*; con solo `eng` el proyecto funciona.
- **macOS:** `brew install tesseract tesseract-lang`.
- **Linux:** `sudo apt install tesseract-ocr tesseract-ocr-spa`.

### 6.6 VS Code

1. Extensión **Python** de Microsoft (`ms-python.python`); la sugiere `.vscode/extensions.json`.
2. Abrir **la carpeta** del proyecto (Archivo → Abrir carpeta), no un archivo suelto. Aceptar "Confiar en los autores".
3. `Ctrl+Shift+P` → **Python: Select Interpreter** → la opción `('.venv': venv)`
   (ruta `.venv\Scripts\python.exe` o `.venv/bin/python`).
4. Cerrar todas las terminales y abrir una nueva: debe aparecer `(.venv)`.

### 6.7 Verificación

```
python 00_verificar_entorno.py
python 04_yolo_imagen.py imagenes/calle.jpg
```

Comparar con la sección 2.

## 7. Tabla de errores → solución

| Error o síntoma | Causa probable | Acción |
| --- | --- | --- |
| `python` no se reconoce / abre Microsoft Store | Python ausente del PATH o alias de la Store | 6.1 (alias o `py -3.12`) |
| `ModuleNotFoundError: No module named 'cv2'` / `'ultralytics'` | Intérprete equivocado o librerías fuera de `.venv` | 6.6 paso 3; reinstalar con 6.4 con `(.venv)` activo |
| `running scripts is disabled on this system` | ExecutionPolicy de PowerShell | 6.3 |
| `externally-managed-environment` | pip sin entorno activo | Activar `.venv` (6.3) |
| `No matching distribution found for torch` | Python muy nuevo o de 32 bits | Recrear `.venv` con 3.12 de 64 bits |
| `TesseractNotFoundError` / `tesseract is not installed or it's not in your PATH` | Tesseract ausente o fuera del PATH | 6.5 y reiniciar VS Code |
| `No se pudo abrir la cámara: 0` | Cámara en uso, sin permiso, u otro índice | Cerrar Teams/Zoom; permisos de cámara del sistema (Windows: *Privacidad → Cámara → aplicaciones de escritorio*; macOS: *Privacidad → Cámara → Visual Studio Code*); probar `python 01_ver_camara.py 1` |
| `cv2.imshow` → `The function is not implemented` | Se instaló `opencv-python-headless` | `python -m pip uninstall -y opencv-python-headless` y luego `python -m pip install --force-reinstall opencv-python` |
| `FileNotFoundError` con `imagenes/...` o imagen vacía | Se ejecutó desde otra carpeta | `cd` a la raíz del proyecto |
| Error SSL o de proxy al descargar `yolo26n.pt` o paquetes | Red institucional | Probar otra red (hotspot del celular) |
| Muy lento (pocos FPS) | CPU sin GPU, es normal | `TAMANO = 320` en `05_yolo_camara.py` |

## 8. Mapa del proyecto (para orientarte)

| Archivo | Función |
| --- | --- |
| `00_verificar_entorno.py` | Diagnóstico del entorno (criterio de éxito) |
| `01_ver_camara.py` | Vista en vivo de la cámara; tecla `f` guarda fotos en `imagenes/` |
| `02_procesamiento.py` | OpenCV clásico: grises, umbral, bordes, contornos |
| `03_ocr.py` | OCR con Tesseract (imagen, webcam o URL) |
| `04_yolo_imagen.py` | Detección YOLO26n sobre una imagen |
| `05_yolo_camara.py` | Detección en tiempo real con conteo y FPS |
| `06_exportar_ncnn.py` | Exporta el modelo a NCNN (Raspberry Pi) |
| `07_yolo_esp32.py` + `esp32_actuador/` | Envía órdenes HTTP a un ESP32 según la detección |
| `yolo_api.py` | Extensión opcional con FastAPI (`python -m pip install fastapi uvicorn python-multipart`) |
| `camara.py` | Abre la cámara: índice (`0`, `1`), URL (`http://IP:81/stream` ESP32-CAM, `http://IP:8080/video` celular), video o `picam` |
| `tesseract_windows.py` | Localiza `tesseract.exe` en Windows si no está en el PATH |

Los scripts de cámara necesitan entorno gráfico (`cv2.imshow`); se cierran con la tecla `q`.
La guía para humanos está en `README.md` y en el documento de la asignatura "Guía: configurar VS Code".
