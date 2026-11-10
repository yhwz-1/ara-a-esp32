"""
07 - Integración: el teléfono "ve", el computador detecta con YOLO y el ESP32 "actúa".

El teléfono se usa como cámara IP SIN instalar ninguna app: solo abre una página en su navegador.
Este script levanta dos servidores web en el computador:
  - HTTPS :8443  -> página para el teléfono (el navegador exige https para usar la cámara).
                    El teléfono envía fotos JPEG por WebSocket.
  - HTTP  :8081  -> visor web y streams para cualquier equipo de la red (navegador, VLC, OpenCV, OBS):
                    /video (cámara original), /detecciones (con las cajas de YOLO), /shot.jpg, /status
Cuando YOLO detecta la clase objetivo, se envía una petición HTTP al ESP32 para encender un LED
(o un buzzer, un relé, un servo...). Cargar antes esp32_actuador/esp32_actuador.ino en el ESP32.

Uso:  python 07_yolo_esp32.py                          (cámara del teléfono por el navegador)
      python 07_yolo_esp32.py --token abc              (exige ?token=abc en todas las URLs)
      python 07_yolo_esp32.py --esp32 192.168.1.77 --clase "cell phone"
      python 07_yolo_esp32.py 0                        (modo clásico: webcam, sin interfaz web)
      python 07_yolo_esp32.py http://IP:81/stream      (modo clásico: ESP32-CAM como cámara)
Dependencias extra:  python -m pip install aiohttp cryptography qrcode   (qrcode es opcional)
"""
import argparse, asyncio, datetime, ipaddress, os, socket, ssl, threading, time
from collections import deque

import requests

IP_ESP32 = "192.168.1.50"        # <-- cambiar por la IP que muestra el ESP32 en el Monitor Serie
CLASE_OBJETIVO = "person"        # prueba también con: cell phone, bottle, cup, dog...
CERT, CLAVE = "cert.pem", "key.pem"


def log(*partes):
    print(time.strftime("%H:%M:%S"), *partes, flush=True)


# ---------------------------------------------------------------------------------------------
# Detección con YOLO + aviso al ESP32 (lo usan los dos modos: teléfono y clásico)
# ---------------------------------------------------------------------------------------------
class Detector:
    def __init__(self, ip_esp32, clase):
        from ultralytics import YOLO            # se importa aquí: tarda unos segundos en cargar
        ruta = "yolo26n_ncnn_model" if os.path.isdir("yolo26n_ncnn_model") else "yolo26n.pt"
        self.modelo = YOLO(ruta)
        self.ip_esp32, self.clase = ip_esp32, clase
        self.estado_anterior = None
        self.detectado = False
        self.esp32_ok = None                     # None = aún no se ha intentado contactar
        log("Modelo cargado:", ruta, "| clase objetivo:", clase, "| ESP32:", ip_esp32)

    def procesar(self, frame):
        """Detecta en un frame BGR, avisa al ESP32 si cambia el estado y devuelve el frame anotado."""
        r = self.modelo(frame, imgsz=320, conf=0.5, verbose=False)[0]
        self.detectado = any(self.modelo.names[int(c.cls)] == self.clase for c in r.boxes)

        if self.detectado != self.estado_anterior:          # solo avisar cuando cambia el estado
            estado = "on" if self.detectado else "off"
            try:
                requests.get(f"http://{self.ip_esp32}/led", params={"estado": estado}, timeout=1)
                log(self.clase, "->", estado)
                self.esp32_ok = True
            except requests.RequestException as e:
                log(self.clase, "->", estado, "| No se pudo contactar al ESP32:", e)
                self.esp32_ok = False
            self.estado_anterior = self.detectado
        return r.plot()                                      # imagen con las cajas dibujadas


def modo_clasico(fuente, args):
    """El comportamiento original: lee una webcam o una URL (ESP32-CAM) con camara.py."""
    from camara import abrir_camara
    detector = Detector(args.esp32, args.clase)
    leer = abrir_camara(fuente)
    while True:
        frame = leer()
        if frame is None:
            break
        detector.procesar(frame)


# ---------------------------------------------------------------------------------------------
# Utilidades de red: IP local y certificado autofirmado
# ---------------------------------------------------------------------------------------------
def ip_local():
    """IP del PC en la red local. Un socket UDP "conectado" a 8.8.8.8 no envía nada,
    pero el sistema elige la interfaz de salida y getsockname() revela su IP."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def preparar_certificado(ip):
    """Crea cert.pem y key.pem (RSA 2048, 1 año) si no existen o si no incluyen la IP actual."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    if os.path.exists(CERT) and os.path.exists(CLAVE):
        with open(CERT, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        try:
            ips = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName) \
                      .value.get_values_for_type(x509.IPAddress)
        except x509.ExtensionNotFound:
            ips = []
        if ipaddress.ip_address(ip) in ips:
            return                                           # el certificado actual sirve
        log("La IP cambió: se genera un certificado nuevo")

    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "practica_vision")])
    ips = {ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address(ip)}
    san = x509.SubjectAlternativeName([x509.DNSName("localhost")] + [x509.IPAddress(i) for i in ips])
    ahora = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(nombre).issuer_name(nombre)              # autofirmado: emisor = sujeto
            .public_key(clave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(ahora - datetime.timedelta(minutes=5))
            .not_valid_after(ahora + datetime.timedelta(days=365))
            .add_extension(san, critical=False)
            .sign(clave, hashes.SHA256()))
    with open(CLAVE, "wb") as f:
        f.write(clave.private_bytes(serialization.Encoding.PEM,
                                    serialization.PrivateFormat.TraditionalOpenSSL,
                                    serialization.NoEncryption()))
    with open(CERT, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    log("Certificado autofirmado creado:", CERT, CLAVE)


def tamano_jpeg(datos):
    """Lee ancho y alto de la cabecera del JPEG (marcador SOF), sin decodificar la imagen."""
    i = 2
    while i + 9 < len(datos):
        if datos[i] != 0xFF:
            return None
        marcador = datos[i + 1]
        if marcador == 0xFF:                                 # relleno entre marcadores
            i += 1
            continue
        if marcador in (0xC0, 0xC1, 0xC2):
            alto = int.from_bytes(datos[i + 5:i + 7], "big")
            ancho = int.from_bytes(datos[i + 7:i + 9], "big")
            return ancho, alto
        i += 2 + int.from_bytes(datos[i + 2:i + 4], "big")   # saltar al siguiente segmento
    return None


def imprimir_qr(url):
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except ImportError:
        print("(Para ver un código QR aquí: python -m pip install qrcode)")
    except UnicodeEncodeError:
        print("(Esta terminal no puede dibujar el código QR)")


# ---------------------------------------------------------------------------------------------
# Canal: guarda solo el ÚLTIMO frame y avisa a quienes esperan uno nuevo
# ---------------------------------------------------------------------------------------------
class Canal:
    def __init__(self):
        self.frame = None                    # bytes JPEG
        self.seq = 0                         # número de frame, para saber si hay uno nuevo
        self.t = 0.0                         # instante en que llegó el último frame
        self.tiempos = deque(maxlen=60)
        self.cond = asyncio.Condition()

    async def publicar(self, jpg):
        async with self.cond:
            self.frame, self.seq, self.t = jpg, self.seq + 1, time.time()
            self.tiempos.append(self.t)
            self.cond.notify_all()

    async def esperar(self, seq_visto):
        """Espera un frame distinto del último que vio el cliente. Si el cliente es lento,
        recibe directamente el más reciente: los frames intermedios se saltan, nunca se encolan."""
        async with self.cond:
            await self.cond.wait_for(lambda: self.frame is not None and self.seq != seq_visto)
            return self.frame, self.seq

    def fps(self):
        recientes = [t for t in self.tiempos if time.time() - t < 2]
        if len(recientes) < 2:
            return 0.0
        return round((len(recientes) - 1) / (recientes[-1] - recientes[0]), 1)


def hilo_deteccion(loop, camara, detecciones, info, args, detener):
    """Corre en un hilo aparte para no bloquear el servidor: YOLO tarda decenas de ms por frame."""
    try:
        import cv2
        import numpy as np
        detector = Detector(args.esp32, args.clase)
    except Exception as e:
        log("No se pudo cargar YOLO (el video sigue funcionando, pero sin detecciones):", e)
        return
    info["detector"] = detector
    seq_visto, tiempos = 0, deque(maxlen=30)
    while not detener.is_set():
        if camara.frame is None or camara.seq == seq_visto:
            time.sleep(0.01)                 # aún no hay un frame nuevo
            continue
        seq_visto, datos = camara.seq, camara.frame
        frame = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            continue
        anotado = detector.procesar(frame)
        ok, jpg = cv2.imencode(".jpg", anotado, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            asyncio.run_coroutine_threadsafe(detecciones.publicar(jpg.tobytes()), loop)
        tiempos.append(time.time())
        if len(tiempos) > 1:
            info["fps_yolo"] = round((len(tiempos) - 1) / (tiempos[-1] - tiempos[0]), 1)


# ---------------------------------------------------------------------------------------------
# Servidor web (aiohttp)
# ---------------------------------------------------------------------------------------------
def crear_apps(args, ip, camara, detecciones, info):
    from aiohttp import web, WSMsgType

    estado = {"emisor": None, "viewers": 0}
    sufijo = f"?token={args.token}" if args.token else ""

    @web.middleware
    async def verificar_token(request, handler):
        if args.token and request.query.get("token") != args.token:
            raise web.HTTPUnauthorized(text="401: falta ?token=... en la URL o es incorrecto")
        return await handler(request)

    # ---- teléfono (HTTPS) ----
    async def pagina_emisora(request):
        return web.Response(text=PAGINA_EMISORA, content_type="text/html")

    async def websocket(request):
        ws = web.WebSocketResponse(max_msg_size=16 * 1024 * 1024, heartbeat=20)
        await ws.prepare(request)
        anterior, estado["emisor"] = estado["emisor"], ws
        if anterior is not None and not anterior.closed:     # solo un emisor a la vez
            log("Se conectó otro teléfono: reemplaza al anterior")
            await anterior.close(code=4000, message=b"reemplazado")
        log("Teléfono conectado:", request.remote)
        n = 0
        try:
            async for msg in ws:
                if msg.type == WSMsgType.BINARY:
                    await camara.publicar(msg.data)
                    n += 1
                    if n == 1:
                        log("Llegó el primer frame:", tamano_jpeg(msg.data), f"{len(msg.data) // 1024} KB")
                elif msg.type == WSMsgType.ERROR:
                    log("Error en el WebSocket:", ws.exception())
        finally:
            if estado["emisor"] is ws:
                estado["emisor"] = None
            log("Teléfono desconectado:", request.remote, f"({n} frames recibidos)")
        return ws

    # ---- consumidores (HTTP) ----
    async def visor(request):
        html = (PAGINA_VISOR.replace("__IP__", ip).replace("__HTTP__", str(args.http_port))
                .replace("__HTTPS__", str(args.https_port)).replace("__TOKEN__", sufijo))
        return web.Response(text=html, content_type="text/html")

    async def mjpeg(request, canal):
        resp = web.StreamResponse(headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-cache, no-store", "Pragma": "no-cache"})
        await resp.prepare(request)
        estado["viewers"] += 1
        seq = 0
        try:
            while True:
                try:
                    jpg, seq = await asyncio.wait_for(canal.esperar(seq), timeout=5)
                except asyncio.TimeoutError:             # sin frames nuevos: ¿sigue ahí el cliente?
                    if request.transport is None or request.transport.is_closing():
                        break
                    continue
                await resp.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                 + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
        except ConnectionError:
            pass                                         # el visor cerró la conexión
        finally:
            estado["viewers"] -= 1
        return resp

    async def video(request):
        return await mjpeg(request, camara)

    async def video_detecciones(request):
        return await mjpeg(request, detecciones)

    async def foto(request):
        if camara.frame is None:
            raise web.HTTPServiceUnavailable(text="503: todavía no hay un teléfono enviando video")
        return web.Response(body=camara.frame, content_type="image/jpeg",
                            headers={"Cache-Control": "no-cache"})

    async def status(request):
        conectado = estado["emisor"] is not None and not estado["emisor"].closed
        tam = tamano_jpeg(camara.frame) if camara.frame else None
        det = info.get("detector")
        return web.json_response({
            "connected": conectado,
            "fps": camara.fps() if conectado else 0.0,
            "last_frame_age_ms": int((time.time() - camara.t) * 1000) if camara.frame else None,
            "viewers": estado["viewers"],
            "resolution": f"{tam[0]}x{tam[1]}" if tam else None,
            "yolo": {
                "listo": det is not None,
                "clase": args.clase,
                "detectado": det.detectado if det else False,
                "fps": info.get("fps_yolo", 0.0),
                "esp32": args.esp32,
                "esp32_ok": det.esp32_ok if det else None,
            },
        })

    telefono = web.Application(middlewares=[verificar_token])
    telefono.add_routes([web.get("/", pagina_emisora), web.get("/ws", websocket),
                         web.get("/status", status)])
    consumo = web.Application(middlewares=[verificar_token])
    consumo.add_routes([web.get("/", visor), web.get("/video", video),
                        web.get("/detecciones", video_detecciones),
                        web.get("/shot.jpg", foto), web.get("/status", status)])
    return telefono, consumo


async def servidor(args):
    from aiohttp import web

    ip = ip_local()
    preparar_certificado(ip)
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(CERT, CLAVE)

    camara, detecciones, info = Canal(), Canal(), {}
    telefono, consumo = crear_apps(args, ip, camara, detecciones, info)

    # Los dos servidores comparten el mismo event loop
    r1, r2 = web.AppRunner(telefono), web.AppRunner(consumo)
    await r1.setup()
    await r2.setup()
    try:
        await web.TCPSite(r1, args.host, args.https_port, ssl_context=ctx).start()
        await web.TCPSite(r2, args.host, args.http_port).start()
    except OSError as e:
        log("No se pudo abrir el puerto:", e)
        log("¿Otro programa lo usa? Prueba con otros: --https-port 8444 --http-port 8082")
        await r1.cleanup()
        await r2.cleanup()
        return

    sufijo = f"?token={args.token}" if args.token else ""
    url_tel = f"https://{ip}:{args.https_port}/{sufijo}"
    base = f"http://{ip}:{args.http_port}"
    print("\n" + "=" * 64)
    print(" 1) En el TELÉFONO (misma red WiFi) abre:   ", url_tel)
    print("    Aparecerá una advertencia de certificado: es normal, acéptala")
    print("    (Android: Configuración avanzada -> Acceder | iPhone: Mostrar detalles -> visitar)")
    print(" 2) En el COMPUTADOR mira el resultado en:  ", f"{base}/{sufijo}")
    print("    Video original  :", f"{base}/video{sufijo}")
    print("    Video con YOLO  :", f"{base}/detecciones{sufijo}")
    print("    Foto actual     :", f"{base}/shot.jpg{sufijo}")
    print("    Estado (JSON)   :", f"{base}/status{sufijo}")
    print("=" * 64)
    imprimir_qr(url_tel)
    print("Ctrl+C para salir\n", flush=True)

    detener = threading.Event()
    threading.Thread(target=hilo_deteccion, daemon=True,
                     args=(asyncio.get_running_loop(), camara, detecciones, info, args, detener)).start()
    try:
        await asyncio.Event().wait()                     # esperar para siempre (hasta Ctrl+C)
    finally:
        detener.set()
        await r1.cleanup()
        await r2.cleanup()


# ---------------------------------------------------------------------------------------------
# Páginas web (HTML + CSS + JavaScript sin frameworks)
# ---------------------------------------------------------------------------------------------
PAGINA_EMISORA = r"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cámara del teléfono</title>
<style>
  body { margin:0; font-family:system-ui,sans-serif; background:#111; color:#eee; }
  main { max-width:900px; margin:auto; padding:12px; display:grid; gap:12px; }
  @media (orientation:landscape) and (min-width:600px) { main { grid-template-columns:3fr 2fr; } }
  video { width:100%; max-height:70vh; background:#000; border-radius:10px; object-fit:contain; }
  h1 { font-size:1.2rem; margin:0 0 8px; }
  .chip { display:inline-block; padding:6px 12px; border-radius:20px; background:#444; font-weight:bold; }
  .ok { background:#1b7f3b; } .error { background:#a12828; }
  .metricas { display:flex; gap:8px; flex-wrap:wrap; margin:10px 0; }
  .metricas span { background:#222; padding:6px 10px; border-radius:8px; }
  button { width:100%; font-size:1.3rem; padding:16px; border:0; border-radius:12px;
           background:#2563eb; color:#fff; font-weight:bold; }
  button.detener { background:#a12828; }
  label { display:flex; justify-content:space-between; align-items:center; gap:10px; margin:12px 0; font-size:1.05rem; }
  select, input[type=range] { font-size:1.05rem; padding:8px; min-width:45%; }
  #aviso { color:#fbbf24; font-size:.9rem; }
</style></head>
<body><main>
  <video id="vista" playsinline muted autoplay></video>
  <section>
    <h1>Cámara del teléfono → YOLO</h1>
    <span id="estado" class="chip">Desconectado</span>
    <div class="metricas">
      <span id="fps">0 fps</span><span id="kb">0 KB/frame</span><span id="det">YOLO: —</span>
    </div>
    <button id="boton">Iniciar cámara</button>
    <label>Cámara <select id="camara">
      <option value="environment">Trasera</option><option value="user">Frontal</option></select></label>
    <label>Resolución <select id="res">
      <option value="480">480p</option><option value="720" selected>720p</option>
      <option value="1080">1080p</option></select></label>
    <label>FPS objetivo <select id="fpsObj">
      <option>5</option><option selected>10</option><option>15</option><option>20</option>
      <option>30</option></select></label>
    <label>Calidad <span id="calidadTxt">0.70</span>
      <input type="range" id="calidad" min="0.3" max="0.95" step="0.05" value="0.7"></label>
    <p id="aviso"></p>
  </section>
</main>
<canvas id="lienzo" hidden></canvas>
<script>
const $ = id => document.getElementById(id);
const token = new URLSearchParams(location.search).get('token');
const sufijo = token ? '?token=' + encodeURIComponent(token) : '';
const RES = { 480: [640, 480], 720: [1280, 720], 1080: [1920, 1080] };
const UMBRAL = 1024 * 1024;     // si hay más de 1 MB sin enviar, se salta el frame (evita latencia)

let stream = null, ws = null, activo = false, temporizador = null, wakeLock = null;
let reintento = 1000, codificando = false, enviados = 0, bytes = 0, t0 = performance.now();

function estado(texto, clase) { $('estado').textContent = texto; $('estado').className = 'chip ' + (clase || ''); }

// Abre (o reabre) la cámara con la cámara y resolución elegidas
async function abrirCamara() {
  if (stream) stream.getTracks().forEach(t => t.stop());
  const [w, h] = RES[$('res').value];
  stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: $('camara').value, width: { ideal: w }, height: { ideal: h } }, audio: false });
  $('vista').srcObject = stream;
  await $('vista').play();
}

// WebSocket con reconexión automática (espera 1 s, 2 s, 4 s... hasta 10 s)
function conectar() {
  const s = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws' + sufijo);
  ws = s;
  estado('Conectando…');
  s.onopen = () => { estado('Conectado', 'ok'); reintento = 1000; };
  s.onclose = ev => {
    if (ws === s) ws = null;
    if (ev.code === 4000) { estado('Otro teléfono tomó el control', 'error'); detener(); return; }
    if (!activo) { estado('Desconectado'); return; }
    estado('Sin conexión, reintentando en ' + reintento / 1000 + ' s…', 'error');
    setTimeout(() => { if (activo && !ws) conectar(); }, reintento);
    reintento = Math.min(reintento * 2, 10000);
  };
}

// Bucle de captura: video -> canvas -> JPEG -> WebSocket, al ritmo del FPS objetivo
function capturar() {
  const inicio = performance.now(), v = $('vista'), c = $('lienzo');
  if (ws && ws.readyState === WebSocket.OPEN && v.videoWidth && !codificando && ws.bufferedAmount < UMBRAL) {
    if (c.width !== v.videoWidth || c.height !== v.videoHeight) { c.width = v.videoWidth; c.height = v.videoHeight; }
    c.getContext('2d').drawImage(v, 0, 0);
    codificando = true;
    c.toBlob(b => {
      codificando = false;
      if (b && ws && ws.readyState === WebSocket.OPEN) { ws.send(b); enviados++; bytes += b.size; }
    }, 'image/jpeg', Number($('calidad').value));
  }
  const intervalo = 1000 / Number($('fpsObj').value);
  if (activo) temporizador = setTimeout(capturar, Math.max(0, intervalo - (performance.now() - inicio)));
}

// Mantener la pantalla encendida (Wake Lock API)
async function pedirWakeLock() {
  if (!('wakeLock' in navigator)) {
    $('aviso').textContent = 'Este navegador no puede mantener la pantalla encendida: evita que se bloquee.';
    return;
  }
  try { wakeLock = await navigator.wakeLock.request('screen'); }
  catch (e) { $('aviso').textContent = 'No se pudo mantener la pantalla encendida: ' + e.message; }
}
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && activo) pedirWakeLock();
});

async function iniciar() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    estado('Sin acceso a la cámara: abre la página con https://', 'error'); return;
  }
  try { await abrirCamara(); }
  catch (e) { estado('No se pudo abrir la cámara: ' + e.message, 'error'); return; }
  activo = true;
  $('boton').textContent = 'Detener'; $('boton').classList.add('detener');
  conectar(); pedirWakeLock(); capturar();
}

function detener() {
  activo = false;
  clearTimeout(temporizador);
  if (ws) ws.close();
  if (stream) stream.getTracks().forEach(t => t.stop());
  stream = null;
  if (wakeLock) { wakeLock.release(); wakeLock = null; }
  $('boton').textContent = 'Iniciar cámara'; $('boton').classList.remove('detener');
}

$('boton').onclick = () => activo ? detener() : iniciar();
// Cambiar cámara o resolución reinicia solo el video, sin recargar la página
$('camara').onchange = $('res').onchange = async () => {
  if (!activo) return;
  try { await abrirCamara(); } catch (e) { estado('No se pudo cambiar la cámara: ' + e.message, 'error'); }
};
$('calidad').oninput = () => { $('calidadTxt').textContent = Number($('calidad').value).toFixed(2); };

// Indicadores: FPS reales, tamaño promedio y resultado de YOLO (cada 1 s)
setInterval(async () => {
  const dt = (performance.now() - t0) / 1000;
  $('fps').textContent = (enviados / dt).toFixed(1) + ' fps';
  $('kb').textContent = (enviados ? bytes / enviados / 1024 : 0).toFixed(0) + ' KB/frame';
  enviados = 0; bytes = 0; t0 = performance.now();
  if (!activo) return;
  try {
    const y = (await (await fetch('/status' + sufijo)).json()).yolo;
    $('det').textContent = !y.listo ? 'YOLO: cargando…' : y.clase + ': ' + (y.detectado ? 'SÍ' : 'no');
  } catch (e) { /* el servidor no respondió: se reintenta en el siguiente segundo */ }
}, 1000);
</script>
</body></html>
"""

PAGINA_VISOR = r"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Visor YOLO</title>
<style>
  body { margin:0; font-family:system-ui,sans-serif; background:#111; color:#eee; }
  main { max-width:1200px; margin:auto; padding:16px; }
  .grid { display:grid; gap:12px; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); }
  figure { margin:0; } figcaption { color:#aaa; margin-top:4px; }
  img { width:100%; background:#000; border-radius:10px; min-height:150px; }
  table { border-collapse:collapse; margin:12px 0; }
  td { padding:4px 12px 4px 0; } td:first-child { color:#aaa; }
  .si { color:#4ade80; font-weight:bold; } .no { color:#f87171; }
  .url { display:flex; gap:8px; margin:6px 0; }
  .url input { flex:1; font-family:monospace; padding:6px; background:#222; color:#eee; border:1px solid #444; border-radius:6px; }
  .url button { padding:6px 12px; border-radius:6px; border:0; background:#2563eb; color:#fff; }
</style></head>
<body><main>
  <h1>Visor: cámara del teléfono + YOLO</h1>
  <div class="grid">
    <figure><img src="/detecciones__TOKEN__" alt="Esperando detecciones…"><figcaption>Con YOLO (/detecciones)</figcaption></figure>
    <figure><img src="/video__TOKEN__" alt="Esperando al teléfono…"><figcaption>Original (/video)</figcaption></figure>
  </div>
  <table id="tabla"></table>
  <h2>URLs</h2>
  <div id="urls"></div>
</main>
<script>
const base = 'http://__IP__:__HTTP__', t = '__TOKEN__';
const urls = [
  ['Teléfono (abrir en su navegador)', 'https://__IP__:__HTTPS__/' + t],
  ['Video original (VLC, OpenCV, OBS)', base + '/video' + t],
  ['Video con detecciones', base + '/detecciones' + t],
  ['Foto actual', base + '/shot.jpg' + t],
  ['Estado JSON', base + '/status' + t],
];
// Botones "Copiar": en http:// no siempre existe navigator.clipboard, por eso se usa execCommand
const lista = document.getElementById('urls');
urls.forEach(([nombre, url]) => {
  const div = document.createElement('div');
  div.innerHTML = '<div>' + nombre + '</div><div class="url"><input readonly><button>Copiar</button></div>';
  const input = div.querySelector('input');
  input.value = url;
  div.querySelector('button').onclick = () => { input.select(); document.execCommand('copy'); };
  lista.appendChild(div);
});

const sino = v => v ? '<span class="si">sí</span>' : '<span class="no">no</span>';
setInterval(async () => {
  try {
    const s = await (await fetch('/status' + t)).json(), y = s.yolo;
    document.getElementById('tabla').innerHTML =
      '<tr><td>Teléfono conectado</td><td>' + sino(s.connected) + '</td></tr>' +
      '<tr><td>FPS recibidos</td><td>' + s.fps + '</td></tr>' +
      '<tr><td>Resolución</td><td>' + (s.resolution || '—') + '</td></tr>' +
      '<tr><td>Antigüedad del último frame</td><td>' + (s.last_frame_age_ms ?? '—') + ' ms</td></tr>' +
      '<tr><td>Visores conectados</td><td>' + s.viewers + '</td></tr>' +
      '<tr><td>YOLO</td><td>' + (y.listo ? y.fps + ' fps' : 'cargando modelo…') + '</td></tr>' +
      '<tr><td>¿Detecta "' + y.clase + '"?</td><td>' + sino(y.detectado) + '</td></tr>' +
      '<tr><td>ESP32 (' + y.esp32 + ')</td><td>' +
        (y.esp32_ok === null ? 'sin contactar aún' : y.esp32_ok ? sino(true) + ' responde' : sino(false) + ' no responde') + '</td></tr>';
  } catch (e) { document.getElementById('tabla').innerHTML = '<tr><td>El servidor no responde</td></tr>'; }
}, 1000);
</script>
</body></html>
"""


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="YOLO + ESP32 usando la cámara del teléfono por el navegador")
    p.add_argument("fuente", nargs="?", help="modo clásico: índice de webcam (0, 1) o URL de una cámara IP")
    p.add_argument("--https-port", type=int, default=8443, help="puerto para el teléfono (8443)")
    p.add_argument("--http-port", type=int, default=8081, help="puerto del visor y los streams (8081)")
    p.add_argument("--host", default="0.0.0.0", help="interfaz donde escuchar (0.0.0.0 = todas)")
    p.add_argument("--token", help="si se indica, todas las URLs exigen ?token=...")
    p.add_argument("--esp32", default=IP_ESP32, help=f"IP del ESP32 ({IP_ESP32})")
    p.add_argument("--clase", default=CLASE_OBJETIVO, help=f"clase que activa el ESP32 ({CLASE_OBJETIVO})")
    args = p.parse_args()

    if args.fuente is not None:
        modo_clasico(args.fuente, args)
    else:
        try:
            asyncio.run(servidor(args))
        except KeyboardInterrupt:
            print("\nServidor detenido")
