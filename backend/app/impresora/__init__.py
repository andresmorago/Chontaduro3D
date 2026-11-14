"""Integración con la impresora Bambu Lab A1 (MQTT y FTPS locales).

El servicio (`python -m app.impresora.servicio`) es lo único que tiene las credenciales de la
impresora: escribe el estado y los trabajos en la base, y ejecuta las órdenes que deja el backend.
"""
