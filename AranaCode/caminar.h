#ifndef CAMINAR_H
#define CAMINAR_H

#include <Arduino.h>
#include "estabilizador.h"

/*
 * caminar.h - Generación de patrones de marcha para el Robot Araña
 */

enum EstadoMarcha {
    MARCHA_STOP = 0,
    MARCHA_ADELANTE,
    MARCHA_ATRAS,
    MARCHA_GIRAR_IZQ,
    MARCHA_GIRAR_DER
};

inline void darPasoAdelante() {
    Serial.println("[MARCHA] Ejecutando paso: ADELANTE >>");
    // Secuencia cinemática de patas (gait) hacia adelante
}

inline void darPasoAtras() {
    Serial.println("[MARCHA] Ejecutando paso: ATRAS <<");
    // Secuencia cinemática de patas hacia atrás
}

inline void girarIzquierda() {
    Serial.println("[MARCHA] Ejecutando giro: IZQUIERDA <=");
    // Secuencia cinemática de rotación sobre su eje
}

inline void girarDerecha() {
    Serial.println("[MARCHA] Ejecutando giro: DERECHA =>");
    // Secuencia cinemática de rotación sobre su eje
}

inline void detenerMarcha() {
    Serial.println("[MARCHA] DETENIDO (STOP).");
    posturaNeutral();
}

#endif // CAMINAR_H
