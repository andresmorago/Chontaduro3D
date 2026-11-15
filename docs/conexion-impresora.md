# Conexión de la impresora y de Bambu Cloud

Se configura en **Administración → Conexión**. Esta nota explica cómo funciona por dentro y qué se protege.

## Piezas

- **Backend** (`app/api/impresora_conexion.py`): valida y guarda la configuración, hace el inicio de sesión en Bambu
  Cloud (`app/impresora/nube_login.py`) y deja pedidos de sincronización. **No** habla con la impresora.
- **Base** (`impresora_config`, una fila): `ip`, `serial`, `codigo_acceso` (cifrado), `nube_sesion` (token, cifrado),
  `nube_correo`, `version` y `nube_solicitada_en`.
- **Servicio `impresora`** (`app/impresora/servicio.py`): cada 2 s compara la configuración de la base con la que usa;
  si cambió, cierra la conexión MQTT y abre otra. Escribe en `impresora_estado` qué versión aplicó (`config_version`),
  si conectó y, si no, por qué (`conexion_error`: `credenciales` o `red`). El panel usa eso para decir «Conectando…»,
  «Conectada» o el motivo del fallo.

## Flujos

1. **Guardar la impresora**: `PUT /api/impresora/conexion` → sube `version` → el servicio reconecta → el panel espera
   el resultado (hasta ~20 s) y lo muestra.
2. **Vincular Bambu**: `POST /nube/entrar` (correo + contraseña) → Bambu devuelve el token, o pide verificación
   (`codigo` por correo / `tfa`) → `POST /nube/verificar`. Alternativa: `POST /nube/token` (token pegado de la cookie
   de bambulab.com). Al vincular se pide una sincronización inmediata.
3. **Sincronizar ahora**: `POST /nube/sincronizar` pone `nube_solicitada_en`; el servicio la ve, consulta la nube y
   marca `nube_atendida_en`. Mientras `atendida < solicitada` el panel muestra «Sincronizando…».
4. **Desvincular**: `DELETE /nube` borra el token y el correo; los trabajos ya traídos se conservan.

## Seguridad

- Cifrado en reposo con Fernet; la clave sale de `SECRET_KEY` (HKDF-SHA256). Backend y servicio deben compartirla
  (`docker-compose.prod.yml` se la pasa a ambos). Con otra `SECRET_KEY`, `descifrar` devuelve `None` y el panel marca
  los datos como «ilegibles» para escribirlos de nuevo.
- La API nunca devuelve el código ni el token. La contraseña de Bambu no se guarda, no entra en la auditoría y no se
  repite en los errores de validación.
- IP: solo red local, VPN o rango compartido (no públicas, loopback, link-local, multicast). Serial: 8–20 letras y
  números (va dentro del tema MQTT, así no puede colar comodines). Código de acceso: 4–32 caracteres visibles.
- Todo requiere sesión y la cabecera anti-CSRF; cada cambio queda en la auditoría (sin secretos).

## Migración desde el `.env`

Al arrancar, si la base no tiene configuración, el servicio importa una vez `BAMBU_IP`, `BAMBU_SERIAL` y
`BAMBU_ACCESS_CODE` y el token de `data/nube/bambu.json` (solo si la cuenta nunca se vinculó desde el panel; no borra el archivo). Después el `.env` ya no se usa
para eso y esas variables se pueden quitar.

## Pruebas

`backend/tests/test_impresora_conexion.py` (API, cifrado, validaciones) y los casos de configuración en
`test_impresora_servicio.py` (reconexión, motivo del fallo, importación única).
