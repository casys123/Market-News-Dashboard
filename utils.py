# ---------------------------
# HTML Daily Digest Builder
# ---------------------------

def build_html_digest(metrics: dict, sector_df: pd.DataFrame, headlines: list[dict],
                      suggestions: list[str], earn_df: pd.DataFrame | None = None) -> str:
    """Return a standalone HTML string with key cards, sector 'heatmap', headlines, earnings, suggestions."""
    def pct(v):
        try:
            return f"{v:+.2f}%"
        except Exception:
            return "—"

    # Macro cards
    cards = []
    for k in ["SPY","QQQ","DIA","VIX","TNX","GLD","UUP"]:
        v = metrics.get(k,{})
        cards.append({
            "label": k,
            "val": f"{v.get('last'):.2f}" if isinstance(v.get('last'), (int,float)) else "—",
            "pct": pct(v.get("pct"))
        })

    # Sector heatmap
    def color_for(val):
        if val is None:
            return "#ffffff"
        v = max(-3.0, min(3.0, float(val)))   # clamp to ±3%
        t = (v + 3.0)/6.0
        r = int(255*(1-t))
        g = int(255*(t))
        b = 230
        return f"rgb({r},{g},{b})"

    rows = ""
    if isinstance(sector_df, pd.DataFrame) and not sector_df.empty:
        for _, r in sector_df.iterrows():
            chg1 = f"{r['chg_1d']:+.2f}%" if pd.notna(r['chg_1d']) else "—"
            chgM = f"{r['chg_period']:+.2f}%" if pd.notna(r['chg_period']) else "—"
            rows += f"<tr><td><b>{r['ticker']}</b></td><td style='background:{color_for(r['chg_1d'])};'>{chg1}</td><td>{chgM}</td></tr>"

    heads_html = "".join([f"<li><a href='{h.get('link','#')}'>{h.get('title','')}</a> <em>({h.get('source','')})</em></li>" for h in headlines[:10]])
    sugg_html = "".join([f"<li>{s}</li>" for s in suggestions])

    earn_html = ""
    if earn_df is not None and not earn_df.empty:
        keep = [c for c in ["date","symbol","time","epsEstimate","revenueEstimate"] if c in earn_df.columns]
        small = earn_df[keep].head(15).to_dict("records")
        rows_earn = "".join([f"<tr><td>{r.get('date','')}</td><td>{r.get('symbol','')}</td><td>{r.get('time','')}</td><td>{r.get('epsEstimate','')}</td><td>{r.get('revenueEstimate','')}</td></tr>" for r in small])
        earn_html = f"""
        <h3>Upcoming Earnings (next 14 days)</h3>
        <table><thead><tr><th>Date</th><th>Symbol</th><th>Time</th><th>EPS Est.</th><th>Revenue Est.</th></tr></thead>
        <tbody>{rows_earn}</tbody></table>
        """

    html = f"""
    <html><body style="font-family:Arial;">
    <h1>Market Sentinel — Morning Playbook</h1>
    <h2>Macro Snapshot</h2>
    {" ".join([f"{c['label']}: {c['val']} ({c['pct']})" for c in cards])}
    <h2>Sector Heatmap</h2>
    <table>{rows}</table>
    <h2>Strategy Suggestions</h2>
    <ul>{sugg_html}</ul>
    <h2>Headlines</h2>
    <ul>{heads_html}</ul>
    {earn_html}
    </body></html>
    """
    return html
