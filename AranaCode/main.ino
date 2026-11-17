/*
 * main.ino - Firmware para Robot Araña con ESP32 y Prevención Activa de Colisiones
 *
 * Recibe:
 * 1. Comandos del operador humano (vía WiFi HTTP /control o Monitor Serie).
 * 2. Estado de seguridad y telemetría de la IA (vía WiFi HTTP /seguridad y /telemetria).
 *
 * Si la IA detecta que el camino está bloqueado, se anulan automáticamente
 * los intentos humanos de avanzar hacia el obstáculo.
 */

#include <WiFi.h>
#include <WebServer.h>
#include "estabilizador.h"
#include "caminar.h"
#include "control.h"

// ================= CONFIGURACIÓN DE RED =================
const char* SSID_WIFI = "NOMBRE_DE_TU_WIFI";
const char* PASS_WIFI = "CONTRASENA_WIFI";

WebServer servidorWeb(80);

// Variables globales de control
bool bloqueoObstaculoActivo = false;
String ultimoComandoHumano = "STOP";
unsigned long tiempoUltimoComando = 0;

// ================= MANEJADORES DE SERVIDOR WEB =================

// Endpoint para el operador humano: /control?cmd=ADELANTE
void manejarControlHumano() {
    if (!servidorWeb.hasArg("cmd")) {
        servidorWeb.send(400, "text/plain", "Falta parametro 'cmd'");
        return;
    }
    String cmd = servidorWeb.arg("cmd");
    String resultado = procesarComandoHumano(cmd);
    
    servidorWeb.send(200, "application/json", 
        "{\"comando\":\"" + cmd + "\",\"resultado\":\"" + resultado + "\",\"bloqueo_activo\":" + (bloqueoObstaculoActivo ? "true" : "false") + "}");
}

// Endpoint para la IA de Visión (Python / YOLO): /seguridad?bloqueo=1
void manejarSeguridadIA() {
    if (!servidorWeb.hasArg("bloqueo")) {
        servidorWeb.send(400, "text/plain", "Falta parametro 'bloqueo' (1 o 0)");
        return;
    }
    String estado = servidorWeb.arg("bloqueo");
    bool bloquear = (estado == "1" || estado == "true" || estado == "on");
    
    actualizarSeguridadIA(bloquear);
    
    servidorWeb.send(200, "text/plain", bloquear ? "BLOQUEO_ACTIVO" : "CAMINO_LIBRE");
}

// Endpoint para recibir paquete de telemetría completo (JSON)
void manejarTelemetriaIA() {
    if (servidorWeb.hasArg("plain")) {
        String jsonPayload = servidorWeb.arg("plain");
        // Serial.println("[TELEMETRIA IA RECIBIDA]: " + jsonPayload);
    }
    servidorWeb.send(200, "application/json", "{\"status\":\"ok\"}");
}

// Endpoint de estado general: /status
void manejarStatus() {
    String json = "{";
    json += "\"bloqueo_obstaculo\":" + String(bloqueoObstaculoActivo ? "true" : "false") + ",";
    json += "\"ultimo_comando\":\"" + ultimoComandoHumano + "\",";
    json += "\"ip\":\"" + WiFi.localIP().toString() + "\"";
    json += "}";
    servidorWeb.send(200, "application/json", json);
}

// ================= SETUP Y LOOP =================

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n--- INICIALIZANDO ROBOT ARANA ESP32 ---");

    inicializarEstabilizador();
    posturaNeutral();

    // Conectar a la red WiFi
    Serial.print("Conectando a WiFi: ");
    Serial.println(SSID_WIFI);
    WiFi.begin(SSID_WIFI, PASS_WIFI);

    // Timeout de 15 segundos para WiFi
    unsigned long t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
        delay(500);
        Serial.print(".");
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi conectado exitosamente!");
        Serial.print("Direccion IP asignada: ");
        Serial.println(WiFi.localIP());
        Serial.println("Usa esta IP en el script Python: vision_arana_obstaculos.py --esp32 " + WiFi.localIP().toString());
    } else {
        Serial.println("\n[AVISO] No se pudo conectar a WiFi. Funcionando en modo Serial local.");
    }

    // Configurar rutas del servidor web
    servidorWeb.on("/control", manejarControlHumano);
    servidorWeb.on("/seguridad", manejarSeguridadIA);
    servidorWeb.on("/telemetria", HTTP_POST, manejarTelemetriaIA);
    servidorWeb.on("/status", manejarStatus);
    servidorWeb.begin();

    Serial.println("Comandos disponibles en Monitor Serie:");
    Serial.println("  w -> ADELANTE");
    Serial.println("  s -> ATRAS");
    Serial.println("  a -> GIRAR IZQUIERDA");
    Serial.println("  d -> GIRAR DERECHA");
    Serial.println("  x -> STOP");
    Serial.println("  b -> SIMULAR BLOQUEO DE OBSTACULO (ON/OFF)");
}

void loop() {
    servidorWeb.handleClient();

    // Control opcional por Monitor Serie para pruebas rápidas en laboratorio
    if (Serial.available()) {
        char tecla = Serial.read();
        switch (tecla) {
            case 'w': case 'W': procesarComandoHumano("ADELANTE"); break;
            case 's': case 'S': procesarComandoHumano("ATRAS"); break;
            case 'a': case 'A': procesarComandoHumano("GIRAR_IZQ"); break;
            case 'd': case 'D': procesarComandoHumano("GIRAR_DER"); break;
            case 'x': case 'X': procesarComandoHumano("STOP"); break;
            case 'b': case 'B': 
                actualizarSeguridadIA(!bloqueoObstaculoActivo); 
                break;
        }
    }
}
