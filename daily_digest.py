import os
from utils import (
    get_conf_from_env_or_dict, fetch_key_dashboard, fetch_sector_perf,
    fetch_news, fetch_finnhub_earnings, strategy_suggestions,
    build_html_digest, send_email, send_slack, send_telegram
)

def main():
    conf = get_conf_from_env_or_dict()
    metrics = fetch_key_dashboard()
    sectors = fetch_sector_perf("1mo")
    headlines = fetch_news(12)
    earn = fetch_finnhub_earnings(conf.get("FINNHUB_API_KEY",""), days_ahead=14)

    html = build_html_digest(metrics, sectors, headlines, strategy_suggestions(metrics), earn)

    subj = "Market Sentinel — Morning Playbook"
    send_email(conf, subj, html)
    msg = f"Market Playbook: SPY {metrics['SPY'].get('pct')}%, VIX {metrics['VIX'].get('last')}, 10Y {metrics['TNX'].get('last')}%"
    send_slack(conf, msg)
    send_telegram(conf, msg)

if __name__ == "__main__":
    main()
