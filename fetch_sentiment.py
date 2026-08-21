#!/usr/bin/env python3
"""
fetch_sentiment.py
------------------
Captura semanal de indicadores de sentimiento de mercado para el panel HTML.

Mismo patrón que monitor.py (rotación sectorial ETFs): se ejecuta desde
GitHub Actions, escribe/actualiza data.json en el repo, y el panel HTML
lee ese JSON en runtime (vía GitHub Pages).

De los 8 indicadores del panel, 5 se capturan aquí automáticamente:
    - VIX (yfinance)
    - % de S&P 500 sobre su media de 200 sesiones (calculado en bruto)
    - CNN Fear & Greed (endpoint no oficial)
    - AAII Bull-Bear Spread (scraping de la página pública)
    - CBOE Put/Call ratio equity (scraping best-effort)

Los otros 3 (NAAIM, Insider Buy/Sell Ratio, Smart/Dumb Money) son de pago
en origen: este script NUNCA los toca. Si no existen en data.json, los
crea con valores placeholder y una fecha "manual_updated" que el propio
panel usa para avisar si llevan demasiado tiempo sin refrescar.

Cada fetch está aislado en try/except: si una fuente falla o cambia de
formato, el resto de indicadores se actualiza igual y el campo que
falló conserva su último valor bueno, marcado como "stale": true.
"""

import json
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sentiment.json"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def load_existing():
    if DATA_PATH.exists():
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return default_skeleton()


def default_skeleton():
    return {
        "meta": {"last_run": None, "generated_by": "fetch_sentiment.py"},
        "fearGreed": {"value": None, "label": "", "date": None, "stale": True},
        "aaii": {
            "bullish": None, "neutral": None, "bearish": None,
            "avgBullish": 37.5, "avgNeutral": 31.5, "avgBearish": 31.0,
            "spread": None, "avgSpread": 6.5, "date": None, "stale": True,
            "history": []
        },
        "extra": {
            "vix": {"value": None, "date": None, "source": "Cboe / yfinance", "stale": True},
            "putCall": {"value": None, "date": None, "source": "CBOE Equity P/C", "stale": True},
            "naaim": {"value": 79.70, "prev": 84.02, "date": "2026-07-29",
                      "source": "NAAIM Exposure Index", "manual": True,
                      "manual_updated": "2026-08-17"},
            "insiderRatio": {"value": 0.23, "avg": 0.39, "date": "2026-07-01",
                              "source": "GuruFocus", "manual": True,
                              "manual_updated": "2026-08-17"},
            "pct200dma": {"value": None, "date": None,
                          "source": "S&P 500 constituents, calculado", "stale": True},
            "smartDumb": {"smart": 30, "dumb": 61, "date": "2026-07-16",
                          "source": "SentimenTrader", "manual": True,
                          "manual_updated": "2026-08-17"},
            "fedCut": {"cut": 31, "hold": 69, "meetingDate": "2026-09-16",
                       "date": "2026-08-14", "source": "CME FedWatch", "manual": True,
                       "manual_updated": "2026-08-17"}
        }
    }


def safe(fn, label, data):
    """Run a fetch function; on failure, keep old value and mark stale."""
    try:
        fn(data)
        print(f"  [ok] {label}")
    except Exception as e:
        print(f"  [FAIL] {label}: {e}")
        traceback.print_exc(limit=1)


# ---------------------------------------------------------------------
# 1) VIX — yfinance
# ---------------------------------------------------------------------
def fetch_vix(data):
    import yfinance as yf
    hist = yf.Ticker("^VIX").history(period="5d")
    if hist.empty:
        raise RuntimeError("yfinance devolvió histórico vacío para ^VIX")
    value = round(float(hist["Close"].iloc[-1]), 2)
    data["extra"]["vix"] = {
        "value": value, "date": TODAY, "source": "Cboe / yfinance", "stale": False
    }


# ---------------------------------------------------------------------
# 2) % S&P 500 sobre su media de 200 sesiones — calculado en bruto
# ---------------------------------------------------------------------
def fetch_pct_above_200dma(data):
    import pandas as pd
    import yfinance as yf

    tables = pd.read_html(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    )
    tickers = tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist()

    above = 0
    counted = 0
    batch_size = 50
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            hist = yf.download(
                batch, period="210d", interval="1d",
                group_by="ticker", progress=False, threads=True
            )
        except Exception:
            continue
        for t in batch:
            try:
                closes = hist[t]["Close"].dropna()
                if len(closes) < 150:  # exige histórico suficiente
                    continue
                ma200 = closes.tail(200).mean()
                last = closes.iloc[-1]
                counted += 1
                if last > ma200:
                    above += 1
            except Exception:
                continue
        time.sleep(1)  # cortesía con Yahoo

    if counted < 300:  # umbral mínimo de confianza (de ~500 tickers)
        raise RuntimeError(f"Solo se pudo evaluar {counted} tickers, insuficiente")

    pct = round(100 * above / counted, 1)
    data["extra"]["pct200dma"] = {
        "value": pct, "date": TODAY,
        "source": f"{counted} de {len(tickers)} tickers S&P500, calculado", "stale": False
    }


# ---------------------------------------------------------------------
# 3) CNN Fear & Greed — endpoint no oficial
# ---------------------------------------------------------------------
def fetch_fear_greed(data):
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    j = r.json()
    score = j["fear_and_greed"]["score"]
    rating = j["fear_and_greed"]["rating"]
    label_map = {
        "extreme fear": "Miedo extremo", "fear": "Miedo",
        "neutral": "Neutral", "greed": "Codicia", "extreme greed": "Codicia extrema"
    }
    data["fearGreed"] = {
        "value": round(float(score), 1),
        "label": label_map.get(rating, rating),
        "date": TODAY, "stale": False
    }


# ---------------------------------------------------------------------
# 4) AAII Bull-Bear — scraping de la página pública
# ---------------------------------------------------------------------
def fetch_aaii(data):
    url = "https://www.aaii.com/sentimentsurvey"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    text = r.text

    def pick(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            raise RuntimeError(f"patrón no encontrado: {pattern}")
        return float(m.group(1))

    bullish = pick(r"Bullish[^0-9%]{0,80}?(\d+\.?\d*)\s*%")
    neutral = pick(r"Neutral[^0-9%]{0,80}?(\d+\.?\d*)\s*%")
    bearish = pick(r"Bearish[^0-9%]{0,80}?(\d+\.?\d*)\s*%")
    spread = round(bullish - bearish, 1)

    hist = data["aaii"].get("history", [])
    date_label = datetime.now().strftime("%d %b").lower()
    if not hist or hist[-1].get("spread") != spread:
        hist.append({"date": date_label, "spread": spread})
        hist = hist[-8:]  # conserva últimas 8 lecturas

    data["aaii"].update({
        "bullish": bullish, "neutral": neutral, "bearish": bearish,
        "spread": spread, "date": TODAY, "stale": False, "history": hist
    })


# ---------------------------------------------------------------------
# 5) CBOE Put/Call ratio (equity) — scraping best-effort
# ---------------------------------------------------------------------
def fetch_put_call(data):
    url = "https://www.cboe.com/us/options/market_statistics/daily/"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    text = r.text
    m = re.search(r"Equity[^0-9]{0,60}?(\d\.\d{2})", text, re.IGNORECASE)
    if not m:
        raise RuntimeError("no se encontró el ratio equity put/call en la página")
    value = float(m.group(1))
    data["extra"]["putCall"] = {
        "value": value, "date": TODAY, "source": "CBOE Equity P/C", "stale": False
    }


# ---------------------------------------------------------------------
def main():
    data = load_existing()
    print(f"Ejecutando captura de sentimiento — {TODAY}")

    safe(fetch_vix, "VIX", data)
    safe(fetch_fear_greed, "CNN Fear & Greed", data)
    safe(fetch_aaii, "AAII Sentiment Survey", data)
    safe(fetch_put_call, "CBOE Put/Call ratio", data)
    safe(fetch_pct_above_200dma, "% S&P500 > media 200d", data)

    # Campos manuales: nunca se tocan aquí, solo se avisa si llevan mucho sin editar
    for key in ("naaim", "insiderRatio", "smartDumb", "fedCut"):
        entry = data["extra"].get(key, {})
        if "manual_updated" in entry:
            try:
                last = datetime.strptime(entry["manual_updated"], "%Y-%m-%d")
                days = (datetime.now() - last).days
                entry["days_since_manual_update"] = days
            except Exception:
                pass
            data["extra"][key] = entry

    data["meta"]["last_run"] = datetime.now(timezone.utc).isoformat()

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nEscrito {DATA_PATH}")


if __name__ == "__main__":
    sys.exit(main())
