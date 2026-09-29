# services/licencias.py
"""
Cliente Python para el sistema de licencias de Revisor Judicial.
Se comunica con https://cordobayabogados.com/api/
"""

import hashlib
import json
import logging
import os
import platform
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

from core.constantes import ARCHIVO_CONFIG

log = logging.getLogger(__name__)

# ====================================================================
# CONFIGURACIÓN
# ====================================================================

API_BASE = "https://cordobayabogados.com/api"
TIMEOUT_HTTP = 12

ARCHIVO_LICENCIA_LOCAL = os.path.join(
    os.path.dirname(ARCHIVO_CONFIG), "licencia.json")


# ====================================================================
# IDENTIFICADOR DE MÁQUINA
# ====================================================================

def _uuid_placa_madre() -> str:
    """UUID de la placa madre. PowerShell → wmic → vacío."""
    try:
        salida = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
            timeout=6, stderr=subprocess.DEVNULL, text=True,
        ).strip()
        if salida and salida.lower() not in (
            "", "00000000-0000-0000-0000-000000000000",
        ):
            return salida
    except Exception:
        pass

    try:
        salida = subprocess.check_output(
            "wmic csproduct get uuid",
            shell=True, timeout=4, stderr=subprocess.DEVNULL,
        ).decode(errors="ignore")
        lineas = [l.strip() for l in salida.splitlines() if l.strip()]
        if len(lineas) >= 2:
            return lineas[1]
    except Exception:
        pass

    return ""


def _obtener_hash_maquina() -> str:
    """Hash estable de la máquina (64 chars)."""
    import uuid

    partes = [
        platform.node(),
        platform.machine(),
        platform.processor(),
        platform.system(),
        platform.release(),
        platform.version(),
        os.environ.get("USERNAME", ""),
        os.environ.get("USERDOMAIN", ""),
        os.environ.get("COMPUTERNAME", ""),
    ]

    uuid_placa = _uuid_placa_madre()
    if uuid_placa:
        partes.append(uuid_placa)

    try:
        partes.append(str(uuid.getnode()))
    except Exception:
        pass

    base = "|".join(str(p) for p in partes)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def obtener_info_maquina() -> str:
    try:
        return "{} · {} · {}".format(
            platform.system(),
            platform.release(),
            os.environ.get("USERNAME", "usuario"),
        )
    except Exception:
        return "PC desconocida"


# ====================================================================
# CLIENTE HTTP
# ====================================================================

def _post(endpoint: str, datos: dict) -> dict:
    """
    Hace un POST JSON a la API.

    IMPORTANTE: distingue entre:
      - Servidor responde con JSON (éxito o error de negocio) → devuelve ese JSON
      - Sin conexión / DNS falla → devuelve {"ok": False, "codigo": "SIN_CONEXION", ...}
      - Otro error de red → devuelve {"ok": False, "codigo": "SIN_CONEXION", ...}
    """
    url = f"{API_BASE}/{endpoint}"
    payload = json.dumps(datos).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "RevisorJudicial/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_HTTP) as resp:
            cuerpo = resp.read().decode("utf-8")
            return json.loads(cuerpo)

    except urllib.error.HTTPError as e:
        # El servidor SÍ respondió, pero con error HTTP. Intentamos leer su JSON.
        try:
            cuerpo = e.read().decode("utf-8")
            data = json.loads(cuerpo)
            # Aseguramos que traiga "ok"
            if "ok" not in data:
                data["ok"] = False
            return data
        except Exception:
            # No podemos leer el JSON → sí fue un problema de comunicación
            return {
                "ok": False,
                "codigo": "SIN_CONEXION",
                "error": "Error HTTP {} sin JSON legible.".format(e.code),
            }

    except urllib.error.URLError as e:
        # Sin conexión, DNS falla, timeout, etc.
        razon = getattr(e, "reason", e)
        log.info("Sin conexión al servidor de licencias: %s", razon)
        return {
            "ok": False,
            "codigo": "SIN_CONEXION",
            "error": "Sin conexión al servidor: {}".format(razon),
        }

    except Exception as e:
        log.info("Error inesperado contactando al servidor: %s", e)
        return {
            "ok": False,
            "codigo": "SIN_CONEXION",
            "error": "Error inesperado: {}".format(e),
        }


# ====================================================================
# ALMACENAMIENTO LOCAL
# ====================================================================

def _leer_licencia_local() -> dict:
    if not os.path.exists(ARCHIVO_LICENCIA_LOCAL):
        return {}
    try:
        with open(ARCHIVO_LICENCIA_LOCAL, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_licencia_local(datos: dict) -> None:
    try:
        with open(ARCHIVO_LICENCIA_LOCAL, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning("No se pudo guardar licencia local: %s", e)


# ====================================================================
# API PÚBLICA
# ====================================================================

def activar(token: str) -> dict:
    """Activa un token en esta máquina."""
    token = (token or "").strip()
    if not token:
        return {"ok": False, "error": "Token vacío"}

    maquina_hash = _obtener_hash_maquina()
    maquina_info = obtener_info_maquina()

    resp = _post("activar.php", {
        "token": token,
        "maquina_hash": maquina_hash,
        "maquina_info": maquina_info,
    })

    if resp.get("ok"):
        _guardar_licencia_local({
            "token": token,
            "maquina_hash": maquina_hash,
            "vence": resp.get("vence", ""),
            "plan": resp.get("plan", ""),
            "dias_restantes": resp.get("dias_restantes", 0),
            "activada_en": datetime.now().isoformat(),
            "ultima_validacion_ok": datetime.now().isoformat(),
        })
        log.info("✅ Licencia activada. Vence: %s", resp.get("vence"))

    return resp


def validar(silencioso: bool = False) -> dict:
    """
    Verifica si la licencia actual sigue válida.

    Devuelve:
      - { "ok": True, ... }                          → todo OK
      - { "ok": False, "codigo": "SIN_LICENCIA" }    → no hay token
      - { "ok": False, "codigo": "SIN_CONEXION" }    → no se pudo contactar al servidor
      - { "ok": False, "codigo": "VENCIDA" | "REVOCADA" | "MAQUINA_NO_ACTIVADA" }
    """
    local = _leer_licencia_local()
    token = local.get("token", "")
    if not token:
        return {
            "ok": False,
            "error": "No hay licencia activada",
            "codigo": "SIN_LICENCIA",
        }

    maquina_hash = local.get("maquina_hash") or _obtener_hash_maquina()

    resp = _post("validar.php", {
        "token": token,
        "maquina_hash": maquina_hash,
    })

    if resp.get("ok"):
        local["vence"] = resp.get("vence", local.get("vence", ""))
        local["dias_restantes"] = resp.get("dias_restantes", 0)
        local["plan"] = resp.get("plan", local.get("plan", ""))
        local["ultima_validacion_ok"] = datetime.now().isoformat()
        local.pop("invalida", None)
        _guardar_licencia_local(local)
        return resp

    # A partir de aquí: ok=False.
    codigo = (resp.get("codigo") or "").strip()

    if codigo == "SIN_CONEXION":
        # No hay red. NO marcamos la licencia como inválida.
        # main.py decidirá si aplicar periodo de gracia.
        if not silencioso:
            log.info("Sin conexión al servidor de licencias: %s",
                     resp.get("error"))
        return resp

    # Código de negocio: VENCIDA, REVOCADA, MAQUINA_NO_ACTIVADA
    if codigo in ("VENCIDA", "REVOCADA", "MAQUINA_NO_ACTIVADA"):
        if not silencioso:
            log.warning("❌ Licencia no válida: %s", resp.get("error"))
        local["invalida"] = codigo
        _guardar_licencia_local(local)
        return resp

    # Otros errores del servidor (no marcan la licencia como inválida)
    if not silencioso:
        log.warning("Error del servidor de licencias: %s", resp.get("error"))
    return resp


def solicitar_prueba(email: str, nombre: str = "") -> dict:
    """Solicita un trial de 3 días."""
    email = (email or "").strip()
    nombre = (nombre or "").strip()

    if not email or "@" not in email:
        return {"ok": False, "error": "Correo inválido"}
    if len(nombre) < 3:
        return {"ok": False, "error": "Ingresa tu nombre completo"}

    maquina_hash = _obtener_hash_maquina()
    maquina_info = obtener_info_maquina()

    resp = _post("solicitar_prueba.php", {
        "email": email,
        "nombre": nombre,
        "maquina_hash": maquina_hash,
        "maquina_info": maquina_info,
    })

    if resp.get("ok"):
        _guardar_licencia_local({
            "token": resp.get("token", ""),
            "maquina_hash": maquina_hash,
            "vence": resp.get("vence", ""),
            "plan": "trial",
            "dias_restantes": resp.get("dias_restantes", 3),
            "activada_en": datetime.now().isoformat(),
            "ultima_validacion_ok": datetime.now().isoformat(),
            "email": email,
            "nombre": nombre,
        })
        log.info("🎁 Trial activado hasta %s", resp.get("vence"))

    return resp


def obtener_estado_local() -> dict:
    """Lee la licencia local sin consultar al servidor."""
    return _leer_licencia_local()


def limpiar_licencia() -> None:
    """Elimina la licencia local."""
    try:
        if os.path.exists(ARCHIVO_LICENCIA_LOCAL):
            os.remove(ARCHIVO_LICENCIA_LOCAL)
    except Exception:
        pass