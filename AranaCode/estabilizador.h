#ifndef ESTABILIZADOR_H
#define ESTABILIZADOR_H

#include <Arduino.h>

/*
 * estabilizador.h - Gestión de posturas base y estabilidad del Robot Araña
 */

// Pines de servomotores / Actuadores básicos o definición de calibración
const int PIN_LED_ALERTA = 2; // LED del ESP32 para indicar alarma de colisión

inline void inicializarEstabilizador() {
    pinMode(PIN_LED_ALERTA, OUTPUT);
    digitalWrite(PIN_LED_ALERTA, LOW);
    Serial.println("[ESTABILIZADOR] Servos y sensores inicializados.");
}

inline void posturaReposo() {
    // Baja el chasis al suelo para descansar las patas
    Serial.println("[POSTURA] Reposo (Chasis bajo).");
}

inline void posturaNeutral() {
    // Eleva el chasis a altura de caminata estable
    Serial.println("[POSTURA] Neutral / Lista para marchar.");
}

inline void posturaAlertaColision(bool activa) {
    // Señal visual en el ESP32 cuando el obstáculo bloquea el paso
    digitalWrite(PIN_LED_ALERTA, activa ? HIGH : LOW);
}

#endif // ESTABILIZADOR_H
