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
            {"id": "0", "tray_type": "PLA", "tray_color": "000000FF", "remain": 100},
            {"id": "1", "tray_type": "PLA", "tray_color": "FFFFFFFF", "remain": 40},
            {"id": "2", "tray_type": "", "tray_color": "00000000", "remain": -1},
        ]}],
    },
    "vt_tray": {"id": "254", "tray_type": "PETG", "tray_color": "443089FF", "remain": 0},
    "sn": "NO-DEBE-SALIR", "net": {"conf": 1}, "ipcam": {"x": 1},
}  # fmt: skip


def test_normalizar_estado():
    n = bambu.normalizar(CRUDO)
    assert n["estado"] == "imprimiendo" and n["trabajo"] == "tfic-angled"
    assert (n["progreso"], n["capa"], n["capas"], n["restante_min"]) == (85, 91, 100, 9)
    assert (n["boquilla"], n["cama"], n["velocidad"], n["luz"]) == (230.1, 64.9, 2, "on")
    assert n["ams"][0] == {
        "id": "0", "vacia": False, "tipo": "PLA", "color": "#000000", "restante": 100,
        "en_uso": False,
    }  # fmt: skip
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
