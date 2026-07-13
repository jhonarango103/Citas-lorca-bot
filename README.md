# Bot de aviso de citas — Jura de Nacionalidad, Registro Civil de Lorca

Vigila la web oficial de cita previa del Ministerio de Justicia y te avisa
por Telegram (mensaje de texto **y** nota de voz) en cuanto haya una cita
disponible **antes** de la fecha que tú elijas.

Corre gratis en los servidores de GitHub (GitHub Actions), cada 15 minutos,
para siempre, sin que tu móvil ni tu PC tengan que estar encendidos.

⚠️ **No reserva la cita por ti.** Solo te avisa. La reserva final (con tus
datos personales) la tienes que hacer tú a mano, en cuanto te llegue el aviso.

---

## 1. Crear tu bot de Telegram (2 minutos, gratis)

1. Abre Telegram y busca **@BotFather**.
2. Escríbele `/newbot` y sigue las instrucciones (te pedirá un nombre).
3. Al terminar te dará un **token** parecido a `123456789:AAExxxxxxxxxxxxxxxxxxxxxxx`. Guárdalo.
4. Busca tu propio bot por el nombre de usuario que le pusiste y pulsa
   **Iniciar** (o escríbele "hola").
5. Para saber tu **chat_id**, abre en el navegador (cambiando `TU_TOKEN`
   por el tuyo):
   `https://api.telegram.org/botTU_TOKEN/getUpdates`
   Verás algo como `"chat":{"id":123456789,...}`. Ese número es tu `chat_id`.

## 2. Subir este proyecto a GitHub (gratis)

1. Crea una cuenta en [github.com](https://github.com) si no tienes.
2. Crea un repositorio nuevo, **público** (así los minutos de GitHub Actions
   son ilimitados y no te cuesta nada), por ejemplo `citas-lorca-bot`.
   No pasa nada porque sea público: el código no contiene tu token ni tus
   datos, eso va aparte en "Secrets" (ahora lo vemos).
3. Sube todos los archivos de esta carpeta al repositorio. Lo más fácil
   si nunca has usado Git: en la página del repo, botón **"Add file" →
   "Upload files"**, arrastras todos los archivos y carpetas (incluida la
   carpeta `.github/`) y das a **Commit changes**.

## 3. Configurar tus datos (Secrets y Variables)

En tu repositorio: **Settings → Secrets and variables → Actions**.

### Pestaña "Secrets" → New repository secret (2 secrets):

| Nombre | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN` | el token que te dio BotFather |
| `TELEGRAM_CHAT_ID` | tu chat_id |

### Pestaña "Variables" → New repository variable (al menos esta):

| Nombre | Valor |
|---|---|
| `FECHA_LIMITE` | la fecha más tardía que te sirve, formato `2026-12-31` |
| `KEYWORD_OFICINA` | `lorca` (déjalo así salvo que te diga lo contrario) |
| `KEYWORD_TRAMITE` | `nacionalidad` (déjalo así salvo que te diga lo contrario) |

No hace falta tocar nada más: el archivo `.github/workflows/citas-lorca.yml`
ya está programado para ejecutarse solo cada 15 minutos.

## 4. Probarlo ya, sin esperar 15 minutos

En tu repositorio, pestaña **Actions** → click en "Comprobar citas Registro
Civil Lorca" → botón **Run workflow** (arriba a la derecha) → **Run workflow**.

Espera 1-2 minutos y dale a refrescar: verás el resultado de esa ejecución.
Si algo falla, entra en esa ejecución y mira el log del paso "Ejecutar
comprobación" — te dirá exactamente qué ha pasado.

## 5. ¿Cómo sabré si ha fallado?

Dos formas:
- GitHub te manda un correo automático si una ejecución falla (activado por defecto).
- Si el bot falla 3 veces seguidas comprobando la web, te manda también un
  aviso por Telegram explicando el error.

## 6. Si el bot no encuentra el trámite correcto

La web del Registro Civil puede tener el texto del trámite escrito de forma
distinta a como lo he supuesto (por ejemplo "Jura de Nacionalidad Española"
en vez de solo "nacionalidad"). Si ves un error tipo *"No se encontró ningún
trámite que contenga..."*:

1. Cambia temporalmente la variable `DEBUG` a `true` en el workflow (o
   avísame y lo ajustamos juntos con las capturas).
2. En modo debug se guardan capturas en `debug_screenshots/`. Como GitHub
   Actions no tiene pantalla, súbelas como "artifact" — si quieres, dime y
   te añado ese paso al workflow para que puedas descargarlas después de
   cada ejecución.
3. Mándame lo que veas ahí y te doy el valor exacto para `KEYWORD_TRAMITE`.

## 7. Cosas que debes saber

- **No hace falta tu móvil ni tu PC encendidos.** El aviso te llegará a
  Telegram (y por tanto a tu móvil) igualmente, esté donde esté corriendo.
- **Si el repositorio está 60 días sin actividad**, GitHub pausa
  automáticamente los workflows programados por cron (para evitar bots
  abandonados). Si eso pasa, basta con entrar en la pestaña Actions y
  reactivarlo con un clic, o hacer login en GitHub de vez en cuando.
- **Si aparece un captcha** en la web, el bot se detiene ahí y te avisa
  por error; no intenta saltárselo.
- **La web puede cambiar** su estructura en cualquier momento (es habitual
  en estas sedes electrónicas). Si el bot deja de funcionar, avísame y
  revisamos juntos las capturas de debug.

## (Opcional) Correrlo en tu propio PC en vez de GitHub

Si alguna vez quieres probarlo en tu PC en lugar de en GitHub Actions:

```
pip install -r requirements.txt
playwright install chromium
copy config.example.json config.json
```

Rellena `config.json` con tus datos y ejecuta:

```
python citas_lorca_bot.py
```

Este modo (sin `--once`) se queda corriendo en bucle para siempre, comprobando
cada `intervalo_minutos`. Ciérralo con `Ctrl+C`.
