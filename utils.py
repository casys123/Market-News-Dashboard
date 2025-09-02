# utils.py
from __future__ import annotations  # <- postpone evaluation of type hints

import os
import json
import time
import smtplib
import feedparser
import requests
import pandas as pd               # <- import pandas before using pd.DataFrame in annotations
import yfinance as yf
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
from datetime import datetime, timedelta, timezone

# ---------------------------
# Configuration helpers
# ---------------------------

def get_conf_from_env_or_dict(conf: dict | None = None) -> dict:
    conf = conf or {}
    return {
        "FINNHUB_API_KEY": conf.get("FINNHUB_API_KEY") or os.getenv("FINNHUB_API_KEY", ""),
        "EMAIL_HOST": conf.get("EMAIL_HOST") or os.getenv("EMAIL_HOST", "smtp.gmail.com"),
        "EMAIL_PORT": int(conf.get("EMAIL_PORT") or os.getenv("EMAIL_PORT", "587")),
        "EMAIL_USERNAME": conf.get("EMAIL_USERNAME") or os.getenv("EMAIL_USERNAME", ""),
        "EMAIL_PASSWORD": conf.get("EMAIL_PASSWORD") or os.getenv("EMAIL_PASSWORD", ""),
        "EMAIL_FROM": conf.get("EMAIL_FROM") or os.getenv("EMAIL_FROM", ""),
        "EMAIL_TO": conf.get("EMAIL_TO") or os.getenv("EMAIL_TO", ""),
        "ALERT_RECIPIENTS": conf.get("ALERT_RECIPIENTS") or os.getenv("ALERT_RECIPIENTS", ""),
        "TIMEZONE": conf.get("TIMEZONE") or os.getenv("TIMEZONE", "America/New_York"),
        # Webhooks
        "SLACK_WEBHOOK_URL": conf.get("SLACK_WEBHOOK_URL") or os.getenv("SLACK_WEBHOOK_URL", ""),
        "TELEGRAM_BOT_TOKEN": conf.get("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_CHAT_ID": conf.get("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID", ""),
    }

# ---------------------------
# Data fetchers (Yahoo)
# ---------------------------

def fetch_yf_series(ticker: str, period="1mo", interval="1d") -> pd.DataFrame:
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if isinstance(df, pd.DataFrame) and not df.empty:
            df = df.dropna(how="all")
        return df
    except Exception:
        return pd.DataFrame()

def fetch_quote(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker).fast_info
        return {
            "last": float(t.last_price) if t.last_price is not None else None,
            "prev_close": float(t.previous_close) if t.previous_close is not None else None,
            "currency": t.currency,
        }
    except Exception:
        return {"last": None, "prev_close": None, "currency": None}

def pct_change(a, b):
    try:
        if a is None or b in (None, 0):
            return None
        return (a - b) / b * 100.0
    except Exception:
        return None

# ---------------------------
# News (Reuters RSS) + Finnhub
# ---------------------------

REUTERS_RSS = "https://feeds.reuters.com/reuters/businessNews"
MARKETS_RSS = "https://feeds.reuters.com/reuters/USMarketsNews"

def fetch_news(max_items=10) -> list[dict]:
    items = []
    for url in [MARKETS_RSS, REUTERS_RSS]:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[: max(0, max_items//2)]:
                items.append({
                    "title": getattr(e, "title", ""),
                    "link": getattr(e, "link", ""),
                    "published": getattr(e, "published", ""),
                    "summary": getattr(e, "summary", ""),
                    "source": "Reuters",
                })
        except Exception:
            continue
    return items[:max_items]

def fetch_finnhub_company_news(api_key: str, symbols: list[str], days_back: int = 7) -> dict:
    """Return dict: {symbol: [news_items]} using Finnhub company-news endpoint."""
    out = {}
    if not api_key or not symbols:
        return out
    import finnhub
    finnhub_client = finnhub.Client(api_key=api_key)
    to = datetime.utcnow().date()
    frm = to - timedelta(days=days_back)
    for sym in symbols:
        try:
            items = finnhub_client.company_news(sym, _from=frm.isoformat(), to=to.isoformat())
            out[sym] = [{
                "headline": it.get("headline",""),
                "datetime": it.get("datetime"),
                "url": it.get("url",""),
                "source": it.get("source","Finnhub"),
                "summary": it.get("summary","")
            } for it in items][:20]
        except Exception:
            out[sym] = []
    return out

def fetch_finnhub_earnings(api_key: str, days_ahead: int = 14) -> pd.DataFrame:
    """Fetch earnings calendar for the next N days. Returns DataFrame."""
    if not api_key:
        return pd.DataFrame()
    import finnhub
    finnhub_client = finnhub.Client(api_key=api_key)
    start = datetime.utcnow().date()
    end = start + timedelta(days=days_ahead)
    try:
        data = finnhub_client.earnings_calendar(_from=start.isoformat(), to=end.isoformat())
        eps = data.get("earningsCalendar", [])
        if not eps:
            return pd.DataFrame()
        df = pd.DataFrame(eps)
        keep = [c for c in ["date","symbol","epsEstimate","revenueEstimate","time","quarter","year"] if c in df.columns]
        return df[keep].sort_values(["date","symbol"]).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()

# ---------------------------
# Sector performance
# ---------------------------

SECTOR_ETFS = ["XLE","XLU","XLK","XLF","XLI","XLY","XLP","XLV","XLB","XLRE","XLC"]

def fetch_sector_perf(period="1mo") -> pd.DataFrame:
    frames = []
    for t in SECTOR_ETFS:
        q = fetch_quote(t)
        hist = fetch_yf_series(t, period=period, interval="1d")
        if q["last"] is None or hist.empty:
            continue
        prev_close = q["prev_close"]
        chg_1d = pct_change(q["last"], prev_close) if prev_close else None
        chg_period = pct_change(q["last"], float(hist["Close"].iloc[0])) if not hist.empty else None
        frames.append({"ticker": t, "last": q["last"], "chg_1d": chg_1d, "chg_period": chg_period})
    return pd.DataFrame(frames).sort_values("chg_1d", ascending=False, na_position="last")

# ---------------------------
# Key dashboard
# ---------------------------

def fetch_key_dashboard() -> dict:
    tickers = {"VIX": "^VIX","SPY": "SPY","QQQ":"QQQ","DIA":"DIA","GLD":"GLD","UUP":"UUP","TNX":"^TNX"}
    out = {}
    for label, t in tickers.items():
        q = fetch_quote(t)
        out[label] = q
    # Adjust TNX to percent
    if out.get("TNX", {}).get("last") is not None:
        out["TNX"]["last"] = out["TNX"]["last"] / 10.0
        if out["TNX"].get("prev_close") is not None:
            out["TNX"]["prev_close"] = out["TNX"]["prev_close"] / 10.0
    # Daily %
    for k, v in out.items():
        v["pct"] = pct_change(v.get("last"), v.get("prev_close"))
    return out

# ---------------------------
# Suggestions
# ---------------------------

def strategy_suggestions(metrics: dict) -> list[str]:
    vix = metrics.get("VIX", {}).get("last")
    tnx = metrics.get("TNX", {}).get("last")
    spy_pct = metrics.get("SPY", {}).get("pct")

    sugg = []
    if vix is not None:
        if vix >= 20:
            sugg.append("IV elevated (VIX ≥ 20): Favor selling premium (put credit spreads, covered calls).")
        elif vix <= 14:
            sugg.append("IV subdued (VIX ≤ 14): Debit strategies may be cheaper (long calls/puts, calendars).")
    if tnx is not None:
        if tnx >= 4.25:
            sugg.append("10Y yield ≥ 4.25%: Growth may be pressured; consider defensive/value tilt.")
        elif tnx <= 3.75:
            sugg.append("10Y yield ≤ 3.75%: Growth tailwind; tech momentum setups may perform.")
    if spy_pct is not None:
        if spy_pct <= -1:
            sugg.append("Broad risk-off (SPY ≤ −1%): Tighten risk, look for reversal patterns for swings.")
        elif spy_pct >= 1:
            sugg.append("Risk-on (SPY ≥ +1%): Trend-following entries may have higher follow-through.")
    if not sugg:
        sugg.append("Neutral backdrop: Use stock-specific catalysts and technical confirmations.")
    return sugg

# ---------------------------
# Alerts (email + Slack + Telegram)
# ---------------------------

def build_alerts(metrics: dict, sector_df: pd.DataFrame, thresholds: dict, earnings_df: pd.DataFrame | None = None) -> list[str]:
    notes = []
    vix = metrics.get("VIX",{})
    tnx = metrics.get("TNX",{})
    spy = metrics.get("SPY",{})
    # Moves
    if vix.get("pct") is not None and abs(vix["pct"]) >= thresholds.get("VIX_PCT", 5.0):
        notes.append(f"VIX moved {vix['pct']:.2f}% today (level: {vix.get('last'):.2f}).")
    if tnx.get("pct") is not None and abs(tnx["pct"]) >= thresholds.get("TNX_PCT", 1.0):
        notes.append(f"10Y yield moved {tnx['pct']:.2f}% (now {tnx.get('last'):.2f}%).")
    if spy.get("pct") is not None and abs(spy["pct"]) >= thresholds.get("SPY_PCT", 1.0):
        notes.append(f"SPY moved {spy['pct']:.2f}% on the day.")
    # Sector rotations
    if isinstance(sector_df, pd.DataFrame) and not sector_df.empty:
        top3 = sector_df.dropna(subset=["chg_1d"]).nlargest(3, "chg_1d")["ticker"].tolist()
        bot3 = sector_df.dropna(subset=["chg_1d"]).nsmallest(3, "chg_1d")["ticker"].tolist()
        notes.append(f"Sectors (1d): Leaders {', '.join(top3)} | Laggards {', '.join(bot3)}")
    # Upcoming earnings (today/tomorrow)
    if isinstance(earnings_df, pd.DataFrame) and not earnings_df.empty and "date" in earnings_df.columns:
        today = datetime.utcnow().date().isoformat()
        upcoming = earnings_df[earnings_df["date"] >= today]
        soon = upcoming.head(10)  # summarize a few
        if not soon.empty:
            tickers = ", ".join(soon["symbol"].head(10).tolist())
            notes.append(f"Earnings coming up soon: {tickers}")
    # Headlines (RSS)
    try:
        news = fetch_news(6)
        if news:
            notes.append("Latest headlines: " + " | ".join([n["title"] for n in news[:3]]))
    except Exception:
        pass
    return notes

def send_email(conf: dict, subject: str, body_html: str, body_text: str | None = None):
    if not conf.get("EMAIL_USERNAME") or not conf.get("EMAIL_PASSWORD") or not conf.get("EMAIL_TO"):
        return False, "Email not configured"
    msg = MIMEMultipart("alternative")
    msg["From"] = conf.get("EMAIL_FROM") or conf["EMAIL_USERNAME"]
    msg["To"] = conf.get("EMAIL_TO") or conf.get("ALERT_RECIPIENTS") or ""
    recipients = [r.strip() for r in (conf.get("ALERT_RECIPIENTS") or conf.get("EMAIL_TO","")).split(",") if r.strip()]
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject
    text = body_text or "See HTML version"
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(body_html, "html"))
    try:
        with smtplib.SMTP(conf["EMAIL_HOST"], conf["EMAIL_PORT"]) as server:
            server.starttls()
            server.login(conf["EMAIL_USERNAME"], conf["EMAIL_PASSWORD"])
            server.sendmail(msg["From"], recipients, msg.as_string())
        return True, "OK"
    except Exception as e:
        return False, str(e)

def send_slack(conf: dict, text: str):
    url = conf.get("SLACK_WEBHOOK_URL","")
    if not url:
        return False, "No Slack webhook URL"
    try:
        r = requests.post(url, json={"text": text}, timeout=10)
        if r.status_code // 100 == 2:
            return True, "OK"
        return False, f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return False, str(e)

def send_telegram(conf: dict, text: str):
    token = conf.get("TELEGRAM_BOT_TOKEN","")
    chat_id = conf.get("TELEGRAM_CHAT_ID","")
    if not token or not chat_id:
        return False, "Telegram not configured"
    try:
        api = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(api, data={"chat_id": chat_id, "text": text, "parse_mode":"HTML"}, timeout=10)
        if r.status_code // 100 == 2:
            return True, "OK"
        return False, f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return False, str(e)

# ---------------------------
# HTML Daily Digest Builder (FIXED — safe to use pd.DataFrame in annotations)
# ---------------------------

def build_html_digest(
    metrics: dict,
    sector_df: pd.DataFrame,
    headlines: list[dict],
    suggestions: list[str],
    earn_df: pd.DataFrame | None = None
) -> str:
    """Return standalone HTML with key cards, sector 'heatmap', headlines, earnings, suggestions."""
    def pct(v):
        try:
            return f"{v:+.2f}%"
        except Exception:
            return "—"

    # Macro cards
    cards = []
    for k in ["SPY","QQQ","DIA","VIX","TNX","GLD","UUP"]:
        v = metrics.get(k,{})
        last = v.get("last")
        cards.append({
            "label": k,
            "val": f"{last:.2f}" if isinstance(last, (int,float)) else "—",
            "pct": pct(v.get("pct"))
        })

    # Sector table w/ simple color scale
    def color_for(val):
        if val is None:
            return "#ffffff"
        v = max(-3.0, min(3.0, float(val)))   # clamp ±3%
        t = (v + 3.0)/6.0
        r = int(255*(1-t)); g = int(255*t); b = 230
        return f"rgb({r},{g},{b})"

    sector_html_rows = ""
    if isinstance(sector_df, pd.DataFrame) and not sector_df.empty:
        for _, r in sector_df.iterrows():
            chg1 = "—" if pd.isna(r["chg_1d"]) else f"{r['chg_1d']:+.2f}%"
            chgM = "—" if pd.isna(r["chg_period"]) else f"{r['chg_period']:+.2f}%"
            sector_html_rows += (
                f"<tr><td><b>{r['ticker']}</b></td>"
                f"<td style='background:{color_for(r['chg_1d'])};'>{chg1}</td>"
                f"<td>{chgM}</td></tr>"
            )

    heads_html = "".join(
        f"<li><a href='{h.get('link','#')}'>{h.get('title','')}</a> <em>({h.get('source','')})</em></li>"
        for h in (headlines or [])[:10]
    )
    sugg_html = "".join(f"<li>{s}</li>" for s in (suggestions or []))

    earn_html = ""
    if isinstance(earn_df, pd.DataFrame) and not earn_df.empty:
        cols = [c for c in ["date","symbol","time","epsEstimate","revenueEstimate"] if c in earn_df.columns]
        small = earn_df[cols].head(15).to_dict("records")
        rows = "".join(
            f"<tr><td>{r.get('date','')}</td><td>{r.get('symbol','')}</td>"
            f"<td>{r.get('time','')}</td><td>{r.get('epsEstimate','')}</td>"
            f"<td>{r.get('revenueEstimate','')}</td></tr>"
            for r in small
        )
        earn_html = f"""
        <h3 style="margin-top:20px;">Upcoming Earnings (next 14 days)</h3>
        <table cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%;">
          <thead><tr style="background:#f0f0f0;"><th>Date</th><th>Symbol</th><th>Time</th><th>EPS Est.</th><th>Revenue Est.</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        """

    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    macro_cells = "".join(
        f"<td style='border:1px solid #eee; text-align:center;'>"
        f"<div style='font-size:12px;color:#666'>{c['label']}</div>"
        f"<div style='font-size:20px;font-weight:700'>{c['val']}</div>"
        f"<div style='color:{('#1a7f37' if c['pct'].startswith('+') else '#b32d2e')}'>{c['pct']}</div>"
        f"</td>"
        for c in cards
    )

    return f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>Market Sentinel — Morning Playbook</title></head>
<body style="font-family:Arial, Helvetica, sans-serif; color:#111; margin:0; padding:20px;">
  <h1>Market Sentinel — Morning Playbook</h1>
  <div style="color:#666;font-size:12px;">Generated {now}</div>

  <h2 style="margin-top:20px;">Macro Snapshot</h2>
  <table cellspacing="0" cellpadding="8" style="border-collapse:collapse;">
    <tr>{macro_cells}</tr>
  </table>

  <h2 style="margin-top:24px;">Sector Heatmap</h2>
  <table cellspacing="0" cellpadding="6" style="border-collapse:collapse;min-width:480px;">
    <thead><tr style="background:#f0f0f0;"><th>Sector ETF</th><th>1D</th><th>~1M</th></tr></thead>
    <tbody>{sector_html_rows}</tbody>
  </table>

  <h2 style="margin-top:24px;">Strategy Suggestions</h2>
  <ul>{sugg_html}</ul>

  <h2 style="margin-top:24px;">Headlines</h2>
  <ul>{heads_html}</ul>

  {earn_html}
  <div style="margin-top:32px; font-size:12px;color:#777;">© Market Sentinel</div>
</body></html>
"""
