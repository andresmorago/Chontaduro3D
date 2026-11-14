"""Protocolo de la Bambu Lab A1 por MQTT local: leer el estado y construir órdenes.

La impresora publica en `device/<serie>/report` y recibe en `device/<serie>/request`. Usuario
`bblp`, contraseña = código de acceso. Estas funciones son puras (sin red) para poder probarlas."""

import json
import ssl
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

# gcode_state de la impresora → estado en español que usa la app.
ESTADOS = {
    "IDLE": "lista",
    "PREPARE": "preparando",
    "RUNNING": "imprimiendo",
    "PAUSE": "pausada",
    "FINISH": "terminada",
    "FAILED": "fallida",
}
ACTIVOS = {"PREPARE", "RUNNING", "PAUSE"}
VELOCIDADES = {"1": "Silencioso", "2": "Estándar", "3": "Deportivo", "4": "Ludicrous"}

# Órdenes con un valor numérico → (mínimo, máximo, unidad). Límites de la A1; la boquilla admite 0
# (apagar) o de BOQUILLA_MIN hacia arriba: por debajo no hay nada útil que hacer con ella.
LIMITES = {
    "temp_boquilla": (0, 300, "°C"),
    "temp_cama": (0, 100, "°C"),
    "ventilador_pieza": (0, 100, "%"),
    "ventilador_aux": (0, 100, "%"),
}
BOQUILLA_MIN = 150
NOMBRES_NUMERICOS = {
    "temp_boquilla": "La temperatura de la boquilla",
    "temp_cama": "La temperatura de la cama",
    "ventilador_pieza": "El ventilador de la pieza",
    "ventilador_aux": "El ventilador auxiliar",
}


def validar_numero(comando: str, valor: str | None) -> int:
    """El valor entero de una orden numérica, o ValueError con un mensaje claro."""
    minimo, maximo, unidad = LIMITES[comando]
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{NOMBRES_NUMERICOS[comando]} debe ser un número entero.") from None
    if not minimo <= n <= maximo:
        raise ValueError(f"{NOMBRES_NUMERICOS[comando]} va de {minimo} a {maximo} {unidad}.")
    if comando == "temp_boquilla" and 0 < n < BOQUILLA_MIN:
        raise ValueError(f"La boquilla se apaga (0) o va de {BOQUILLA_MIN} a {maximo} °C.")
    return n


def _entero(v: Any) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _ventilador(v: Any) -> int | None:
    """La impresora informa los ventiladores en 15 pasos (0–15): se muestran en %."""
    g = _entero(v)
    return round(g * 100 / 15) if g is not None and 0 <= g <= 15 else None


def _numero(v: Any) -> float | None:
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def _color(v: Any) -> str | None:
    """«RRGGBBAA» (como lo informa el AMS) → «#rrggbb»."""
    s = str(v or "").strip().lstrip("#")
    if len(s) >= 6 and all(c in "0123456789abcdefABCDEF" for c in s[:6]):
        return "#" + s[:6].lower()
    return None


def _bandeja(t: dict[str, Any], en_uso: bool) -> dict[str, Any]:
    tipo = str(t.get("tray_type") or "").strip()
    restante = _entero(t.get("remain"))
    # El «restante» solo es una medición real en bobinas Bambu con chip RFID (tag_uid ≠ 0). Sin chip
    # la impresora no sabe cuánto queda: informa 100 por defecto (ranuras) o 0 (bobina externa).
    medido = bool(str(t.get("tag_uid") or "").strip("0"))
    return {
        "id": str(t.get("id", "")),
        "vacia": not tipo,
        "tipo": tipo or None,
        "marca": str(t.get("tray_sub_brands") or "").strip() or None,
        "color": _color(t.get("tray_color")) if tipo else None,
        "medido": medido,
        "restante": restante if medido and restante is not None and restante >= 0 else None,
        "en_uso": en_uso,
    }


def normalizar(raw: dict[str, Any]) -> dict[str, Any]:
    """Lo que la app necesita del estado, sin identificadores ni datos de red de la impresora."""
    gcode_state = raw.get("gcode_state")
    luz = None
    for fila in raw.get("lights_report") or []:
        if isinstance(fila, dict) and fila.get("node") in ("chamber_light", "work_light"):
            luz = fila.get("mode")
            break

    ams: list[dict[str, Any]] = []
    en_uso = str((raw.get("ams") or {}).get("tray_now", ""))
    for unidad in (raw.get("ams") or {}).get("ams", []) or []:
        base = (_entero(unidad.get("id")) or 0) * 4
        for t in unidad.get("tray", []) or []:
            pos = base + (_entero(t.get("id")) or 0)
            ams.append(_bandeja(t, en_uso == str(pos)))
    externa = raw.get("vt_tray")
    return {
        "estado": ESTADOS.get(str(gcode_state), "desconocido"),
        "gcode_state": gcode_state,
        "trabajo": raw.get("subtask_name") or None,
        "archivo": raw.get("gcode_file") or None,
        "progreso": _entero(raw.get("mc_percent")),
        "capa": _entero(raw.get("layer_num")),
        "capas": _entero(raw.get("total_layer_num")),
        "restante_min": _entero(raw.get("mc_remaining_time")),
        "boquilla": _numero(raw.get("nozzle_temper")),
        "boquilla_objetivo": _numero(raw.get("nozzle_target_temper")),
        "cama": _numero(raw.get("bed_temper")),
        "cama_objetivo": _numero(raw.get("bed_target_temper")),
        "boquilla_mm": raw.get("nozzle_diameter") or None,
        "velocidad": _entero(raw.get("spd_lvl")),
        "ventilador_pieza": _ventilador(raw.get("cooling_fan_speed")),
        "ventilador_aux": _ventilador(raw.get("big_fan1_speed")),
        "luz": luz if luz in ("on", "off") else None,
        "wifi": raw.get("wifi_signal") or None,
        "error": _entero(raw.get("print_error")) or 0,
        "alertas": len(raw.get("hms") or []),
        "ams": ams,
        "externa": _bandeja(externa, en_uso == "254") if isinstance(externa, dict) else None,
    }


def construir_orden(
    comando: str, valor: str | None = None, nodo_luz: str = "chamber_light"
) -> dict:
    """Mensaje MQTT para una orden de la app. Lanza ValueError si no es válida."""
    sec = "0"
    if comando in ("pausar", "reanudar", "cancelar"):
        nombre = {"pausar": "pause", "reanudar": "resume", "cancelar": "stop"}[comando]
        return {"print": {"sequence_id": sec, "command": nombre, "param": ""}}
    if comando == "luz":
        if valor not in ("on", "off"):
            raise ValueError("La luz admite «on» u «off».")
        return {
            "system": {
                "sequence_id": sec, "command": "ledctrl", "led_node": nodo_luz,
                "led_mode": valor, "led_on_time": 500, "led_off_time": 500,
                "loop_times": 0, "interval_time": 0,
            }
        }  # fmt: skip
    if comando == "velocidad":
        if valor not in VELOCIDADES:
            raise ValueError("La velocidad va de 1 a 4.")
        return {"print": {"sequence_id": sec, "command": "print_speed", "param": valor}}
    if comando in LIMITES:
        n = validar_numero(comando, valor)
        # G-code de Marlin que entiende la A1; debe terminar en salto de línea.
        gcode = {
            "temp_boquilla": f"M104 S{n}",
            "temp_cama": f"M140 S{n}",
            "ventilador_pieza": f"M106 P1 S{(n * 255 + 50) // 100}",
            "ventilador_aux": f"M106 P2 S{(n * 255 + 50) // 100}",
        }[comando]
        return {"print": {"sequence_id": sec, "command": "gcode_line", "param": gcode + "\n"}}
    raise ValueError(f"Orden desconocida: {comando}")


class ClienteBambu:
    """Conexión MQTT con reconexión automática. El estado se va completando con cada mensaje
    (la A1 manda solo lo que cambió) y se refresca con un «pushall» periódico."""

    def __init__(self, ip: str, serie: str, codigo: str) -> None:
        import paho.mqtt.client as mqtt

        self._ip, self._serie = ip, serie
        self._lock = threading.Lock()
        self._estado: dict[str, Any] = {}
        self._ultimo: datetime | None = None
        self._conectada = False
        # Cliente único por proceso: dos con el mismo id se expulsan entre sí.
        self._c = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=f"misimpresiones-{uuid.uuid4().hex[:8]}"
        )
        self._c.username_pw_set("bblp", codigo)
        # La impresora usa un certificado propio (autofirmado) y se alcanza por IP de la red local.
        self._c.tls_set(cert_reqs=ssl.CERT_NONE)
        self._c.tls_insecure_set(True)
        self._c.reconnect_delay_set(min_delay=2, max_delay=30)
        self._c.on_connect = self._al_conectar
        self._c.on_disconnect = self._al_desconectar
        self._c.on_message = self._al_mensaje

    # --- ciclo de vida ---
    def iniciar(self) -> None:
        self._c.connect_async(self._ip, 8883, keepalive=30)
        self._c.loop_start()

    def detener(self) -> None:
        self._c.loop_stop()
        self._c.disconnect()

    # --- callbacks (hilo de paho) ---
    def _al_conectar(self, cliente, _u, _f, rc, *_a) -> None:
        if getattr(rc, "is_failure", False):
            return
        with self._lock:
            self._conectada = True
        cliente.subscribe(f"device/{self._serie}/report")
        self.pedir_todo()

    def _al_desconectar(self, *_a) -> None:
        with self._lock:
            self._conectada = False

    def _al_mensaje(self, _c, _u, m) -> None:
        try:
            datos = json.loads(m.payload).get("print")
        except (ValueError, AttributeError):
            return
        if isinstance(datos, dict):
            with self._lock:
                self._estado.update(datos)
                self._ultimo = datetime.now(UTC)

    # --- uso desde el servicio ---
    def pedir_todo(self) -> None:
        self._publicar({"pushing": {"sequence_id": "0", "command": "pushall"}})

    def _publicar(self, orden: dict) -> bool:
        info = self._c.publish(f"device/{self._serie}/request", json.dumps(orden), qos=0)
        return info.rc == 0

    def enviar(self, comando: str, valor: str | None = None) -> bool:
        nodo = "chamber_light"
        for fila in self.crudo().get("lights_report") or []:
            if isinstance(fila, dict) and fila.get("node"):
                nodo = fila["node"]
                break
        return self._publicar(construir_orden(comando, valor, nodo))

    @property
    def conectada(self) -> bool:
        with self._lock:
            return self._conectada

    def crudo(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._estado)

    @property
    def ultimo_mensaje(self) -> datetime | None:
        with self._lock:
            return self._ultimo
