# RevisorJudicial.spec
# -*- mode: python ; coding: utf-8 -*-
"""
Configuración de PyInstaller para empaquetar Revisor Judicial.

Genera una carpeta 'dist/RevisorJudicial/' con el .exe y todas
las dependencias internas.

Usa collect_all() para traer TODOS los submódulos de las librerías
complejas (selenium, customtkinter, etc.), evitando errores como
'No module named selenium.webdriver.chrome.options'.

Uso:
    pyinstaller RevisorJudicial.spec --clean
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# ====================================================================
# RUTAS
# ====================================================================

BASE_DIR = Path(os.path.abspath(SPECPATH)).parent

# ====================================================================
# RECOLECCIÓN AUTOMÁTICA DE SUBMÓDULOS
# ====================================================================
#
# collect_all('paquete') devuelve (datas, binaries, hiddenimports)
# con TODO el contenido del paquete. Es la forma robusta de asegurar
# que todos los submódulos internos se incluyan.

datas = []
binaries = []
hiddenimports = []

# Paquetes que necesitan recolección completa
paquetes_completos = [
    'selenium',
    'webdriver_manager',
    'customtkinter',
    'darkdetect',
    'PIL',
    'pandas',
    'numpy',
    'openpyxl',
    'xlrd',
    'requests',
    'urllib3',
    'charset_normalizer',
    'certifi',
    'trio',
    'trio_websocket',
    'wsproto',
    'h11',
    'attrs',
    'outcome',
    'sniffio',
    'sortedcontainers',
    'idna',
    'dateutil',
    'tzdata',
    'et_xmlfile',
]

for paquete in paquetes_completos:
    try:
        d, b, h = collect_all(paquete)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        # Si el paquete no existe, lo ignoramos
        pass

# Paquetes de Windows (pywin32)
try:
    d, b, h = collect_all('win32com')
    datas += d
    binaries += b
    hiddenimports += h
except Exception:
    pass

try:
    d, b, h = collect_all('pythoncom')
    datas += d
    binaries += b
    hiddenimports += h
except Exception:
    pass

try:
    d, b, h = collect_all('pywintypes')
    datas += d
    binaries += b
    hiddenimports += h
except Exception:
    pass

# Recursos propios del proyecto
datas += [('resources', 'resources')]

# Hidden imports adicionales específicos
hiddenimports += [
    'PIL._tkinter_finder',
    'selenium.webdriver.chrome.options',
    'selenium.webdriver.chrome.service',
    'selenium.webdriver.common.by',
    'selenium.webdriver.common.keys',
    'selenium.webdriver.support.ui',
    'selenium.webdriver.support.expected_conditions',
    'selenium.common.exceptions',
    'webdriver_manager.chrome',
    'webdriver_manager.core',
    'webdriver_manager.core.driver_cache',
    'webdriver_manager.core.manager',
    'webdriver_manager.core.os_manager',
]

# ====================================================================
# ANÁLISIS
# ====================================================================

a = Analysis(
    ['main.py'],
    pathex=[str(BASE_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Excluir lo que no usamos (reduce el tamaño)
        'matplotlib',
        'scipy',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'wx',
        'notebook',
        'IPython',
        'jupyter',
        'pytest',
    ],
    noarchive=False,
    optimize=0,
)

# ====================================================================
# PYZ
# ====================================================================

pyz = PYZ(a.pure)

# ====================================================================
# EXE
# ====================================================================

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RevisorJudicial',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/icons/icono.ico',
)

# ====================================================================
# COLLECT
# ====================================================================

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RevisorJudicial',
)