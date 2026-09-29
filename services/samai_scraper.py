"""
services/samai_scraper.py
=========================
Módulo de consulta a SAMAI (Consejo de Estado - Jurisdicción Contencioso Administrativa).

Uso desde el orquestador:
    from services import samai_scraper
    resultado = samai_scraper.consultar("25000233300020240012300")

Uso reutilizando un driver existente (recomendado para consultas múltiples):
    driver = samai_scraper._crear_driver(headless=False)
    r1 = samai_scraper.consultar("...", driver=driver)
    r2 = samai_scraper.consultar("...", driver=driver)
    driver.quit()
"""

import logging
import os
import re
import time
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# 👇 IMPORTANTE: usa las rutas correctas desde core.constantes
from core.constantes import BASE_DIR


# ====================================================================
# RUTAS (usando BASE_DIR escribible)
# ====================================================================

CARPETA_LOGS = os.path.join(BASE_DIR, "logs", "samai")
CARPETA_CAPTURAS = os.path.join(BASE_DIR, "capturas", "samai")

for _c in (CARPETA_LOGS, CARPETA_CAPTURAS):
    try:
        os.makedirs(_c, exist_ok=True)
    except Exception:
        pass

ARCHIVO_LOG = os.path.join(
    CARPETA_LOGS,
    "log_samai_{}.txt".format(datetime.now().strftime("%Y%m%d_%H%M%S")),
)


# ====================================================================
# PARÁMETROS
# ====================================================================

URL_BASE = "https://samai.consejodeestado.gov.co"
URL_DETALLE = URL_BASE + "/Vistas/Casos/list_procesos.aspx?guid={guid}"

TIMEOUT_CAPTCHA = 20
TIMEOUT_DETALLE = 30
MAX_INTENTOS_CAPTCHA = 4
MAX_ACTUACIONES_GUARDAR = 5
MAX_CAPTCHAS_POR_RADICADO = 6

SEL_CAPTCHA_INPUT = "#MainContent_TxtCaptcha2"
XPATH_CAPTCHA_SPANS = ("//span[contains(@id,'Lbldato') or contains(@id,'LblIdato') "
                       "or contains(@id,'LBLDATO') or contains(@id,'LBLIDATO')]")
SEL_BOTON_CONTINUAR = "#MainContent_CmdNoRobot_btnInfo"
SEL_DETALLE_BLOQUE = "#esperaINFO_basicos"
SEL_DETALLE_RADICADO = "#MainContent_lblradicacion"

SEL_TAB_SUJETOS = "#MainContent_LbtSujetos"
POSTBACK_SUJETOS = "ctl00$MainContent$LbtSujetos"


# ====================================================================
# JERARQUÍA DE CORPORACIONES
# ====================================================================

SUPERIOR_DE_JUZGADO = {
    "Juzgados Administrativos de Antioquia": "Tribunal Administrativo de Antioquia",
    "Juzgados Administrativos de Medellín": "Tribunal Administrativo de Antioquia",
    "Juzgados Administrativos de Barranquilla": "Tribunal Administrativo del Atlántico",
    "Juzgados Administrativos de Cartagena": "Tribunal Administrativo de Bolívar",
    "Juzgados Administrativos de Tunja": "Tribunal Administrativo de Boyacá",
    "Juzgados Administrativos de Manizales": "Tribunal Administrativo de Caldas",
    "Juzgados Administrativos de Florencia": "Tribunal Administrativo del Caquetá",
    "Juzgados Administrativos de Yopal": "Tribunal Administrativo de Casanare",
    "Juzgados Administrativos de Popayán": "Tribunal Administrativo de Cauca",
    "Juzgados Administrativos de Valledupar": "Tribunal Administrativo de Cesar",
    "Juzgados Administrativos de Quibdó": "Tribunal Administrativo del Chocó",
    "Juzgados Administrativos de Montería": "Tribunal Administrativo de Córdoba",
    "Juzgados Administrativos de Bogotá D.C.": "Tribunal Administrativo de Cundinamarca",
    "Juzgados Administrativos de Cundinamarca": "Tribunal Administrativo de Cundinamarca",
    "Juzgados Administrativos de Neiva": "Tribunal Administrativo del Huila",
    "Juzgados Administrativos de Riohacha": "Tribunal Administrativo de La Guajira",
    "Juzgados Administrativos de Santa Marta": "Tribunal Administrativo del Magdalena",
    "Juzgados Administrativos de Villavicencio": "Tribunal Administrativo del Meta",
    "Juzgados Administrativos de Pasto": "Tribunal Administrativo de Nariño",
    "Juzgados Administrativos de Cúcuta": "Tribunal Administrativo de Norte de Santander",
    "Juzgados Administrativos de Armenia": "Tribunal Administrativo del Quindío",
    "Juzgados Administrativos de Pereira": "Tribunal Administrativo de Risaralda",
    "Juzgados Administrativos de San Andrés y Providencia": "Tribunal Administrativo de San Andrés y Providencia",
    "Juzgados Administrativos de Bucaramanga": "Tribunal Administrativo de Santander",
    "Juzgados Administrativos de Sincelejo": "Tribunal Administrativo de Sucre",
    "Juzgados Administrativos de Ibagué": "Tribunal Administrativo de Tolima",
    "Juzgados Administrativos de Cali": "Tribunal Administrativo del Valle del Cauca",
}
SUPERIOR_DE_TRIBUNAL = "Consejo de Estado"

DANE_CIUDAD_A_DEPARTAMENTO = {
    "11001": "25000", "05001": "05000", "08001": "08000", "13001": "13000",
    "15001": "15000", "17001": "17000", "18001": "18000", "85001": "85000",
    "19001": "19000", "20001": "20000", "27001": "27000", "23001": "23000",
    "41001": "41000", "44001": "44000", "47001": "47000", "50001": "50000",
    "52001": "52000", "54001": "54000", "63001": "63000", "66001": "66000",
    "88001": "88000", "68001": "68000", "70001": "70000", "73001": "73000",
    "76001": "76000",
}


def obtener_superior(corporacion):
    if not corporacion:
        return ""
    c = corporacion.strip()
    if c == SUPERIOR_DE_TRIBUNAL:
        return ""
    if c in SUPERIOR_DE_JUZGADO:
        return SUPERIOR_DE_JUZGADO[c]
    if c.startswith("Tribunal Administrativo"):
        return SUPERIOR_DE_TRIBUNAL
    if "Consejo de Estado" in c:
        return ""
    return ""


# ====================================================================
# LOGGING
# ====================================================================

try:
    _fh = logging.FileHandler(ARCHIVO_LOG, encoding="utf-8")
    _fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S"))
except Exception:
    _fh = None

_ch = logging.StreamHandler()
_ch.setFormatter(logging.Formatter(
    "%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S"))

_logger = logging.getLogger("samai")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    if _fh:
        _logger.addHandler(_fh)
    _logger.addHandler(_ch)


def log(msg):
    _logger.info(msg)


# ====================================================================
# DRIVER
# ====================================================================

def _crear_driver(headless=False):
    """Crea un driver de Chrome para SAMAI."""
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        log("🚗 Chrome iniciado (webdriver-manager).")
        return driver
    except ImportError:
        log("ℹ️ webdriver-manager no instalado, usando Selenium Manager...")
    except Exception as e:
        log("⚠️ webdriver-manager falló: {}. Probando Selenium Manager...".format(e))

    try:
        driver = webdriver.Chrome(options=options)
        log("🚗 Chrome iniciado (Selenium Manager).")
        return driver
    except Exception as e:
        log("❌ No se pudo iniciar Chrome: {}".format(e))
        return None


# ====================================================================
# HELPERS
# ====================================================================

def limpiar_radicado(numero):
    return re.sub(r"\D", "", str(numero or "")).strip()


def _sanitize(texto):
    if not texto:
        return ""
    return re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", str(texto))


def _norm(txt):
    return re.sub(r"\s+", " ", (txt or "").strip())


def _solo_fecha(txt):
    if not txt:
        return ""
    s = str(txt)
    m = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", s)
    if m:
        return "{}-{:02d}-{:02d}".format(m.group(1), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", s)
    if m:
        return "{}-{:02d}-{:02d}".format(m.group(3), int(m.group(2)), int(m.group(1)))
    return ""


def tomar_captura(driver, nombre):
    # Respeta el flag global de scraper.py
    try:
        from core import scraper as _scraper_mod
        if not getattr(_scraper_mod, "GUARDAR_CAPTURAS_GLOBAL", True):
            return ""
    except Exception:
        pass

    path = os.path.join(CARPETA_CAPTURAS, "{}.png".format(nombre))
    try:
        driver.save_screenshot(path)
        return path
    except Exception:
        return ""


def _limpiar_sesion(driver):
    try:
        driver.delete_all_cookies()
    except Exception:
        pass
    try:
        driver.execute_script(
            "try{window.localStorage.clear();}catch(e){}"
            "try{window.sessionStorage.clear();}catch(e){}")
    except Exception:
        pass


# ====================================================================
# GUID CANDIDATOS
# ====================================================================

def guids_candidatos(radicado_limpio):
    if not radicado_limpio or len(radicado_limpio) < 23:
        return []

    dane = radicado_limpio[:5]
    tipo = radicado_limpio[5:7]
    candidatos = [(dane, tipo)]

    dane_dep = DANE_CIUDAD_A_DEPARTAMENTO.get(dane)
    if dane_dep and dane_dep != dane:
        candidatos.append((dane_dep, "23"))
        candidatos.append((dane_dep, "03"))

    for t in ("33", "03", "23"):
        if t != tipo:
            candidatos.append((dane, t))

    vistos, out = set(), []
    for c in candidatos:
        if c not in vistos:
            vistos.add(c)
            out.append(radicado_limpio + c[0] + c[1])
    return out


# ====================================================================
# CAPTCHA
# ====================================================================

def _extraer_texto_spans(driver, spans):
    def _num_id(s):
        m = re.search(r"(\d+)\s*$", s.get_attribute("id") or "")
        return int(m.group(1)) if m else 9999
    partes = []
    for s in sorted(spans, key=_num_id):
        t = (s.text or "").strip()
        if not t:
            try:
                t = (driver.execute_script(
                    "return (arguments[0].textContent || '').trim();", s) or "").strip()
            except Exception:
                t = ""
        t = re.sub(r"\s+", "", t)
        if t:
            partes.extend(list(t))
    return re.sub(r"[^A-Za-z0-9]", "", "".join(partes))


def _leer_captcha(driver):
    try:
        WebDriverWait(driver, TIMEOUT_CAPTCHA).until(
            lambda d: len(d.find_elements(By.XPATH, XPATH_CAPTCHA_SPANS)) >= 2)
    except TimeoutException:
        pass
    spans = driver.find_elements(By.XPATH, XPATH_CAPTCHA_SPANS)
    if not spans:
        spans = driver.find_elements(By.XPATH, "//span[contains(@id,'dato')]")
    return _extraer_texto_spans(driver, spans) if spans else ""


def _enviar_captcha(driver, valor):
    try:
        inp = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SEL_CAPTCHA_INPUT)))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
        inp.click()
        inp.clear()
        inp.send_keys(valor)
        time.sleep(0.15)
    except Exception as e:
        log("   ⚠️ No se pudo escribir captcha: {}".format(e))
        return False
    try:
        btn = driver.find_element(By.CSS_SELECTOR, SEL_BOTON_CONTINUAR)
        driver.execute_script("arguments[0].click();", btn)
        return True
    except Exception:
        pass
    try:
        inp = driver.find_element(By.CSS_SELECTOR, SEL_CAPTCHA_INPUT)
        inp.send_keys(Keys.ENTER)
        return True
    except Exception:
        return False


def _detalle_cargado(driver, timeout=TIMEOUT_DETALLE):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SEL_DETALLE_BLOQUE)))
        return True
    except TimeoutException:
        return False


def _resolver_captcha(driver):
    for intento in range(1, MAX_INTENTOS_CAPTCHA + 1):
        captcha = _leer_captcha(driver)
        if not captcha:
            log("   ⚠️ Captcha vacío (intento {})".format(intento))
            time.sleep(1.5)
            continue
        log("   🧩 Captcha leído: '{}'".format(captcha))
        if not _enviar_captcha(driver, captcha):
            time.sleep(1.0)
            continue
        time.sleep(2.0)
        if _detalle_cargado(driver):
            log("   ✅ Captcha aceptado.")
            return True
        if driver.find_elements(By.CSS_SELECTOR, SEL_CAPTCHA_INPUT):
            log("   🔄 Reintentando captcha...")
            time.sleep(0.8)
    return False


# ====================================================================
# CLICK EN SUJETOS
# ====================================================================

def _sujetos_visibles(driver):
    try:
        body = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
        if "demandante" in body and "demandado" in body:
            return True
    except Exception:
        pass
    for css in ("div[id*='SujetosProcesales']", "div[id*='divSujetos']",
                "div[id*='divsujetos']", "div[id*='Sujetos']"):
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, css):
                if el.is_displayed() and (el.text or "").strip():
                    t = el.text.lower()
                    if "demandante" in t or "apoderado" in t or "tipo de sujeto" in t:
                        return True
        except Exception:
            continue
    return False


def _click_sujetos(driver):
    if _sujetos_visibles(driver):
        log("   ✅ Panel Sujetos ya visible")
        return True

    intentos = (
        (SEL_TAB_SUJETOS, "click"),
        (SEL_TAB_SUJETOS, "js_click"),
    )

    for sel, modo in intentos:
        try:
            el = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.3)

            if modo == "click":
                el.click()
                log("   🖱️ Click normal Sujetos ({})".format(sel))
            else:
                driver.execute_script("arguments[0].click();", el)
                log("   🖱️ JS click Sujetos ({})".format(sel))

            for _ in range(6):
                time.sleep(0.5)
                if _sujetos_visibles(driver):
                    return True
        except Exception as e:
            log("   ⚠️ Intento '{}' falló: {}".format(modo, e))

    try:
        for el in driver.find_elements(
                By.XPATH,
                "//a[contains(translate(text(),'SUJETOS','sujetos'),'sujetos')]"):
            if el.is_displayed():
                driver.execute_script("arguments[0].click();", el)
                log("   🖱️ Click por texto 'Sujetos'")
                for _ in range(6):
                    time.sleep(0.5)
                    if _sujetos_visibles(driver):
                        return True
    except Exception:
        pass

    log("   ⚠️ No se pudo cargar el panel Sujetos (rápido).")
    return False


# ====================================================================
# PARSERS
# ====================================================================

def _texto_por_selector(driver, css):
    try:
        return _norm(driver.find_element(By.CSS_SELECTOR, css).text)
    except Exception:
        return ""


def _texto_pagina(driver):
    try:
        return driver.find_element(By.TAG_NAME, "body").text or ""
    except Exception:
        return ""


def _parse_encabezado(driver):
    datos = {"radicado": "", "ponente": "", "clase": "",
             "marco_legal": "", "vigente": "", "salas": ""}
    datos["radicado"] = limpiar_radicado(
        _texto_por_selector(driver, SEL_DETALLE_RADICADO))
    try:
        texto = driver.find_element(By.CSS_SELECTOR, SEL_DETALLE_BLOQUE).text or ""
    except Exception:
        texto = _texto_pagina(driver)

    def _m(pat):
        r = re.search(pat, texto, re.IGNORECASE)
        return _norm(r.group(1)) if r else ""

    datos["ponente"] = _m(r"Ponente\s*:\s*(.+?)(?=\n|Clase|$)")
    datos["ponente"] = re.sub(r"^Consejo de Estado\s*-\s*", "",
                              datos["ponente"], flags=re.IGNORECASE).strip()
    datos["clase"] = _m(r"Clase\s*:\s*(.+?)(?=\n|Marco legal|$)")
    datos["marco_legal"] = _m(r"Marco legal\s*:\s*(.+?)(?=\n|Veces|$)")
    datos["salas"] = _m(r"Sala que conoce\s*:\s*(.+?)(?=\n|Sala que decide|$)")

    m = re.search(r"VIGENTE\s*\(\s*(SI|NO)\s*\)", texto, re.IGNORECASE)
    if m:
        datos["vigente"] = m.group(1).upper()
    else:
        m2 = re.search(r"VIGENTE\s*\(\s*(SI|NO)\s*\)",
                       _texto_pagina(driver), re.IGNORECASE)
        if m2:
            datos["vigente"] = m2.group(1).upper()
    return datos


def _parse_asunto_panel(driver):
    out = {"ubicacion": "", "etapa": "", "asunto": ""}
    panel_texto = ""
    for css in ("#MainContent_divAsunto", "div[id*='divAsunto']",
                "div[id*='Asunto']", "textarea[id*='Asunto']"):
        try:
            for c in driver.find_elements(By.CSS_SELECTOR, css):
                if c.is_displayed() and (c.text or "").strip():
                    panel_texto = c.text
                    break
            if panel_texto:
                break
        except Exception:
            continue
    if not panel_texto:
        panel_texto = _texto_pagina(driver)

    m = re.search(r"Ubicaci[óo]n\s*:\s*([^\n\r]+)", panel_texto, re.IGNORECASE)
    if m:
        out["ubicacion"] = _norm(m.group(1))
    m = re.search(r"Etapa\s*:\s*([^\n\r]+)", panel_texto, re.IGNORECASE)
    if m:
        out["etapa"] = _norm(m.group(1))
    m = re.search(
        r"Asunto\s*:\s*(.+?)(?=\n?Tipo de proceso|\n?Despacho origen|\n?Ciudad origen|$)",
        panel_texto, re.IGNORECASE | re.DOTALL)
    if m:
        out["asunto"] = _sanitize(_norm(m.group(1)))[:2000]
    return out


def _parse_actuaciones(driver):
    actuaciones = []
    tabla = None
    selectores = [
        "#MainContent_GridVwHistoricoActuaciones",
        "table[id*='GridVwHistoricoActuaciones']",
        "table[id*='HistoricoActuaciones']",
        "table[id*='GridVwActuaciones']",
        "table[id*='GridVwHist']",
        "table[id*='GridVw']",
        "table[id*='Historial']",
        "table[id*='Actuaciones']",
    ]
    for _ in range(30):
        for sel in selectores:
            try:
                for e in driver.find_elements(By.CSS_SELECTOR, sel):
                    filas = e.find_elements(By.TAG_NAME, "tr")
                    if len(filas) <= 1:
                        continue
                    ths = [_norm(t.text).lower() for t in
                           filas[0].find_elements(By.TAG_NAME, "th")]
                    unidos = " ".join(ths)
                    if (("fecha" in unidos and ("actuaci" in unidos or "anotaci" in unidos))
                            or ("actuaci" in unidos and "registro" in unidos)):
                        tabla = e
                        log("   📊 Tabla actuaciones: {}".format(sel))
                        break
                if tabla:
                    break
            except Exception:
                continue
        if tabla:
            break
        time.sleep(0.5)

    if tabla is None:
        return actuaciones

    try:
        filas = tabla.find_elements(By.CSS_SELECTOR, "tbody tr") or \
                tabla.find_elements(By.TAG_NAME, "tr")
        if len(filas) <= 1:
            return actuaciones

        encabezados = []
        try:
            encabezados = [_norm(t.text).lower()
                           for t in filas[0].find_elements(By.TAG_NAME, "th")]
        except Exception:
            pass

        idx = {"fecha_registro": 1, "fecha_actuacion": 2,
               "actuacion": 3, "anotacion": 4}
        for i, h in enumerate(encabezados):
            if "fecha registro" in h or "fecha de registro" in h:
                idx["fecha_registro"] = i
            elif "fecha actuaci" in h or "fecha de actuaci" in h:
                idx["fecha_actuacion"] = i
            elif h.startswith("actuaci"):
                idx["actuacion"] = i
            elif "anotaci" in h or "detalle" in h:
                idx["anotacion"] = i

        idx_max = max(idx.values())
        inicio = 1 if encabezados else 0

        for fila in filas[inicio:]:
            celdas = fila.find_elements(By.TAG_NAME, "td")
            if len(celdas) <= idx_max:
                continue
            item = {}
            for k, i in idx.items():
                try:
                    item[k] = _norm(celdas[i].text)
                except Exception:
                    item[k] = ""
            item["fecha_registro"] = _solo_fecha(item.get("fecha_registro", ""))
            item["fecha_actuacion"] = _solo_fecha(item.get("fecha_actuacion", ""))
            if any(item.values()):
                actuaciones.append(item)
        log("   📊 Actuaciones: {}".format(len(actuaciones)))
    except Exception as e:
        log("   ⚠️ Error extrayendo actuaciones: {}".format(e))
    return actuaciones


def _parse_sujetos_panel(driver):
    out = {
        "demandante": "", "demandado": "", "apoderado": "",
        "procurador": "", "otros": "",
    }

    tabla = None
    selectores = [
        "#MainContent_GridVwSujetosProcesales",
        "table[id*='GridVwSujetosProcesales']",
        "table[id*='GridVwSujetos']",
        "table[id*='GridSujetos']",
        "table[id*='SujetosProcesales']",
        "table[id*='Sujetos']",
        "table[id*='sujetos']",
    ]

    for _ in range(20):
        for sel in selectores:
            try:
                for e in driver.find_elements(By.CSS_SELECTOR, sel):
                    if not e.is_displayed():
                        continue
                    filas = e.find_elements(By.TAG_NAME, "tr")
                    if len(filas) <= 1:
                        continue
                    ths = " ".join(_norm(t.text).lower()
                                   for t in filas[0].find_elements(By.TAG_NAME, "th"))
                    if ("sujeto" in ths and "nombre" in ths) or \
                       ("tipo" in ths and "nombre" in ths):
                        tabla = e
                        log("   👤 Tabla Sujetos: {}".format(sel))
                        break
                if tabla:
                    break
            except Exception:
                continue
        if tabla:
            break
        time.sleep(0.5)

    if tabla is None:
        for t in driver.find_elements(By.TAG_NAME, "table"):
            try:
                if not t.is_displayed():
                    continue
                filas = t.find_elements(By.TAG_NAME, "tr")
                if len(filas) <= 1:
                    continue
                ths = " ".join(_norm(x.text).lower()
                               for x in filas[0].find_elements(By.TAG_NAME, "th"))
                if "tipo de sujeto" in ths or "descripción del sujeto" in ths \
                        or "descripcion del sujeto" in ths:
                    tabla = t
                    log("   👤 Tabla Sujetos (fallback header)")
                    break
            except Exception:
                continue

    if tabla is None:
        log("   ⚠️ No se encontró la tabla de Sujetos; probando texto...")
        return _parse_sujetos_por_texto(driver)

    try:
        filas = tabla.find_elements(By.CSS_SELECTOR, "tbody tr") or \
                tabla.find_elements(By.TAG_NAME, "tr")
        if len(filas) <= 1:
            return out

        encabezados = []
        try:
            encabezados = [_norm(t.text).lower()
                           for t in filas[0].find_elements(By.TAG_NAME, "th")]
            log("   📋 Encabezados Sujetos: {}".format(encabezados))
        except Exception:
            pass

        i_tipo, i_nombre = 1, 2
        for i, h in enumerate(encabezados):
            if "tipo de sujeto" in h or h == "tipo":
                i_tipo = i
            elif "nombre" in h or "descripci" in h:
                i_nombre = i

        demandantes, demandados, apoderados, procuradores, otros = [], [], [], [], []

        inicio = 1 if encabezados else 0
        for fila in filas[inicio:]:
            celdas = fila.find_elements(By.TAG_NAME, "td")
            if len(celdas) <= max(i_tipo, i_nombre):
                continue
            tipo = _norm(celdas[i_tipo].text)
            nombre = _norm(celdas[i_nombre].text)
            if not nombre:
                continue
            tl = tipo.lower()

            if "demandante" in tl:
                demandantes.append(nombre)
            elif "demandado" in tl:
                demandados.append(nombre)
            elif "apoderado" in tl:
                apoderados.append(nombre)
            elif "procurador" in tl:
                procuradores.append(nombre)
            else:
                if tl and "sin tipo" not in tl:
                    otros.append("{}: {}".format(tipo, nombre))
                elif not tl:
                    otros.append(nombre)

        out["demandante"] = "; ".join(demandantes)
        out["demandado"] = "; ".join(demandados)
        out["apoderado"] = "; ".join(apoderados)
        out["procurador"] = "; ".join(procuradores)
        out["otros"] = "; ".join(otros)

        log("   👤 Sujetos parseados → Dte:{} Ddo:{} Apod:{} Proc:{}".format(
            len(demandantes), len(demandados),
            len(apoderados), len(procuradores)))

    except Exception as e:
        log("   ⚠️ Error parseando tabla Sujetos: {}".format(e))

    return out


def _parse_sujetos_por_texto(driver):
    out = {
        "demandante": "", "demandado": "", "apoderado": "",
        "procurador": "", "otros": "",
    }
    texto = _texto_pagina(driver)

    patterns = {
        "demandante": r"Demandantes?\s*[:\-]\s*([^\n\r]+)",
        "demandado": r"Demandados?\s*:\s*([^\n\r]+)",
        "apoderado": r"Apoderados?(?:\s+del\s+demandante)?\s*[:\-]\s*([^\n\r]+)",
        "procurador": r"Procuradores?\s*[:\-]\s*([^\n\r]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, texto, re.IGNORECASE)
        if m:
            out[key] = _norm(m.group(1))
    return out


# ====================================================================
# PUNTAJE
# ====================================================================

def _score(r):
    s = 0
    if r.get("demandante") and r["demandante"] not in ("Sin demandante",):
        s += 5
    if r.get("demandado") and r["demandado"] not in ("Sin demandado",):
        s += 5
    if r.get("apoderado") and r["apoderado"] not in ("Sin apoderado",):
        s += 3
    if r.get("procurador"):
        s += 2
    if r.get("fecha_ultima_actuacion"):
        s += 5
    if r.get("resumen"):
        s += 3
    if r.get("despacho"):
        s += 1
    if r.get("ubicacion"):
        s += 1
    if r.get("etapa"):
        s += 1
    return s


def _tiene_datos_utiles(r):
    if r.get("demandante") and r["demandante"] not in ("Sin demandante", ""):
        return True
    if r.get("demandado") and r["demandado"] not in ("Sin demandado", ""):
        return True
    if r.get("fecha_ultima_actuacion"):
        return True
    if r.get("resumen"):
        return True
    return False


# ====================================================================
# CONSULTA INTERNA
# ====================================================================

def _dict_error(radicado, msg, captura=""):
    return {
        "radicado": radicado,
        "jurisdiccion": "SAMAI",
        "estado": "",
        "fecha_ultima_actuacion": "",
        "observacion": msg,
        "despacho": "",
        "demandante": "",
        "demandado": "",
        "apoderado": "",
        "procurador": "",
        "resumen": "",
        "captura": captura,
        "captura_actuaciones": "",
        "ponente": "",
        "clase": "",
        "vigente": "",
        "ubicacion": "",
        "etapa": "",
        "error": msg,
    }


def _parsear_detalle_actual(driver, radicado_limpio, guardar_captura,
                             captura_listado, debug=False,
                             cantidad_actuaciones=5):
    enc = _parse_encabezado(driver)
    asunto = _parse_asunto_panel(driver)
    log("   📌 Ubicación: '{}' | Etapa: '{}'".format(
        asunto["ubicacion"], asunto["etapa"]))

    click_ok = _click_sujetos(driver)
    log("   👤 Click Sujetos: {}".format("OK" if click_ok else "FALLÓ"))
    time.sleep(0.8)
    sujetos = _parse_sujetos_panel(driver)
    log("   📌 Demandante: '{}' | Demandado: '{}' | Apoderado: '{}' | Procurador: '{}'".format(
        sujetos["demandante"][:50], sujetos["demandado"][:50],
        sujetos["apoderado"][:50], sujetos["procurador"][:50]))

    actuaciones = _parse_actuaciones(driver)

    captura_detalle = tomar_captura(
        driver, "samai_detalle_{}".format(radicado_limpio)) if guardar_captura else ""

    if debug and (not actuaciones or not sujetos["demandante"]):
        try:
            path = os.path.join(CARPETA_CAPTURAS,
                                "debug_{}.html".format(radicado_limpio))
            with open(path, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            log("   🐞 HTML debug: {}".format(path))
        except Exception:
            pass

    actuaciones_top = actuaciones[:max(1, int(cantidad_actuaciones))]

    fecha_ult = ""
    observacion = ""
    partes_resumen = []
    if actuaciones_top:
        fecha_ult = actuaciones_top[0].get("fecha_actuacion", "") or ""
        p = actuaciones_top[0]
        observacion = " | ".join(x for x in (p.get("actuacion"), p.get("anotacion")) if x)
        for a in actuaciones_top:
            partes_resumen.append("{} | {} | {} | {}".format(
                a.get("fecha_registro", ""),
                a.get("fecha_actuacion", ""),
                a.get("actuacion", ""),
                a.get("anotacion", ""),
            ))
    if not fecha_ult and not observacion:
        observacion = "Sin actuaciones registradas en SAMAI"

    return {
        "radicado": enc.get("radicado") or radicado_limpio,
        "jurisdiccion": "SAMAI",
        "estado": asunto.get("ubicacion", "") or "",
        "fecha_ultima_actuacion": fecha_ult,
        "observacion": _sanitize(observacion),
        "despacho": enc.get("ponente", ""),
        "demandante": sujetos.get("demandante", ""),
        "demandado": sujetos.get("demandado", ""),
        "apoderado": sujetos.get("apoderado", ""),
        "procurador": sujetos.get("procurador", ""),
        "resumen": _sanitize(" || ".join(partes_resumen)),
        "captura": captura_listado,
        "captura_actuaciones": captura_detalle,
        "ponente": enc.get("ponente", ""),
        "clase": enc.get("clase", ""),
        "vigente": enc.get("vigente", ""),
        "ubicacion": asunto.get("ubicacion", ""),
        "etapa": asunto.get("etapa", ""),
        "error": None,
    }


def _consultar_con_driver(driver, radicado, guardar_captura=True, debug=False,
                          cantidad_actuaciones=5, debe_pausar=None):
    """Lógica interna que asume que el driver ya está listo."""
    radicado_limpio = limpiar_radicado(radicado)
    if not radicado_limpio:
        return _dict_error(radicado, "Radicado vacío.")

    log("\n🔍 SAMAI → radicado {}".format(radicado_limpio))

    guids = guids_candidatos(radicado_limpio)
    if not guids:
        return _dict_error(radicado_limpio, "No se pudo construir guid.")

    mejor = None
    mejor_score = -1
    captchas_resueltos = 0

    for i, guid in enumerate(guids):
        if captchas_resueltos >= MAX_CAPTCHAS_POR_RADICADO and mejor is None:
            log("   🛑 Se resolvieron {} captchas sin datos útiles. "
                "Abortando para no alertar a SAMAI.".format(captchas_resueltos))
            break

        if debe_pausar is not None and debe_pausar():
            log("   ⏸️ Pausa detectada. Abortando consulta SAMAI.")
            return _dict_error(
                radicado_limpio,
                "Consulta interrumpida por pausa/cancelación del usuario.",
            )

        es_fb = (i > 0)
        url = URL_DETALLE.format(guid=guid)
        log("   🌐 Intento {}/{} {}: {}".format(
            i + 1, len(guids), "(fallback)" if es_fb else "(primario)", guid))

        if i == 0:
            _limpiar_sesion(driver)

        try:
            driver.get("about:blank")
            time.sleep(0.3)
            driver.get(url)
        except WebDriverException as e:
            log("   ⚠️ Error cargando URL: {}".format(e))
            continue

        time.sleep(1.5)

        if driver.find_elements(By.CSS_SELECTOR, SEL_CAPTCHA_INPUT):
            log("   🧩 Captcha requerido")
            if not _resolver_captcha(driver):
                log("   ❌ Captcha no resuelto; siguiente guid")
                if guardar_captura:
                    tomar_captura(driver,
                                  "captcha_fail_{}_{}".format(radicado_limpio, i))
                continue
            captchas_resueltos += 1

        if not _detalle_cargado(driver):
            log("   ❌ Detalle no cargó")
            if guardar_captura:
                tomar_captura(driver,
                              "sin_detalle_{}_{}".format(radicado_limpio, i))
            continue

        log("   ✅ Detalle cargado")

        captura_listado = tomar_captura(
            driver, "samai_{}{}".format(radicado_limpio, "_fb" if es_fb else "")
        ) if guardar_captura else ""

        r = _parsear_detalle_actual(
            driver, radicado_limpio, guardar_captura, captura_listado,
            debug=debug, cantidad_actuaciones=cantidad_actuaciones,
        )
        sc = _score(r)
        log("   📊 Score: {}".format(sc))

        if sc > mejor_score:
            mejor = r
            mejor_score = sc

        if _tiene_datos_utiles(r):
            log("   ✅ Datos útiles con este guid; me quedo con él.")
            return r

        log("   ⚠️ Sin datos útiles con este guid; siguiente...")

    if mejor is not None:
        log("   ℹ️ Se devuelve el mejor resultado (score={}).".format(mejor_score))
        return mejor
    return _dict_error(radicado_limpio, "Ningún guid cargó el detalle.")


# ====================================================================
# FUNCIÓN PÚBLICA
# ====================================================================

def consultar(radicado, driver=None, guardar_captura=True, debug=False,
              cantidad_actuaciones=5, debe_pausar=None):
    """
    Consulta pública de SAMAI.
    """
    if driver is not None:
        return _consultar_con_driver(
            driver, radicado,
            guardar_captura=guardar_captura, debug=debug,
            cantidad_actuaciones=cantidad_actuaciones,
            debe_pausar=debe_pausar,
        )

    driver_temporal = _crear_driver(headless=False)
    if driver_temporal is None:
        return _dict_error(radicado, "No se pudo iniciar el navegador Chrome.")
    try:
        return _consultar_con_driver(
            driver_temporal, radicado,
            guardar_captura=guardar_captura, debug=debug,
            cantidad_actuaciones=cantidad_actuaciones,
            debe_pausar=debe_pausar,
        )
    finally:
        try:
            driver_temporal.quit()
        except Exception:
            pass


# ====================================================================
# PRUEBA MANUAL
# ====================================================================

if __name__ == "__main__":
    radicado_prueba = input("Ingrese el radicado a consultar: ").strip()
    resultado = consultar(radicado_prueba, debug=True)
    print("\n=== RESULTADO ===")
    for k, v in resultado.items():
        print(f"{k}: {v}")