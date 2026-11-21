"""Protocolo de la A1, lector de .3mf y detección de trabajos (sin red ni impresora)."""

import io
import zipfile
from decimal import Decimal

import pytest

from app.impresora import bambu, lector3mf, maquina

# Un mensaje real de la A1 (recortado y con valores de ejemplo).
CRUDO = {
    "gcode_state": "RUNNING", "subtask_name": "tfic-angled", "gcode_file": "tfic-angled.3mf",
    "task_id": "1440858776", "mc_percent": 85, "mc_remaining_time": 9, "layer_num": 91,
    "total_layer_num": 100, "nozzle_temper": 230.125, "nozzle_target_temper": 230,
    "bed_temper": 64.875, "bed_target_temper": 65, "nozzle_diameter": "0.4", "spd_lvl": 2,
    "wifi_signal": "-28dBm", "print_error": 0, "hms": [],
    "lights_report": [{"node": "chamber_light", "mode": "on"}],
    "ams": {
        "tray_now": "1",
        "ams": [{"id": "0", "tray": [
            {"id": "0", "tray_type": "PLA", "tray_color": "000000FF", "remain": 100,
             "tag_uid": "B9656CFE00000100", "tray_sub_brands": "PLA Basic"},
            {"id": "1", "tray_type": "PLA", "tray_color": "FFFFFFFF", "remain": 100,
             "tag_uid": "0000000000000000"},
            {"id": "2", "tray_type": "", "tray_color": "00000000", "remain": -1},
        ]}],
    },
    "vt_tray": {"id": "254", "tray_type": "PETG", "tray_color": "443089FF", "remain": 0,
                "tag_uid": "0000000000000000"},
    "sn": "NO-DEBE-SALIR", "net": {"conf": 1}, "ipcam": {"x": 1},
}  # fmt: skip


def test_normalizar_estado():
    n = bambu.normalizar(CRUDO)
    assert n["estado"] == "imprimiendo" and n["trabajo"] == "tfic-angled"
    assert (n["progreso"], n["capa"], n["capas"], n["restante_min"]) == (85, 91, 100, 9)
    assert (n["boquilla"], n["cama"], n["velocidad"], n["luz"]) == (230.1, 64.9, 2, "on")
    assert n["ams"][0] == {
        "id": "0", "vacia": False, "tipo": "PLA", "marca": "PLA Basic", "color": "#000000",
        "medido": True, "tag": "B9656CFE00000100", "peso": None, "restante": 100, "en_uso": False,
    }  # fmt: skip
    # Sin chip RFID la impresora no mide: el 100 de una ranura y el 0 de la externa no son datos.
    assert n["ams"][1]["medido"] is False and n["ams"][1]["restante"] is None
    assert n["externa"]["medido"] is False and n["externa"]["restante"] is None
    # Y sin chip no hay UID que identifique la bobina (el 0000… no es un identificador).
    assert n["ams"][1]["tag"] is None and n["externa"]["tag"] is None
    assert n["ams"][1]["en_uso"] is True and n["ams"][1]["color"] == "#ffffff"
    assert n["ams"][2]["vacia"] is True and n["ams"][2]["color"] is None
    assert n["ams"][2]["restante"] is None  # -1 = desconocido
    assert n["externa"]["tipo"] == "PETG" and n["externa"]["color"] == "#443089"
    # Nada de identificadores ni datos de red de la impresora.
    assert "NO-DEBE-SALIR" not in str(n) and "net" not in n and "sn" not in n


@pytest.mark.parametrize(
    ("gcode", "esperado"),
    [("IDLE", "lista"), ("PREPARE", "preparando"), ("PAUSE", "pausada"), ("FINISH", "terminada"),
     ("FAILED", "fallida"), ("XXX", "desconocido"), (None, "desconocido")],
)  # fmt: skip
def test_estados_en_espanol(gcode, esperado):
    assert bambu.normalizar({"gcode_state": gcode})["estado"] == esperado


def test_normalizar_tolera_mensaje_vacio_o_raro():
    n = bambu.normalizar(
        {"mc_percent": "x", "ams": {"ams": [{"tray": [{}]}]}, "lights_report": "?"}
    )
    assert n["progreso"] is None and n["luz"] is None and n["ams"][0]["vacia"] is True


def test_ordenes():
    assert bambu.construir_orden("pausar")["print"]["command"] == "pause"
    assert bambu.construir_orden("reanudar")["print"]["command"] == "resume"
    assert bambu.construir_orden("cancelar")["print"]["command"] == "stop"
    luz = bambu.construir_orden("luz", "off", "chamber_light")["system"]
    assert luz["command"] == "ledctrl" and luz["led_mode"] == "off"
    assert bambu.construir_orden("velocidad", "3")["print"]["param"] == "3"
    for malo in (("luz", "x"), ("velocidad", "9"), ("velocidad", None), ("explotar", None)):
        with pytest.raises(ValueError):
            bambu.construir_orden(*malo)


# --------------------------------------------------------------------------- máquina
def snap(estado, nombre="Pieza", tarea="100", progreso=0, archivo="pieza.3mf"):
    return maquina.Instantanea(estado, nombre, archivo, tarea, progreso)


ABIERTO = maquina.Abierto("Pieza", "pieza.3mf", "100")


def test_trabajo_se_abre_al_preparar_o_imprimir():
    for estado in ("PREPARE", "RUNNING", "PAUSE"):
        assert maquina.decidir(snap(estado), None) == [maquina.Accion(abrir=True)]
    for estado in ("IDLE", "FINISH", "FAILED", None):
        assert maquina.decidir(snap(estado), None) == []  # un FINISH viejo no es un trabajo nuevo
    assert maquina.decidir(snap("RUNNING", nombre=""), None) == []  # aún sin nombre


def test_trabajo_termina_con_finish():
    assert maquina.decidir(snap("FINISH", progreso=100), ABIERTO) == [
        maquina.Accion(cerrar="terminado")
    ]


def test_cancelado_o_fallido_queda_interrumpido():
    for estado in ("FAILED", "IDLE"):
        assert maquina.decidir(snap(estado), ABIERTO) == [maquina.Accion(cerrar="interrumpido")]


def test_mientras_imprime_solo_actualiza_progreso_aunque_cambie_el_archivo():
    # El nombre del archivo puede llegar tarde: con el mismo task_id es el mismo trabajo.
    acc = maquina.decidir(snap("RUNNING", archivo="otra-cosa.3mf", progreso=40), ABIERTO)
    assert acc == [maquina.Accion(actualizar_progreso=True)]


def test_trabajo_nuevo_sin_ver_el_final_del_anterior():
    acc = maquina.decidir(snap("RUNNING", nombre="Otra", tarea="200"), ABIERTO)
    assert acc == [maquina.Accion(cerrar="interrumpido"), maquina.Accion(abrir=True)]


def test_sin_task_id_se_compara_por_nombre():
    sin_id = maquina.Abierto("Pieza", "x.3mf", "0")
    assert maquina.decidir(snap("RUNNING", tarea="0"), sin_id)[0].actualizar_progreso
    assert maquina.decidir(snap("RUNNING", nombre="Otra", tarea="0"), sin_id)[0].cerrar


def test_instantanea_de_crudo():
    s = maquina.instantanea_de(CRUDO)
    assert (s.nombre, s.tarea_id, s.progreso, s.gcode_state) == (
        "tfic-angled",
        "1440858776",
        85,
        "RUNNING",
    )
    assert maquina.instantanea_de({}).gcode_state is None


# -------------------------------------------------------------------------- lector .3mf
def hacer_3mf(plates: list[dict]) -> bytes:
    filas = []
    for p in plates:
        fil = "".join(
            f'<filament id="{i}" type="{f[0]}" color="{f[1]}" used_m="1" used_g="{f[2]}"/>'
            for i, f in enumerate(p.get("filamentos", []), 1)
        )
        filas.append(
            f'<plate><metadata key="index" value="{p["index"]}"/>'
            f'<metadata key="prediction" value="{p.get("seg", 3600)}"/>'
            f'<metadata key="weight" value="{p.get("peso", 10)}"/>{fil}</plate>'
        )
    xml = f'<?xml version="1.0"?><config>{"".join(filas)}</config>'
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("Metadata/slice_info.config", xml)
    return b.getvalue()


def test_lee_gramos_tiempo_y_filamentos():
    datos = hacer_3mf(
        [{"index": 2, "seg": 1072, "peso": "0.88", "filamentos": [("PLA", "#FFB673", "0.88")]}]
    )
    info = lector3mf.analizar_3mf(datos)
    assert info.plate == 2 and info.minutos == 18 and info.gramos == Decimal("0.88")
    assert info.filamentos == [{"tipo": "PLA", "color": "#ffb673", "gramos": 0.88}]


def test_varias_plates_exigen_saber_cual():
    datos = hacer_3mf([{"index": 1, "peso": 5}, {"index": 2, "peso": 7, "seg": 120}])
    assert lector3mf.analizar_3mf(datos) is None  # ambiguo: mejor sin dato que uno equivocado
    assert lector3mf.analizar_3mf(datos, plate=2).gramos == Decimal("7.00")
    assert lector3mf.analizar_3mf(datos, plate=2).minutos == 2
    assert lector3mf.analizar_3mf(datos, plate=3) is None


def test_peso_se_suma_de_filamentos_si_falta():
    datos = hacer_3mf(
        [{"index": 1, "peso": 0, "filamentos": [("PLA", "#000000", "3.5"), ("PLA", "#fff", "1.5")]}]
    )
    assert lector3mf.analizar_3mf(datos).gramos == Decimal("5.00")


def test_archivo_invalido_o_sin_metadatos():
    assert lector3mf.analizar_3mf(b"no es un zip") is None
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("otra.txt", "x")
    assert lector3mf.analizar_3mf(b.getvalue()) is None


def test_xml_de_metadatos_gigante_se_rechaza():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Metadata/slice_info.config", "<config>" + " " * (6 * 1024 * 1024) + "</config>")
    assert lector3mf.analizar_3mf(b.getvalue()) is None


def test_plate_y_eleccion_de_archivo():
    assert lector3mf.plate_de("Snowman_plate_2.3mf") == 2 and lector3mf.plate_de("x", None) is None
    nombres = [
        "tfic-angled.3mf",
        "Snowman_Trees_plate_2.3mf",
        "otra.gcode",
        "octopus_plate_2.gcode.3mf",
    ]
    assert lector3mf.elegir_archivo(nombres, "tfic-angled.3mf", "tfic-angled") == "tfic-angled.3mf"
    # Impresión local: el archivo es una ruta interna; se encuentra por el nombre del trabajo.
    assert (
        lector3mf.elegir_archivo(nombres, "/data/Metadata/plate_2.gcode", "octopus_plate_2")
        == "octopus_plate_2.gcode.3mf"
    )
    assert (
        lector3mf.elegir_archivo(nombres, None, "Snowman Trees plate 2")
        == "Snowman_Trees_plate_2.3mf"
    )
    assert lector3mf.elegir_archivo(nombres, "nada.3mf", "nada") is None


def test_un_nombre_exacto_en_cache_gana_a_uno_parecido_en_la_raiz():
    # Caso real: `/` tenía un DestapaLatas_plate_2.gcode.3mf nuevo (38 g) y `/cache` el
    # DestapaLatas_plate_2.3mf que de verdad se imprimió (173 g).
    listados = {
        "/": {"DestapaLatas_plate_2.gcode.3mf": 1000},
        "/cache": {"DestapaLatas_plate_2.3mf": 3767, "otro.3mf": 1},
    }
    elegir = lector3mf.elegir_en_carpetas
    assert elegir(listados, "DestapaLatas_plate_2.3mf", "DestapaLatas_plate_2") == (
        "/cache", "DestapaLatas_plate_2.3mf",
    )  # fmt: skip
    assert elegir(listados, "DestapaLatas_plate_2.gcode.3mf", "DestapaLatas_plate_2") == (
        "/", "DestapaLatas_plate_2.gcode.3mf",
    )  # fmt: skip
    # Sin exacto en ninguna carpeta, sirve el parecido (como antes).
    assert elegir({"/": {"X_plate_1.gcode.3mf": 1}}, "X_plate_1.3mf", "X") == (
        "/", "X_plate_1.gcode.3mf",
    )  # fmt: skip
    assert elegir(listados, "nada.3mf", "nada") is None


# ----------------------------------------------- el estado se completa, no se reemplaza (MQTT)
def _ams(n):
    return [(b["id"], b["tipo"], b["color"], b["tag"], b["restante"]) for b in n["ams"]]


def test_un_mensaje_parcial_no_borra_las_bandejas_del_ams():
    estado = bambu.mezclar_estado({}, CRUDO)
    antes = _ams(bambu.normalizar(estado))
    estado = bambu.mezclar_estado(
        estado, {"ams": {"tray_now": "2"}}
    )  # solo cambia la bandeja en uso
    assert _ams(bambu.normalizar(estado)) == antes
    assert estado["ams"]["tray_now"] == "2"  # y lo nuevo sí se actualizó


def test_una_bandeja_sola_cambia_solo_esos_campos():
    estado = bambu.mezclar_estado({}, CRUDO)
    msg = {"ams": {"ams": [{"id": "0", "tray": [{"id": "0", "remain": 55}]}]}}
    n = bambu.normalizar(bambu.mezclar_estado(estado, msg))
    assert _ams(n)[0] == (
        "0",
        "PLA",
        "#000000",
        "B9656CFE00000100",
        55,
    )  # tipo, color y chip intactos
    assert len(n["ams"]) == 3 and n["ams"][1]["tipo"] == "PLA"  # las otras no se tocan


def test_una_bandeja_que_se_vacia_si_se_refleja():
    estado = bambu.mezclar_estado({}, CRUDO)
    vacia = {
        "ams": {
            "ams": [{"id": "0", "tray": [{"id": "0", "tray_type": "", "tray_color": "00000000"}]}]
        }
    }
    b0 = bambu.normalizar(bambu.mezclar_estado(estado, vacia))["ams"][0]
    assert b0["vacia"] and b0["tipo"] is None


def test_una_bandeja_nueva_se_agrega_y_las_listas_sin_id_se_reemplazan():
    estado = bambu.mezclar_estado({}, CRUDO)
    nueva = {
        "ams": {
            "ams": [
                {"id": "0", "tray": [{"id": "3", "tray_type": "PETG", "tray_color": "FF0000FF"}]}
            ]
        }
    }
    assert len(bambu.normalizar(bambu.mezclar_estado(estado, nueva))["ams"]) == 4
    luz = bambu.mezclar_estado(
        estado, {"lights_report": [{"node": "work_light", "mode": "off"}], "hms": []}
    )
    assert luz["lights_report"] == [{"node": "work_light", "mode": "off"}] and luz["hms"] == []


def test_mezclar_no_modifica_lo_recibido():
    base = {"ams": {"tray_now": "1", "ams": [{"id": "0", "tray": [{"id": "0", "remain": 10}]}]}}
    copia = {"ams": {"tray_now": "1", "ams": [{"id": "0", "tray": [{"id": "0", "remain": 10}]}]}}
    bambu.mezclar_estado(
        base, {"ams": {"tray_now": "2", "ams": [{"id": "0", "tray": [{"id": "0", "remain": 5}]}]}}
    )
    assert base == copia


def test_el_cliente_acumula_los_mensajes_sin_perder_las_bandejas():
    import json
    import threading

    c = object.__new__(bambu.ClienteBambu)  # sin conectar: solo se prueba cómo recibe mensajes
    c._lock, c._estado, c._ultimo = threading.Lock(), {}, None

    class Msg:
        def __init__(self, datos):
            self.payload = json.dumps({"print": datos}).encode()

    c._al_mensaje(None, None, Msg(CRUDO))
    for parcial in (
        {"ams": {"tray_now": "0"}},
        {"mc_percent": 86},
        {"ams": {"ams": [{"id": "0", "tray": [{"id": "1", "remain": 90}]}]}},
    ):
        c._al_mensaje(None, None, Msg(parcial))
        llenas = [b for b in bambu.normalizar(c.crudo())["ams"] if not b["vacia"]]
        assert len(llenas) == 2, "las ranuras no deben desaparecer entre mensajes"
    assert c.crudo()["mc_percent"] == 86 and c.ultimo_mensaje is not None


# ------------------------------------------------------------ auditoría: validar datos externos
@pytest.mark.parametrize(
    ("tag", "esperado"),
    [
        ("b9656cfe00000100", "B9656CFE00000100"),
        (" 0E45AABB ", "0E45AABB"),
        ("0000000000000000", None),
        ("", None),
        ("ABC", None),  # muy corto
        ("A" * 33, None),  # muy largo
        ("../spool/1", None),
        ("ZZZZ1234", None),  # no hexadecimal
        ("AB12\n34", None),
    ],
)
def test_tag_uid_solo_hexadecimal(tag, esperado):
    b = bambu._bandeja({"id": "0", "tray_type": "PLA", "tag_uid": tag, "remain": 50}, False)
    assert b["tag"] == esperado and b["medido"] is (esperado is not None)


def test_gramos_absurdos_del_3mf_se_descartan():
    datos = hacer_3mf(
        [{"index": 1, "peso": "1e6", "filamentos": [("PLA", "#000", "1e6"), ("PLA", "#fff", "8")]}]
    )
    info = lector3mf.analizar_3mf(datos)
    assert info.filamentos == [{"tipo": "PLA", "color": "#fff", "gramos": 8.0}]
    assert info.gramos == Decimal("8.00")  # el peso total absurdo se ignora; sale de lo válido
    # Cada línea cabe, pero el total pasa de 20000 g: no hay en qué confiar.
    muchas = [("PLA", "#000", "4000")] * 6
    info = lector3mf.analizar_3mf(hacer_3mf([{"index": 1, "peso": "24000", "filamentos": muchas}]))
    assert info.filamentos == [] and info.gramos is None
    # NaN e infinito tampoco pasan.
    info = lector3mf.analizar_3mf(
        hacer_3mf([{"index": 1, "peso": "nan", "filamentos": [("PLA", "#000", "inf")]}])
    )
    assert info.filamentos == [] and info.gramos is None


@pytest.mark.parametrize(("crudo", "esperado"), [(250, 100), (-5, 0), (42, 42), ("x", 0)])
def test_progreso_se_acota_a_0_100(crudo, esperado):
    assert maquina.instantanea_de({"mc_percent": crudo}).progreso == esperado
    n = bambu.normalizar({"mc_percent": crudo, "gcode_state": "RUNNING"})
    assert n["progreso"] == (esperado if crudo != "x" else None)
