# ⚖️ Revisor Judicial

**Monitoreo inteligente de procesos judiciales para Rama Judicial y SAMAI (Consejo de Estado).**

Herramienta de escritorio para abogados y firmas legales que permite consultar de forma masiva el estado de procesos judiciales en Colombia, generar informes en Excel con clasificación automática y mantener un historial completo de las consultas.

---

## ✨ Características

- 🔍 **Consulta masiva** de radicados en Rama Judicial y SAMAI.
- 📊 **Informes Excel** con formato condicional (Revisar / Fuera / Errores).
- 📞 **Directorio judicial** con correos, direcciones y teléfonos de despachos.
- 📚 **Historial completo** de cada escaneo, con búsqueda y filtros.
- 📋 **Gestión de radicados** con respaldo automático.
- 🖼️ **Capturas automáticas** de cada consulta.
- 🌐 **Resiliencia de red**: reintentos, backoff y rotación de IP con WARP.
- 🔒 **Sistema de licencias** con activación por máquina.

## 🎯 ¿Para quién es?

- Abogados litigantes con múltiples procesos.
- Firmas legales que monitorean cartera de casos.
- Departamentos jurídicos de empresas.
- Áreas de cobranza y recuperación de cartera.

## 📥 Instalación

Consulta **[docs/GUIA_INSTALACION.md](docs/GUIA_INSTALACION.md)** para instrucciones paso a paso.

## 📖 Manual de uso

Consulta **[docs/MANUAL_USO.md](docs/MANUAL_USO.md)** para aprender a usar la herramienta.

## 🖥️ Requisitos

- **Windows 10** o superior (64 bits).
- **4 GB de RAM** mínimo.
- **500 MB de espacio** libre.
- **Conexión a internet**.

## 💻 Desarrollo

### Requisitos

- Python 3.10+
- Google Chrome instalado.

### Instalación en desarrollo

```bash
git clone https://github.com/serperior13/revisor-judicial.git
cd revisor-judicial
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py