# Panel de Sentimiento de Mercado

Barómetro de Fear & Greed + AAII + 6 indicadores adicionales (VIX, Put/Call,
NAAIM, Insider Ratio, % S&P500 sobre media 200d, Smart/Dumb Money, Fed cut
probability), con captura semanal automática vía GitHub Actions.

## Puesta en marcha (10 minutos)

1. **Crea un repo nuevo en GitHub** (puede ser privado o público) y sube todo
   el contenido de esta carpeta tal cual (mantén la estructura de carpetas:
   `.github/workflows/`, `data/`, `scripts/`, `index.html`).

2. **Activa GitHub Pages con Actions como origen:**
   Settings → Pages → "Build and deployment" → Source: **GitHub Actions**.

3. **Comprueba los permisos del workflow:**
   Settings → Actions → General → "Workflow permissions" → marca
   **Read and write permissions**. Sin esto el job no puede hacer commit de
   `data/sentiment.json`.

4. **Lánzalo una vez a mano** para comprobar que todo funciona:
   pestaña **Actions** → "Captura semanal de sentimiento" → **Run workflow**.
   Tarda 3-5 minutos (el cálculo de % S&P500 > media 200d es lo más lento,
   porque descarga histórico de ~500 tickers).

5. **Abre la URL de Pages** que aparece en Settings → Pages tras el primer
   despliegue (algo como `https://tu-usuario.github.io/tu-repo/`). Guárdala
   en marcadores — es la que revisarás una vez por semana.

## Qué se automatiza y qué no

| Indicador | Automatizado | Fuente |
|---|---|---|
| VIX | ✅ | yfinance (`^VIX`) |
| CNN Fear & Greed | ✅ | endpoint JSON no oficial de CNN |
| AAII Bull-Bear Spread | ✅ | scraping de aaii.com/sentimentsurvey |
| Put/Call ratio (equity) | ✅ (best-effort) | scraping de cboe.com |
| % S&P500 > media 200d | ✅ | calculado desde cero con yfinance |
| NAAIM Exposure Index | ❌ manual | de pago |
| Insider Buy/Sell Ratio | ❌ manual | GuruFocus, de pago |
| Smart/Dumb Money | ❌ manual | SentimenTrader, de pago |
| Fed cut probability | ❌ manual | CME FedWatch no tiene API pública |

## Actualizar los 4 campos manuales

Edita `data/sentiment.json` directamente en GitHub (icono del lápiz, sin
clonar nada), cambia el valor y el campo `manual_updated` a la fecha de hoy,
y haz commit a `main`. La próxima ejecución automática (los jueves) respeta
esos 4 campos tal cual los dejaste — el script solo toca los 5 automatizados.

## Si algo del scraping se rompe

CNN, AAII y Cboe pueden cambiar el HTML/JSON de sus páginas en cualquier
momento sin avisar. Si eso pasa, el campo correspondiente simplemente
conserva su último valor bueno (el job no falla entero) y verás en los logs
de Actions un `[FAIL] <indicador>: <motivo>`. Dímelo y te actualizo el
selector/regex correspondiente en `scripts/fetch_sentiment.py`.

## Frecuencia

El cron está puesto para los **jueves a las 22:00 UTC** (tras el cierre de
EE.UU. y la publicación semanal de AAII). Si prefieres otro día/hora, cambia
la línea `cron:` en `.github/workflows/sentiment-weekly.yml`
([crontab.guru](https://crontab.guru) ayuda a construir la expresión).
