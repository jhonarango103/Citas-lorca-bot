"""
Bot de monitorización de citas — Jura de Nacionalidad
Registro Civil de Lorca (Murcia)

Comprueba periódicamente la web oficial de cita previa del Ministerio de
Justicia (sistema icpplus) y avisa por Telegram (texto + nota de voz)
en cuanto aparezca una cita disponible ANTES de la fecha límite que
configures en config.json.

IMPORTANTE — léelo antes de usarlo:
- Esto SOLO consulta disponibilidad. No reserva la cita por ti (reservar
  suele requerir tus datos personales y a veces un captcha; eso lo tienes
  que hacer tú a mano en cuanto te avise el bot).
- La web puede cambiar su estructura en cualquier momento. Si el bot deja
  de encontrar el trámite o el calendario, ejecútalo con debug=true en
  config.json: te guardará capturas en debug_screenshots/ para que
  puedas ver qué ha cambiado.
"""

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path

import requests
from gtts import gTTS
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
ESTADO_PATH = BASE_DIR / "estado.json"
LOG_PATH = BASE_DIR / "bot.log"
SCREENSHOT_DIR = BASE_DIR / "debug_screenshots"
AUDIO_PATH = BASE_DIR / "aviso.mp3"

URL_INICIO = "https://sede.administracionespublicas.gob.es/icpplustiej/citar?i=es&org=JUS-RC"

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

TEXTOS_NO_DISPONIBLE = [
    "no hay citas disponibles",
    "no existen citas disponibles",
    "no hay horas disponibles",
    "en este momento no hay citas",
    "vuelva a intentarlo más tarde",
    "no se ha encontrado ningún hueco",
]

TEXTOS_BOTON_SIGUIENTE = ["Aceptar", "Continuar", "Solicitar Cita", "Entrar", "Siguiente"]

SELECTORES_DIA_DISPONIBLE = [
    "a.diaDisp",
    "td.diaDisponible a",
    ".ui-datepicker-calendar a",
    "table.calendar a",
    "a[id*='dia']:not([disabled])",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("citas_lorca")


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

def cargar_config():
    """Carga la configuración desde variables de entorno (modo GitHub Actions)
    si están presentes; si no, cae en config.json (modo local/PC)."""
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        cfg = {
            "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN"),
            "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID"),
            "fecha_limite": os.environ.get("FECHA_LIMITE"),
            "keyword_oficina": os.environ.get("KEYWORD_OFICINA", "lorca"),
            "keyword_tramite": os.environ.get("KEYWORD_TRAMITE", "nacionalidad"),
            "intervalo_minutos": int(os.environ.get("INTERVALO_MINUTOS", "15")),
            "debug": os.environ.get("DEBUG", "false").lower() == "true",
            "avisar_errores": os.environ.get("AVISAR_ERRORES", "true").lower() == "true",
        }
    else:
        if not CONFIG_PATH.exists():
            log.error(
                "No encuentro config.json ni variables de entorno TELEGRAM_BOT_TOKEN. "
                "Copia config.example.json a config.json y rellena tus datos."
            )
            sys.exit(1)
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("keyword_oficina", "lorca")
        cfg.setdefault("keyword_tramite", "nacionalidad")
        cfg.setdefault("intervalo_minutos", 15)
        cfg.setdefault("debug", False)
        cfg.setdefault("avisar_errores", True)

    obligatorios = ["telegram_bot_token", "telegram_chat_id", "fecha_limite"]
    faltan = [k for k in obligatorios if not cfg.get(k)]
    if faltan:
        log.error(f"Faltan datos de configuración: {faltan}")
        sys.exit(1)

    try:
        cfg["fecha_limite_obj"] = datetime.strptime(cfg["fecha_limite"], "%Y-%m-%d").date()
    except ValueError:
        log.error("fecha_limite debe tener formato AAAA-MM-DD, por ejemplo 2026-12-31")
        sys.exit(1)

    return cfg


def cargar_estado():
    if ESTADO_PATH.exists():
        try:
            with open(ESTADO_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"ultima_fecha_notificada": None, "fallos_seguidos": 0}


def guardar_estado(estado):
    with open(ESTADO_PATH, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Notificaciones por Telegram
# ---------------------------------------------------------------------------

def enviar_telegram_texto(token, chat_id, texto):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": texto}, timeout=15)
        r.raise_for_status()
    except Exception as e:
        log.error(f"Error enviando mensaje de Telegram: {e}")


def enviar_telegram_audio(token, chat_id, texto_audio):
    try:
        tts = gTTS(text=texto_audio, lang="es")
        tts.save(str(AUDIO_PATH))
        url = f"https://api.telegram.org/bot{token}/sendAudio"
        with open(AUDIO_PATH, "rb") as f:
            r = requests.post(
                url,
                data={"chat_id": chat_id, "title": "Aviso cita Lorca"},
                files={"audio": f},
                timeout=30,
            )
            r.raise_for_status()
    except Exception as e:
        log.error(f"Error enviando audio de Telegram: {e}")


def notificar_cita(cfg, fecha_encontrada):
    texto = (
        f"✅ Hay cita disponible para JURA DE NACIONALIDAD en el "
        f"Registro Civil de Lorca: {fecha_encontrada}\n\n"
        f"Resérvala ya (el bot NO reserva por ti):\n{URL_INICIO}"
    )
    log.info(texto)
    enviar_telegram_texto(cfg["telegram_bot_token"], cfg["telegram_chat_id"], texto)
    enviar_telegram_audio(
        cfg["telegram_bot_token"],
        cfg["telegram_chat_id"],
        f"Atención. Hay cita disponible para jura de nacionalidad en el "
        f"registro civil de Lorca. Fecha: {fecha_encontrada}. Entra a reservarla cuanto antes.",
    )


def notificar_error(cfg, mensaje):
    if not cfg.get("avisar_errores", True):
        return
    texto = f"⚠️ El bot de citas de Lorca lleva varios intentos fallando.\nÚltimo error: {mensaje}"
    enviar_telegram_texto(cfg["telegram_bot_token"], cfg["telegram_chat_id"], texto)


# ---------------------------------------------------------------------------
# Navegación de la web (Playwright)
# ---------------------------------------------------------------------------

def aceptar_cookies(page):
    for texto in ["Aceptar todas", "Acepto", "Aceptar"]:
        try:
            boton = page.get_by_text(texto, exact=False).first
            if boton and boton.is_visible():
                boton.click(timeout=3000)
                return
        except Exception:
            pass


def seleccionar_select_por_opcion(page, texto_opcion):
    """Busca entre todos los <select> de la página uno que tenga una opción
    con el texto indicado, y la selecciona. Devuelve True si lo consigue."""
    selects = page.locator("select")
    for i in range(selects.count()):
        sel = selects.nth(i)
        opciones = sel.locator("option")
        for j in range(opciones.count()):
            try:
                texto = (opciones.nth(j).inner_text() or "").strip().lower()
            except Exception:
                continue
            if texto_opcion.lower() in texto:
                valor = opciones.nth(j).get_attribute("value")
                sel.select_option(value=valor)
                return True
    return False


def buscar_y_click_tramite(page, palabra_oficina, palabra_tramite, debug=False):
    """Busca una fila/enlace/etiqueta que contenga a la vez la oficina y el
    trámite deseados, y hace clic en su radio/checkbox/enlace."""
    elementos = page.locator("tr, label, a, li")
    total = elementos.count()
    encontrados = []
    for i in range(total):
        el = elementos.nth(i)
        try:
            txt = (el.inner_text() or "").strip().lower()
        except Exception:
            continue
        if palabra_oficina.lower() in txt and palabra_tramite.lower() in txt:
            encontrados.append((i, txt[:150]))
    if debug:
        log.info(f"Coincidencias de trámite encontradas ({len(encontrados)}): {encontrados}")
    if not encontrados:
        return False

    idx = encontrados[0][0]
    el = elementos.nth(idx)
    try:
        interactivo = el.locator("input[type=radio], input[type=checkbox], a").first
        if interactivo.count() > 0:
            interactivo.click(timeout=5000)
        else:
            el.click(timeout=5000)
        return True
    except Exception as e:
        log.warning(f"No se pudo hacer click en el trámite encontrado: {e}")
        return False


def _texto_cabecera_mes(page):
    cabecera = page.locator(".ui-datepicker-title, .mesActual, .calendarHeader, h2, h3")
    if cabecera.count() > 0:
        try:
            return cabecera.first.inner_text().strip()
        except Exception:
            return ""
    return ""


def _parsear_mes_anio(texto):
    """Intenta sacar (mes, año) de una cabecera tipo 'Julio 2026' o 'julio de 2026'."""
    texto = texto.lower()
    for nombre, numero in MESES_ES.items():
        if nombre in texto:
            m = re.search(r"(\d{4})", texto)
            if m:
                return numero, int(m.group(1))
    return None, None


def _dias_disponibles_en_vista(page):
    """Devuelve lista de números de día habilitados visibles en el calendario actual."""
    dias = []
    for selector in SELECTORES_DIA_DISPONIBLE:
        celdas = page.locator(selector)
        for i in range(celdas.count()):
            try:
                txt = celdas.nth(i).inner_text().strip()
            except Exception:
                continue
            m = re.search(r"\d{1,2}", txt)
            if m:
                dias.append(int(m.group(0)))
        if dias:
            break  # ya encontramos el selector que funciona en esta web
    return dias


def extraer_fechas_disponibles(page, debug=False):
    """Recorre el calendario visible (y, si existe, un botón de 'mes siguiente')
    y devuelve una lista de objetos date() con los días habilitados que ha
    conseguido identificar con certeza."""
    resultado = []

    for intento in range(2):  # vista actual, y opcionalmente el mes siguiente
        cabecera = _texto_cabecera_mes(page)
        mes, anio = _parsear_mes_anio(cabecera)
        dias = _dias_disponibles_en_vista(page)
        if debug:
            log.info(f"Vista de calendario -> cabecera='{cabecera}' días={dias}")

        if mes and anio:
            for d in dias:
                try:
                    resultado.append(date(anio, mes, d))
                except ValueError:
                    continue
        elif dias:
            # Hay días marcados como disponibles pero no pudimos leer el mes/año
            # con certeza: lo señalamos igualmente para no ocultar una cita real.
            resultado.append("INCIERTO")

        if intento == 0:
            boton_siguiente = page.locator(
                ".ui-datepicker-next, a[title*='Sig'], button[aria-label*='sig'], a[title*='sig']"
            )
            if boton_siguiente.count() > 0 and boton_siguiente.first.is_visible():
                try:
                    boton_siguiente.first.click(timeout=3000)
                    page.wait_for_timeout(800)
                    continue
                except Exception:
                    break
            else:
                break
        else:
            break

    return resultado


def _mejor_resultado(fechas, fecha_limite_obj):
    """De la lista de fechas encontradas (algunas pueden ser el marcador
    'INCIERTO'), decide qué reportar:
    - Si hay alguna fecha real <= fecha_limite: la más temprana de ellas.
    - Si solo hay 'INCIERTO': lo reportamos igualmente (mejor avisar de más
      que dejar pasar una cita real por un fallo de lectura).
    - Si no hay nada: None.
    """
    reales = sorted(f for f in fechas if isinstance(f, date))
    validas = [f for f in reales if f <= fecha_limite_obj]
    if validas:
        return validas[0].strftime("%d/%m/%Y")
    if reales:
        return None  # hay citas, pero todas después de tu fecha límite
    if "INCIERTO" in fechas:
        return "fecha sin verificar automáticamente (revisa el calendario a mano)"
    return None


def avanzar_hasta_calendario(page, cfg, debug=False, max_pasos=6):
    for paso in range(max_pasos):
        contenido = page.content().lower()

        if any(t in contenido for t in TEXTOS_NO_DISPONIBLE):
            return None  # confirmado: sin citas

        if "captcha" in contenido or page.locator("iframe[src*='recaptcha']").count() > 0:
            raise RuntimeError("La página mostró un captcha; no se puede continuar automáticamente.")

        fechas = extraer_fechas_disponibles(page, debug=debug)
        if fechas:
            return _mejor_resultado(fechas, cfg["fecha_limite_obj"])

        avanzo = False
        for texto_boton in TEXTOS_BOTON_SIGUIENTE:
            boton = page.get_by_role("button", name=texto_boton, exact=False)
            if boton.count() == 0:
                boton = page.get_by_text(texto_boton, exact=False)
            if boton.count() > 0 and boton.first.is_visible():
                try:
                    boton.first.click(timeout=5000)
                    page.wait_for_load_state("networkidle", timeout=15000)
                    avanzo = True
                    if debug:
                        page.screenshot(path=str(SCREENSHOT_DIR / f"paso_{paso}_{texto_boton}.png"))
                    break
                except Exception:
                    continue
        if not avanzo:
            break

    fechas = extraer_fechas_disponibles(page, debug=debug)
    return _mejor_resultado(fechas, cfg["fecha_limite_obj"])


def comprobar_una_vez(cfg):
    debug = cfg.get("debug", False)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not debug)
        context = browser.new_context(locale="es-ES")
        page = context.new_page()
        page.set_default_timeout(20000)
        try:
            page.goto(URL_INICIO, wait_until="domcontentloaded")
            aceptar_cookies(page)
            if debug:
                page.screenshot(path=str(SCREENSHOT_DIR / "01_inicio.png"))

            if not seleccionar_select_por_opcion(page, "Murcia"):
                raise RuntimeError("No se encontró el desplegable de provincia con la opción 'Murcia'.")
            page.wait_for_load_state("networkidle")
            if debug:
                page.screenshot(path=str(SCREENSHOT_DIR / "02_provincia.png"))

            if not buscar_y_click_tramite(page, cfg["keyword_oficina"], cfg["keyword_tramite"], debug=debug):
                raise RuntimeError(
                    f"No se encontró ningún trámite que contenga "
                    f"'{cfg['keyword_oficina']}' y '{cfg['keyword_tramite']}' a la vez. "
                    f"Activa debug=true en config.json y revisa debug_screenshots/02_provincia.png "
                    f"para ver el texto exacto del trámite en la web."
                )
            page.wait_for_load_state("networkidle")
            if debug:
                page.screenshot(path=str(SCREENSHOT_DIR / "03_tramite.png"))

            resultado = avanzar_hasta_calendario(page, cfg, debug=debug)
            if debug:
                page.screenshot(path=str(SCREENSHOT_DIR / "04_resultado.png"))
            return resultado
        finally:
            context.close()
            browser.close()


# ---------------------------------------------------------------------------
# Bucle principal
# ---------------------------------------------------------------------------

def ejecutar_una_comprobacion(cfg, estado):
    """Hace una comprobación y decide si hay que avisar, comparando con el
    último resultado guardado en estado.json para no repetir el mismo aviso
    en cada ejecución mientras la cita siga disponible."""
    try:
        fecha = comprobar_una_vez(cfg)
        estado["fallos_seguidos"] = 0

        if fecha and fecha != estado.get("ultima_fecha_notificada"):
            log.info(f"¡Cita nueva encontrada!: {fecha}")
            notificar_cita(cfg, fecha)
            estado["ultima_fecha_notificada"] = fecha
        elif fecha:
            log.info(f"Sigue disponible la misma cita ya notificada: {fecha}")
        else:
            log.info("Sin citas disponibles por ahora.")
            estado["ultima_fecha_notificada"] = None

    except Exception as e:
        estado["fallos_seguidos"] = estado.get("fallos_seguidos", 0) + 1
        log.error(f"Error en la comprobación ({estado['fallos_seguidos']} seguidos): {e}")
        if estado["fallos_seguidos"] == 3:
            notificar_error(cfg, str(e))

    return estado


def bucle_principal():
    """Modo local: se queda corriendo para siempre, comprobando cada
    intervalo_minutos. Pensado para dejarlo en un PC o VPS encendido."""
    cfg = cargar_config()
    estado = cargar_estado()
    log.info(
        f"Bot iniciado (modo bucle). Trámite objetivo: '{cfg['keyword_tramite']}' en "
        f"'{cfg['keyword_oficina']}'. Fecha límite: {cfg['fecha_limite']}. "
        f"Comprobando cada {cfg['intervalo_minutos']} min."
    )
    while True:
        estado = ejecutar_una_comprobacion(cfg, estado)
        guardar_estado(estado)
        espera = cfg["intervalo_minutos"] * 60 + random.randint(-30, 60)
        time.sleep(max(60, espera))


def ejecutar_una_vez():
    """Modo CI: hace UNA comprobación y termina. Pensado para GitHub Actions,
    que se encarga de repetirlo con su propio cron."""
    cfg = cargar_config()
    estado = cargar_estado()
    log.info(
        f"Bot iniciado (modo --once). Trámite objetivo: '{cfg['keyword_tramite']}' en "
        f"'{cfg['keyword_oficina']}'. Fecha límite: {cfg['fecha_limite']}."
    )
    estado = ejecutar_una_comprobacion(cfg, estado)
    guardar_estado(estado)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once", action="store_true",
        help="Hace una sola comprobación y termina (modo GitHub Actions)."
    )
    args = parser.parse_args()

    if args.once:
        ejecutar_una_vez()
    else:
        bucle_principal()
