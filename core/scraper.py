# core/scraper.py
"""
Scraping del portal de la Rama Judicial usando Selenium.

Incluye:
  - Modo STEALTH: oculta que el navegador es controlado por Selenium.
  - User-Agent rotativo en cada driver.
  - Soporte de PROXY (para superar bloqueos por IP).
  - Manejo de modales (Network Error / varios registros).
  - Reintento interno con backoff exponencial.
  - Timeout ADAPTATIVO (30s → 45s → 60s según intento).
  - Detección temprana de conexión caída (no esperamos 30s en vano).
  - Retry anti-stale al extraer actuaciones.
  - Flag GLOBAL de capturas (activar/desactivar desde config).
  - Detección de driver caído y utilidad para reciclarlo.
  - Clic robusto sobre la última actuación (button padre).
  - Dump de HTML cuando falla la extracción (debug).
"""

import logging
import os
import random
import re
import time
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from core.constantes import (
    ARCHIVO_SALIDA,
    BACKOFF_SEGUNDOS,
    CARPETA_CAPTURAS,
    COLUMNA_CAPTURA_ACT,
    COLUMNA_LINEAS_INTERNA,
    COLUMNA_RESUMEN,
    DIAS_ACTUACIONES_RECIENTES,
    ESPERA_CARGA_ACTUACIONES,
    ESPERA_CLIC_ACTUACION,
    ESPERA_INGRESO_RADICADO,
    ESPERA_RESULTADOS,
    MAX_INTENTOS_INTERNOS,
    TIMEOUT_CAMPO_RADICADO,
    TIMEOUT_RESULTADOS,
    TIMEOUT_TABLA_ACTUACIONES,
    URL_CONSULTA,
)
from core.resumen import construir_resumen_actuaciones

log = logging.getLogger(__name__)


# ====================================================================
# FLAG GLOBAL DE CAPTURAS
# ====================================================================
#
# Si está en False, NINGUNA captura se guarda en disco (ni PNG ni HTML).
# Se controla desde escaneo_view.py al iniciar cada escaneo, según la
# configuración del usuario.

GUARDAR_CAPTURAS_GLOBAL = True


def _set_guardar_capturas(activo: bool) -> None:
    """Activa/desactiva la captura de pantalla en TODO el módulo."""
    global GUARDAR_CAPTURAS_GLOBAL
    GUARDAR_CAPTURAS_GLOBAL = bool(activo)


def capturas_activas() -> bool:
    """Devuelve el estado actual del flag."""
    return GUARDAR_CAPTURAS_GLOBAL


# ====================================================================
# CONFIGURACIÓN INTERNA
# ====================================================================

# Timeout adaptativo por intento interno (segundos)
TIMEOUTS_POR_INTENTO = [30, 45, 60]

# Reintentos al extraer actuaciones (por stale elements)
MAX_REINTENTOS_EXTRAER_ACTUACIONES = 3
ESPERA_ENTRE_REINTENTOS_ACTUACIONES = 1.5

# Marcadores que indican que Chrome perdió la conexión con el servidor
MARCADORES_CONEXION_CAIDA = (
    "err_connection_closed",
    "err_connection_reset",
    "err_connection_refused",
    "err_connection_timed_out",
    "err_name_not_resolved",
    "err_internet_disconnected",
    "err_address_unreachable",
    "err_empty_response",
    "this site can't be reached",
    "no se puede acceder a este sitio",
)


# ====================================================================
# STEALTH: User-Agents rotativos
# ====================================================================

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]


_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
        {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
        {name: 'Native Client', filename: 'internal-nacl-plugin'}
    ]
});
Object.defineProperty(navigator, 'languages', {get: () => ['es-CO', 'es', 'en']});
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : originalQuery(parameters)
);
"""


def _aplicar_stealth(driver) -> None:
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": _STEALTH_JS},
        )
        driver.execute_script(_STEALTH_JS)
    except Exception as e:
        log.debug("No se pudo aplicar stealth: %s", e)


# ====================================================================
# DRIVER
# ====================================================================

def crear_driver(proxy=None):
    """Crea el driver de Chrome con anti-detección y soporte de proxy."""
    options = webdriver.ChromeOptions()

    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")

    options.add_argument("--user-agent={}".format(random.choice(_USER_AGENTS)))

    options.add_experimental_option(
        "excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    options.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.default_content_setting_values.notifications": 2,
    })

    if proxy:
        proxy_limpio = proxy.replace("http://", "").replace("https://", "")
        options.add_argument("--proxy-server=http://{}".format(proxy_limpio))
        log.info("🌐 Usando proxy: %s", proxy_limpio)

    driver = None

    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        log.info("Navegador iniciado (webdriver-manager + stealth%s).",
                 " + proxy" if proxy else "")
    except ImportError:
        log.info("webdriver-manager no instalado, usando Selenium Manager...")
    except Exception as e:
        log.warning("webdriver-manager falló: %s. Probando Selenium Manager...", e)

    if driver is None:
        try:
            driver = webdriver.Chrome(options=options)
            log.info("Navegador iniciado (Selenium Manager + stealth%s).",
                     " + proxy" if proxy else "")
        except Exception as e:
            log.error("No se pudo iniciar Chrome: %s", e)
            return None

    _aplicar_stealth(driver)
    return driver


def driver_sigue_vivo(driver) -> bool:
    if driver is None:
        return False
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


def cerrar_driver_seguro(driver) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass


# ====================================================================
# HELPERS
# ====================================================================

def limpiar_radicado(numero) -> str:
    return re.sub(r"[\.\-\s]", "", str(numero or "")).strip()


def tomar_captura(driver, nombre: str) -> str:
    """
    Toma captura de pantalla SOLO si el flag global está activo.
    Devuelve la ruta del PNG o "" si no se guardó.
    """
    if not GUARDAR_CAPTURAS_GLOBAL:
        return ""
    os.makedirs(CARPETA_CAPTURAS, exist_ok=True)
    path = os.path.join(CARPETA_CAPTURAS, "{}.png".format(nombre))
    try:
        driver.save_screenshot(path)
        return path
    except Exception as e:
        log.warning("No se pudo guardar la captura '%s': %s", nombre, e)
        return ""


def _dump_html(driver, nombre: str) -> str:
    """
    Guarda el HTML actual SOLO si el flag global está activo.
    """
    if not GUARDAR_CAPTURAS_GLOBAL:
        return ""
    try:
        os.makedirs(CARPETA_CAPTURAS, exist_ok=True)
        path = os.path.join(CARPETA_CAPTURAS, "{}.html".format(nombre))
        with open(path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        log.info("   🐞 HTML de depuración: %s", path)
        return path
    except Exception as e:
        log.warning("No se pudo guardar HTML: %s", e)
        return ""


def _normalizar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip().lower()


# ====================================================================
# DETECCIÓN DE CONEXIÓN CAÍDA
# ====================================================================

def _pagina_es_error_de_conexion(driver) -> bool:
    """
    Comprueba si la página actual es una pantalla de error de Chrome.
    Si es así, no tiene sentido esperar al timeout completo.
    """
    try:
        page_source = driver.page_source.lower()
    except Exception:
        return False

    for marcador in MARCADORES_CONEXION_CAIDA:
        if marcador in page_source:
            return True

    return False


# ====================================================================
# PARSERS
# ====================================================================

def extraer_sujetos(texto_sujetos: str):
    if "PROCESO PRIVADO" in texto_sujetos.upper():
        return "Proceso Privado", "Proceso Privado", "Proceso Privado"

    demandante = "Sin demandante"
    demandado = "Sin demandado"
    apoderado = "Sin apoderado"

    patron_dem = re.compile(r"^(demandantes?|accionantes?)", re.IGNORECASE)
    patron_ddo = re.compile(r"^(demandados?|indiciados?|causantes?)", re.IGNORECASE)
    patron_apod = re.compile(r"^(apoderados?|defensores?|abogados?)", re.IGNORECASE)

    for line in (l.strip() for l in texto_sujetos.split("\n") if l.strip()):
        if ":" in line:
            partes = line.split(":", 1)
            rol, nombre = partes[0].strip(), partes[1].strip()
            if patron_dem.search(rol):
                demandante = nombre
            elif patron_ddo.search(rol):
                demandado = nombre
            elif patron_apod.search(rol):
                apoderado = nombre
        else:
            if patron_dem.search(line) and demandante == "Sin demandante":
                demandante = line
            elif patron_ddo.search(line) and demandado == "Sin demandado":
                demandado = line
            elif patron_apod.search(line) and apoderado == "Sin apoderado":
                apoderado = line
    return demandante, demandado, apoderado


def obtener_estado_y_fecha(fechas: list, dias_umbral: int = 10):
    if not fechas:
        return "Sin resultado", "", "El proceso no tiene fecha de actuación"
    fechas_dt = []
    for f in fechas:
        try:
            fechas_dt.append(datetime.strptime(f, "%Y-%m-%d"))
        except (ValueError, TypeError):
            continue
    if not fechas_dt:
        return "Sin resultado", "", "El proceso no tiene fecha de actuación"
    fecha_mas_reciente = max(fechas_dt)
    str_fecha = fecha_mas_reciente.strftime("%Y-%m-%d")
    hace_n_dias = datetime.now() - timedelta(days=dias_umbral)
    if fecha_mas_reciente >= hace_n_dias:
        return ("Revisar", str_fecha,
                "CON actuaciones últimos {} días".format(dias_umbral))
    return ("Con actuaciones fuera de búsqueda", str_fecha,
            "SIN Última actuación hace más de {} días".format(dias_umbral))


# ====================================================================
# LOCALIZACIÓN DE ELEMENTOS
# ====================================================================

def _encontrar_tabla_resultados(driver):
    try:
        return driver.find_element(
            By.XPATH,
            "//table[.//th[contains(text(),'Fecha de Radicación')]]")
    except Exception:
        pass
    for t in driver.find_elements(By.TAG_NAME, "table"):
        if len(t.find_elements(By.TAG_NAME, "tr")) > 1:
            return t
    return None


def seleccionar_todos_los_procesos(driver) -> bool:
    try:
        label = driver.find_element(
            By.XPATH, "//label[contains(., 'Todos los Procesos')]")
        driver.execute_script("arguments[0].click();", label)
        return True
    except Exception:
        pass
    try:
        radio_icon = driver.find_element(
            By.XPATH, "(//div[contains(@class, 'v-radio')])[2]")
        driver.execute_script("arguments[0].click();", radio_icon)
        return True
    except Exception:
        pass
    return False


# ====================================================================
# MODALES
# ====================================================================

def _buscar_boton_volver(driver):
    try:
        for b in driver.find_elements(
                By.XPATH,
                "//button[contains(., 'VOLVER') or contains(., 'Volver') "
                "or contains(., 'ACEPTAR') or contains(., 'Aceptar')]"):
            if b.is_displayed():
                return b
    except Exception:
        pass
    return None


def _cerrar_modal_si_existe(driver):
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text or ""
    except Exception:
        body_text = ""

    body_low = body_text.lower()

    if "network error" in body_low or "error de red" in body_low:
        btn = _buscar_boton_volver(driver)
        if btn is not None:
            try:
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.8)
            except Exception:
                pass
        return "network_error"

    if ("varios registros" in body_low
            or "mismo número de radicación" in body_low
            or "mismo numero de radicacion" in body_low):
        btn = _buscar_boton_volver(driver)
        if btn is not None:
            try:
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.8)
            except Exception:
                pass
        return "varios_registros"

    btn = _buscar_boton_volver(driver)
    if btn is not None:
        try:
            dialogs = driver.find_elements(
                By.XPATH,
                "//div[contains(@class,'v-dialog') "
                "and not(contains(@style,'display: none'))]")
            if any(d.is_displayed() for d in dialogs):
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.5)
                return "otro_modal"
        except Exception:
            pass

    return None


# ====================================================================
# ESPERA INTELIGENTE CON TIMEOUT ADAPTATIVO
# ====================================================================

_XPATH_SIN_RESULTADOS = (
    "//*[contains(text(),'La consulta no generó resultados')]"
)


def _timeout_para_intento(intento: int) -> int:
    """
    Devuelve el timeout en segundos según el número de intento interno.
    1 → 30s, 2 → 45s, 3 → 60s.
    """
    idx = min(max(intento - 1, 0), len(TIMEOUTS_POR_INTENTO) - 1)
    return TIMEOUTS_POR_INTENTO[idx]


def _esperar_resultado_rama(driver, timeout: int):
    """
    Espera activamente a uno de:
      - Tabla con filas                            → "tabla"
      - "La consulta no generó resultados"         → "sin_resultados"
      - Modal Network Error (ya se cerró)          → "error_red"
      - Página de error de conexión (early abort)  → "conexion_caida"
      - Timeout                                     → "timeout"
    """
    inicio = time.time()
    ultimo_log = 0.0
    varios_registros_intentos = 0
    chequeo_conexion_intervalo = 2.0
    ultimo_chequeo_conexion = 0.0

    while True:
        transcurrido = time.time() - inicio

        # 1) Tabla con filas
        try:
            tabla = _encontrar_tabla_resultados(driver)
            if tabla is not None:
                filas = tabla.find_elements(By.TAG_NAME, "tr")
                if len(filas) >= 2:
                    return "tabla"
        except Exception:
            pass

        # 2) "sin resultados"
        try:
            if driver.find_elements(By.XPATH, _XPATH_SIN_RESULTADOS):
                return "sin_resultados"
        except Exception:
            pass

        # 3) Chequeo periódico de conexión caída
        if transcurrido - ultimo_chequeo_conexion >= chequeo_conexion_intervalo:
            ultimo_chequeo_conexion = transcurrido
            try:
                if _pagina_es_error_de_conexion(driver):
                    log.info("   🔌 Conexión caída detectada (%.1fs). "
                             "Abortando espera.", transcurrido)
                    return "conexion_caida"
            except Exception:
                pass

        # 4) Modales
        modal = _cerrar_modal_si_existe(driver)

        if modal == "network_error":
            log.info("   🔻 Modal Network Error cerrado.")
            return "error_red"

        if modal == "varios_registros":
            varios_registros_intentos += 1
            log.info("   📋 Modal 'varios registros' cerrado (intento %s).",
                     varios_registros_intentos)
            if varios_registros_intentos >= 3:
                return "sin_resultados"
            time.sleep(0.8)
            continue

        # 5) Timeout global
        if transcurrido >= timeout:
            return "timeout"

        # 6) Log de progreso
        if transcurrido - ultimo_log >= 10:
            log.info("   ⏳ Esperando resultados... (%.0fs / %ss)",
                     transcurrido, timeout)
            ultimo_log = transcurrido

        time.sleep(0.5)


# ====================================================================
# EXTRACCIÓN DE LA TABLA DE RESULTADOS
# ====================================================================

def extraer_filas_de_tabla(driver, radicado_limpio: str,
                            dias_umbral: int = 10) -> list:
    registros = []
    try:
        tabla = _encontrar_tabla_resultados(driver)
        if tabla is None:
            return registros
        filas = tabla.find_elements(By.TAG_NAME, "tr")
        if len(filas) < 2:
            return registros

        encabezados = filas[0].find_elements(By.TAG_NAME, "th")
        idx_fecha, idx_despacho, idx_sujetos = 2, 3, 4
        for i, th in enumerate(encabezados):
            texto = th.text.strip().lower()
            if "fecha" in texto:
                idx_fecha = i
            elif "despacho" in texto:
                idx_despacho = i
            elif "sujetos" in texto:
                idx_sujetos = i
        idx_max = max(idx_fecha, idx_despacho, idx_sujetos)

        for fila in filas[1:]:
            try:
                celdas = fila.find_elements(By.TAG_NAME, "td")
            except StaleElementReferenceException:
                raise
            if len(celdas) <= idx_max:
                continue
            despacho = celdas[idx_despacho].text.strip()
            texto_sujetos = celdas[idx_sujetos].text.strip()

            if "PROCESO PRIVADO" in fila.text.upper():
                registros.append({
                    "Radicado": radicado_limpio,
                    "Estado": "Proceso Privado",
                    "Fecha_Ultima_Actuacion": "",
                    "Observacion": "Proceso bajo reserva legal / privado",
                    COLUMNA_RESUMEN: "",
                    COLUMNA_LINEAS_INTERNA: [],
                    "Despacho": despacho,
                    "Demandante": "Proceso Privado",
                    "Demandado": "Proceso Privado",
                    "Apoderado": "Proceso Privado",
                })
                continue

            celda_fecha = celdas[idx_fecha]
            fechas_fila = []
            for enlace in celda_fecha.find_elements(By.TAG_NAME, "a"):
                m = re.search(r"\d{4}-\d{2}-\d{2}", enlace.text.strip())
                if m:
                    fechas_fila.append(m.group())
            if not fechas_fila:
                for sp in celda_fecha.find_elements(By.CSS_SELECTOR,
                                                     "span.v-btn__content"):
                    m = re.search(r"\d{4}-\d{2}-\d{2}", sp.text.strip())
                    if m:
                        fechas_fila.append(m.group())
            if not fechas_fila:
                fechas_fila.extend(
                    re.findall(r"\d{4}-\d{2}-\d{2}", celda_fecha.text.strip()))

            estado, fecha_ultima, observacion = obtener_estado_y_fecha(
                fechas_fila, dias_umbral)
            demandante, demandado, apoderado = extraer_sujetos(texto_sujetos)

            registros.append({
                "Radicado": radicado_limpio,
                "Estado": estado,
                "Fecha_Ultima_Actuacion": fecha_ultima,
                "Observacion": observacion,
                COLUMNA_RESUMEN: "",
                COLUMNA_LINEAS_INTERNA: [],
                "Despacho": despacho,
                "Demandante": demandante,
                "Demandado": demandado,
                "Apoderado": apoderado,
            })
    except StaleElementReferenceException:
        raise
    except Exception as e:
        log.warning("Error extrayendo datos de la tabla: %s", e)
    return registros


# ====================================================================
# CLIC EN LA ÚLTIMA ACTUACIÓN
# ====================================================================

def _elemento_clicable_de(fecha_element):
    try:
        tag = (fecha_element.tag_name or "").lower()
    except Exception:
        return fecha_element

    if tag == "span":
        try:
            padre = fecha_element.find_element(By.XPATH, "./ancestor::button[1]")
            if padre and padre.is_displayed():
                return padre
        except Exception:
            pass
        try:
            padre = fecha_element.find_element(By.XPATH, "./ancestor::a[1]")
            if padre and padre.is_displayed():
                return padre
        except Exception:
            pass

    return fecha_element


def hacer_clic_ultima_actuacion(driver, radicado_limpio: str):
    try:
        tabla = _encontrar_tabla_resultados(driver)
        if tabla is None:
            log.warning("No se encontró la tabla de resultados.")
            return None
        filas = tabla.find_elements(By.TAG_NAME, "tr")
        if len(filas) < 2:
            return None

        encabezados = filas[0].find_elements(By.TAG_NAME, "th")
        idx_fecha = 2
        for i, th in enumerate(encabezados):
            if "fecha" in th.text.strip().lower():
                idx_fecha = i
                break

        mejor_fecha = None
        mejor_elemento = None
        mejor_tipo = None
        mejor_fila_idx = None
        filas_con_candidatos = 0

        for fila_idx, fila in enumerate(filas[1:], start=1):
            celdas = fila.find_elements(By.TAG_NAME, "td")
            if len(celdas) <= idx_fecha:
                continue
            celda_fecha = celdas[idx_fecha]

            candidatos = []
            for e in celda_fecha.find_elements(By.TAG_NAME, "a"):
                m = re.search(r"\d{4}-\d{2}-\d{2}", e.text.strip())
                if m:
                    candidatos.append((m.group(), e, "a"))
            for e in celda_fecha.find_elements(By.CSS_SELECTOR,
                                                "span.v-btn__content"):
                m = re.search(r"\d{4}-\d{2}-\d{2}", e.text.strip())
                if m:
                    candidatos.append((m.group(), e, "span.v-btn__content"))
            for e in celda_fecha.find_elements(By.TAG_NAME, "button"):
                m = re.search(r"\d{4}-\d{2}-\d{2}", e.text.strip())
                if m:
                    candidatos.append((m.group(), e, "button"))
            for e in celda_fecha.find_elements(By.CSS_SELECTOR,
                                                "[role='button']"):
                m = re.search(r"\d{4}-\d{2}-\d{2}", e.text.strip())
                if m:
                    candidatos.append((m.group(), e, "[role=button]"))

            if not candidatos:
                continue

            filas_con_candidatos += 1
            fecha_max_fila, elemento_max_fila, tipo_fila = max(
                candidatos, key=lambda x: x[0])

            if mejor_fecha is None or fecha_max_fila > mejor_fecha:
                mejor_fecha = fecha_max_fila
                mejor_elemento = elemento_max_fila
                mejor_tipo = tipo_fila
                mejor_fila_idx = fila_idx

        if mejor_elemento is None:
            log.info("No hay elementos clicables con fecha en la tabla.")
            return None

        if filas_con_candidatos > 1:
            log.info("%d filas con actuaciones. Se elige la más reciente: "
                     "%s (fila %s).",
                     filas_con_candidatos, mejor_fecha, mejor_fila_idx)
        else:
            log.info("Clic en última actuación %s (%s) [%s]",
                     mejor_fecha, radicado_limpio, mejor_tipo)

        objetivo = _elemento_clicable_de(mejor_elemento)

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", objetivo)
            time.sleep(0.4)
        except Exception:
            pass

        try:
            driver.execute_script("arguments[0].click();", objetivo)
        except Exception:
            try:
                objetivo.click()
            except Exception as e:
                log.warning("No se pudo hacer clic: %s", e)
                return None

        time.sleep(ESPERA_CLIC_ACTUACION)
        captura = tomar_captura(driver, "actuaciones_{}".format(radicado_limpio))
        return captura or "<sin-captura>"

    except Exception as e:
        log.warning("Error al hacer clic en la última actuación: %s", e)
        return None


# ====================================================================
# EXTRACCIÓN DE ACTUACIONES (con retry anti-stale)
# ====================================================================

def _esperar_tabla_actuaciones(driver,
                                timeout: int = TIMEOUT_TABLA_ACTUACIONES) -> bool:
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//th[contains(., 'Actuación') or contains(., 'Actuacion')]")))
        return True
    except TimeoutException:
        return False


def _extraer_actuaciones_una_vez(driver) -> list:
    """Extrae actuaciones una vez. Puede lanzar StaleElementReferenceException."""
    actuaciones = []

    tabla = None
    for t in driver.find_elements(By.TAG_NAME, "table"):
        for th in t.find_elements(By.TAG_NAME, "th"):
            if "fecha de actuaci" in _normalizar_texto(th.text):
                tabla = t
                break
        if tabla is not None:
            break
    if tabla is None:
        for t in driver.find_elements(By.TAG_NAME, "table"):
            if "actuaci" in _normalizar_texto(t.text):
                tabla = t
                break
    if tabla is None:
        return actuaciones

    filas = tabla.find_elements(By.TAG_NAME, "tr")
    if len(filas) < 2:
        return actuaciones

    encabezados = filas[0].find_elements(By.TAG_NAME, "th")
    idx_fecha, idx_actuacion, idx_anotacion = 0, 1, 2
    idx_ini_term, idx_fin_term, idx_registro = 3, 4, 5

    for i, th in enumerate(encabezados):
        txt = _normalizar_texto(th.text)
        if "fecha de actuaci" in txt:
            idx_fecha = i
        elif txt.startswith("actuaci"):
            idx_actuacion = i
        elif "anotaci" in txt:
            idx_anotacion = i
        elif "inicia" in txt and "termin" in txt:
            idx_ini_term = i
        elif "finaliza" in txt and "termin" in txt:
            idx_fin_term = i
        elif "registro" in txt:
            idx_registro = i

    idx_max = max(idx_fecha, idx_actuacion, idx_anotacion,
                  idx_ini_term, idx_fin_term, idx_registro)

    for fila in filas[1:]:
        celdas = fila.find_elements(By.TAG_NAME, "td")
        if len(celdas) <= idx_max:
            continue

        def _txt(idx):
            try:
                return celdas[idx].text.strip()
            except StaleElementReferenceException:
                raise
            except Exception:
                return ""

        d = {
            "fecha": _txt(idx_fecha),
            "actuacion": _txt(idx_actuacion),
            "anotacion": _txt(idx_anotacion),
            "inicia_termino": _txt(idx_ini_term),
            "finaliza_termino": _txt(idx_fin_term),
            "fecha_registro": _txt(idx_registro),
        }
        if any(d.values()):
            actuaciones.append(d)

    return actuaciones


def extraer_actuaciones(driver) -> list:
    """Extrae actuaciones con reintentos anti-stale."""
    for intento in range(1, MAX_REINTENTOS_EXTRAER_ACTUACIONES + 1):
        try:
            return _extraer_actuaciones_una_vez(driver)
        except StaleElementReferenceException:
            log.info("   ⚠️ Tabla de actuaciones se re-renderizó "
                     "(stale element). Reintento %s/%s…",
                     intento, MAX_REINTENTOS_EXTRAER_ACTUACIONES)
            time.sleep(ESPERA_ENTRE_REINTENTOS_ACTUACIONES)
        except Exception as e:
            log.warning("Error extrayendo actuaciones: %s", e)
            return []

    log.warning("   ⚠️ No se pudo extraer la tabla de actuaciones "
                "tras %s reintentos.", MAX_REINTENTOS_EXTRAER_ACTUACIONES)
    return []


def _esperar_y_extraer_actuaciones(driver, timeout: int = 25) -> list:
    inicio = time.time()
    while time.time() - inicio < timeout:
        acts = extraer_actuaciones(driver)
        if acts:
            return acts
        time.sleep(1.0)
    return []


# ====================================================================
# REGISTRO DE ERROR
# ====================================================================

def _registro_error(radicado, estado, observacion, captura):
    return {
        "Radicado": radicado,
        "Estado": estado,
        "Fecha_Ultima_Actuacion": "",
        "Observacion": observacion,
        COLUMNA_RESUMEN: "",
        COLUMNA_LINEAS_INTERNA: [],
        "Despacho": "",
        "Demandante": "Sin demandante",
        "Demandado": "Sin demandado",
        "Apoderado": "Sin apoderado",
        "Captura": captura,
        COLUMNA_CAPTURA_ACT: "",
    }


# ====================================================================
# CONSULTA INDIVIDUAL — un intento
# ====================================================================

def _intentar_consulta(
    driver, radicado_limpio,
    dias_umbral, modo_actuaciones, cantidad_actuaciones,
    intento=1,
):
    """
    Realiza UN intento de consulta con timeout adaptativo.

    Devuelve (exito: bool, filas: list, motivo: str).
    """
    timeout_este_intento = _timeout_para_intento(intento)

    driver.get(URL_CONSULTA)
    seleccionar_todos_los_procesos(driver)

    try:
        campo_rad = WebDriverWait(driver, TIMEOUT_CAMPO_RADICADO).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//input[@type='text' and (contains(@id, 'Radicacion') "
                "or contains(@name, 'radicacion'))]")))
    except TimeoutException:
        campo_rad = driver.find_element(By.XPATH, "//input[@type='text'][1]")

    campo_rad.clear()
    for ch in radicado_limpio:
        campo_rad.send_keys(ch)
        time.sleep(random.uniform(0.02, 0.06))

    log.info("   Radicado ingresado. Esperando respuesta del servidor... "
             "(timeout adaptativo: %ss)", timeout_este_intento)
    time.sleep(ESPERA_INGRESO_RADICADO)

    try:
        btn_consultar = driver.find_element(
            By.XPATH,
            "//button[contains(., 'Consultar') or contains(., 'Buscar')]")
        driver.execute_script("arguments[0].click();", btn_consultar)
    except Exception:
        campo_rad.send_keys(Keys.ENTER)

    t_inicio = time.time()
    estado_espera = _esperar_resultado_rama(driver, timeout_este_intento)
    t_esperado = time.time() - t_inicio

    # --- CONEXIÓN CAÍDA (early abort) ---
    if estado_espera == "conexion_caida":
        log.warning("   🔌 Conexión caída tras %.1fs", t_esperado)
        captura = tomar_captura(
            driver, "conexion_caida_{}".format(radicado_limpio))
        return False, [_registro_error(
            radicado_limpio,
            "⚠️ Sin resultado / Conexión caída",
            "La conexión con el portal se cayó durante la consulta.",
            captura)], "conexion_caida"

    # --- ERROR DE RED (modal) ---
    if estado_espera == "error_red":
        captura = tomar_captura(
            driver, "network_error_{}".format(radicado_limpio))
        return False, [_registro_error(
            radicado_limpio,
            "⚠️ Sin resultado / Error Red",
            "Fallo de red en el portal de la Rama Judicial",
            captura)], "error_red"

    # --- SIN RESULTADOS ---
    if estado_espera == "sin_resultados":
        log.warning("   ⚠️ La consulta no generó resultados (%.1fs)", t_esperado)
        captura = tomar_captura(
            driver, "sin_resultado_{}".format(radicado_limpio))
        return True, [_registro_error(
            radicado_limpio,
            "⚠️ La consulta no generó resultados",
            "La consulta no generó resultados en el portal",
            captura)], "sin_resultados"

    # --- TIMEOUT ---
    if estado_espera == "timeout":
        log.warning("   ⏱️ Timeout tras %.1fs sin resultados", t_esperado)
        captura = tomar_captura(driver, "timeout_{}".format(radicado_limpio))
        return False, [_registro_error(
            radicado_limpio,
            "⚠️ Sin resultado / Error Servidor",
            "⚠️ El servidor de la Rama no respondió en {}s".format(
                timeout_este_intento),
            captura)], "timeout"

    # ---------- HAY TABLA ----------
    log.info("   ✅ Resultados cargados en %.1fs", t_esperado)
    time.sleep(ESPERA_RESULTADOS)

    # Extraer filas con retry anti-stale
    filas = []
    for intento_ext in range(1, MAX_REINTENTOS_EXTRAER_ACTUACIONES + 1):
        try:
            filas = extraer_filas_de_tabla(
                driver, radicado_limpio, dias_umbral)
            break
        except StaleElementReferenceException:
            log.info("   ⚠️ Tabla resultados stale. Reintento %s/%s…",
                     intento_ext, MAX_REINTENTOS_EXTRAER_ACTUACIONES)
            time.sleep(ESPERA_ENTRE_REINTENTOS_ACTUACIONES)
            time.sleep(1.0)

    if not filas:
        captura = tomar_captura(
            driver, "sin_resultado_{}".format(radicado_limpio))
        return True, [_registro_error(
            radicado_limpio,
            "Sin resultado",
            "El proceso no tiene fecha de actuación",
            captura)], "ok"

    captura = tomar_captura(driver, "exito_{}".format(radicado_limpio))
    for reg in filas:
        reg["Captura"] = captura
        reg.setdefault(COLUMNA_RESUMEN, "")
        reg.setdefault(COLUMNA_LINEAS_INTERNA, [])
        reg.setdefault(COLUMNA_CAPTURA_ACT, "")
        log.info("   Registro extraído -> Estado: %s | Obs: %s",
                 reg["Estado"], reg["Observacion"])

    captura_act = hacer_clic_ultima_actuacion(driver, radicado_limpio)

    if captura_act:
        actuaciones = _esperar_y_extraer_actuaciones(driver, timeout=25)

        if not actuaciones:
            log.warning("   ⚠️ Sin actuaciones tras 25s. Guardando HTML debug.")
            _dump_html(driver, "sin_actuaciones_{}".format(radicado_limpio))

        lineas, texto_plano = construir_resumen_actuaciones(
            actuaciones,
            modo=modo_actuaciones,
            cantidad=cantidad_actuaciones,
            dias_recientes=DIAS_ACTUACIONES_RECIENTES,
        )

        log.info("   Captura de actuaciones: %s",
                 captura_act if captura_act != "<sin-captura>" else "(desactivada)")
        log.info("   %s actuaciones extraídas, %s incluidas en el resumen.",
                 len(actuaciones), len(lineas))

        for reg in filas:
            reg[COLUMNA_CAPTURA_ACT] = (
                captura_act if captura_act != "<sin-captura>" else "")
            reg[COLUMNA_RESUMEN] = texto_plano
            reg[COLUMNA_LINEAS_INTERNA] = lineas
    else:
        log.info("   No se pudo abrir la vista de actuaciones.")

    return True, filas, "ok"


# ====================================================================
# CONSULTA INDIVIDUAL — con backoff exponencial
# ====================================================================

def consultar_radicado_individual(
    driver, radicado_limpio, i_actual, total_procesos,
    es_reintento=False, dias_umbral=10,
    modo_actuaciones="personalizado", cantidad_actuaciones=5,
):
    log.info("\nProcesando %s/%s: %s",
             i_actual, total_procesos, radicado_limpio)

    ultimo_exito = False
    ultimas_filas = []

    for intento in range(1, MAX_INTENTOS_INTERNOS + 1):
        espera = BACKOFF_SEGUNDOS[min(intento - 1, len(BACKOFF_SEGUNDOS) - 1)]
        if espera > 0:
            log.info("   ⏸️ Backoff: esperando %ss antes de reintentar…", espera)
            time.sleep(espera)

        try:
            exito, filas, motivo = _intentar_consulta(
                driver, radicado_limpio,
                dias_umbral, modo_actuaciones, cantidad_actuaciones,
                intento=intento,
            )
        except WebDriverException as e:
            log.error("   💀 Driver caído: %s", e)
            return False, [_registro_error(
                radicado_limpio,
                "⚠️ Error",
                "El navegador se cerró inesperadamente. "
                "Se reiniciará en la próxima consulta.",
                "")]
        except Exception as e:
            log.error("   Error procesando %s: %s", radicado_limpio, e)
            try:
                captura = tomar_captura(
                    driver, "error_{}".format(radicado_limpio))
            except Exception:
                captura = ""
            return False, [_registro_error(
                radicado_limpio,
                "⚠️ Error",
                "Error no controlado: {}".format(e),
                captura)]

        ultimo_exito = exito
        ultimas_filas = filas

        if motivo == "error_red" and intento < MAX_INTENTOS_INTERNOS:
            log.info("   🔄 Reintento interno %s/%s tras Network Error…",
                     intento + 1, MAX_INTENTOS_INTERNOS)
            continue

        if motivo == "conexion_caida" and intento < MAX_INTENTOS_INTERNOS:
            log.info("   🔄 Reintento interno %s/%s tras conexión caída…",
                     intento + 1, MAX_INTENTOS_INTERNOS)
            continue

        if motivo == "timeout" and intento < MAX_INTENTOS_INTERNOS:
            log.info("   🔄 Reintento interno %s/%s tras timeout…",
                     intento + 1, MAX_INTENTOS_INTERNOS)
            continue

        return exito, filas

    return ultimo_exito, ultimas_filas