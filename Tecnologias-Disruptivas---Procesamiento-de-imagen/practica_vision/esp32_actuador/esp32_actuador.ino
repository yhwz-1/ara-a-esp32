// esp32_actuador.ino - Servidor web mínimo en el ESP32 que recibe órdenes de la Raspberry Pi.
// Petición esperada:  http://<IP_DEL_ESP32>/led?estado=on   (u off)
#include <WiFi.h>
#include <WebServer.h>

const char* SSID = "NOMBRE_RED";        // <-- misma red WiFi que la Raspberry Pi
const char* PASS = "CLAVE_RED";
const int PIN_LED = 2;                  // LED integrado en muchas placas ESP32 DevKit

WebServer servidor(80);

void manejarLed() {
  String estado = servidor.arg("estado");
  digitalWrite(PIN_LED, estado == "on" ? HIGH : LOW);
  servidor.send(200, "text/plain", "LED " + estado);
  Serial.println("Orden recibida: " + estado);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  WiFi.begin(SSID, PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.print("\nIP del ESP32: ");
  Serial.println(WiFi.localIP());       // copiar esta IP en 06_yolo_esp32.py
  servidor.on("/led", manejarLed);
  servidor.begin();
}

void loop() {
  servidor.handleClient();
}
