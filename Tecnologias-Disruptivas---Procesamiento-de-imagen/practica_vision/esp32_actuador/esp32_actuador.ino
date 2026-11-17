// esp32_actuador.ino - Servidor web en ESP32 con Actuador y Seguridad Anticolisión
// Petición clásica:   http://<IP_DEL_ESP32>/led?estado=on (u off)
// Petición seguridad: http://<IP_DEL_ESP32>/seguridad?bloqueo=1 (o 0)
// Petición control:   http://<IP_DEL_ESP32>/control?cmd=ADELANTE (o ATRAS, GIRAR_IZQ, etc.)
#include <WiFi.h>
#include <WebServer.h>

const char* SSID = "NOMBRE_RED";        // <-- Misma red WiFi que el PC / Raspberry Pi
const char* PASS = "CLAVE_RED";
const int PIN_LED = 2;                  // LED integrado en ESP32 DevKit

WebServer servidor(80);

bool bloqueoObstaculoActivo = false;
String estadoMovimiento = "STOP";

void manejarLed() {
  String estado = servidor.arg("estado");
  digitalWrite(PIN_LED, estado == "on" ? HIGH : LOW);
  servidor.send(200, "text/plain", "LED " + estado);
  Serial.println("[ACTUADOR] LED: " + estado);
}

void manejarSeguridad() {
  String valor = servidor.arg("bloqueo");
  bloqueoObstaculoActivo = (valor == "1" || valor == "true" || valor == "on");
  
  if (bloqueoObstaculoActivo) {
    digitalWrite(PIN_LED, HIGH); // Alerta visual de bloqueo
    Serial.println("\n[SEGURIDAD IA] >> ¡OBSTACULO EN CAMINO! Bloqueo de avance activado.");
    if (estadoMovimiento == "ADELANTE") {
      estadoMovimiento = "STOP";
      Serial.println("[SEGURIDAD IA] >> Freno de emergencia automático ejecutado.");
    }
  } else {
    digitalWrite(PIN_LED, LOW);
    Serial.println("[SEGURIDAD IA] Camino despejado. Avance habilitado.");
  }
  servidor.send(200, "text/plain", bloqueoObstaculoActivo ? "BLOQUEO_ACTIVO" : "CAMINO_LIBRE");
}

void manejarControl() {
  String cmd = servidor.arg("cmd");
  cmd.toUpperCase();
  
  if (cmd == "ADELANTE") {
    // PASO 2: VETO ACTIVO DE COLISIÓN
    if (bloqueoObstaculoActivo) {
      estadoMovimiento = "STOP";
      Serial.println("[VETO ANTICHOQUE] >> El humano ordenó ADELANTE, pero la IA detectó un obstáculo. ¡Acción bloqueada!");
      servidor.send(403, "text/plain", "ACCION_BLOQUEADA: Obstaculo en la trayectoria");
      return;
    } else {
      estadoMovimiento = "ADELANTE";
      Serial.println("[MOVIMIENTO] Avanzando...");
      servidor.send(200, "text/plain", "EJECUTANDO_ADELANTE");
      return;
    }
  } else if (cmd == "ATRAS") {
    estadoMovimiento = "ATRAS";
    Serial.println("[MOVIMIENTO] Retrocediendo de forma segura.");
    servidor.send(200, "text/plain", "EJECUTANDO_ATRAS");
  } else if (cmd == "GIRAR_IZQ" || cmd == "IZQUIERDA") {
    estadoMovimiento = "GIRAR_IZQ";
    Serial.println("[MOVIMIENTO] Girando a la izquierda para esquivar.");
    servidor.send(200, "text/plain", "EJECUTANDO_GIRAR_IZQ");
  } else if (cmd == "GIRAR_DER" || cmd == "DERECHA") {
    estadoMovimiento = "GIRAR_DER";
    Serial.println("[MOVIMIENTO] Girando a la derecha para esquivar.");
    servidor.send(200, "text/plain", "EJECUTANDO_GIRAR_DER");
  } else if (cmd == "STOP") {
    estadoMovimiento = "STOP";
    Serial.println("[MOVIMIENTO] Detenido.");
    servidor.send(200, "text/plain", "EJECUTANDO_STOP");
  } else {
    servidor.send(400, "text/plain", "COMANDO_DESCONOCIDO");
  }
}

void manejarStatus() {
  String json = "{";
  json += "\"bloqueo_obstaculo\":" + String(bloqueoObstaculoActivo ? "true" : "false") + ",";
  json += "\"movimiento\":\"" + estadoMovimiento + "\"";
  json += "}";
  servidor.send(200, "application/json", json);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  WiFi.begin(SSID, PASS);
  Serial.print("Conectando a WiFi...");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.print("\nIP del ESP32: ");
  Serial.println(WiFi.localIP());

  servidor.on("/led", manejarLed);
  servidor.on("/seguridad", manejarSeguridad);
  servidor.on("/control", manejarControl);
  servidor.on("/status", manejarStatus);
  servidor.begin();
  Serial.println("Servidor web listo.");
}

void loop() {
  servidor.handleClient();
}
