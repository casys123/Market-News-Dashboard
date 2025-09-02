import streamlit as st
from datetime import datetime
from utils import (
    get_conf_from_env_or_dict, fetch_key_dashboard, fetch_sector_perf,
    fetch_news, fetch_finnhub_earnings, strategy_suggestions,
    build_html_digest, send_email
)

st.set_page_config(page_title="Market Sentinel", layout="wide")
st.title("📈 Market Sentinel")

CONF = get_conf_from_env_or_dict(dict(st.secrets) if st.secrets else {})

metrics = fetch_key_dashboard()
sectors = fetch_sector_perf("1mo")
headlines = fetch_news(10)

tabs = st.tabs(["🌅 Daily Dashboard", "🔍 Details & News"])

with tabs[0]:
    st.header("Morning Playbook — Daily Dashboard")

    # Macro snapshot
    cols = st.columns(7)
    for i, lbl in enumerate(["SPY","QQQ","DIA","VIX","TNX","GLD","UUP"]):
        with cols[i]:
            val = metrics[lbl].get("last")
            pct = metrics[lbl].get("pct")
            st.metric(lbl, f"{val:,.2f}" if val else "—", f"{pct:+.2f}%" if pct else None)

    # Sector heatmap
    st.subheader("Sector Heatmap")
    if not sectors.empty:
        st.dataframe(sectors, use_container_width=True, hide_index=True)

    # Headlines
    st.subheader("Headlines")
    for n in headlines[:10]:
        st.markdown(f"- [{n['title']}]({n['link']}) — *{n.get('source','')}*")

    # Strategy cues
    st.subheader("Quick Strategy Cues")
    for s in strategy_suggestions(metrics):
        st.write("• " + s)

    # Email digest button
    if st.button("✉️ Email today's Morning Playbook"):
        earn = fetch_finnhub_earnings(CONF.get("FINNHUB_API_KEY",""), days_ahead=14)
        html = build_html_digest(metrics, sectors, headlines, strategy_suggestions(metrics), earn)
        ok, msg = send_email(CONF, subject="Market Sentinel — Morning Playbook", body_html=html)
        st.success("Email sent") if ok else st.error(f"Email failed: {msg}")

with tabs[1]:
    st.write("Additional charts, Finnhub company news, and earnings can go here…")
