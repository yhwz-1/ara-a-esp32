# SPEC — Cámara IP desde el navegador del teléfono

> Instrucciones para Claude Code: lee este archivo completo e implementa la app descrita. Trabaja por etapas (ver "Plan de implementación"), verifica cada criterio de aceptación y pregunta solo si algo es realmente ambiguo.

## 1. Objetivo

Usar la cámara de un teléfono (Android o iPhone) como **cámara IP** sin instalar ninguna app en el teléfono. El teléfono solo abre una página en su navegador; un servidor en el PC recibe el video y lo publica como stream accesible por IP desde cualquier equipo de la red local (navegador, VLC, OpenCV, OBS).

## 2. Arquitectura

```
[Teléfono: navegador]                  [PC: server.py]                     [Otros equipos]
 getUserMedia (cámara)                  HTTPS :8443                          HTTP :8081
 canvas -> JPEG  ── WebSocket (wss) ──>  /ws  recibe frames   ──>  último frame en memoria
                                        /     página emisora                 /video    (MJPEG)
                                                                             /shot.jpg (foto)
                                                                             /         (visor web)
```

- **Puerto HTTPS (8443)** para el teléfono: el navegador exige un contexto seguro para acceder a la cámara.
- **Puerto HTTP (8081)** para los consumidores: VLC, OpenCV y otros clientes funcionan mejor sin TLS autofirmado.
- Los frames viajan como JPEG binario por WebSocket. El servidor guarda solo el último frame y lo reparte a todos los consumidores.

## 3. Stack

- Python 3.10 o superior.
- `aiohttp`: servidor HTTP/HTTPS, WebSocket y respuestas en streaming.
- `cryptography`: generación del certificado autofirmado.
- Frontend: HTML, CSS y JavaScript vanilla, **embebidos como strings en `server.py`**. Sin frameworks ni build.
- Archivos del proyecto: `server.py`, `requirements.txt`, `README.md`.

## 4. Requisitos funcionales

### 4.1 Servidor (`server.py`)

- **Al iniciar:**
  - Detecta la IP local del PC en la LAN. Truco: abrir un socket UDP hacia `8.8.8.8` y leer `getsockname()`, sin enviar datos.
  - Si no existen `cert.pem` y `key.pem`, los genera: certificado autofirmado RSA 2048 con validez de 1 año, con SAN que incluya la IP detectada, `localhost` y `127.0.0.1`.
  - Imprime en consola, de forma clara:
    - la URL para el teléfono, por ejemplo `https://192.168.1.20:8443`;
    - las URLs para consumir: `http://192.168.1.20:8081/video`, `/shot.jpg` y `/`;
    - un recordatorio de que el teléfono mostrará una advertencia de certificado y hay que aceptarla.
  - Opcional: muestra un **código QR en la terminal** con la URL del teléfono (librería `qrcode`, con fallback si no está instalada).
- **Argumentos CLI (`argparse`):**
  - `--https-port` (por defecto 8443)
  - `--http-port` (por defecto 8081)
  - `--host` (por defecto `0.0.0.0`)
  - `--token` (opcional): si se define, se exige `?token=...` en la página emisora, en el WebSocket y en los endpoints de consumo.
- **Endpoints HTTPS (teléfono):**
  - `GET /`: página emisora.
  - `GET /ws`: WebSocket que recibe mensajes binarios (JPEG). Cada frame actualiza `latest_frame` y su timestamp, y notifica a los consumidores con un `asyncio.Condition` o `Event`.
  - Se permite **un solo emisor** a la vez. Si se conecta otro, reemplaza al anterior y se registra en el log.
- **Endpoints HTTP (consumidores):**
  - `GET /video`: stream MJPEG (`multipart/x-mixed-replace; boundary=frame`). Envía cada nuevo frame a cada cliente. Si un cliente es lento, se le salta frames: nunca se encola sin límite.
  - `GET /shot.jpg`: último frame, o `503` si aún no hay emisor.
  - `GET /status`: JSON con `{connected, fps, last_frame_age_ms, viewers, resolution}`.
  - `GET /`: visor web simple con `<img src="/video">`, el estado (consultando `/status`) y las URLs listas para copiar.
- **Manejo de errores:** las desconexiones de clientes o del emisor se registran sin que caiga el servidor. Ctrl+C cierra limpiamente.

### 4.2 Página emisora (teléfono)

- Botón **"Iniciar cámara"**. El permiso se pide tras un gesto del usuario, algo que Safari en iOS exige.
- `getUserMedia({ video: { facingMode: 'environment', width, height } , audio: false })`.
- **Controles:**
  - cámara trasera o frontal (cambiar `facingMode` reinicia el stream);
  - resolución: 480p, 720p o 1080p;
  - FPS objetivo: 5, 10, 15, 20 o 30;
  - calidad JPEG: entre 0.3 y 0.95;
  - botón Iniciar/Detener.
- **Bucle de captura:** `video` → `canvas.drawImage` → `canvas.toBlob('image/jpeg', calidad)` → `ws.send(blob)`.
  - **Control de saturación:** no enviar un frame si `ws.bufferedAmount` supera un umbral (por ejemplo 1 MB). Así se evita acumular latencia.
  - Respetar el FPS objetivo con temporización, no con un bucle sin pausa.
- **Wake Lock API** (`navigator.wakeLock.request('screen')`) para que la pantalla no se apague. Se vuelve a pedir en `visibilitychange`. Si no está disponible, se muestra un aviso.
- **Reconexión automática del WebSocket** con backoff, si se cae.
- **Indicadores en pantalla:** estado de la conexión, FPS reales enviados, tamaño promedio por frame (KB) y vista previa local.
- Interfaz móvil, con botones grandes y legible en vertical y horizontal.

## 5. Requisitos no funcionales

- Latencia razonable en la LAN: menos de 500 ms a 720p y 15 fps.
- Sin dependencias pesadas: no usar OpenCV en el servidor.
- El código debe estar comentado en español, porque se usará también con fines docentes.
- Debe funcionar en Windows, macOS y Linux.

## 6. Fuera de alcance (v1)

- Audio.
- WebRTC peer-to-peer.
- Grabación a disco. Puede quedar como mejora futura.
- Acceso desde fuera de la LAN. En el README, recomendar Tailscale en vez de abrir puertos.

## 7. Plan de implementación

1. Crear `requirements.txt` y el esqueleto de `server.py`: detección de IP, generación del certificado y arranque de los dos servidores en el mismo event loop (`web.AppRunner` con dos `TCPSite`, uno con `ssl_context`).
2. Implementar la página emisora y el endpoint `/ws`. Verificar en los logs que llegan frames.
3. Implementar `/shot.jpg`, `/video` (MJPEG) y `/status`.
4. Implementar el visor web en el puerto HTTP.
5. Agregar `--token`, el QR en la terminal, la reconexión y el Wake Lock.
6. Escribir el `README.md`, con instalación, uso, consumo desde VLC, OpenCV y OBS, y la sección de problemas comunes.

## 8. Criterios de aceptación

- [ ] `pip install -r requirements.txt && python server.py` arranca e imprime las URLs correctas.
- [ ] Desde el teléfono, al abrir la URL HTTPS y aceptar la advertencia del certificado, se ve la vista previa y el estado pasa a "Conectado".
- [ ] `http://IP:8081/video` se ve en vivo en un navegador del PC.
- [ ] VLC abre `http://IP:8081/video` (Medio → Abrir ubicación de red).
- [ ] Este script muestra el video:
  ```python
  import cv2
  cap = cv2.VideoCapture("http://IP:8081/video")
  ```
- [ ] `/shot.jpg` devuelve la imagen actual y `/status` devuelve datos coherentes.
- [ ] Cambiar entre cámara frontal y trasera y cambiar la resolución funciona sin recargar la página.
- [ ] Varios visores simultáneos no degradan al emisor.
- [ ] Desconectar y reconectar el teléfono no requiere reiniciar el servidor.
- [ ] Con `--token abc`, las URLs sin token devuelven 401.

## 9. Problemas comunes (incluir en el README)

- **No conecta:** revisar que ambos equipos estén en la misma red. Las redes institucionales o de invitados suelen tener *client isolation*. Alternativa: usar el hotspot del teléfono y conectar el PC a esa red.
- **Firewall:** permitir Python o los puertos 8443 y 8081. En Windows aparecerá un aviso la primera vez; marcar "Redes privadas".
- **iPhone (Safari):** en la advertencia del certificado, tocar "Mostrar detalles" y luego "visitar este sitio web".
- **Android (Chrome):** tocar "Configuración avanzada" y luego "Acceder a … (sitio no seguro)".
- **La pantalla se apaga y se corta el video:** mantener la página en primer plano. El Wake Lock ayuda, pero el navegador no transmite en segundo plano.
- **La IP cambia:** las IP de la LAN son dinámicas. Volver a mirar la consola o reservar la IP en el router.
