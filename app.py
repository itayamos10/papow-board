"""PapoW board — a read-only VIEWER over pre-computed snapshots stored in a database.

This app contains NO trading logic, NO strategy code, and NO analysis — it only renders JSON
payloads that a private research system writes elsewhere. Password-gated. Demo/paper research
dashboard; nothing here is investment advice and nothing places orders.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(page_title="PapoW — the board",
                   page_icon=str(Path(__file__).parent / "assets/icon.svg"),
                   layout="wide")

# ---------- PAPOW brand (docs/brand/BRAND.md in the core repo) ----------
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Inter:wght@400;600;800&display=swap');
html, body, [data-testid="stAppViewContainer"] { background:#0B0F1A !important; }
[data-testid="stHeader"] { background:rgba(11,15,26,.6) !important; }
h1,h2,h3,h4 { color:#F2F5FA !important; font-family:Inter,'Segoe UI',sans-serif; }
p, li, span, label, .stMarkdown { color:#C9D2E3; }
.papow-word { font-family:'Archivo Black','Arial Black',sans-serif; font-size:44px;
  letter-spacing:2px; color:#F2F5FA; line-height:1; }
.papow-word .hit { color:#C8FF37; }
.papow-tag { color:#8B96AC; font-size:13px; margin-top:4px; letter-spacing:.5px; }
.papow-ribbon { display:flex; gap:10px; flex-wrap:wrap; margin:14px 0 4px; }
.papow-chip { background:#141B2E; border:1px solid #232E4A; border-radius:999px;
  padding:6px 14px; font-size:13px; color:#C9D2E3; }
.papow-chip b { color:#F2F5FA; }
.papow-chip.volt { border-color:#C8FF37; color:#C8FF37; }
.papow-chip.gold { border-color:#FFC24B; color:#FFC24B; }
.papow-chip.coral { border-color:#FF4D5E; color:#FF6D7C; }
.papow-card { background:#141B2E; border:1px solid #232E4A; border-radius:14px;
  padding:14px 16px; margin:6px 0; }
.papow-card .tkr { font-weight:800; font-size:17px; color:#F2F5FA; }
.papow-card .sub { color:#8B96AC; font-size:12.5px; margin-top:2px; }
.papow-key { display:inline-block; border-radius:6px; padding:1px 8px; font-size:12px;
  margin-left:4px; border:1px solid #232E4A; }
.papow-key.on  { background:rgba(200,255,55,.12); color:#C8FF37; border-color:#C8FF37; }
.papow-key.off { background:rgba(255,77,94,.10); color:#FF6D7C; border-color:#FF4D5E; }
.papow-stage { color:#FFC24B; font-size:12px; letter-spacing:1px; }
[data-testid="stMetric"] { background:#141B2E; border:1px solid #232E4A;
  border-radius:14px; padding:12px 14px; }
[data-testid="stMetricValue"] { color:#F2F5FA !important; }
button[data-baseweb="tab"] { font-weight:600; }
/* proper RTL: Hebrew text reads right-to-left, mixed EN/HE stops scrambling */
.stMarkdown, .stCaption, [data-testid="stCaptionContainer"],
[data-testid="stExpander"] summary, .stAlert, [data-testid="stMetricLabel"] {
  direction:rtl; text-align:right; unicode-bidi:plaintext; }
.papow-card, .papow-ribbon { direction:rtl; text-align:right; }
.papow-card .sub, .papow-card .tkr { unicode-bidi:plaintext; }
[data-testid="stDataFrame"] { direction:ltr; }  /* tables stay LTR — numbers align */
/* ---- full RTL for the Israeli user (owner 13.07): the WHOLE surface reads right-to-left */
section.main, [data-testid="stAppViewContainer"] > section { direction:rtl !important; }
[data-testid="stMarkdownContainer"] { text-align:right; }
[data-testid="stMetric"] { direction:rtl; text-align:right; }
div[data-testid="stTabs"] { direction:rtl !important; }
div[data-testid="stTabs"] [data-baseweb="tab-list"],
div[data-testid="stTabs"] div[role="tablist"],
.stTabs [data-baseweb="tab-list"] { direction:rtl !important;
  justify-content:flex-start !important; }
div[data-testid="stTabs"] button[role="tab"],
.stTabs [data-baseweb="tab-list"] button { direction:rtl; }
div[data-testid="stTabs"] [data-baseweb="tab-highlight"],
div[data-testid="stTabs"] [data-baseweb="tab-border"] { direction:rtl !important; }
[data-testid="stExpander"] summary { direction:rtl; text-align:right; }
[data-testid="stCaptionContainer"] { text-align:right; }
[data-testid="stHorizontalBlock"] { direction:rtl; }
[data-testid="stAlert"] { direction:rtl; text-align:right; }
</style>
"""


def _logo_html(height: int = 40) -> str:
    """L1: the OWNER'S original logo art (transparent, compact row), inlined base64."""
    try:
        raw = (Path(__file__).parent / "assets/logo-compact.png").read_bytes()
        b64 = base64.b64encode(raw).decode()
        return (f'<img src="data:image/png;base64,{b64}" alt="PapoW" '
                f'style="height:{height}px;vertical-align:middle">')
    except OSError:                                        # asset missing -> text fallback
        return '<span class="papow-word">Papo<span class="hit">W</span></span>'


def _hero(sub: str = "") -> None:
    """L1 header, Hebrew-first: the logo sits on the RIGHT, slogan aligned beside it;
    disclaimers do NOT live here — they are one line at the page bottom (_footer)."""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown('<div style="display:flex;align-items:center;gap:16px;'
                'flex-direction:row;direction:rtl">'
                + _logo_html(44)
                + '<div class="papow-tag" dir="ltr" style="text-align:left">watch. '
                '<span class="hit">aim.</span> PapoW</div></div>',
                unsafe_allow_html=True)


def _footer() -> None:
    st.markdown('<div style="margin-top:28px;padding-top:10px;border-top:1px solid '
                '#232E4A;color:#8B96AC;font-size:11px;text-align:center">'
                'קוקפיט לקריאה-בלבד · דמו/נייר · לא ייעוץ ולא פקודות · '
                '<span dir="ltr">watch. aim. PapoW</span></div>',
                unsafe_allow_html=True)


def _ribbon() -> None:
    chips = []
    lead = _latest("leadership_snapshots") or {}
    acct = _latest("account_snapshots") or {}
    mr = lead.get("market_regime") or {}
    if lead.get("date"):
        chips.append(f'<span class="papow-chip">🗓 <b>{lead.get("date")}</b></span>')
    if mr.get("regime_type"):
        frag = str(mr.get("market_fragility"))
        cls = "coral" if frag in ("high", "elevated") else "volt"
        chips.append(f'<span class="papow-chip {cls}">🧭 {mr.get("regime_type")} · '
                     f'{frag}</span>')
    eq = (acct.get("metrics") or {}).get("terminal_equity")
    if eq:
        chips.append(f'<span class="papow-chip">💼 ₪<b>{eq:,.0f}</b></span>')
    vipq = _latest_note("vip_board")
    if vipq:
        cap = vipq.get("capacity") or {}
        chips.append(f'<span class="papow-chip gold">👑 VIP {cap.get("vip", "—")} · '
                     f'עומק {cap.get("deep", "—")}</span>')
    if chips:
        st.markdown('<div class="papow-ribbon">' + "".join(chips) + "</div>",
                    unsafe_allow_html=True)


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
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown('<div dir="ltr">' + _logo_html(40)
                + '<div class="papow-tag">watch. <span class="hit">aim.</span> PapoW'
                '</div></div>', unsafe_allow_html=True)
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
def _latest_note(kind: str) -> dict[str, Any] | None:
    """Newest research note of a kind (e.g. the nightly vip_board queue snapshot)."""
    try:
        with _engine().connect() as c:
            row = c.execute(text('select content from research_notes where kind = :k '
                                 'order by date desc limit 1'), {"k": kind}).fetchone()
        return json.loads(row[0]) if row else None
    except Exception:
        return None


def _approve_trade(ticker: str, decision: str, reason: str = "") -> None:
    """The manager's yes/no/undo on a pending fill — a research note the engine reads at
    fill time (approve fills next open; reject drops + the reason feeds the org memory;
    undo returns the decision to WAITING while its expiry clock keeps running)."""
    today = date.today().isoformat()
    nid = f"trade_approval:{ticker}:{today}"
    payload = json.dumps({"ticker": ticker, "decision": decision, "date": today,
                          "reason": reason, "by": "board"}, ensure_ascii=False)
    with _engine().begin() as c:
        c.execute(text(
            'insert into research_notes (id, date, kind, title, content) '
            'values (:i, :d, :k, :t, :c) '
            'on conflict (id) do update set content = excluded.content, '
            'date = excluded.date'),
            {"i": nid, "d": today, "k": "trade_approval",
             "t": f"Trade approval — {ticker}: {decision}", "c": payload})
    _notes_of.clear()


@st.cache_data(ttl=600, show_spinner=False)
def _notes_of(kind: str, limit: int = 12) -> list[dict[str, Any]]:
    """Newest N research notes of a kind, parsed, with their id/date riding along."""
    try:
        with _engine().connect() as c:
            rows = c.execute(text('select id, date, content from research_notes '
                                  'where kind = :k order by date desc limit :n'),
                             {"k": kind, "n": limit}).fetchall()
        out = []
        for rid, d, content in rows:
            payload = json.loads(content)
            if isinstance(payload, dict):
                payload.setdefault("_id", rid)
                payload.setdefault("_date", str(d))
            out.append(payload)
        return out
    except Exception:
        return []


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


def _ml_write(sql: str, params: dict) -> None:
    with _engine().begin() as c:
        c.execute(text('create table if not exists mailing_list ('
                       'email text primary key, status text, added_at text, '
                       'onboarded_at text, removed_at text)'))
        c.execute(text(sql), params)


def _mailing_list_ui() -> None:
    """Owner 13.07: structured add/remove for the distribution list. An added address
    becomes PENDING; the sentinel (5-min tick) sends the branded onboarding and flips it
    to ACTIVE. Removal keeps the row — every email stays in the DB with its status."""
    st.markdown("#### 📧 רשימת-התפוצה")
    c1, c2 = st.columns([3, 1])
    new_mail = c1.text_input("הוספת מייל", key="ml_add",
                             placeholder="name@example.com").strip().lower()
    if c2.button("➕ הוסף") and "@" in new_mail and "." in new_mail.split("@")[-1]:
        today = date.today().isoformat()
        _ml_write('insert into mailing_list (email, status, added_at, onboarded_at, '
                  'removed_at) values (:e, :s, :d, \'\', \'\') '
                  'on conflict (email) do update set status = :s, added_at = :d, '
                  'removed_at = \'\'',
                  {"e": new_mail, "s": "pending", "d": today})
        st.success(f"{new_mail} נוסף — מייל-ה-onboarding יישלח תוך ~5 דקות (דרך הזקיף)")
    try:
        with _engine().connect() as c:
            c.execute(text('alter table mailing_list add column if not exists '
                           'last_sent_kind text default \'\''))
            c.execute(text('alter table mailing_list add column if not exists '
                           'last_sent_at text default \'\''))
            rows = c.execute(text(
                'select email, status, added_at, onboarded_at, removed_at, '
                'last_sent_kind, last_sent_at from mailing_list order by email')).fetchall()
    except Exception:
        rows = []
    if not rows:
        st.caption("הרשימה ריקה — כל כתובת שתוסיף תישמר כאן עם הסטטוס שלה.")
        return
    he = {"pending": "🟡 ממתין ל-onboarding", "active": "🟢 פעיל", "removed": "⚪ הוסר"}
    kind_he = {"morning_0930": "☀️ 09:30", "premarket_1130": "🌅 11:30",
               "prep_1530": "🧭 15:30", "session_1830": "🏛️ 18:30",
               "close_2200": "🌆 22:00"}
    for email, status, added, onb, rem, lsk, lsa in rows:
        c1, c2, c3 = st.columns([3, 2, 1])
        c1.markdown(f"**{email}**")
        last = (f" · 📬 אחרון: {kind_he.get(str(lsk), lsk)} ({str(lsa)[:16]})"
                if lsk else " · 📭 טרם נשלח דוח")
        c2.caption(f"{he.get(str(status), status)} · נוסף {added}"
                   + (f" · הצטרף {onb}" if onb else "")
                   + (f" · הוסר {rem}" if rem else "")
                   + (last if status == "active" else ""))
        if status != "removed" and c3.button("🗑 הסר", key=f"ml_rm_{email}"):
            _ml_write('update mailing_list set status = \'removed\', removed_at = :d '
                      'where email = :e',
                      {"e": email, "d": date.today().isoformat()})
            st.rerun()
    st.caption("המנויים מקבלים את הדוחות המתוזמנים בלבד (BCC — כתובות לא נחשפות זו לזו); "
               "דחיפות תפעוליות (🔐/🎯/🚨) נשארות למנהל בלבד.")


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


_RECOVERY = {
    "engine": "1) הרץ ידנית run_forward_daily.cmd · 2) backfill: forward_leadership.py <תאריך>",
    "db": "בדוק Supabase status · הריצות עושות retry×3; מייל-הערב יוצא degraded ממקורות מקומיים",
    "board": "רענן (cache 10ד') · ודא vip_board note קיים (queue_snapshot backfill)",
    "reports": "בדוק daily_run.log + LastTaskResult במתזמן · הקוד חייב להיות ממוזג ל-main",
}


def _operator_tab() -> None:
    from datetime import date, timedelta
    _mailing_list_ui()
    st.divider()
    today = date.today().isoformat()
    prev = today
    for _ in range(4):                          # last expected NY session (weekend-aware)
        d = date.fromisoformat(prev) - timedelta(days=1)
        prev = d.isoformat()
        if d.weekday() < 5:
            break
    ops = _latest_note("ops_health") or {}
    lead = _latest("leadership_snapshots") or {}
    acct = _latest("account_snapshots") or {}
    vipq = _latest_note("vip_board") or {}
    checks: list[tuple[str, str, str, str]] = []   # (name, state, detail, recovery_key)

    def add(name, ok, warn, detail, rk):
        checks.append((name, "PASS" if ok else ("WARN" if warn else "FAIL"), detail, rk))

    eng_date = str(lead.get("date") or "—")
    add("מנוע לילי (23:15)", eng_date >= prev, False,
        f"מפה אחרונה: {eng_date} (צפוי ≥ {prev})", "engine")
    av = str(ops.get("audit_verdict") or "—")
    add("אודיט-אמת (A8+A8X)", av.startswith("PASS"), av.startswith("CONDITIONAL"),
        av + (f" · {ops.get('audit_blockers')}" if ops.get("audit_blockers") else ""),
        "reports")
    add("VIP queue", bool(vipq.get("members")), False,
        f"{len(vipq.get('members') or [])} חברים · {vipq.get('capacity')}", "board")
    acct_date = str(acct.get("date") or "—")
    add("חשבון/סלוטים", acct_date >= prev, False, f"snapshot: {acct_date}", "engine")
    wh = ops.get("watcher_health") or []
    fails = [i for i in wh if i.get("level") == "FAIL"]
    add("בריאות-Watcher", not fails, bool(wh and not fails),
        "; ".join(str(i.get("what")) for i in wh[:2]) or "נקי", "db")

    n_fail = sum(1 for c in checks if c[1] == "FAIL")
    n_warn = sum(1 for c in checks if c[1] == "WARN")
    if n_fail:
        st.markdown('<div class="papow-card" style="border-color:#FF4D5E">'
                    f'<span class="tkr" style="color:#FF6D7C">🔴 NO-GO — {n_fail} רכיבים '
                    'כשלו</span><div class="sub">פעל לפי סדר-העדיפויות: מנוע → DB → בורד '
                    '→ דוחות → legacy</div></div>', unsafe_allow_html=True)
    elif n_warn:
        st.markdown('<div class="papow-card" style="border-color:#FFC24B">'
                    f'<span class="tkr" style="color:#FFC24B">🟡 GO עם הסתייגות — {n_warn} '
                    'אזהרות</span></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="papow-card" style="border-color:#C8FF37">'
                    '<span class="tkr" style="color:#C8FF37">🟢 GO — המערכת Operational'
                    '</span><div class="sub">כל הרכיבים עברו את בדיקת-הבוקר</div></div>',
                    unsafe_allow_html=True)
    for name, state, detail, rk in checks:
        icon = {"PASS": "✅", "WARN": "🟡", "FAIL": "🔴"}[state]
        rec = f'<div class="sub">🔧 שחזור: {_RECOVERY.get(rk)}</div>' if state == "FAIL"             else ""
        st.markdown(f'<div class="papow-card"><span class="tkr">{icon} {name}</span>'
                    f'<div class="sub">{detail}</div>{rec}</div>', unsafe_allow_html=True)
    ccs = ops.get("pending_ccs") or []
    if ccs:
        st.warning(f"🎯 נדרשת פעולה שלך: {len(ccs)} החלטות ממתינות — {', '.join(ccs)} "
                   "(טאב Improvement)")
    ms = ops.get("milestones") or []
    nxt = sorted((mm for mm in ms if mm.get("eta_days") is not None),
                 key=lambda x: x["eta_days"])[:2]
    for mm in nxt:
        st.caption(f"⏭️ אבן-הדרך הקרובה: {mm.get('id')} — n={mm.get('n')}/"
                   f"{mm.get('next_gate')} (~{mm.get('eta_days')} ימים)")
    if ops.get("b0a"):
        st.caption(f"🏦 {ops.get('b0a')}")


def _slots_tab() -> None:
    """מנהל-העסקאות: פוזיציות ו-P&L קודם; פסק-הדסק כרצועה (Deal Desk המלא בהרחבה —
    הערך העסקי שלו: הוא השוער שקובע אם מותר לפרוס הון היום; owner 13.07)."""
    _accrual()
    acct = _latest("account_snapshots") or {}
    board = acct.get("slot_board") or {}
    if not board:
        st.info("no board yet — the nightly loop populates it")
        return
    d = _latest("forward_desk_snapshots") or {}
    r0, c0 = d.get("readiness") or {}, d.get("calibration") or {}
    verdict = "🟢 מותר לקנות" if r0.get("verdict") == "buy_now" else "🟠 ממתינים"
    hr = "—" if c0.get("hit_rate") is None else f"{c0['hit_rate']:.0%}"
    st.markdown(f'<div class="papow-card"><b>שוער-הפריסה:</b> {verdict} · '
                f'קריאות מדורגות: {c0.get("n", 0)} · דיוק: {hr}'
                f'<div class="sub">{r0.get("reason", "")} — סלוט פנוי נשאר מזומן עד '
                f'שהדסק מכויל; הון נפרס רק כשהוא הרוויח את הזכות.</div></div>',
                unsafe_allow_html=True)
    with st.expander("🧭 מנוע-הקצב המלא (Deal Desk)"):
        _desk_tab()
    # MANAGER-APPROVAL GATE (owner 13.07): no slot fills without an explicit yes here.
    # The card carries EVERYTHING a decision needs (owner: synthesis of the whole
    # process + both engines + bottom line) and reflects YOUR click immediately.
    pend = acct.get("pending_fills") or []
    if pend:
        st.markdown("#### 🔐 החלטות-קנייה ממתינות לאישורך")
        st.caption("אישור = מילוי בפתיחת-המסחר הבאה (CC001 — מעובד בריצת 23:15); דחייה "
                   "מפילה; שתיקה של 3 סשנים מפקיעה.")
        appr: dict[str, dict[str, str]] = {}
        for n in _notes_of("trade_approval", 30):          # newest first per ticker
            t0 = str(n.get("ticker", "")).upper()
            if t0 and t0 not in appr:
                appr[t0] = {"decision": str(n.get("decision")),
                            "reason": str(n.get("reason") or "")}
        pipe_rows = {str(r.get("ticker")): r for r in board.get("pipeline") or []}
        vip_m = {str(m.get("ticker")): m
                 for m in (_latest_note("vip_board") or {}).get("members") or []}
        nb = acct.get("not_bought_today") or []
        cands = [r for r in board.get("pipeline") or []
                 if r.get("state") == "candidate" and str(r.get("ticker")) not in
                 {str(x.get("ticker")) for x in pend}]
        for p in pend:
            t = str(p.get("ticker"))
            row = pipe_rows.get(t) or {}
            vm = vip_m.get(t) or {}
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.markdown(f"**{t}** · ₪{p.get('alloc', 0):,.0f} · הוחלט "
                        f"{p.get('decision_date')} · ממתין "
                        f"{p.get('sessions_waiting', 0)}/3 סשנים")
            my = (appr.get(t) or {}).get("decision")
            my_reason = (appr.get(t) or {}).get("reason") or ""
            if my == "approve":
                c2.markdown("✅ **אושר על-ידך** — ימולא בפתיחה הבאה")
                if c3.button("↩️ בטל", key=f"tru_{t}",
                             help="החזרה להמתנה — אפשרי עד המילוי (ריצת 23:15)"):
                    _approve_trade(t, "undo", "החלטה בוטלה על-ידי המנהל")
                    st.rerun()
            elif my == "reject":
                c2.markdown("❌ **נדחה על-ידך**"
                            + (f" — _{my_reason[:60]}_" if my_reason else ""))
                if c3.button("↩️ בטל", key=f"tru_{t}",
                             help="ביטול הדחייה — חוזרת להמתנה"):
                    _approve_trade(t, "undo", "דחייה בוטלה על-ידי המנהל")
                    st.rerun()
            else:
                if c2.button("✅ אשר", key=f"tra_{t}"):
                    _approve_trade(t, "approve")
                    st.rerun()
                if c3.button("❌ דחה", key=f"trr_{t}"):
                    st.session_state[f"rej_{t}"] = True
                if st.session_state.get(f"rej_{t}"):
                    rsn = st.text_input(
                        "למה נדחתה? (נשמר בזיכרון הארגוני וביומן-ההחלטות)",
                        key=f"rejr_{t}",
                        placeholder="למשל: מתוחה מדי אחרי הריצה; אין לי אמון בסקטור השבוע")
                    if st.button("אשר דחייה", key=f"rejc_{t}") and rsn.strip():
                        _approve_trade(t, "reject", rsn.strip())
                        st.session_state[f"rej_{t}"] = False
                        st.rerun()
            with st.expander(f"🔎 {t} — הסינתזה המלאה להחלטה"):
                # 1 ── why it was chosen + the standard it sits on
                st.markdown(f"**למה נבחרה:** {row.get('why') or 'שורת-הצנרת לא זמינה'}")
                st.caption(f"טכניקה: {row.get('technique') or '—'} · טריות: "
                           f"{row.get('freshness') or '—'}"
                           + (f" (יום {row.get('signal_age_days')})"
                              if row.get("signal_age_days") is not None else "")
                           + f" · אופי: {row.get('char_class') or '—'}")
                # 2 ── the deal plan: entry / stop / size / risk
                sl_pct = row.get("sl_pct")
                risk = (f"₪{abs(float(p.get('alloc', 0)) * float(sl_pct) / 100):,.0f}"
                        if sl_pct else "—")
                st.markdown(f"| כניסה | סטופ | גודל | סיכון-בסטופ | סגנון-יציאה |\n"
                            f"|---|---|---|---|---|\n"
                            f"| {row.get('entry_level') or 'פתיחה הבאה'} "
                            f"| {row.get('sl_price') or '—'} ({sl_pct or '—'}%) "
                            f"| ₪{p.get('alloc', 0):,.0f} | {risk} "
                            f"| {row.get('technique') or '—'} |")
                # 3 ── the metric engine: gates
                if row.get("gates"):
                    st.dataframe(pd.DataFrame(
                        [{"": "🟢" if g["ok"] else "🔴", "שער": g["gate"],
                          "נימוק": g["why"]} for g in row["gates"]]),
                        use_container_width=True, hide_index=True)
                # 4 ── the qualitative engine (VIP deep) — or the honest gap
                q = vm.get("qual") or {}
                if q.get("rec") or vm.get("bottom_line"):
                    st.markdown(f"**האנליסט (עומק):** {q.get('rec') or '—'} · ביטחון "
                                f"{q.get('confidence') or '—'} · מנוע {q.get('engine') or '—'}")
                    if (vm.get("bottom_line") or {}).get("read_he"):
                        st.caption(vm["bottom_line"]["read_he"])
                else:
                    st.warning("⚠️ לא עבר ניתוח-עומק VIP ואימות שני-מפתחות — הגיע "
                               "מצינור-השערים המטרי בלבד. זה בדיוק מה שהשער הזה בודק.")
                beh_states = [str(x) for x in vm.get("behavior_states") or []]
                if beh_states:
                    st.markdown("🧬 **העדשה-השלישית (חיזוק-הקשר, לא שער):** "
                                + " · ".join(_BEHAV_HE.get(s, s)
                                             for s in beh_states[:3]))
                # 5 ── the competition: who lost the slot and why
                if nb:
                    st.markdown("**מי התחרה ולא נבחר:** " + " · ".join(
                        f"{x.get('ticker')} ({str(x.get('reason'))[:40]})"
                        for x in nb[:4]))
                # 6 ── alternatives that may mature inside your approval window
                if cands:
                    st.markdown("**מבשילות שעשויות להחליף בחלון-האישור:** " + " · ".join(
                        f"{c0.get('ticker')} ({c0.get('maturity') or '—'})"
                        for c0 in cands[:4]))
                # 7 ── bottom line: both engines, one sentence
                metric_full = str(row.get("state")) == "buy_signal"
                rec = str(q.get("rec") or "")
                if metric_full and rec == "BUY":
                    st.success("🟢 שורה תחתונה: שני המנועים מסכימים — מטרי מלא + אנליסט "
                               "BUY. כשיר לאישור.")
                elif metric_full and not q:
                    st.info("🟡 שורה תחתונה: מטרי מלא אך ללא מנוע-עומק — האישור הוא "
                            "שיקול-הסיכון שלך.")
                elif rec in ("WAIT", "DROP"):
                    st.error(f"🔴 שורה תחתונה: האנליסט אומר {rec} — שקול לדחות או להמתין.")
                else:
                    st.info("🟡 שורה תחתונה: תמונה חלקית — ראה שערים ואנליסט למעלה.")
    st.caption(f"as of **{board.get('date')}** · desk verdict: **{board.get('desk_verdict')}**")
    cols = st.columns(4)
    for i, s in enumerate((board.get("slots") or [])[:4]):
        with cols[i]:
            state = s.get("state")
            if state == "filled":
                st.metric(f"{_ICON['filled']} Slot {i+1}", s.get("ticker"),
                          f"day {s.get('days_held')}")
                pnl = s.get("pnl_pct")
                pnl_c = "#C8FF37" if (pnl or 0) >= 0 else "#FF6D7C"
                pnl_html = (f' · P&L <b style="color:{pnl_c}">{pnl:+.2f}%</b> '
                            f'(₪{s.get("pnl_ils", 0):+,.0f})' if pnl is not None else "")
                st.markdown(
                    f'<div class="papow-card"><div class="sub">קנייה ₪{s.get("cost", 0):,.0f}'
                    f' @ {s.get("entry_price")} ({s.get("entry_date")}) · אחרון '
                    f'{s.get("last_price", "—")}{pnl_html}<br>סטופ '
                    f'<span style="color:#FF6D7C">{s.get("sl_pct")}%</span> · יציאה: '
                    f'{s.get("exit_style")} · נותרו {s.get("days_left")} ימים'
                    f'</div></div>', unsafe_allow_html=True)
            elif state == "research":
                st.metric(f"{_ICON['research']} Slot {i+1}", "research",
                          f"{s.get('days_left')}d left")
            else:
                st.metric(f"{_ICON['ready']} Slot {i+1}", "ready", "cash")
    # nightly HOLD reads per open position — the manager's real question: להחזיק? להדק?
    held_names = [str(s.get("ticker")) for s in (board.get("slots") or [])
                  if s.get("state") == "filled"]
    if held_names:
        st.markdown("#### 🩺 קריאת-ההחזקה של הלילה")
        holds = _notes_of("trade_hold", limit=12)
        shown = set()
        for h in holds:
            p = h.get("parsed") or {}
            t = str(h.get("ticker") or "")
            if t in shown or t not in held_names or not h.get("valid"):
                continue
            shown.add(t)
            rec_he = {"hold": "החזק", "tighten_stop": "הדק סטופ",
                      "take_partial": "מימוש חלקי", "exit": "צא"}.get(
                str(p.get("manage")), str(p.get("manage") or "—"))
            st.markdown(f'<div class="papow-card"><span class="tkr">{t}</span> '
                        f'<b>{rec_he}</b> · תזה: {p.get("thesis_state", "—")}'
                        f'<div class="sub">{str(p.get("manage_why") or "")[:180]} '
                        f'<i>({h.get("_date")}; המלצה בלבד — ההחלטה שלך)</i></div></div>',
                        unsafe_allow_html=True)
        if not shown:
            st.caption("אין עדיין קריאת-לילה לפוזיציות — נכתבת בריצת 23:15.")
    closes = _notes_of("trade_close", limit=3)
    if closes:
        st.markdown("#### 📕 סגירות אחרונות")
        for cnote in closes:
            if cnote.get("read_he"):
                st.markdown(f"- {cnote['read_he']} _({cnote.get('_date')})_")
    st.caption("🪜 סולם-הצנרת המלא (מי מתקרב לסלוט, שערים וטריות) עבר לטאב 🚪 תור-VIP — "
               "כאן מנהלים רק מה שחי.")
    gone = board.get("departed_since_prev") or []
    if gone:
        st.info("🚪 עזבו את הצנרת מאתמול: "
                + " · ".join(f"**{g['ticker']}** — {g['reason']}" for g in gone))
    with st.expander("📓 פנקס-העסקאות שלי — רישום עסקת-אמת (D1)"):
        st.caption("רישום בלבד; המנוע מצרף בלילה את מה שהמכונה אמרה באותו יום, ובסגירה — "
                   "תוצאה ו-post-mortem. לא ייעוץ, לא פקודה.")
        c1, c2, c3, c4 = st.columns(4)
        tk = c1.text_input("טיקר", key="mt_tk").upper().strip()
        side = c2.selectbox("צד", ["buy", "sell"], key="mt_side")
        px = c3.number_input("מחיר", min_value=0.0, step=0.01, key="mt_px")
        qty = c4.number_input("כמות", min_value=0.0, step=1.0, key="mt_qty")
        note = st.text_input("הערה (למה?)", key="mt_note")
        if st.button("📥 רשום עסקה") and tk and px > 0:
            rid = f"{date.today().isoformat()}:{tk}:{side}:{uuid.uuid4().hex[:4]}"
            with _engine().begin() as c:
                c.execute(text(
                    'create table if not exists my_trades (id text primary key, date text, '
                    'ticker text, side text, price float, qty float, note text, '
                    "machine_json text default '{}', outcome_json text default '{}')"))
                c.execute(text(
                    'insert into my_trades (id, date, ticker, side, price, qty, note) '
                    'values (:i, :d, :t, :s, :p, :q, :n)'),
                    {"i": rid, "d": date.today().isoformat(), "t": tk, "s": side,
                     "p": px, "q": qty, "n": note})
            st.success(f"נרשם ({rid}) — ההעשרה בריצת-הלילה")
    m = acct.get("metrics") or {}
    st.caption(f"account (paper): equity {m.get('terminal_equity')} · withdrawn "
               f"{m.get('withdrawn')} · net {m.get('return_vs_deposit')}")
    dfd = acct.get("deferred_today") or []
    if dfd:
        st.warning("potential buys NOT taken (desk not calibrated): "
                   + ", ".join(f"{c['ticker']} ({c['list']})" for c in dfd))


_STAGE_HE = {"VIP_MATURING": "מבשילה", "VIP_READY_FOR_DEEP_ANALYSIS": "מוכנה לעומק",
             "DECISION_READY": "בנקודת-החלטה", "SHADOW_BUY": "BUY-צל 💥",
             "CONTINUE_DEEP_ANALYSIS": "ממתינה לטריגר", "CONTINUE_WATCH": "במעקב",
             "DROPPED_FROM_DEEP_ANALYSIS": "ירדה מעומק", "DROPPED_FROM_VIP": "יצאה"}


def _render_memory(ticker: str) -> None:
    """🧠 the organizational brain: what we KNOW about this name + similar cases."""
    brain = _latest_note("memory_brain") or {}
    d = (brain.get("dossiers") or {}).get(ticker)
    if not d:
        return
    st.markdown(f'<div class="papow-card"><span class="tkr">🧠 {d.get("read_he")}</span>'
                + (f'<div class="sub">🔁 {d.get("similar")}</div>'
                   if d.get("similar") else "")
                + "".join(f'<div class="sub">📌 לקח: {les}</div>'
                          for les in d.get("lessons") or [])
                + '</div>', unsafe_allow_html=True)


def _render_deep_notes(ticker: str, n: int = 2) -> None:
    """The full daily deep-analysis records of one name, straight from the queue card."""
    try:
        with _engine().connect() as c:
            rows = c.execute(text(
                "select date, title, content from research_notes where kind = 'vip' "
                "and title like :t order by date desc limit :n"),
                {"t": f"%{ticker}%", "n": n}).fetchall()
    except Exception:
        rows = []
    if not rows:
        st.caption("אין עדיין ניתוח שמור לשם הזה (נשמר בכל לילה-עומק).")
    for _dt, title, content in rows:
        st.markdown(f"**{title}**")
        try:
            day = json.loads(content)
            parsed = day.get("parsed") or {}
            st.caption(f"מנוע: {day.get('analysis_engine')} · פרומפט: "
                       f"{day.get('prompt_version')} · תקף: {day.get('valid')}")
            for k, v in parsed.items():
                if isinstance(v, list):
                    for item in v:
                        st.caption(f"• {item}")
                elif v not in (None, ""):
                    st.markdown(f"**{k}:** {v}")
        except Exception:
            st.text(str(content)[:2000])
        st.divider()


def _vip_tab() -> None:
    q = _latest_note("vip_board")
    if not q:
        st.info("אין עדיין תצלום-VIP — הריצה הלילית תייצר אותו")
        return
    cap = q.get("capacity") or {}
    c1, c2, c3 = st.columns(3)
    c1.metric("👑 קיבולת VIP", cap.get("vip", "—"))
    c2.metric("🔬 בניתוח-עומק", cap.get("deep", "—"))
    c3.metric("💥 החלטות הלילה", len(q.get("decisions") or []))
    members = q.get("members") or []
    deep = [m for m in members if str(m.get("status", "")).startswith(
        ("DEEP", "DECISION", "CONTINUE_DEEP"))]
    rest = [m for m in members if m not in deep]
    st.markdown("#### תור-העומק — שני מפתחות, מנעול אחד")
    if not deep:
        st.caption("אין שמות בעומק כרגע — ההבשלה עובדת.")
    for m in deep:
        weakening = "weakening" in (m.get("review_flags") or [])
        q = m.get("qual") or {}
        rec, buyable = str(q.get("rec") or ""), q.get("buyable")
        conf = q.get("confidence")
        k1 = ('<span class="papow-key off">🔑 מטרי · נחלש</span>' if weakening
              else '<span class="papow-key on">🔑 מטרי · עובר</span>')
        if buyable is True or rec == "BUY":
            k2 = f'<span class="papow-key on">🔑 איכותני · BUY {conf or ""}</span>'
        elif rec in ("WAIT", "DROP") or buyable is False:
            k2 = f'<span class="papow-key off">🔑 איכותני · {rec or "לא עכשיו"}</span>'
        else:
            k2 = '<span class="papow-key">🔑 איכותני · צובר</span>'
        eng = q.get("engine")
        gate = f" · חסר: {m.get('missing_gate')}" if m.get("missing_gate") else " · מלאה"
        stage = _STAGE_HE.get(str(m.get("status")), m.get("status"))
        read = (f' · {rec[:110]}' if rec and rec not in ("BUY", "WAIT", "DROP") else "")
        read += f' · מנוע: {eng}' if eng else ""
        mag = ' <span class="papow-chip gold">🧲 מגנט-כסף</span>' if m.get("magnet")             else ""
        if m.get("thesis"):
            mag += f' <span class="papow-chip">🧪 תזה: {m.get("thesis")}</span>'
        if m.get("correlative"):
            mag += f' <span class="papow-chip">🧩 מפגר-אשכול: {m.get("correlative")}</span>'
        beh = "".join(f' <span class="papow-chip cyan">🧬 {_BEHAV_HE.get(x, x)}</span>'
                      for x in (m.get("behavior_states") or []))
        st.markdown(
            f'<div class="papow-card"><span class="tkr">{m.get("ticker")}</span>{mag}{beh} '
            f'{k1}{k2} <span class="papow-stage">{stage}</span>'
            f'<div class="sub">בשלות {m.get("maturity")}{gate} · יום-עומק '
            f'{m.get("days_analyzed")} → תחנה {m.get("next_station")} · מקור: '
            f'{m.get("source")}{read}</div></div>', unsafe_allow_html=True)
        with st.expander(f"🔬 ניתוח-העומק המלא של {m.get('ticker')}"):
            _render_memory(str(m.get("ticker")))
            _render_deep_notes(str(m.get("ticker")))
    for d in q.get("decisions") or []:
        mv, qv = d.get("metric_vector") or {}, d.get("qual_vector") or {}
        st.success(f"💥 {d.get('ticker')}: **{d.get('decision')}** · מטרי "
                   f"{'✅' if mv.get('pass') else '❌'} · איכותני "
                   f"{'✅' if qv.get('pass') else '❌'} — {d.get('explanation')}")
    st.caption("תור-הכניסה המלא (מבשילים, מקורות, קודי-סיבה, תזות) — בטאב 🚪 תור-VIP.")


def _vip_queue_tab() -> None:
    """The ENTRY queue — who is maturing toward VIP, from which lane, and why (owner
    13.07: managed separately from the deal manager)."""
    q = _latest_note("vip_board")
    if not q:
        st.info("אין עדיין תצלום-VIP — הריצה הלילית תייצר אותו")
        return
    cap = q.get("capacity") or {}
    c1, c2 = st.columns(2)
    c1.metric("👑 קיבולת VIP", cap.get("vip", "—"))
    c2.metric("🔬 בניתוח-עומק", cap.get("deep", "—"))
    members = q.get("members") or []
    rest = [m for m in members if not str(m.get("status", "")).startswith(
        ("DEEP", "DECISION", "CONTINUE_DEEP"))]
    if rest:
        st.markdown("#### מבשילים בתור")
        st.dataframe(pd.DataFrame([{
            "ticker": m.get("ticker"),
            "שלב": _STAGE_HE.get(str(m.get("status")), m.get("status")),
            "בשלות": m.get("maturity"), "חסר": m.get("missing_gate"),
            "גיל-VIP": m.get("vip_age_days"), "מקור": m.get("source"),
            "🧲": "🧲" if m.get("magnet") else "", "🧪": m.get("thesis") or "",
            "🧩": m.get("correlative") or ""}
            for m in rest]), use_container_width=True, hide_index=True)
    else:
        st.caption("אין שמות בהבשלה כרגע — התור ריק וזה נתון, לא תקלה.")
    # the slot-pipeline ladder (moved from the deal manager — it's queue business)
    acct = _latest("account_snapshots") or {}
    pipe = (acct.get("slot_board") or {}).get("pipeline") or []
    if pipe:
        st.markdown("#### 🪜 סולם-הצנרת לסלוטים")
        st.dataframe(pd.DataFrame([{
            "state": _STATE_HE.get(r["state"], r["state"]), "ticker": r["ticker"],
            "בשלות": r.get("maturity") or "—",
            "טריות": {"fresh": "🟢 טרי", "aging": "🟡 מזדקן", "stale": "🔴 רקוב"}.get(
                str(r.get("freshness")),
                "—") + (f" (יום {r['signal_age_days']})"
                        if r.get("signal_age_days") is not None else ""),
            "thesis": r.get("thesis") or "—",
            "character": r.get("char_class") or "—",
            "technique": r.get("technique") or "—",
            "entry": r.get("entry_level") or "—",
            "SL": f"{r['sl_price']} ({r['sl_pct']}%)" if r.get("sl_price") else "—",
            "size": f"₪{r['size_hint']:,.0f}" if r.get("size_hint")
                    and r["state"] != "watch" else "—",
            "why": r.get("why")} for r in pipe]), use_container_width=True,
            hide_index=True)
        for r in pipe:
            if r["state"] == "watch":
                continue
            with st.expander(f"🔍 {r['ticker']} — פירוט-שערים מלא"):
                if r.get("gates"):
                    st.dataframe(pd.DataFrame([{"gate": g["gate"],
                                                "status": "🟢" if g["ok"] else "🔴",
                                                "detail": g["why"]} for g in r["gates"]]),
                                 use_container_width=True, hide_index=True)
                for k, v in (r.get("entry_rules") or {}).items():
                    st.markdown(f"- `{k}`: {v}")
                if r.get("prior"):
                    st.caption(f"prior (in-sample): {r['prior']}")
    _thesis_card()                      # theses ARE an entry lane — they live here
    ev = q.get("events_today") or []
    if ev:
        with st.expander(f"🧾 reason codes של הלילה ({len(ev)})"):
            for e in ev:
                st.caption(f"{e.get('ticker')} · {e.get('reason_code')} — "
                           f"{e.get('detail')}")


_TH_HE = {"DORMANT": "🛌 רדומה", "WARMING": "🌡️ מתחממת", "AWAKE": "🚨 ערה"}

_BEHAV_HE = {"CROWDED_SHORT": "🩳 שורט צפוף", "EXTREME_SHORT_INTEREST": "🧨 שורט קיצוני",
             "SQUEEZE_PRESSURE_BUILDING": "🔥 לחץ-סקוויז", "ACTIVE_SQUEEZE": "🚀 סקוויז פעיל",
             "SQUEEZE_EXHAUSTION": "🎇 סקוויז מתפוגג",
             "INSIDER_OPEN_MARKET_CLUSTER": "👔 קניות-פנים",
             "RETAIL_CHASE_INTO_STRENGTH": "🎪 רדיפת-ריטייל"}


def _thesis_card() -> None:
    """The research-thesis pipeline — the SECOND VIP entry lane, its own gates."""
    tw = _latest_note("thesis_watch")
    if not tw:
        return
    st.markdown("#### 🧪 תזות-מחקר — פייפליין-כניסה שני (שערים משלו)")
    for s in tw.get("scans") or []:
        core = s.get("core") or {}
        ew = core.get("ew_20d")
        bits = [_TH_HE.get(str(s.get("status")), s.get("status"))]
        if ew is not None:
            bits.append(f"EW20 {ew:+.1f}%")
        if core.get("rs_share") is not None:
            bits.append(f"RS>0: {int(core['rs_share'] * 100)}%")
        if s.get("locomotives"):
            bits.append(f"קטר→VIP: {', '.join(s['locomotives'])}")
        if s.get("mode") == "risk":
            bits.append("עדשת-סיכון")
        qt = s.get("qual_today") or []
        silent = s.get("days_since_news")
        if qt:
            senti = s.get("qual_sentiment") or {}
            tone = (f" (👍{senti.get('positive', 0)}/👎{senti.get('negative', 0)})"
                    if senti.get("positive") or senti.get("negative") else "")
            bits.append(f"📰 {len(qt)} כותרות-פרופיל היום{tone}")
        elif silent is not None:
            thr = s.get("feed_starved_days")
            bits.append(f"🔇 שקט {silent} ימ'" + (f" (סף {thr})" if thr else ""))
        st.markdown(f"**{s.get('title_he')}** — " + " · ".join(str(b) for b in bits))
        if s.get("reasons"):
            st.caption(" · ".join(str(r) for r in s["reasons"][:2]))
        for h in qt[:2]:
            st.caption(f"📰 {h.get('ticker')}: \"{h.get('title')}\" "
                       f"({', '.join(h.get('matched') or [])})")
    st.caption("תזה ערה מושיבה רק את הקטר שלה (עד 2 כיסאות-תזה בכל ה-VIP); שאר הסל "
               "ב-WATCHLISTS. שערי-הכניסה של תזה הם תנאי-ההתעוררות שלה — לא חמשת שערי-"
               "הצינור הרגיל. הפיד האיכותני: כותרות שנוגעות בפרופיל-החדשות של התזה — "
               "ראיה לרלוונטיות, לא שער.")


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
    st.caption("★ חודש-מסחר = 20 ימי-מסחר ≈ חודש קלנדרי — חלון-ההחלטה של הסווינג "
               "(מול Yahoo/TradingView: יום/שבוע זהים; 'חודש' אצלם קלנדרי — סטייה קטנה "
               "צפויה).")
    _typ_he = {"provenance": "מקור", "basis": "בסיס ראייתי", "purpose": "משפט-החלטה",
               "feed": "הזנה", "entry": "תנאי-כניסה", "maturation": "הבשלה",
               "decision_window": "חלון-החלטה", "expiry": "פקיעה",
               "vip_lane": "נתיב-VIP", "measurement_hook": "מדידה",
               "resistance": "התנגדות"}
    _top_level = ("provenance", "basis", "purpose", "measurement_hook")
    for wl in w.get("watchlists", []):
        st.markdown(f"**[{wl.get('provenance')}·{wl.get('basis')}] {wl.get('kind')}** — "
                    f"{wl.get('purpose')}")
        if wl.get("members"):
            df = pd.DataFrame(wl["members"]).rename(columns={
                "ret_20d": "חודש-מסחר % ★", "ret_1d": "יום %", "ret_5d": "שבוע %"})
            st.dataframe(df, use_container_width=True, hide_index=True)
        typing = wl.get("typing") or {}
        filled = sum(1 for f in _typ_he
                     if typing.get(f) or (f in _top_level and wl.get(f)))
        st.caption(f"⚖️ {wl.get('measurement_hook')} · 🏷️ טיפוס {filled}/{len(_typ_he)}"
                   + ("" if filled == len(_typ_he)
                      else " (חלקי — סימן-בדיקה, לא פסילה)"))
        if typing:
            with st.expander(f"🏷️ תעודת-הזהות של הרשימה ({wl.get('kind')})"):
                for f in _typ_he:
                    v = typing.get(f) or (wl.get(f) if f in _top_level else None)
                    st.markdown(f"- **{_typ_he[f]}:** {v or '— חסר'}")


_ALIGN_HE = {"confirmed": ("מגובה-חדשות", "volt"),
             "contradicted": ("בניגוד לחדשות", "coral"),
             "no_news_move": ("מהלך בלי סיפור", "cyan"), "quiet": ("יום שקט", ""),
             "no_relevant_news": ("בלי חדשות רלוונטיות", "cyan")}
_PLAYERS_HE = {"institutions": "מוסדיים", "swing_traders": "סווינג",
               "day_traders": "יומיים", "speculators": "ספקולנטים",
               "passive_flows": "זרימה פסיבית", "unclear": "לא ברור"}


def _story_cards(tape) -> None:
    st.markdown("#### 🎬 סיפורי-הנכסים")
    assets = [a for a in tape.get("assets", []) if a.get("status") == "analyzed"]
    if assets:
        ups = [a for a in assets
               if ((a.get("facts") or {}).get("change_pct") or 0) > 0]
        top = max(assets, key=lambda a: abs((a.get("facts") or {}).get("change_pct") or 0))
        backed = sum(1 for a in assets if a.get("alignment") == "confirmed")
        st.markdown(
            f'<div class="papow-card"><b>סקירת-מנהלים:</b> {len(ups)}/{len(assets)} '
            f'נכסי-הפוקוס עלו · {backed} מהלכים מגובי-חדשות · הבולט: '
            f'<b>{top.get("ticker")}</b> '
            f'{(top.get("facts") or {}).get("change_pct"):+.2f}% — '
            f'{str(top.get("narrative") or "").split(".")[0][:110]}.</div>',
            unsafe_allow_html=True)
    for a in tape.get("assets", []):
        if a.get("status") != "analyzed":
            continue
        chg = (a.get("facts") or {}).get("change_pct") or 0.0
        al, cls = _ALIGN_HE.get(str(a.get("alignment")), (a.get("alignment"), ""))
        col = "#C8FF37" if chg > 0 else "#FF6D7C"
        hook = str(a.get("narrative") or "").split(".")[0][:130]
        st.markdown(
            f'<div class="papow-card"><span class="tkr">{a["ticker"]}</span> '
            f'<b style="color:{col}">{chg:+.2f}%</b> '
            f'<span class="papow-chip {cls}">{al}</span>'
            f'<div style="margin-top:6px;color:#E6ECF7">{hook}.</div></div>',
            unsafe_allow_html=True)
        with st.expander("הסיפור המלא · לוגיקת הסוחרים · שחקנים"):
            st.markdown(a.get("narrative") or "")
            st.markdown(f"**לוגיקת הסוחרים:** {a.get('trader_logic')}")
            pl = " · ".join(_PLAYERS_HE.get(str(x.get("type")), str(x.get("type")))
                            for x in a.get("players", []))
            conf = a.get("confidence")
            st.caption(f"שחקנים: {pl}" + (f" · דרגת-קריאה: {conf}"
                                          if conf and conf != "None" else ""))


def _leadership_tab() -> None:
    """Order matters (owner, 5th ask): the VERIFIABLE numbers open the tab — every figure
    with an explicit window a user can check on Yahoo/TradingView — and only then the
    narrative, behind a loud window-disclaimer. Trust before story."""
    m = _latest("leadership_snapshots") or {}
    story = m.get("market_story") or {}

    # 1 ── the numbers a user checks first, windows explicit, straight from the map
    st.markdown("#### 🔢 המדדים — יום · שבוע · חודש-מסחר")
    idx_rows = []
    for sym in ("SPY", "QQQ"):
        r = (story.get(sym) or {}).get("returns") or {}
        if r:
            idx_rows.append({"": sym, "יום %": r.get("1d"), "שבוע (5d) %": r.get("5d"),
                             "חודש-מסחר (20d) % ★": r.get("20d")})
    if idx_rows:
        st.dataframe(pd.DataFrame(idx_rows), use_container_width=True, hide_index=True)
    secs = m.get("leading_sectors") or []
    if secs:
        st.markdown("**הסקטורים המובילים**")
        st.dataframe(pd.DataFrame([{"sector": s["sector"],
                                    "יום %": ((s.get("returns") or {}).get("1d")),
                                    "שבוע (5d) %": ((s.get("returns") or {}).get("5d")),
                                    "חודש-מסחר (20d) % ★":
                                    ((s.get("returns") or {}).get("20d")),
                                    "persistence":
                                    (s.get("persistence") or {}).get("score"),
                                    "trend": s.get("trend")} for s in secs]),
                     use_container_width=True, hide_index=True)
    st.markdown("**המניות המובילות**")
    st.dataframe(pd.DataFrame([{"ticker": c["ticker"], "sector": c.get("sector"),
                                "pocket": c.get("pocket_id"),
                                "יום %": c.get("ret_1d"),
                                "שבוע (5d) %": c.get("ret_5d"),
                                "חודש-מסחר (20d) % ★": c.get("ret_20d"),
                                "stage": c.get("move_stage")}
                               for c in m.get("stock_leaders", [])]),
                 use_container_width=True, hide_index=True)
    st.caption("★ חודש-מסחר = 20 ימי-מסחר ≈ חודש קלנדרי — חלון-ההחלטה של הסווינג (אופק "
               "≤4 שבועות). יום ושבוע זהים ל-Yahoo/TradingView אחד-לאחד; ה'חודש' שלהם "
               "קלנדרי — סטייה קטנה צפויה. עמודות ריקות מתמלאות בריצת-הלילה.")

    # 2 ── the narrative, ONLY after the numbers, behind an explicit window warning
    if story.get("narrative") or (m.get("tape_story") or {}).get("market_paragraph"):
        st.markdown("#### 📰 הסיפור")
        st.warning("⚠️ מספר בסיפור שלמטה בלי תווית-חלון מפורשת = **חודש-מסחר (20 ימי "
                   "מסחר)**, לא יום ולא שבוע. לאימות מהיר — הטבלאות שלמעלה.")
    tape = m.get("tape_story") or {}
    if tape.get("market_paragraph"):
        st.info(tape["market_paragraph"])
        if tape.get("stocks_paragraph"):
            st.info(tape["stocks_paragraph"])
        led = tape.get("alignment_ledger") or {}
        if led.get("n_assets"):
            st.caption(f"מאזן: {led.get('confirmed', 0)} מגובי-חדשות · "
                       f"{led.get('contradicted', 0)} בניגוד · "
                       f"{led.get('no_news_move', 0)} בלי סיפור — היפותזה פתוחה, הקשר בלבד")
        _story_cards(tape)
    if story.get("narrative"):
        st.caption(story["narrative"])
    rg = m.get("regime_v2") or {}
    if rg.get("read_he"):
        st.info("🌊 " + str(rg["read_he"]))
        if rg.get("qual_note_he"):
            st.caption(str(rg["qual_note_he"]))
    # money flows + the behavioral third lens (owner 13.07: depth belongs here)
    st.markdown("#### 💸 זרימות-הכסף והעדשה-ההתנהגותית")
    flows = []
    for key, icon in (("locomotive_mix", "🚂"), ("sector_rotation", "🔄"),
                      ("smart_money_pulse", "🫀")):
        blk = m.get(key) or {}
        if blk.get("read_he"):
            flows.append(f"- {icon} {blk['read_he']}")
    if flows:
        st.markdown("\n".join(flows))
    else:
        st.caption("אין קריאות-זרימה במפה הנוכחית.")
    beh = _latest_note("behavior_states")
    if beh:
        tally: dict[str, int] = {}
        chips = []
        for t, states in list(beh.items())[:40]:
            if not isinstance(states, list):
                continue
            names = [s.get("state") if isinstance(s, dict) else str(s) for s in states]
            for n0 in names:
                tally[str(n0)] = tally.get(str(n0), 0) + 1
            if names and len(chips) < 8:
                chips.append(f'<span class="papow-chip cyan">🧬 {t}: '
                             + " · ".join(_BEHAV_HE.get(str(x), str(x))
                                          for x in names[:2]) + "</span>")
        if tally:
            st.markdown("**תצפיות-התנהגות הלילה:** " + " · ".join(
                f"{_BEHAV_HE.get(k, k)}×{v}"
                for k, v in sorted(tally.items(), key=lambda x: -x[1])[:5]))
        if chips:
            st.markdown('<div class="papow-ribbon">' + "".join(chips) + "</div>",
                        unsafe_allow_html=True)
        st.caption("עדשה-שלישית, תצפית בלבד — המתאם בינה לבין זרימות-הכסף נמדד ביומן "
                   "(וקטור עצמאי); טרם נקבעה סיבתיות ולא נבנה ממנה שער.")
    else:
        st.caption("🧬 אין עדיין note-התנהגות — נכתב בריצה הלילית.")
    for k, v in (m.get("caveats") or {}).items():
        st.caption(f"⚠️ {k}: {v}")


def _improvement_tab() -> None:
    st.caption("Approve = log + monitor + queue. NOTHING auto-applies; approved changes are "
               "implemented in a batch when the logic engine opens.")
    # the CLOSED learning loop (owner 14.07): matured journal reviews graded fwd-vs-QQQ
    jr = ((_latest("leadership_snapshots") or {}).get("learning")
          or {}).get("journal_reviews") or {}
    if jr:
        st.markdown("#### 🎓 הלולאה עונה — ביקורות-החלטה שהבשילו")
        st.caption(f"נסגרו הלילה: {jr.get('closed', 0)} · ממתינות לחלון מלא: "
                   f"{jr.get('waiting', 0)} · דורשות שיפוט-אנושי: "
                   f"{jr.get('manual_open', 0)} (עולות במוצ\"ש)")
        for les in jr.get("lessons") or []:
            st.markdown(f"- {les}")
        st.divider()
    allc = _changes()
    active = [c for c in allc if c["status"] in ("proposed", "approved")]
    archived = [c for c in allc if c["status"] not in ("proposed", "approved")]
    st.markdown(f"**פעילים ({len(active)})** — רק מה שדורש/מחכה להחלטה")
    for ch in active:
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
    with st.expander(f"🗄️ ארכיון ({len(archived)}) — הוכרעו/יושמו; להשוואה, לא להחלטה"):
        for ch in archived:
            st.markdown(f"`{ch['status']}` **{ch['id']}** — {ch['title']}"
                        + (f"  \n_{ch['dismissed_reason']}_" if ch.get("dismissed_reason")
                           else ""))


def _inbox_insert(when: str, txt: str, kind: str, images: list[str]) -> str:
    rid = f"ozbeki:{when}:{uuid.uuid4().hex[:6]}"
    with _engine().begin() as c:
        c.execute(text(
            'create table if not exists review_inbox (id text primary key, date text, '
            "source text, kind text default 'daily_review', raw_text text, "
            "images_json text default '[]', status text, result_json text)"))
        c.execute(text("alter table review_inbox add column if not exists kind text "
                       "default 'daily_review'"))
        c.execute(text("alter table review_inbox add column if not exists images_json text "
                       "default '[]'"))
        c.execute(text(
            'insert into review_inbox (id, date, source, kind, raw_text, images_json, status, '
            "result_json) values (:i, :d, 'ozbeki', :k, :r, :img, 'pending', '{}')"),
            {"i": rid, "d": when, "k": kind, "r": txt, "img": json.dumps(images)})
    return rid


def _ozbeki_tab() -> None:
    st.caption("קלט למידה מאוזבקי — נשמר במסד הנתונים; מנוע המחקר (הריצה הלילית, 23:15) מפענח. "
               "עזר-כיול בלבד: המערכת בודקת את עצמה מולו, לא מאמצת את החשיבה שלו.")
    mode = st.radio("סוג הקלט", ["📄 סקירה יומית (טקסט)", "📈 תמונה תוך-יומית + טקסט קצר", "🧪 מחקר/מאמר (השראה לאסטרטגיה)"],
                    horizontal=True)
    when = st.date_input("תאריך", value=date.today()).isoformat()
    if mode.startswith("🧪"):
        st.caption("מאמר/מחקר מעניין — המנוע מחלץ רעיונות ישימים עם חוזה-אינטגרציה מלא; כל "
                   "רעיון הופך להצעה ב-Improvement. השראה לבדיקה-מחדש, לעולם לא להעתקה.")
        txt = st.text_area("הדבק את המחקר/המאמר (או תקציר+לינק)", height=280)
        if st.button("📥 שמור מחקר לפענוח"):
            if not txt.strip():
                st.warning("אין טקסט")
            else:
                rid = _inbox_insert(when, txt, "research", [])
                st.success(f"נשמר ({rid}) — יפוענח בריצת-הלילה; הצעות יופיעו ב-Improvement")
    elif mode.startswith("📄"):
        txt = st.text_area("טקסט הסקירה", height=280, placeholder="הדבק את הסקירה המלאה כאן…")
        if st.button("📥 שמור לפענוח"):
            if not txt.strip():
                st.warning("אין טקסט להדבקה")
            else:
                rid = _inbox_insert(when, txt, "daily_review", [])
                st.success(f"נשמר ({rid}) — יפוענח בריצת המנוע הבאה, וההצעות יופיעו "
                           "ב-Improvement")
    else:
        st.caption("צילומי גרפים שהוא מפרסם במהלך היום. תמונה בודדת לעולם לא משנה לוגיקה — "
                   "רק בדיקת פוקוס: 'הוא עוקב אחרי X — למה הרשימות שלנו פספסו?'")
        files = st.file_uploader("תמונות (עד 4)", type=["png", "jpg", "jpeg"],
                                 accept_multiple_files=True)
        cap = st.text_area("הטקסט הקצר שצירף", height=100)
        if st.button("📥 שמור סניפט לפענוח"):
            imgs: list[str] = []
            for f in (files or [])[:4]:
                raw = f.getvalue()
                if len(raw) > 4_000_000:
                    st.warning(f"{f.name} גדול מ-4MB — דולג")
                    continue
                import base64
                ext = (f.name.rsplit(".", 1)[-1] or "png").lower()
                ext = "jpeg" if ext == "jpg" else ext
                imgs.append(f"data:image/{ext};base64,{base64.b64encode(raw).decode()}")
            if not imgs and not cap.strip():
                st.warning("אין תמונה ואין טקסט")
            else:
                rid = _inbox_insert(when, cap, "intraday_snippet", imgs)
                st.success(f"נשמר ({rid}, {len(imgs)} תמונות) — בדיקת-פוקוס תרוץ הלילה")
    st.divider()
    st.markdown("**סטטוס הדבקות אחרונות**")
    try:
        with _engine().connect() as c:
            rows = c.execute(text(
                'select id, date, status, result_json, kind from review_inbox '
                'order by date desc, id desc limit 10')).fetchall()
    except Exception:
        rows = []
    if rows:
        recs = []
        for r in rows:
            res = json.loads(r[3] or "{}")
            focus = res.get("focus") or {}
            recs.append({"id": r[0], "date": r[1],
                         "סוג": "📈 סניפט" if r[4] == "intraday_snippet" else "📄 סקירה",
                         "status": {"pending": "⏳ ממתין לפענוח", "processed": "✅ פוענח",
                                    "failed": "🔴 נכשל"}.get(r[2], r[2]),
                         "insights": res.get("n_insights", "—"),
                         "focus": ", ".join(f"{t}:{s}" for t, s in focus.items()) or "—",
                         "CCs": ", ".join(res.get("ccs") or []) or "—",
                         "note": res.get("reason") or ""})
        st.dataframe(pd.DataFrame(recs), use_container_width=True, hide_index=True)
    else:
        st.caption("עוד לא הודבקו סקירות.")


def main() -> None:
    _gate()
    _hero()
    _ribbon()
    # order = the owner's working process (RTL: first renders rightmost): the deal
    # manager and VIP first, the entry queue beside them, context next, ops last.
    tabs = st.tabs(["💼 עסקאות", "👑 VIP", "🚪 תור-VIP", "🦅 הובלה", "📡 רשימות",
                    "🚦 מפעיל", "🛠 שיפורים", "📖 אוזבקי"])
    with tabs[0]:
        _slots_tab()
    with tabs[1]:
        _vip_tab()
    with tabs[2]:
        _vip_queue_tab()
    with tabs[3]:
        _leadership_tab()
    with tabs[4]:
        _watchlists_tab()
    with tabs[5]:
        _operator_tab()
    with tabs[6]:
        _improvement_tab()
    with tabs[7]:
        _ozbeki_tab()
    _footer()


main()
