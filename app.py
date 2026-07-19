"""PapoW board — a read-only VIEWER over pre-computed snapshots stored in a database.

This app contains NO trading logic, NO strategy code, and NO analysis — it only renders JSON
payloads that a private research system writes elsewhere. Password-gated. Demo/paper research
dashboard; nothing here is investment advice and nothing places orders.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import date, datetime
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
        _rg_he = {"fakeout_prone": "שוק חשוד-פריצות-שווא", "trending": "שוק במגמה",
                  "choppy": "שוק קופצני", "risk_off": "שוק בורח-מסיכון",
                  "rotation": "שוק ברוטציה", "range_bound": "שוק בטווח"}
        _fr_he = {"high": "שבירות גבוהה", "elevated": "שבירות מוגברת",
                  "normal": "שבירות רגילה", "low": "שבירות נמוכה"}
        chips.append(f'<span class="papow-chip {cls}">🧭 '
                     f'{_rg_he.get(str(mr.get("regime_type")), mr.get("regime_type"))}'
                     f' · {_fr_he.get(frag, frag)}</span>')
    eq = (acct.get("metrics") or {}).get("terminal_equity")
    if eq:
        chips.append(f'<span class="papow-chip">💼 ₪<b>{eq:,.0f}</b></span>')
    vipq = _latest_note("vip_board")
    if vipq:
        cap = vipq.get("capacity") or {}
        chips.append(f'<span class="papow-chip gold">👑 VIP {cap.get("vip", "—")} · '
                     f'עומק {cap.get("deep", "—")}</span>')
    pulse = _fresh_note("intraday_pulse") or {}
    if pulse.get("date") == date.today().isoformat():
        mk = pulse.get("market") or {}
        _q = mk.get("QQQ")
        chips.append('<span class="papow-chip cyan">🕒 עדכון-ביניים '
                     f'{pulse.get("time_utc")}Z (עיכוב {pulse.get("delay_min")} דק׳)'
                     + (f' · QQQ {_q:+.1f}%' if _q is not None else "")
                     + '</span>')
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
    if _secret("LOCAL_DEV_NO_AUTH") == "yes":     # local UX-testing only — this
        st.session_state["auth_ok"] = True        # key never exists in the cloud
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
def _fresh_note(kind: str) -> dict[str, Any] | None:
    """Same as _latest_note but with a short cache — for 15-min intraday notes."""
    return _fresh_note_impl(kind)


@st.cache_data(ttl=120, show_spinner=False)
def _fresh_note_impl(kind: str) -> dict[str, Any] | None:
    try:
        with _engine().connect() as c:
            row = c.execute(text('select content from research_notes where kind = :k '
                                 'order by date desc limit 1'), {"k": kind}).fetchone()
        return json.loads(row[0]) if row else None
    except Exception:
        return None


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
_ICON = {"filled": "📈", "research": "🔬", "ready": "⚪"}


def _accrual() -> None:
    parts = [f"{n}: {c}d (last {d})" for n, c, d in _counts()]
    with st.expander("🛠 רעננות-נתונים (טכני)"):
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
    _so2 = _fresh_note("sentinel_ops") or {}
    if _so2.get("date") == today:
        _gs = _so2.get("guard_state")
        _w = _so2.get("watched") or {}
        st.markdown("#### 🛰️ שכבת-היום — מה רץ עכשיו")
        st.info(("🛡️ השומר **פעיל** — שומר על: "
                 + ", ".join((_w.get("positions") or []) + (_w.get("triggers") or []))
                 if _gs == "armed" else
                 "🛌 השומר **רדום** — אין פוזיציות/טריגרים לשמור עליהם")
                + f" · דפיקות היום: {_so2.get('ticks_today', 0)}"
                + f" · התראות: {len(_so2.get('alerts_today') or [])}"
                + f" · דופק אחרון: {_so2.get('pulse_time_utc')}Z")
        for a in list(_so2.get("alerts_today") or [])[-8:][::-1]:
            st.caption(f"{a.get('time')}Z {a.get('level')} {a.get('he')}")
        st.caption("⏰ העוגנים הקבועים: "
                   + " · ".join(_so2.get("anchors_il") or []))
        st.divider()
    else:
        st.caption("🛰️ שכבת-היום: אין עדיין דופק מהיום — "
                   "מתעורר בשעות המסחר (16:35 שעון ישראל)")
        st.divider()
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
    st.caption("💼 **מה זה המסך הזה:** שולחן-העסקאות. 4 סלוטים לקניות-נייר, "
               "מה שמחכה לאישורך מופיע עם כפתורים, והחזקות פתוחות מקבלות קריאת-"
               "החזקה לילית. ⚪ פנוי = יש מקום, לא המלצה לקנות.  \n"
               "**המסלול המלא:** 📡 רשימות ← 🚪 תור ← 👑 בדיקת-עומק ← 💼 סלוט (כאן)")
    acct = _latest("account_snapshots") or {}
    board = acct.get("slot_board") or {}
    if not board:
        st.info("אין עדיין לוח — הריצה הלילית תיצור אותו")
        return
    _pl = _fresh_note("intraday_pulse") or {}
    if _pl.get("date") == date.today().isoformat() and _pl.get("positions"):
        _rows = " · ".join(
            f"**{p.get('ticker')}** {p.get('last', '—')}"
            + (f" ({p['est_pnl_pct']:+.1f}%)" if p.get("est_pnl_pct") is not None
               else "")
            for p in _pl["positions"])
        _so0 = _fresh_note("sentinel_ops") or {}
        if (_so0.get("date") == date.today().isoformat()
                and _so0.get("guard_state") == "dormant"):
            st.caption("🛌 השומר רדום — אין פוזיציות פתוחות ואין טריגרים "
                       "חמושים; אין מה לשמור כרגע")
        st.caption(f"🕒 **דופק-ביניים {_pl.get('time_utc')}Z** "
                   f"(עיכוב {_pl.get('delay_min')} דק׳): {_rows}  \n"
                   "_תצוגה בלבד — ההחלטות נופלות על נתוני-הסגירה בריצת-הלילה_")
    d = _latest("forward_desk_snapshots") or {}
    r0, c0 = d.get("readiness") or {}, d.get("calibration") or {}
    hr = "—" if c0.get("hit_rate") is None else f"{c0['hit_rate']:.0%}"
    st.markdown(f'<div class="papow-card"><b>🧪 כיול-תחזיות (מחקר, לא שער-קנייה):</b> '
                f'{c0.get("n", 0)} תחזיות-כיוון נבדקו · דיוק {hr}'
                f'<div class="sub">מודד את חדות-הקריאות שלנו לאורך זמן. קניות-הנייר '
                f'עוברות דרך מפתח-כפול (בדיקת-עומק + אישור-מטרי) ווטו-משטר — לא דרך '
                f'המספר הזה. סלוט "🟢 מוכן" = יש מקום פנוי, לא המלצה לקנות.</div></div>',
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
                        [{"": ("🧊" if g.get("ok") is None else
                               "🟢" if g["ok"] else "🔴"), "שער": g["gate"],
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
    _dv_he = {"GO": "🟢 מותר לפרוס", "WAIT": "🟠 ממתינים — לא פורסים היום",
              "NO_GO": "🔴 לא פורסים"}
    _dv = str(board.get("desk_verdict")).upper()
    st.caption(f"נכון ל-**{board.get('date')}** (הריצה הלילית האחרונה) · "
               f"שוער-הפריסה: **{_dv_he.get(_dv, _dv)}**")
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
                st.metric(f"{_ICON['research']} סלוט {i+1}", "בחקירה",
                          f"נותרו {s.get('days_left')} ימים")
            else:
                st.metric(f"{_ICON['ready']} סלוט {i+1}", "פנוי",
                          "מזומן ממתין — לא המלצה", delta_color="off")
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
             "DEEP_ANALYSIS_DAY_1": "עומק — יום 1", "DEEP_ANALYSIS_DAY_2": "עומק — יום 2",
             "DEEP_ANALYSIS_DAY_3": "עומק — יום 3", "DECISION_READY": "בשלה להחלטה",
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
                {"t": f"%— {ticker} (%", "n": n}).fetchall()
    except Exception:
        rows = []
    if not rows:
        st.caption("אין עדיין ניתוח שמור לשם הזה (נשמר בכל לילה-עומק).")
    for _dt, title, content in rows:
        if f"— {ticker} (" not in str(title):
            continue                              # never show another name's analysis
        bad = ("איננה קיימת" in str(content) or "אינה קיימת" in str(content))
        if bad:
            st.warning("⚠️ ניתוח-הלילה נפסל בבקרת-איכות (המנוע התייחס לנתונים לא "
                       "תואמים) — יופק מחדש בריצה הבאה. לא מסתמכים עליו.")
            continue
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


def _vip_dossier_line(t: str) -> None:
    """The identity block under a VIP card (owner 19.07: 'מי היא? מה דחף אותה?')."""
    dd = ((_latest_note("name_dossier") or {}).get("dossiers") or {}).get(t)
    if not dd:
        return
    ident = dd.get("identity_he") or ""
    _drv_he = {"fundamental": "פונדמנטלי", "narrative": "נרטיב",
               "mechanical_squeeze": "מכני (שורט-סקוויז)", "sympathy": "סימפטיה",
               "mixed": "משולב", "unknown": "לא-ידוע"}
    drv = _drv_he.get(str(dd.get("driver_class")), dd.get("driver_class"))
    cats = dd.get("next_catalysts") or []
    cat_ln = " · ".join(f"{c.get('date')} {c.get('what_he')}"
                        + (" ⚡בינארי" if c.get("binary") else "")
                        for c in cats[:2])
    si = dd.get("short_interest") or {}
    si_ln = (f"שורט {si.get('short_pct_float', 0):.1%} · כיסוי "
             f"{si.get('days_to_cover')}י"
             if si.get("short_pct_float") else "")
    st.caption(f"🪪 **תעודת-זהות:** {ident}  \n"
               + f"מנוע-התנועה: **{drv}**"
               + (f" — {dd.get('driver_he')}" if dd.get("driver_he") else "")
               + (f" · {si_ln}" if si_ln else "")
               + (f"  \n⏰ קטליזטורים: {cat_ln}" if cat_ln else "")
               + (f"  \n📅 דוח קרוב: {dd['next_earnings']}"
                  if dd.get("next_earnings") else ""))
    weak = dd.get("weaken_tests_he") or []
    if weak:
        st.caption("🧪 מה יחליש את התנועה: " + " · ".join(weak[:2]))


def _vip_tab() -> None:
    st.caption("👑 **מה זה המסך הזה:** חדר-הבדיקה. המניות שכבר הבשילו מקבלות "
               "כאן ניתוח-עומק יומי, ובתחנות קבועות נופלת החלטת-צל (קנייה-על-נייר/"
               "המתנה/דחייה). קריאה בלבד — אין כאן כפתורי פעולה.  \n"
               "**המסלול המלא:** 📡 רשימות ← 🚪 תור ← 👑 בדיקת-עומק (כאן) ← 💼 סלוט")
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
        ("DEEP", "DECISION", "CONTINUE_DEEP", "SHADOW_BUY"))]   # decided members keep their card
    st.markdown("#### תור-העומק — שני מפתחות, מנעול אחד")
    if not deep:
        st.caption("אין שמות בעומק כרגע — ההבשלה עובדת.")
    for m in deep:
        weakening = "weakening" in (m.get("review_flags") or [])
        mq = m.get("qual") or {}   # NOT `q` — shadowing the note dict silently killed
        # the 💥 decision banners on exactly the nights decisions happen
        rec, buyable = str(mq.get("rec") or ""), mq.get("buyable")
        conf = mq.get("confidence")
        k1 = ('<span class="papow-key off">🔑 מטרי · נחלש</span>' if weakening
              else '<span class="papow-key on">🔑 מטרי · עובר</span>')
        if buyable is True or rec == "BUY":
            k2 = f'<span class="papow-key on">🔑 איכותני · BUY {conf or ""}</span>'
        elif rec in ("WAIT", "DROP") or buyable is False:
            k2 = f'<span class="papow-key off">🔑 איכותני · {rec or "לא עכשיו"}</span>'
        else:
            k2 = '<span class="papow-key">🔑 איכותני · צובר</span>'
        eng = mq.get("engine")
        gate = f" · חסר: {m.get('missing_gate')}" if m.get("missing_gate") else " · מלאה"

        def _conf_ln(m0: dict) -> str:
            """Candidate-fit (contract clock) — SEPARATE from trade-readiness: the
            audit found one '5/5' impersonating five different maturity kinds."""
            cf = (m0.get("maturity_kinds") or {}).get("candidate_fit") or {}
            if not cf:
                return ""
            out = (f' · התאמת-מועמדת: {cf.get("confirmations", "?")} אישורים '
                   f'(נדרש {cf.get("required", 1)})')
            if cf.get("structural_rule"):
                out += (" · מבנה ✓" if cf.get("structural_confirmed")
                        else f' · ממתין-למבנה ({cf["structural_rule"]})')
            return out
        stage = _STAGE_HE.get(str(m.get("status")), m.get("status"))
        read = (f' · {rec[:110]}' if rec and rec not in ("BUY", "WAIT", "DROP") else "")
        read += f' · מנוע: {eng}' if eng else ""
        mag = ' <span class="papow-chip gold">🧲 מגנט-כסף</span>' if m.get("magnet")             else ""
        # BOOK/DOCTRINE provenance chips (owner blocker 3, post-audit): every card
        # says which book owns it and under which authority role it claimed
        _bk_he = {"core": "📕 Core", "opportunistic": "📗 אופורטוניסטי",
                  "context": "📙 Context"}
        if m.get("book_id"):
            mag += (f' <span class="papow-chip">{_bk_he.get(str(m["book_id"]), m["book_id"])}'
                    + (f' · {m.get("doctrine_id")}' if m.get("doctrine_id") else "")
                    + (f' · {m.get("authority_role")}' if m.get("authority_role")
                       else "") + '</span>')
        if str(m.get("book_id")) == "context":
            mag += (' <span class="papow-chip coral">⚠️ כניסת-Context — הפרת-סמכות '
                    '(אסור מאז ה-Audit)</span>')
        if m.get("late_crowding"):
            mag += ' <span class="papow-chip coral">🌡️ מתוח — עדיפות מופחתת</span>'
        for _rf in (m.get("risk_flags") or [])[:1]:
            mag += f' <span class="papow-chip coral">🛑 וטו-סיכון: {str(_rf)[:60]}</span>'
        if m.get("thesis"):
            mag += f' <span class="papow-chip">🧪 תזה: {m.get("thesis")}</span>'
        if m.get("correlative"):
            mag += f' <span class="papow-chip">🧩 מפגר-אשכול: {m.get("correlative")}</span>'
        if m.get("young"):
            mag += ' <span class="papow-chip">🐣 מהלך-צעיר</span>'
        if m.get("emerging"):
            mag += ' <span class="papow-chip">🌱 הובלה-מתהווה</span>'
        if m.get("invalidation_broken"):
            mag += (f' <span class="papow-chip coral">🛑 invalidation נשבר '
                    f'({m.get("invalidation_level")}) — אין החלטה עד ניתוח מחודש</span>')
        beh = "".join(f' <span class="papow-chip cyan">🧬 {_BEHAV_HE.get(x, x)}</span>'
                      for x in (m.get("behavior_states") or []))
        # Sprint 1 (owner 16.07): the three separated axes + attribution + local scores —
        # the card answers "מה חסר לעסקה, מה מוציא אותה, ומה מצב הדאטה" in one line each
        axes_ln = ""
        if m.get("vip_status"):
            _ax_he = {"ACTIVE": "🟢 פעיל", "DEGRADED": "🟠 נחלש", "EXITED": "⚫ יצא",
                      "IN_DEEP": "🔬 בעומק", "QUEUED": "⏳ בתור-עומק",
                      "NOT_QUEUED": "—", "DEEP_COMPLETE": "🏁 עומק הושלם",
                      "EVICTED": "↩️ פונה (משאב)", "REJECTED": "⛔ נדחה (אנליסט)",
                      "DECIDED": "💥 הוחלט", "CLOSED": "⚫ נסגרה", "EXPIRED": "⌛ פג",
                      "ACCRUING": "צובר-ימים",
                      "ELIGIBLE": "✅ כשיר-להחלטה", "BLOCKED_DEGRADED": "🚫 חסום (נחלש)",
                      "BLOCKED_INVALIDATION": "🛑 חסום (invalidation)",
                      "BLOCKED_DATA": "🧊 חסום (דאטה)",
                      "SHADOW_BUY": "👻 קניית-צל", "NO_BUY": "🚷 לא-לקנות",
                      "DEFER": "⏸️ נדחתה-לטריגר"}
            _s, _d, _c = (m["vip_status"], str(m.get("deep_status")),
                          str(m.get("decision_status")))
            _out = m.get("decision_outcome")
            _act = m.get("latest_decision_action")
            axes_ln = (f'<div class="sub">צירים: VIP {_ax_he.get(_s, _s)} · '
                       f'עומק {_ax_he.get(_d, _d)} · החלטה '
                       f'{_ax_he.get(_c, _c)}'
                       + (f' · תוצאה: {_ax_he.get(str(_out), _out)}' if _out else "")
                       + (f' · פעולה אחרונה: {_ax_he.get(str(_act), _act)}'
                          if _act and not _out else "") + '</div>')
            if _c.startswith("BLOCKED"):
                axes_ln += ('<div class="sub">🚫 <b>השורה התחתונה: אין קנייה '
                            'היום</b> — גם אם הניתוח למעלה חיובי, ההחלטה חסומה '
                            'והכרטיס למעקב בלבד</div>')
            if m.get("data_status") == "DATA_HOLD":
                mag += (f' <span class="papow-chip cyan">🧊 DATA_HOLD — '
                        f'{m.get("data_hold_reason") or "בעיית דאטה"} '
                        f'(שעונים קפואים)</span>')
            else:
                _held = [str(ln0.get("list_id")) for ln0 in m.get("list_links") or []
                         if ln0.get("link_data_status") == "DATA_HOLD"]
                if _held:   # partial hold: ONE thesis unobservable, the member runs on
                    mag += (f' <span class="papow-chip cyan">🧊 תזה מוקפאת-דאטה: '
                            f'{", ".join(_held[:2])}</span>')
        attr_ln = ""
        if m.get("vip_primary_list_id"):
            sup = [ln0.get("list_id") for ln0 in m.get("list_links") or []
                   if ln0.get("role") == "supporting"]
            ent = m.get("vip_entry_list_id")
            attr_ln = (f'<div class="sub">רשימה ראשית: {m["vip_primary_list_id"]}'
                       + (f' (הוכנסה ע"י {ent})'
                          if ent and ent != m.get("vip_primary_list_id") else "")
                       + (f' · מחזקות: {", ".join(str(s) for s in sup[:4])}' if sup else "")
                       + (f' · ייחוס-החלטה: {m["decision_primary_list_id"]}'
                          if m.get("decision_primary_list_id") else "") + "</div>")
        need_ln = ""
        sc = m.get("scores") or {}
        if sc:
            tr, ev = sc.get("trade_readiness") or {}, sc.get("evidence_quality") or {}
            # only actual GAPS ride "לעסקה חסר" — trigger_defined is a plus, not a gap
            need = (", ".join(c.split(":", 1)[1] for c in tr.get("reason_codes") or []
                              if c.startswith("missing:"))
                    or ("טריגר מוגדר — ממתין לו" if tr.get("trigger_defined")
                        else "אין חסמים מוגדרים"))
            fresh = "טרי" if ev.get("latest_price_fresh") else "⚠️ לא-טרי"
            need_ln = (f'<div class="sub">לעסקה חסר: {need} · יציאה: invalidation קשה '
                       f'(מיידי) / נחלש &gt;3 ימים · דאטה: '
                       f'{ev.get("valid_days", 0)}/{ev.get("total_days", 0)} ימים תקפים, '
                       f'מחיר {fresh}</div>')
        st.markdown(
            f'<div class="papow-card"><span class="tkr">{m.get("ticker")}</span>{mag}{beh} '
            f'{k1}{k2} <span class="papow-stage">{stage}</span>'
            f'<div class="sub">מוכנות-מסחר {m.get("maturity")}{gate}'
            f'{_conf_ln(m)} · יום-עומק '
            f'{m.get("days_analyzed")} → תחנה {m.get("next_station")} · מקור: '
            f'{m.get("source")}{read}</div>{axes_ln}{attr_ln}{need_ln}</div>',
            unsafe_allow_html=True)
        _vip_dossier_line(str(m.get("ticker")))
        with st.expander(f"🔬 ניתוח-העומק המלא של {m.get('ticker')}"):
            _render_memory(str(m.get("ticker")))
            _render_deep_notes(str(m.get("ticker")))
    for d in q.get("decisions") or []:
        mv, qv = d.get("metric_vector") or {}, d.get("qual_vector") or {}
        st.success(f"💥 {d.get('ticker')}: **{d.get('decision')}** · מטרי "
                   f"{'✅' if mv.get('pass') else '❌'} · איכותני "
                   f"{'✅' if qv.get('pass') else '❌'} — {d.get('explanation')}")
    st.caption("תור-הכניסה המלא (מבשילים, מקורות, קודי-סיבה, תזות) — בטאב 🚪 תור-VIP.")


def _idea_action(idea_id: str, action: str, notes: str = "") -> None:
    """The owner's judgment on a trade idea — approve freezes the contract and the
    SHADOW list activates on the next nightly; reject/return with notes. Rides
    research_notes exactly like trade approvals; the engine reconciles idempotently."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nid = f"idea_action:{idea_id}:{now}"
    payload = json.dumps({"idea_id": idea_id, "action": action, "notes": notes,
                          "at": now, "by": "owner (board)"}, ensure_ascii=False)
    with _engine().begin() as c:
        c.execute(text(
            'insert into research_notes (id, date, kind, title, content) '
            'values (:i, :d, :k, :t, :c) on conflict (id) do nothing'),
            {"i": nid, "d": date.today().isoformat(), "k": "idea_action",
             "t": f"Idea {action} — {idea_id}", "c": payload})
    _notes_of.clear()


_IDEA_ST_HE = {"PENDING_APPROVAL": "🟡 ממתין לאישורך", "APPROVED": "🟢 מאושר ורץ",
               "REJECTED": "⛔ נדחה", "RETURNED": "↩️ הוחזר לעריכה",
               "REFUTED": "❌ הופרך (בתנאים שאושרו)", "CONFIRMED": "✅ אושש",
               "EXPIRED": "⌛ פג", "DRAFT": "📝 טיוטה", "RETIRED": "⚫ הושבת",
               "BACKLOG_UNPRESENTED": "📦 במלאי — עדיפות נמוכה"}


def _ideas_intro() -> None:
    st.caption("💡 **מה זה המסך הזה:** רעיונות-ניסוי — כמה פרשנויות מתחרות לאותה "
               "תופעה בשוק, שנמדדות זו מול זו על נתונים אמיתיים. רעיון שמנצח "
               "במדידה הופך לגרעין קבוע (לשונית «גרעינים»); רעיון שמופרך נסגר "
               "בכבוד עם כל הלקחים. אתה מאשר/דוחה כל רעיון לפני שהוא רץ.")


def _ideas_tab() -> None:
    _ideas_intro()
    q = _latest_note("idea_board")
    if not q:
        st.info("אין עדיין לוח-רעיונות — הריצה הלילית הקרובה תיצור אותו "
                "(הפיילוט: סיטואציית מחנק-הזיכרון עם שני רעיונות מתחרים)")
        return
    # THE LOGICAL PIPELINE STRIP: source -> situation -> ideas -> review -> approval
    # -> SHADOW runtime -> VIP feed — the factory at a glance
    sits = q.get("situations") or []
    ideas = q.get("ideas") or []
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🎬 סיטואציות פתוחות",
              sum(1 for s in sits if s.get("status") == "OPEN"))
    c2.metric("🟡 ממתינים לאישורך",
              sum(1 for i in ideas
                  if str(i.get("status")) in ("DRAFT", "PENDING_APPROVAL")))
    c3.metric("🟢 רשימות-SHADOW רצות",
              sum(1 for i in ideas if i.get("status") == "APPROVED"))
    c4.metric("📦 במלאי (עדיפות נמוכה)",
              sum(1 for i in ideas if i.get("status") == "BACKLOG_UNPRESENTED"))
    c5.metric("📊 אירועי-מועמדות הלילה",
              sum(sum(v.values()) for v in (q.get("candidate_counts") or {}).values()))
    rep = q.get("scout_report") or {}
    if rep:
        st.caption("🛰️ **דוח-הסקאוט** (" + str(rep.get("date")) + "): נסרקו "
                   + ", ".join(rep.get("scanned") or []) + " · זיהו: "
                   + (", ".join(f0.get("detector", "") for f0 in
                                rep.get("fired") or []) or "—")
                   + " · בלי-קלט: " + (", ".join(rep.get("no_input") or []) or "—")
                   + (" · 🔕 GUARD פעיל (≥4 ממתינים)"
                      if rep.get("pending_guard_active") else ""))
    kw = q.get("kill_watch") or {}
    for iid, k in kw.items():
        line = (f"⚖️ **מבחן גרסה-מול-גרסה {iid}** "
                f"(v{k.get('contract_version')}) — איזו גרסת-כללים חוזה טוב יותר: ")
        if k.get("n_closed"):
            lc = (k.get("loser_catch_by_day") or {}).get("d10") or {}
            line += (f"{k['n_closed']} אפיזודות-forward סגורות · תפיסת-מפסידים d10: "
                     f"v1 {lc.get('v1')} מול v2 {lc.get('v2')} · פגיעת-מנצחים: "
                     f"v1 {(k.get('winner_kill') or {}).get('v1')} מול v2 "
                     f"{(k.get('winner_kill') or {}).get('v2')}")
        else:
            line += "עוד אין עסקאות סגורות למדידה — ההשוואה תתמלא עם הזמן"
        st.caption(line)
    an = _latest_note("idea_analysis")
    if an and an.get("events"):
        with st.expander(f"📡 אירועי-ניתוח אחרונים ({an.get('date')}) — "
                         f"{len(an['events'])}"):
            for a1 in an["events"][:8]:
                icon = "🔴" if a1.get("severity") == "high" else "🔵"
                st.markdown(f"{icon} **{a1.get('kind')}** · {a1.get('title_he')}")
                st.caption(f"רעיון: {a1.get('idea_change_he')}  \n"
                           f"יקום: {a1.get('universe_change_he')}  \n"
                           f"רשימה: {a1.get('watchlist_action_he')}  \n"
                           f"עסקה: {a1.get('trade_implication_he')}")
    for s in sits:
        s_title = (s.get("title_he") or s.get("question_he")
                   or ", ".join(s.get("assets") or []) or s.get("situation_id"))
        _sit_he = {"OPEN": "🟢 פתוחה", "CLOSED": "⚫ סגורה", "EXPIRED": "⌛ פגה"}
        _sit = str(s.get("status") or "OPEN")
        st.markdown(f"### 🎬 {s_title} "
                    f"<span class='papow-stage'>{_sit_he.get(_sit, _sit)}</span>",
                    unsafe_allow_html=True)
        st.markdown(f"**השאלה הפתוחה:** {s.get('question_he')}")
        st.caption(f"התגלה דרך: {s.get('discovered_via')} · נכסים: "
                   f"{', '.join(s.get('assets') or [])} · חלון: "
                   f"{s.get('relevance_window_days')} ימים מ-{s.get('opened_at')}")
        for ev in (s.get("evidence") or [])[:4]:
            st.caption(f"• {ev}")
        cr = s.get("current_read") or {}
        if cr.get("read_he"):
            st.caption(f"📈 **המצב עכשיו ({cr.get('date')}):** {cr['read_he']}")
            if s.get("evidence"):
                st.caption("· הראיות שלמעלה = מרגע פתיחת-הסיטואציה (קפואות); "
                           "השורה הזו מתעדכנת כל לילה")
        elif s.get("evidence"):
            st.caption("· הראיות לעיל = מרגע פתיחת-הסיטואציה, לא מתעדכנות יומית — "
                       "המצב העדכני של הסל בלשונית «🧬 גרעינים»")
        group = [i for i in ideas if i.get("situation_id") == s.get("situation_id")]
        _ord = {"PENDING_APPROVAL": 0, "DRAFT": 0, "APPROVED": 1, "RETURNED": 2}
        group.sort(key=lambda i0: _ord.get(str(i0.get("status")), 3))
        for i in group:
            stt = str(i.get("status"))
            st.markdown(
                f"#### 💡 {i.get('title_he') or i.get('idea_id')} "
                f"<span class='papow-stage'>{_IDEA_ST_HE.get(stt, stt)}</span>"
                + (f" <span class='papow-chip'>v{i.get('contract_version')} "
                   "🔒 חוזה נעול — התנאים לא משתנים בדיעבד</span>"
                   if i.get("frozen") else ""),
                unsafe_allow_html=True)
            # COUNTER-FIRST (external research Q5: the human adds value only when he
            # sees the weakest side, not the pitch — anti rubber-stamping)
            st.error(f"**התרחיש הנגדי קודם:** {i.get('counter_scenario_he')}")
            if i.get("possible_duplicate_of"):
                st.warning(f"⚠️ כפילות-אפשרית של {i['possible_duplicate_of']} "
                           "(חפיפת-יקום ≥50%, אותו כיוון) — ההכרעה שלך")
            if i.get("late_entry_he"):
                st.warning(f"⏰ המהלך כבר רץ — למה נשאר מיץ: {i['late_entry_he']}")
            rc = i.get("replay_calibration") or {}
            if rc:
                st.caption(f"🔁 **Replay-כיול** ({rc.get('label')}): "
                           f"{rc.get('n_episodes')} אפיזודות-עבר לפי כלל · "
                           f"פגיעה-x20 {rc.get('hit_share_x20')} · חציון-עודף-20d "
                           f"{rc.get('median_x20')} · ההפרכה תפסה מפסידים "
                           f"{rc.get('refutation_caught_losers')}")
            st.markdown(f"**תזה (בת-הפרכה):** {i.get('thesis_he')}")
            st.markdown(f"**מנגנון:** {i.get('mechanism_he')}  \n"
                        f"**מה צפוי:** {i.get('expectation_he')}  \n"
                        f"**טכניקה מתאימה:** {i.get('technique_he')}")
            hz = (f"הבשלה מינ' {i.get('min_maturation_days')}י · חלון-כניסה "
                  f"{i.get('entry_window_days')}י · מימוש-צפוי "
                  f"{i.get('expected_realization_days')}י")
            st.caption(f"⏱️ אופק: {hz}")
            cc1, cc2 = st.columns(2)
            with cc1:
                st.markdown("**תנאי-הפרכה (מה יוכיח שטעינו):**")
                for cl in i.get("refutation") or []:
                    st.caption(f"❌ {cl.get('desc_he')} `{cl.get('rule')}`")
            with cc2:
                st.markdown("**תנאי-אישוש (מדידים):**")
                for cl in i.get("confirmation") or []:
                    st.caption(f"✅ {cl.get('desc_he')} `{cl.get('rule')}`")
            if i.get("mechanism_outcome"):
                st.info(f"סגירה כפולה: מנגנון **{i['mechanism_outcome']}** · "
                        f"חלון-סווינג **{i['trade_horizon_outcome']}**")
            for ev0 in (i.get("evidence_log") or [])[-3:]:
                st.caption(f"🧾 {ev0.get('date')} [{ev0.get('modality')}"
                           f"{ev0.get('direction')}] {ev0.get('what_he')}")
            wl = i.get("watchlist") or {}
            st.caption("**הבשלה ל-VIP:** "
                       + " + ".join(str(c0.get("desc_he"))
                                    for c0 in wl.get("maturation") or [])
                       + f" · **תפוגה:** {i.get('expires_at')}"
                       + f" · **מתחרה מול:** {', '.join(i.get('competes_with') or [])}")
            gaps = i.get("activation_gaps") or []
            if gaps:
                st.warning("פערי-הפעלה (הרשימה לא תרוץ עד שיסגרו): "
                           + " · ".join(gaps[:3]))
            state = i.get("state") or {}
            if state.get("last_eval"):
                st.caption(f"קריאה אחרונה ({state.get('last_eval')}): אישוש "
                           f"{state.get('confirmed_days', 0)} ימים · הפרכה רצופה "
                           f"{state.get('refuted_days', 0)} ימים")
            if stt in ("PENDING_APPROVAL", "RETURNED", "DRAFT"):
                nts = st.text_input("הערות (לא חובה)", key=f"idea_n_{i['idea_id']}")
                b1, b2, b3 = st.columns(3)
                if b1.button("✅ אשר והפעל", key=f"idea_a_{i['idea_id']}"):
                    _idea_action(i["idea_id"], "approve", nts)
                    st.success("אושר — החוזה יוקפא (v1) והרשימה תרוץ מהלילה")
                if b2.button("⛔ דחה", key=f"idea_r_{i['idea_id']}"):
                    _idea_action(i["idea_id"], "reject", nts)
                    st.info("נדחה — יתועד עם ההערות")
                if b3.button("↩️ החזר לעריכה", key=f"idea_e_{i['idea_id']}"):
                    _idea_action(i["idea_id"], "return", nts)
                    st.info("הוחזר לעריכה")
        st.divider()
    counts = q.get("candidate_counts") or {}
    if counts:
        st.markdown("#### 📊 אירועי-מועמדות הלילה (מכנה אחיד לכל הרשימות)")
        st.dataframe(pd.DataFrame([
            {"רשימה": k, **v} for k, v in sorted(counts.items())]),
            use_container_width=True, hide_index=True)
        st.caption("⚠️ עדיין אי-אפשר להשוות המרות בין רשימות — שיטת-הספירה "
                   "טרם אוחדה לכולן (עבודה עתידית).")
    with st.expander("➕ פתח סיטואציה / הצע רעיון חדש"):
        st.caption("נסח חופשי — המנוע (בסיוע LLM) יהפוך את זה לטיוטת-חוזה עם תנאים "
                   "מדידים ויחזיר לאישורך. ה-LLM לא ממציא נתונים, לא מאשר ולא משנה "
                   "חוזה פעיל.")
        t0 = st.text_input("כותרת הסיטואציה / הרעיון")
        q0 = st.text_area("מה קרה ומה השאלה הפתוחה? (או: התזה + מה יאשש ומה יפריך)")
        a0 = st.text_input("טיקרים רלוונטיים (מופרדים בפסיק)")
        if st.button("📨 שלח לניסוח-חוזה") and t0.strip() and q0.strip():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with _engine().begin() as c:
                c.execute(text(
                    'insert into research_notes (id, date, kind, title, content) '
                    'values (:i, :d, :k, :t, :c) on conflict (id) do nothing'),
                    {"i": f"idea_intake:{now}", "d": date.today().isoformat(),
                     "k": "idea_intake", "t": f"Idea intake — {t0[:60]}",
                     "c": json.dumps({"title": t0, "text": q0, "tickers": a0,
                                      "at": now}, ensure_ascii=False)})
            _notes_of.clear()
            st.success("נקלט — יעובד לטיוטת-חוזה ויוצג כאן לאישורך")


def _vip_queue_tab() -> None:
    """The ENTRY queue — who is maturing toward VIP, from which lane, and why (owner
    13.07: managed separately from the deal manager)."""
    st.caption("🚪 **מה זה המסך הזה:** חדר-ההמתנה. מניות שהועמדו ע\"י רשימה "
               "מוסמכת מבשילות כאן לפי שעון משלהן, ורק אחר-כך נכנסות לבדיקת-"
               "העומק. צפייה בלבד.  \n"
               "**המסלול המלא:** 📡 רשימות ← 🚪 תור (כאן) ← 👑 בדיקת-עומק ← 💼 סלוט")
    q = _latest_note("vip_board")
    if not q:
        st.info("אין עדיין תצלום-VIP — הריצה הלילית תייצר אותו")
        return
    cap = q.get("capacity") or {}
    ep0 = q.get("epoch") or {}
    if str(ep0.get("phase") or "FORWARD") != "FORWARD":
        st.warning(f"⚠️ פאזת-אפוק: {ep0.get('phase')} — ריצות-צל טכניות; "
                   "האוכלוסייה ללא מעמד-מדידה עד מעבר ל-FORWARD (אחרי ה-Audit)")
    c1, c2, c3 = st.columns(3)
    c1.metric("👑 קיבולת VIP", cap.get("vip", "—"))
    c2.metric("🔬 בניתוח-עומק", cap.get("deep", "—"))
    c3.metric("🧾 אירועי-הלילה", len(q.get("events_today") or []))
    st.caption(f"🔏 חותם-סמכות (טכני): {q.get('authority_snapshot_version') or '—'}")
    # THREE funnels (owner blocker 4): Core / Opportunistic / Context-Discovery —
    # Context must read 0 direct entries; orphans are raw material, not failures
    fns = q.get("funnels") or {}
    if fns:
        fc, fo, fx = (fns.get("core") or {}, fns.get("opportunistic") or {},
                      fns.get("context_discovery") or {})
        b1, b2, b3 = st.columns(3)
        b1.metric("📕 Core", f"{fc.get('active', 0)} פעילים",
                  f"+{len(fc.get('entered_today') or [])} הלילה")
        b2.metric("📗 אופורטוניסטי", f"{fo.get('active', 0)} פעילים",
                  f"+{len(fo.get('entered_today') or [])} הלילה")
        _viol = fx.get("direct_vip_entries", 0)
        b3.metric("📙 Context/Discovery → VIP", str(_viol),
                  "חייב-אפס" if not _viol else "⚠️ הפרה", delta_color="inverse")
        if fx.get("violation_tickers"):
            st.error("הפרת-סמכות: כניסות-Context ישירות — "
                     + ", ".join(fx["violation_tickers"]))
        orp = fx.get("orphaned_high_readiness") or []
        if orp:
            st.info("🧩 מניות חזקות בלי רשימה אחראית (נשלחו לחקר, לא לתור): "
                    + ", ".join(orp))
            st.caption("מניה שעברה את ספי-המסחר אבל אף רעיון/רשימה מוסמכת לא "
                       "מסבירה אותה — לא נכנסת לתור, אלא נשלחת ללשונית-הגרעינים "
                       "כחומר-גלם לרעיון חדש. שום מידע לא נזרק.")
        dob = fx.get("discovery_observations") or []
        if dob:
            st.caption("🔭 מהלכים צעירים בלי קבוצה (במעקב בלבד): " + ", ".join(dob))
    members = q.get("members") or []
    rest = [m for m in members if not str(m.get("status", "")).startswith(
        ("DEEP", "DECISION", "CONTINUE_DEEP"))]
    if rest:
        st.markdown("#### מבשילים בתור")
        st.dataframe(pd.DataFrame([{
            "ticker": m.get("ticker"),
            "שלב": _STAGE_HE.get(str(m.get("status")), m.get("status")),
            "מוכנות-מסחר": m.get("maturity"), "חסר": m.get("missing_gate"),
            "אישורים": (lambda cf: f"{cf.get('confirmations', '?')} מתוך "
                        f"{cf.get('required', 1)}")(
                (m.get("maturity_kinds") or {}).get("candidate_fit") or {}),
            "ספר": m.get("book_id") or "",
            "גיל-VIP": m.get("vip_age_days"), "מקור": m.get("source"),
            "רשימה ראשית": m.get("vip_primary_list_id") or "",
            "מחזקות": ", ".join(str(ln0.get("list_id")) for ln0 in
                                m.get("list_links") or []
                                if ln0.get("role") == "supporting") or "",
            "🧲": "🧲" if m.get("magnet") else "", "🧪": m.get("thesis") or "",
            "🧩": m.get("correlative") or "", "🐣": "🐣" if m.get("young") else "",
            "🛑": f"נשבר {m.get('invalidation_level')}"
                  if m.get("invalidation_broken") else ""}
            for m in rest]), use_container_width=True, hide_index=True)
    else:
        st.caption("אין שמות בהבשלה כרגע — התור ריק וזה נתון, לא תקלה.")
    la = q.get("legacy_archive") or {}
    ep = q.get("epoch") or {}
    if la.get("n"):
        with st.expander(f"🗄️ Legacy/Migration — {la['n']} חברי התקופה הקודמת "
                         f"(ארכיון-עיון; אפוק נוכחי: {ep.get('epoch_id', '—')})"):
            st.caption("סטטוסים קפואים כפי שהיו בחיתוך — לא יציאות ולא כישלונות; "
                       "שם שיעפיל שוב ייכנס כאפיזודה חדשה עם הארכיון כרפרנס. "
                       "אי-חזרה = 'טרם העפיל תחת הדוקטרינה החדשה', לפי חלון-המשפחה.")
            st.caption(", ".join(la.get("tickers") or []))
    # the slot-pipeline ladder (moved from the deal manager — it's queue business)
    acct = _latest("account_snapshots") or {}
    pipe = (acct.get("slot_board") or {}).get("pipeline") or []
    if pipe:
        st.markdown("#### 🪜 סולם-הצנרת לסלוטים")
        st.dataframe(pd.DataFrame([{
            "state": _STATE_HE.get(r["state"], r["state"]), "ticker": r["ticker"],
            "מוכנות-מסחר": r.get("maturity") or "—",
            "רשימות": ", ".join(r.get("lists") or ([r["list"]] if r.get("list")
                                                   else [])),
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
                _vip_dossier_line(str(r["ticker"]))
                if r.get("gates"):
                    st.dataframe(pd.DataFrame([{
                        "gate": g["gate"],
                        "status": ("🧊 DATA_GAP" if g.get("ok") is None
                                   else "🟢" if g["ok"] else "🔴"),
                        "detail": g["why"]} for g in r["gates"]]),
                                 use_container_width=True, hide_index=True)
                st.caption("כללי-הכניסה כפי שנכתבו בחוזה (טכני, באנגלית):")
                for k, v in (r.get("entry_rules") or {}).items():
                    st.markdown(f"- `{k}`: {v}")
                if r.get("prior"):
                    st.caption("סטטיסטיקת-עבר של התבנית (על מדגם היסטורי, "
                               f"לא תחזית): {r['prior']}")
    st.caption("🧬 הגרעינים (התזות) עברו ללשונית משלהם — «גרעינים» — שם רואים כל רעיון, הסל שלו ומצב-ההתעוררות.")
    ev = q.get("events_today") or []
    _CODE_HE = {
        "orphaned_high_readiness": "מוכנה-לסחר אבל בלי רשימה אחראית — נשלחה לחקר",
        "discovery_observation": "מהלך צעיר בלי קבוצה — מעקב בלבד",
        "orphan_superseded": "נמצאה לה רשימה אחראית באותו לילה",
        "list_cap_full": "הרשימה מלאה — ממתינה לתור",
        "family_cap_full": "משפחת-הליבה מלאה (3) — ממתינה",
        "late_crowding_routed": "מתוחה — נותבה למסלול-הנסיגה במקום רדיפה",
        "late_crowding_needs_full": "מתוחה — נדרשת מוכנות מלאה",
        "veto_blocked_entry": "אזהרת-עייפות חסמה כניסה",
        "claim_denied": "הרשימה לא מוסמכת להכניס — נרשם בלבד",
        "vip_entered": "נכנסה לתור-הבדיקה",
        "vip_exited": "יצאה (תנאי-הרשימה נשברו)",
        "degraded_start": "התנאים נחלשו — בהשגחה, בלי קניות חדשות",
        "degraded_recovered": "התנאים חזרו — ההשגחה הוסרה",
        "reserved_seat": "קיבלה עדיפות-תור (מושב שמור)",
        "priority": "נכנסה לבדיקת-עומק",
        "queue_full": "מוכנה אבל אין מקום בעומק — ממתינה",
        "structural_confirmed": "המבנה אושר (נסיגה+חזרה שהחזיקה)",
        "risk_flag": "אזהרת-עייפות פעילה — בלי קניות",
        "decision_blocked": "ההחלטה נחסמה (ראה פירוט)",
    }
    _INTERNAL = ("admin_repair", "migration_over_cap", "epoch_cutover",
                 "link_added", "re_entered_after_exit", "data_hold_start",
                 "data_hold_resolved")
    if ev:
        vis = [e for e in ev if e.get("reason_code") not in _INTERNAL]
        tech = [e for e in ev if e.get("reason_code") in _INTERNAL]
        with st.expander(f"🧾 מה קרה הלילה, שורה-שורה ({len(vis)})"):
            for e in vis:
                he = _CODE_HE.get(str(e.get("reason_code")), e.get("reason_code"))
                st.caption(f"**{e.get('ticker') or '(כלל-מערכת)'}** · {he}  \n"
                           f"<span style='opacity:.55;font-size:.8em'>"
                           f"{str(e.get('detail'))[:110]}</span>",
                           unsafe_allow_html=True)
            if tech:
                st.caption(f"🛠 +{len(tech)} רישומים טכניים (תחזוקה פנימית) — "
                           "ביומן-המערכת, לא רלוונטיים להחלטות")


_TH_HE = {"DORMANT": "🛌 רדומה", "WARMING": "🌡️ מתחממת", "AWAKE": "🚨 ערה"}

_BEHAV_HE = {"CROWDED_SHORT": "🩳 שורט צפוף", "EXTREME_SHORT_INTEREST": "🧨 שורט קיצוני",
             "SQUEEZE_PRESSURE_BUILDING": "🔥 לחץ-סקוויז", "ACTIVE_SQUEEZE": "🚀 סקוויז פעיל",
             "SQUEEZE_EXHAUSTION": "🎇 סקוויז מתפוגג",
             "INSIDER_OPEN_MARKET_CLUSTER": "👔 קניות-פנים",
             "RETAIL_CHASE_INTO_STRENGTH": "🎪 רדיפת-ריטייל"}


def _thesis_action(investigation_id: str, action: str) -> None:
    """The owner's judgment on a RESEARCH thesis (the standing method, 16.07):
    approve -> the engine decomposes it into validated baskets and lands it in
    theses.json (DORMANT; wake gates decide activation). Idempotent notes."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = json.dumps({"investigation_id": investigation_id, "action": action,
                          "at": now, "by": "owner (board)"}, ensure_ascii=False)
    with _engine().begin() as c:
        c.execute(text(
            'insert into research_notes (id, date, kind, title, content) '
            'values (:i, :d, :k, :t, :c) on conflict (id) do nothing'),
            {"i": f"thesis_action:{investigation_id}:{now}",
             "d": date.today().isoformat(), "k": "thesis_action",
             "t": f"Thesis research {action} — {investigation_id}", "c": payload})
    _notes_of.clear()


def _research_theses_card() -> None:
    """Graded research theses (median-of-3 minus 1) — only 8+ reach this card."""
    tr = _latest_note("thesis_research")
    if not tr:
        return
    pend = [r for r in tr.get("results") or [] if r.get("escalated")]
    low = [r for r in tr.get("results") or [] if not r.get("escalated")]
    if pend:
        st.markdown("#### 🔬 תזות-מחקר בדירוג 8+ — ממתינות לשיפוטך")
        for r in pend:
            d0 = r.get("draft") or {}
            iid = str(r.get("investigation_id"))
            st.markdown(
                f'<div class="papow-card"><span class="tkr">{d0.get("title_he")}'
                f'</span> <span class="papow-chip gold">דירוג {r.get("final_grade")}'
                f' (חציון {r.get("grades")} −1)</span>'
                f'<div class="sub">מנגנון: {d0.get("mechanism_he")}</div>'
                f'<div class="sub">אישוש: {d0.get("confirmation_he")} · '
                f'הפרכה: {d0.get("refutation_he")}</div>'
                f'<div class="sub">תרחיש-נגד: {d0.get("counter_he")} · מניות: '
                f'{", ".join(r.get("tickers") or [])}</div></div>',
                unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            if c1.button("✅ אשר — פרק לרשימות", key=f"tr_ok_{iid}"):
                _thesis_action(iid, "approve")
                st.success("אושר — הפירוק לסלים (Perplexity) + ולידציית-Massive ירוצו בלילה")
            if c2.button("🔥 אשר כרשימה חמה", key=f"tr_hot_{iid}"):
                _thesis_action(iid, "approve_hot")
                st.success("אושר כ-🔥 — הרשימה תוכל למלא את מלוא הקיבולת ב-VIP")
            if c3.button("⛔ דחה", key=f"tr_no_{iid}"):
                _thesis_action(iid, "reject")
                st.info("נדחה — החקירה תיסגר")
    if low:
        st.caption("🔬 תזות-מחקר מתחת לרף-8 (נשארות ברשומה): "
                   + " · ".join(f"{(r.get('draft') or {}).get('title_he', '?')} "
                                f"({r.get('final_grade')})" for r in low))
    es = _latest_note("early_signals") or {}
    if es.get("fired") or es.get("pilot"):
        pl = es.get("pilot") or {}
        with st.expander(f"🌱 אותות-מוקדמים (פיילוט-SHADOW) — "
                         f"{len(es.get('fired') or [])} זיהויים · "
                         f"ריצות: {pl.get('runs', 0)}"):
            st.caption("גילוי-מוקדם: אותות חלשים/חוזרים שמצטברים לפני מהלך. "
                       "לעולם לא תובע VIP — רק סיטואציה/חקירה/תצפית. "
                       f"מדד-ראשי: רווח-זמן מול הזיהוי הישן "
                       f"(חציון: {pl.get('median_lead_time_gain', '—')}).")
            for f in (es.get("fired") or [])[:8]:
                st.caption(f"**{f.get('key')}** · משפחות: "
                           f"{', '.join((f.get('families') or {}))} · "
                           f"{f.get('routed_to')}"
                           + (f" → {f.get('routing_id')}"
                              if f.get("routing_id") else ""))


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
        if s.get("hot"):
            bits.append("🔥 רשימה-חמה (קיבולת מלאה ב-VIP)")
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


def _nuclei_tab() -> None:
    """🧬 the nucleus screen — the owner's model: a trade idea is a NUCLEUS that a
    group of stocks orbits; when the idea starts expressing in the group's actual
    movement, it has matured and its strongest names go to VIP for examination.
    Written for a reader who knows NONE of the system's jargon."""
    st.markdown("### 🧬 גרעיני-מסחר — הרעיונות שמאחורי קבוצות של מניות")
    st.caption("כל כרטיס כאן הוא **רעיון אחד** (\"גרעין\") וסביבו סל-מניות שזז יחד "
               "בגללו. כשהרעיון מתחיל להתבטא בתנועה אמיתית של הסל — הוא \"מתעורר\", "
               "והמניות החזקות בו נשלחות לבדיקת-עומק (VIP). "
               "שום דבר כאן לא קונה לבד — הכל המלצת-מעקב.")
    # -- decisions that belong to nuclei: new researched theses awaiting the owner
    _research_theses_card()
    # -- the factory funnel: where NEW nuclei come from, one line, plain words
    tr = _latest_note("thesis_research") or {}
    vb = _latest_note("vip_board") or {}
    fx = (vb.get("funnels") or {}).get("context_discovery") or {}
    n_orph = len(fx.get("orphaned_high_readiness") or [])
    n_obs = len(fx.get("discovery_observations") or [])
    queue = tr.get("queue") or []
    n_open = sum(1 for i in queue if i.get("status") == "OPEN")
    n_wait = sum(1 for r in tr.get("results") or []
                 if r.get("escalated")
                 and str(r.get("owner_decision") or "PENDING") == "PENDING")
    st.markdown("#### 🏭 מאיפה מגיע גרעין חדש")
    st.info(f"מניות חזקות בלי רעיון שמסביר אותן: **{n_orph + n_obs}** ← "
            f"קבוצות שנחקרות עכשיו: **{n_open}** ← "
            f"רעיונות שקיבלו ציון גבוה ומחכים לאישורך: **{n_wait}**")
    st.caption("המערכת אוספת כל לילה מניות שעברו את ספי-המסחר אבל אף רעיון קיים לא "
               "מסביר אותן; כשכמה כאלה זזות יחד — נפתחת חקירה; חקירה שמנוסחת לרעיון "
               "משכנע (ציון 8 ומעלה אחרי הנחת-ספק) מגיעה אליך לאישור. אישרת — נולד "
               "גרעין חדש עם סל-מעקב, והוא מופיע למטה.")
    if queue:
        with st.expander(f"🔎 מה נחקר עכשיו ({n_open} חקירות פתוחות)"):
            _q_he2 = {"OPEN": "🔎 בחקירה", "RESEARCHED": "📄 נוסחה — מתחת לציון",
                      "PARKED_SIGNAL_WATCH": "⏸️ בהמתנה (3 ניסיונות לא צלחו)",
                      "PROMOTED_TO_THESIS": "✅ הפכה לגרעין", "CLOSED": "⚫ נסגרה"}
            for i in queue:
                st.caption(f"{_q_he2.get(str(i.get('status')), i.get('status'))} · "
                           f"**{i.get('cluster_key')}** "
                           f"[{', '.join((i.get('tickers') or [])[:6])}]"
                           + (f" · ציון אחרון {i.get('final_grade')}"
                              if i.get("final_grade") is not None else ""))
                if i.get("question"):
                    st.caption(f"    ❓ {i['question']}")
    # -- the nucleus cards themselves
    tw = _latest_note("thesis_watch")
    if not tw:
        st.info("אין עדיין סריקת-גרעינים — הריצה הלילית תייצר אותה.")
        return
    st.markdown("#### הגרעינים הפעילים")
    members = {str(m.get("ticker")): m for m in (vb.get("members") or [])}
    _wake_he = {"DORMANT": ("🛌 רדום", "התנועה בסל עדיין לא מאשרת את הרעיון — מעקב בלבד"),
                "WARMING": ("🌡️ מתחמם", "חלק מהתנאים כבר מתקיימים — מתקרב"),
                "AWAKE": ("🚨 ער", "הרעיון מתבטא בתנועה אמיתית — המניות החזקות "
                                   "נשלחות לבדיקת-עומק")}
    _wake_risk = {"DORMANT": ("🛌 רדום", "האזהרה לא פעילה — מעקב בלבד"),
                  "WARMING": ("🌡️ מתחמם", "סימני-האזהרה מצטברים"),
                  "AWAKE": ("🛡️ אזהרה פעילה", "הרעיון מתממש בירידה — תפקידו "
                                              "לחסום קניות, לא להציע אותן")}
    scans = sorted(tw.get("scans") or [],
                   key=lambda x: {"AWAKE": 0, "WARMING": 1}.get(
                       str(x.get("status")), 2))
    for sc in scans:
        stt = str(sc.get("status"))
        is_risk = sc.get("mode") == "risk"
        icon, expl = (_wake_risk if is_risk else _wake_he).get(stt, (stt, ""))
        core = sc.get("core") or {}
        ew = core.get("ew_20d")
        rs = core.get("rs_share")
        locos = sc.get("locomotives") or []
        in_vip = [(t, members.get(t)) for t in locos if members.get(t)]
        hot = " 🔥" if sc.get("hot") else ""
        risk = ""
        pulse = []
        if ew is not None:
            pulse.append(f"הסל זז {ew:+.1f}% בחודש-מסחר")
        if rs is not None:
            pulse.append(f"{int(rs * 100)}% מהמניות חזקות מהשוק")
        vip_ln = ""
        if in_vip:
            vip_ln = " · ".join(
                f"**{t}** בבדיקת-עומק ({_STAGE_HE.get(str((m or {}).get('status')), '')})"
                for t, m in in_vip)
        elif locos and stt == "AWAKE":
            vip_ln = "המובילות: " + ", ".join(locos)
        basket = [str(r.get("ticker")) for r in sc.get("core_rows") or []]
        news = sc.get("qual_today") or []
        silent = sc.get("days_since_news")
        news_ln = (f"📰 כותרת אחרונה שנוגעת לרעיון: לפני "
                   f"{silent} ימים" if silent is not None and silent > 0
                   else "📰 יש כותרות טריות שנוגעות לרעיון" if news else "")
        st.markdown(
            f'<div class="papow-card"><span class="tkr">{sc.get("title_he")}</span>'
            f'{hot} <span class="papow-stage">{icon}</span>'
            f'<div class="sub">{str(sc.get("narrative_he") or "")[:150]}{risk}</div>'
            + (f'<div class="sub">🧺 הסל: {", ".join(basket[:8])}</div>'
               if basket else "")
            + f'<div class="sub">{expl}' + (" · " + " · ".join(pulse) if pulse else "")
            + '</div>'
            + (f'<div class="sub">👑 {vip_ln}</div>' if vip_ln else "")
            + (f'<div class="sub">{news_ln}</div>' if news_ln else "")
            + '</div>', unsafe_allow_html=True)
    st.caption("💡 רעיונות-ניסוי (פרשנויות מתחרות שנמדדות זו מול זו) נמצאים "
               "בלשונית \"רעיונות\" — כשרעיון-ניסוי מוכיח את עצמו הוא הופך לגרעין.")


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
    ar = _latest_note("dossier_arena") or {}
    if ar.get("pairs_total"):
        st.markdown("#### 🪪 זירת תיק-הזהות — האם ההקשר משפר את השיפוט?")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("זוגות (עם/בלי)", ar.get("pairs_total", 0))
        c2.metric("נמדדו מול הטייפ", ar.get("pairs_graded", 0))
        c3.metric("ימי-מחלוקת", ar.get("pairs_diverged", 0))
        c4.metric("רצפת-פסיקה",
                  "✅ הושגה" if ar.get("verdict_floor_met") else "⏳ נבנית")
        if ar.get("official_hit_5s") is not None:
            st.caption(f"פגיעה-5ס: עם-תיק {ar.get('official_hit_5s')} מול "
                       f"בלי-תיק {ar.get('control_hit_5s')}"
                       + (f" · בימי-מחלוקת בלבד: עם {ar.get('diverged_official_hit_5s')}"
                          f" מול בלי {ar.get('diverged_control_hit_5s')}"
                          if ar.get("diverged_official_hit_5s") is not None else ""))
        st.caption(str(ar.get("note_he") or ""))
        st.divider()
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


def _decision_strip() -> None:
    """🎯 the ONE strip the owner reads first (17.07 UX): everything that awaits
    HIS judgment, aggregated across tabs — the operator-system contract."""
    items: list[str] = []
    fyi: list[str] = []
    try:
        tr = _latest_note("thesis_research") or {}
        n_th = sum(1 for r in tr.get("results") or []
                   if r.get("escalated")
                   and str(r.get("owner_decision") or "PENDING") == "PENDING")
        if n_th:
            items.append(f"🧪 {n_th} רעיונות-מחקר בציון גבוה — לאשר/לדחות "
                         "בלשונית «🧬 גרעינים»")
        n_open = sum(1 for i in tr.get("queue") or [] if i.get("status") == "OPEN")
        if n_open:
            fyi.append(f"🔎 {n_open} חקירות רצות ברקע (אין פעולה שלך)")
        ib = _latest_note("idea_board") or {}
        n_cards = sum(1 for i in ib.get("ideas") or []
                      if str(i.get("status")) in ("DRAFT", "PENDING_APPROVAL"))
        if n_cards:
            items.append(f"💡 {n_cards} רעיונות עם כפתור אשר/דחה — "
                         "לשונית «💡 רעיונות»")
        vb = _latest_note("vip_board") or {}
        fx = (vb.get("funnels") or {}).get("context_discovery") or {}
        if fx.get("direct_vip_entries"):
            items.append(f"🚨 {fx['direct_vip_entries']} הפרות-סמכות!")
        n_appr = len(vb.get("decisions") or [])
        if n_appr:
            items.append(f"💥 {n_appr} החלטות-VIP הלילה (טאב-VIP)")
    except Exception:                                     # noqa: BLE001 — strip is additive
        return
    _so = _fresh_note("sentinel_ops") or {}
    if (_so.get("date") == date.today().isoformat()
            and _so.get("alerts_today")):
        _last3 = list(_so["alerts_today"])[-3:]
        st.error("🛰️ **התראות-היום מהשומר:** "
                 + " · ".join(f"{a.get('time')}Z {a.get('level')} {a.get('he')}"
                              for a in reversed(_last3))
                 + (f" (+{len(_so['alerts_today']) - 3} נוספות בלשונית «🚦 מפעיל»)"
                    if len(_so["alerts_today"]) > 3 else ""))
    if items:
        st.info("🎯 **מחכה להחלטה שלך (יש כפתור):** " + " · ".join(items)
                + (("  \n🛰️ " + " · ".join(fyi)) if fyi else ""))
    else:
        st.caption("🎯 שום דבר לא מחכה להחלטה שלך כרגע"
                   + (" · " + " · ".join(fyi) if fyi else "")
                   + " — המערכת תעצור רק כשתצטרך להכריע.")


def main() -> None:
    _gate()
    _hero()
    _ribbon()
    _decision_strip()
    # order = the owner's working process (RTL: first renders rightmost): the deal
    # manager and VIP first, the entry queue beside them, context next, ops last.
    tabs = st.tabs(["💼 עסקאות", "👑 VIP", "🚪 תור-VIP", "🧬 גרעינים",
                    "💡 רעיונות", "🦅 הובלה",
                    "📡 רשימות", "🚦 מפעיל", "🛠 שיפורים", "📖 אוזבקי"])
    with tabs[0]:
        _slots_tab()
    with tabs[1]:
        _vip_tab()
    with tabs[2]:
        _vip_queue_tab()
    with tabs[3]:
        _nuclei_tab()
    with tabs[4]:
        _ideas_tab()
    with tabs[5]:
        _leadership_tab()
    with tabs[6]:
        _watchlists_tab()
    with tabs[7]:
        _operator_tab()
    with tabs[8]:
        _improvement_tab()
    with tabs[9]:
        _ozbeki_tab()
    _footer()


main()
