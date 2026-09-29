# services/ip_rotator.py
"""
Rotador de IP para superar bloqueos del portal de la Rama Judicial.
"""

import logging
import random
import re
import subprocess
import time
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)


RUTAS_WARP_CLI = [
    r"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe",
    r"C:\Program Files (x86)\Cloudflare\Cloudflare WARP\warp-cli.exe",
]

URLS_PROXIES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
]

URL_TEST_PROXY = "https://api.ipify.org?format=json"
TIMEOUT_TEST_PROXY = 5
MAX_PROXIES_TESTEAR = 30
CACHE_PROXIES_MINUTOS = 30


class IPRotator:
    """Gestiona el cambio de IP usando WARP o proxies gratuitos."""

    def __init__(self):
        self._ruta_warp = self._localizar_warp()
        self._proxy_actual = None
        self._proxies_validos = []
        self._proxies_cache_ts = 0
        self._warp_conectado = False

    # ------------------------------------------------------------------
    # WARP
    # ------------------------------------------------------------------

    def _localizar_warp(self):
        for ruta in RUTAS_WARP_CLI:
            if Path(ruta).exists():
                log.info("✅ Cloudflare WARP encontrado en: %s", ruta)
                return ruta
        log.info("ℹ️ Cloudflare WARP no está instalado. "
                 "Se usará solo la rotación por proxies.")
        return None

    def warp_disponible(self) -> bool:
        return self._ruta_warp is not None

    def warp_estado(self) -> str:
        if not self._ruta_warp:
            return "no-instalado"
        try:
            salida = subprocess.run(
                [self._ruta_warp, "status"],
                capture_output=True, text=True, timeout=8,
            )
            txt = (salida.stdout + salida.stderr).lower()
            if "connected" in txt and "disconnected" not in txt:
                return "conectado"
            if "disconnected" in txt:
                return "desconectado"
        except Exception as e:
            log.debug("No se pudo consultar WARP: %s", e)
        return "desconocido"

    def warp_reconectar(self) -> bool:
        if not self._ruta_warp:
            return False
        try:
            log.info("🔄 WARP: desconectando para cambiar IP…")
            subprocess.run([self._ruta_warp, "disconnect"],
                           capture_output=True, timeout=15)
            time.sleep(2.0)

            log.info("🔄 WARP: reconectando…")
            subprocess.run([self._ruta_warp, "connect"],
                           capture_output=True, timeout=15)

            for _ in range(20):
                time.sleep(1.0)
                if self.warp_estado() == "conectado":
                    log.info("✅ WARP reconectado. IP nueva activa.")
                    self._warp_conectado = True
                    return True

            log.warning("⚠️ WARP no reportó 'conectado' tras 20s.")
            return False
        except Exception as e:
            log.warning("Error reconectando WARP: %s", e)
            return False

    def desconectar_warp(self) -> bool:
        """Desconecta WARP. Devuelve True si se ejecutó sin error."""
        if not self._ruta_warp:
            return False
        try:
            log.info("🔄 WARP: desconectando al finalizar el escaneo…")
            subprocess.run([self._ruta_warp, "disconnect"],
                           capture_output=True, timeout=10)
            time.sleep(1.0)
            self._warp_conectado = False
            return True
        except Exception as e:
            log.warning("No se pudo desconectar WARP: %s", e)
            return False

    # ------------------------------------------------------------------
    # PROXIES
    # ------------------------------------------------------------------

    def _descargar_lista_proxies(self):
        proxies = set()
        for url in URLS_PROXIES:
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    contenido = resp.read().decode("utf-8", errors="ignore")
                for linea in contenido.splitlines():
                    linea = linea.strip()
                    if re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d{1,5}$", linea):
                        proxies.add(linea)
            except Exception as e:
                log.debug("Fuente %s falló: %s", url, e)
        log.info("📋 %s proxies descargados.", len(proxies))
        return list(proxies)

    def _testear_proxy(self, proxy: str) -> bool:
        try:
            handler = urllib.request.ProxyHandler({
                "http": "http://{}".format(proxy),
                "https": "http://{}".format(proxy),
            })
            opener = urllib.request.build_opener(handler)
            opener.addheaders = [("User-Agent", "Mozilla/5.0")]
            with opener.open(URL_TEST_PROXY, timeout=TIMEOUT_TEST_PROXY) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        return False

    def _refrescar_proxies_validos(self, forzar=False):
        ahora = time.time()
        if (not forzar) and self._proxies_validos and \
                (ahora - self._proxies_cache_ts) < CACHE_PROXIES_MINUTOS * 60:
            return

        log.info("🔍 Buscando proxies funcionales...")
        candidatos = self._descargar_lista_proxies()
        random.shuffle(candidatos)

        validos = []
        for i, proxy in enumerate(candidatos[:MAX_PROXIES_TESTEAR]):
            if self._testear_proxy(proxy):
                validos.append(proxy)
                log.info("   ✔ Proxy OK (%s/%s): %s",
                         i + 1, MAX_PROXIES_TESTEAR, proxy)
                if len(validos) >= 5:
                    break

        self._proxies_validos = validos
        self._proxies_cache_ts = ahora
        log.info("✅ %s proxies válidos en caché.", len(validos))

    def _siguiente_proxy(self):
        self._refrescar_proxies_validos()
        if not self._proxies_validos:
            return None
        return random.choice(self._proxies_validos)

    # ------------------------------------------------------------------
    # API PÚBLICA
    # ------------------------------------------------------------------

    def rotar(self) -> dict:
        if self.warp_disponible():
            if self.warp_reconectar():
                self._proxy_actual = None
                return {
                    "metodo": "warp",
                    "proxy": None,
                    "ok": True,
                    "mensaje": "IP cambiada vía Cloudflare WARP.",
                }
            log.warning("WARP falló; probando proxies gratuitos…")

        proxy = self._siguiente_proxy()
        if proxy:
            self._proxy_actual = proxy
            return {
                "metodo": "proxy",
                "proxy": proxy,
                "ok": True,
                "mensaje": "IP cambiada vía proxy {}.".format(proxy),
            }

        return {
            "metodo": "ninguno",
            "proxy": None,
            "ok": False,
            "mensaje": "No hay WARP ni proxies funcionales disponibles.",
        }

    def get_proxy_actual(self):
        return self._proxy_actual

    def limpiar_proxy(self):
        self._proxy_actual = None

    def resumen(self) -> str:
        return ("WARP: {} | Proxy actual: {} | Proxies válidos en caché: {}"
                .format(
                    self.warp_estado(),
                    self._proxy_actual or "(directo)",
                    len(self._proxies_validos),
                ))