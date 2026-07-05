"""PapoW board — a read-only VIEWER over pre-computed snapshots stored in a database.

This app contains NO trading logic, NO strategy code, and NO analysis — it only renders JSON
payloads that a private research system writes elsewhere. Password-gated. Demo/paper research
dashboard; nothing here is investment advice and nothing places orders.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(page_title="PapoW Board", layout="wide")


# ---------- auth ----------
def _secret(key: str) -> str | None:
    """Read a secret; None when the secrets file is missing or is not valid TOML."""
    try:
        v = st.secrets.get(key)
        return str(v) if v else None
    except Exception:
        return None


_SECRETS_HELP = '''DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME"
APP_PASSWORD = "your-password-here"'''


def _gate() -> bool:
    if st.session_state.get("auth_ok"):
        return True
    st.title("PapoW Board")
    app_pw = _secret("APP_PASSWORD")
    if app_pw is None or _secret("DATABASE_URL") is None:
        st.error("Secrets are missing or not valid TOML. In Streamlit Cloud: **Manage app → "
                 "Settings → Secrets**, delete everything there and paste EXACTLY this shape — "
                 "every value wrapped in straight double quotes (\"), one per line:")
        st.code(_SECRETS_HELP, language="toml")
        st.caption("Common causes: missing quotes around a value, or “smart quotes” pasted from "
                   "Word/WhatsApp instead of plain \" quotes. Save, then reboot the app.")
        st.stop()
    pw = st.text_input("Password", type="password")
    if pw:
        if pw == app_pw:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("wrong password")
    st.stop()
    return False


# ---------- data ----------
@st.cache_resource
def _engine():  # type: ignore[no-untyped-def]
    url = _secret("DATABASE_URL")
    if not url:
        st.error("DATABASE_URL is missing from Secrets — see the login screen for the format.")
        st.stop()
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=600, show_spinner=False)
def _latest(table: str) -> dict[str, Any] | None:
    with _engine().connect() as c:
        row = c.execute(text(
            f'select payload_json from "{table}" order by date desc limit 1')).fetchone()
    return json.loads(row[0]) if row else None


@st.cache_data(ttl=600, show_spinner=False)
def _counts() -> list[tuple[str, int, str]]:
    out = []
    with _engine().connect() as c:
        for label, t in (("map", "leadership_snapshots"), ("watchlists", "watchlist_snapshots"),
                         ("desk", "forward_desk_snapshots"), ("account", "account_snapshots")):
            r = c.execute(text(f'select count(*), max(date) from "{t}"')).fetchone()
            out.append((label, int(r[0] or 0), str(r[1] or "—")))
    return out


@st.cache_data(ttl=120, show_spinner=False)
def _changes() -> list[dict[str, Any]]:
    with _engine().connect() as c:
        rows = c.execute(text(
            'select id, title, proposed_change, status, created, approved_at, dismissed_reason, '
            'still_present, monitored from changes order by id')).fetchall()
    return [dict(r._mapping) for r in rows]


def _decide(cid: str, approve: bool, reason: str = "") -> None:
    now = date.today().isoformat()
    with _engine().begin() as c:
        if approve:
            c.execute(text("update changes set status='approved', monitored=true, "
                           "approved_at=:t where id=:i"), {"t": now, "i": cid})
        else:
            c.execute(text("update changes set status='dismissed', monitored=false, "
                           "dismissed_at=:t, dismissed_reason=:r where id=:i"),
                      {"t": now, "r": reason or "not needed", "i": cid})
    _changes.clear()


# ---------- views ----------
_STATE_HE = {"hold": "בפוזיציה", "buy_signal": "אות קנייה", "candidate": "מועמדת",
             "watch": "מעקב"}
_ICON = {"filled": "📈", "research": "🔬", "ready": "🟢"}


def _accrual() -> None:
    parts = [f"{n}: {c}d (last {d})" for n, c, d in _counts()]
    st.caption("🛰️ accrual [Supabase] · " + " · ".join(parts))
    newest = max((d for _, c, d in _counts() if c and d != "—"), default=None)
    if newest:
        age = (date.today() - date.fromisoformat(newest)).days
        if age > 3:
            st.error(f"🔴 accrual looks stale — newest snapshot {newest} ({age}d old)")


def _slots_tab() -> None:
    _accrual()
    acct = _latest("account_snapshots") or {}
    board = acct.get("slot_board") or {}
    if not board:
        st.info("no board yet — the nightly loop populates it")
        return
    st.caption(f"as of **{board.get('date')}** · desk verdict: **{board.get('desk_verdict')}**")
    cols = st.columns(4)
    for i, s in enumerate((board.get("slots") or [])[:4]):
        with cols[i]:
            state = s.get("state")
            if state == "filled":
                st.metric(f"{_ICON['filled']} Slot {i+1}", s.get("ticker"),
                          f"day {s.get('days_held')}")
            elif state == "research":
                st.metric(f"{_ICON['research']} Slot {i+1}", "research",
                          f"{s.get('days_left')}d left")
            else:
                st.metric(f"{_ICON['ready']} Slot {i+1}", "ready", "cash")
    pipe = board.get("pipeline") or []
    if pipe:
        st.markdown("**The ladder** (long-only)")
        st.dataframe(pd.DataFrame([{
            "state": _STATE_HE.get(r["state"], r["state"]), "ticker": r["ticker"],
            "בשלות": r.get("maturity") or "—", "thesis": r.get("thesis") or "—",
            "character": r.get("char_class") or "—", "technique": r.get("technique") or "—",
            "entry": r.get("entry_level") or "—",
            "SL": f"{r['sl_price']} ({r['sl_pct']}%)" if r.get("sl_price") else "—",
            "size": f"₪{r['size_hint']:,.0f}" if r.get("size_hint") and r["state"] != "watch"
                    else "—",
            "why": r.get("why")} for r in pipe]), use_container_width=True, hide_index=True)
        for r in pipe:
            if r["state"] == "watch":
                continue
            with st.expander(f"🔍 {r['ticker']} — full maturity detail"):
                if r.get("gates"):
                    st.dataframe(pd.DataFrame([{"gate": g["gate"],
                                                "status": "🟢" if g["ok"] else "🔴",
                                                "detail": g["why"]} for g in r["gates"]]),
                                 use_container_width=True, hide_index=True)
                for k, v in (r.get("entry_rules") or {}).items():
                    st.markdown(f"- `{k}`: {v}")
                if r.get("prior"):
                    st.caption(f"prior (in-sample): {r['prior']}")
    m = acct.get("metrics") or {}
    st.caption(f"account (paper): equity {m.get('terminal_equity')} · withdrawn "
               f"{m.get('withdrawn')} · net {m.get('return_vs_deposit')}")
    dfd = acct.get("deferred_today") or []
    if dfd:
        st.warning("potential buys NOT taken (desk not calibrated): "
                   + ", ".join(f"{c['ticker']} ({c['list']})" for c in dfd))


def _desk_tab() -> None:
    d = _latest("forward_desk_snapshots") or {}
    r, c = d.get("readiness") or {}, d.get("calibration") or {}
    v1, v2, v3 = st.columns(3)
    v1.metric("verdict", "🟢 BUY" if r.get("verdict") == "buy_now" else "🟠 WAIT")
    v2.metric("scored calls", c.get("n", 0))
    v3.metric("hit-rate", "—" if c.get("hit_rate") is None else f"{c['hit_rate']:.0%}")
    st.caption(r.get("reason", ""))
    fc = d.get("forecasts") or []
    if fc:
        st.dataframe(pd.DataFrame([{"ticker": f["ticker"], "forecast": f["direction"],
                                    "confidence": f.get("confidence")} for f in fc]),
                     use_container_width=True, hide_index=True)
    ns = d.get("new_scored") or []
    if ns:
        st.markdown("**calls that just matured**")
        st.dataframe(pd.DataFrame(ns), use_container_width=True, hide_index=True)


def _watchlists_tab() -> None:
    w = _latest("watchlist_snapshots") or {}
    for wl in w.get("watchlists", []):
        st.markdown(f"**[{wl.get('provenance')}·{wl.get('basis')}] {wl.get('kind')}** — "
                    f"{wl.get('purpose')}")
        if wl.get("members"):
            st.dataframe(pd.DataFrame(wl["members"]), use_container_width=True, hide_index=True)
        st.caption(f"⚖️ {wl.get('measurement_hook')}")


def _leadership_tab() -> None:
    m = _latest("leadership_snapshots") or {}
    story = m.get("market_story") or {}
    if story.get("narrative"):
        st.info(story["narrative"])
    secs = m.get("leading_sectors") or []
    if secs:
        st.dataframe(pd.DataFrame([{"sector": s["sector"], "persistence":
                                    (s.get("persistence") or {}).get("score"),
                                    "trend": s.get("trend")} for s in secs]),
                     use_container_width=True, hide_index=True)
    st.markdown("**leaders**")
    st.dataframe(pd.DataFrame([{"ticker": c["ticker"], "sector": c.get("sector"),
                                "pocket": c.get("pocket_id"), "ret_20d": c.get("ret_20d"),
                                "stage": c.get("move_stage")}
                               for c in m.get("stock_leaders", [])]),
                 use_container_width=True, hide_index=True)
    for k, v in (m.get("caveats") or {}).items():
        st.caption(f"⚠️ {k}: {v}")


def _improvement_tab() -> None:
    st.caption("Approve = log + monitor + queue. NOTHING auto-applies; approved changes are "
               "implemented in a batch when the logic engine opens.")
    for ch in _changes():
        st.markdown(f"**{ch['id']} — {ch['title']}**  \nstatus: `{ch['status']}` · "
                    f"still_present: {ch.get('still_present')}")
        with st.expander("details"):
            st.write(ch["proposed_change"])
        if ch["status"] == "proposed":
            a, b = st.columns([1, 2])
            if a.button("Approve", key=f"ap_{ch['id']}"):
                _decide(ch["id"], True)
                st.rerun()
            with b:
                reason = st.text_input("reason", key=f"rs_{ch['id']}",
                                       label_visibility="collapsed",
                                       placeholder="why it's not needed")
                if st.button("Dismiss", key=f"dn_{ch['id']}"):
                    _decide(ch["id"], False, reason)
                    st.rerun()
        st.divider()


def main() -> None:
    _gate()
    st.title("PapoW Board — read-only viewer")
    st.caption("🧪 DEMO / PAPER research dashboard. Renders pre-computed snapshots only; contains "
               "no strategy logic; never places orders; not investment advice.")
    tabs = st.tabs(["🎰 Slots", "🧭 Deal Desk", "📋 Watchlists", "🌍 Leadership", "🛠 Improvement"])
    with tabs[0]:
        _slots_tab()
    with tabs[1]:
        _desk_tab()
    with tabs[2]:
        _watchlists_tab()
    with tabs[3]:
        _leadership_tab()
    with tabs[4]:
        _improvement_tab()


main()
