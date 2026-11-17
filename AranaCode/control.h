#ifndef CONTROL_H
#define CONTROL_H

#include <Arduino.h>
#include "caminar.h"
#include "estabilizador.h"

/*
 * control.h - Árbitro de Control y Sistema de Seguridad Activa Antichoque
 *
 * REGLA FUNDAMENTAL DE SEGURIDAD:
 * Si la IA de visión detecta un obstáculo o estructura en la trayectoria frontal,
 * se activa `bloqueoObstaculoActivo = true`.
 * Aunque el operador humano insista en enviar la orden "ADELANTE", el árbitro
 * de seguridad intercepta y bloquea la acción para impedir físicamente la colisión.
 * Sí se permiten movimientos de escape: RETROCEDER o GIRAR.
 */

// Banderas de estado
extern bool bloqueoObstaculoActivo;
extern String ultimoComandoHumano;
extern unsigned long tiempoUltimoComando;

inline void actualizarSeguridadIA(bool hayObstaculo) {
    bloqueoObstaculoActivo = hayObstaculo;
    posturaAlertaColision(hayObstaculo);
    
    if (bloqueoObstaculoActivo) {
        Serial.println("[SEGURIDAD IA] ALERTA: Obstáculo detectado en trayectoria. Veto de avance ACTIVADO.");
        // Si el robot estaba caminando hacia adelante, frenar de inmediato
        if (ultimoComandoHumano == "ADELANTE") {
            detenerMarcha();
        }
    } else {
        Serial.println("[SEGURIDAD IA] Camino despejado. Avance permitido.");
    }
}

inline String procesarComandoHumano(String comando) {
    comando.toUpperCase();
    ultimoComandoHumano = comando;
    tiempoUltimoComando = millis();

    if (comando == "ADELANTE") {
        if (bloqueoObstaculoActivo) {
            // INTERCEPCIÓN DE SEGURIDAD (VIRTUAL BUMPER OVERRIDE)
            detenerMarcha();
            posturaAlertaColision(true);
            Serial.println("[SEGURIDAD ACTIVA] >> VETO EJECUTADO: El humano intentó avanzar hacia un obstáculo. Colisión impedida.");
            return "BLOQUEADO_POR_OBSTACULO";
        } else {
            darPasoAdelante();
            return "EJECUTANDO_ADELANTE";
        }
    } 
    else if (comando == "ATRAS") {
        // El retroceso siempre está habilitado para retirarse del peligro
        darPasoAtras();
        return "EJECUTANDO_ATRAS";
    } 
    else if (comando == "GIRAR_IZQ" || comando == "IZQUIERDA") {
        // Giro habilitado para buscar un camino alternativo
        girarIzquierda();
        return "EJECUTANDO_GIRO_IZQ";
    } 
    else if (comando == "GIRAR_DER" || comando == "DERECHA") {
        // Giro habilitado para buscar un camino alternativo
        girarDerecha();
        return "EJECUTANDO_GIRO_DER";
    } 
    else if (comando == "STOP" || comando == "DETENER") {
        detenerMarcha();
        return "EJECUTANDO_STOP";
    } 
    else {
        Serial.println("[CONTROL] Comando desconocido: " + comando);
        return "COMANDO_INVALIDO";
    }
}

#endif // CONTROL_H
