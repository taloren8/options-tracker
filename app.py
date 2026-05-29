import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime, date
import anthropic

st.set_page_config(page_title="Options Tracker", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.main{background-color:#0e1117}
.metric-card{background:#1e2130;border-radius:12px;padding:1.2rem 1.5rem;border:1px solid #2d3247;margin-bottom:.5rem}
.metric-label{color:#8b8fa8;font-size:13px;margin-bottom:4px}
.metric-value{color:#fff;font-size:26px;font-weight:600}
.metric-sub{font-size:13px;margin-top:2px}
.green{color:#22c55e}.red{color:#ef4444}.yellow{color:#f59e0b}
.stButton>button{background:#3b82f6;color:white;border:none;border-radius:8px;padding:.5rem 1.5rem;font-weight:500;width:100%}
.stButton>button:hover{background:#2563eb}
.warning-box{background:#422006;border:1px solid #92400e;border-radius:8px;padding:.75rem 1rem;color:#fcd34d;font-size:14px;margin-bottom:1rem}
.info-box{background:#1e3a5f;border:1px solid #1d4ed8;border-radius:8px;padding:.75rem 1rem;color:#93c5fd;font-size:14px;margin-bottom:1rem}
.analysis-box{background:#1a1f35;border:1px solid #3b82f6;border-radius:12px;padding:1.25rem 1.5rem;margin-top:1rem;font-size:14px;color:#e2e8f0;line-height:1.7}
.analysis-title{color:#60a5fa;font-weight:600;margin-bottom:.75rem;font-size:15px}
.verdict-go{background:#14532d;border:1px solid #16a34a;border-radius:8px;padding:.75rem 1rem;color:#86efac;font-weight:600;font-size:15px;margin-bottom:.75rem}
.verdict-nogo{background:#450a0a;border:1px solid #dc2626;border-radius:8px;padding:.75rem 1rem;color:#fca5a5;font-weight:600;font-size:15px;margin-bottom:.75rem}
.verdict-caution{background:#422006;border:1px solid #d97706;border-radius:8px;padding:.75rem 1rem;color:#fcd34d;font-weight:600;font-size:15px;margin-bottom:.75rem}
.claude-box{background:#1a1f35;border:1px solid #3b82f6;border-radius:10px;padding:1rem 1.2rem;margin-top:1rem;font-size:14px;color:#e2e8f0;line-height:1.6}
.claude-title{color:#60a5fa;font-weight:600;margin-bottom:.5rem;font-size:13px;text-transform:uppercase;letter-spacing:.05em}
div[data-testid="stExpander"]{border:1px solid #2d3247;border-radius:8px;background:#1e2130}
</style>
""", unsafe_allow_html=True)

# ── Google Sheets ──────────────────────────────────────────────────────────────
SHEET_NAME = "Options Tracker"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"שגיאת חיבור: {e}"); return None

def get_or_create_sheet(client):
    try: sh = client.open(SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        sh = client.create(SHEET_NAME)
        sh.share(None, perm_type='anyone', role='writer')
    try: ws = sh.worksheet("Trades")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet("Trades", 1000, 20)
        ws.append_row(["ID","Date","Ticker","Type","Strike","Expiry","Contracts","Premium",
                        "Stop Loss","TP1","TP2","Catalyst","Trade Type","Max Days",
                        "Exit Price","Exit Date","Status","P&L $","P&L %","Notes"])
    return sh, ws

def load_trades(ws):
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame()

def save_trade(ws, t):
    ws.append_row([t["id"],t["date"],t["ticker"],t["type"],t["strike"],t["expiry"],
                   t["contracts"],t["premium"],t["stop_loss"],t["tp1"],t["tp2"],
                   t["catalyst"],t["trade_type"],t.get("max_days",""),"","","פתוח","","",""])

def update_trade_exit(ws, trade_id, exit_price, exit_date, status, pnl_d, pnl_p, notes=""):
    data = ws.get_all_values()
    for i, row in enumerate(data[1:], start=2):
        if str(row[0]) == str(trade_id):
            ws.update(f"O{i}:T{i}", [[exit_price, exit_date, status, pnl_d, pnl_p, notes]]); break

# ── Calculations ───────────────────────────────────────────────────────────────
def calc_levels(premium, contracts=1):
    return round(premium*.5,2), round(premium*1.6,2), round(premium*2.0,2), premium*contracts

def days_to_expiry(expiry_str):
    try: return (datetime.strptime(str(expiry_str),"%Y-%m-%d").date() - date.today()).days
    except: return None

# ── AI Analysis ────────────────────────────────────────────────────────────────
def analyze_trade(ticker, option_type, strike, expiry, premium, contracts, catalyst):
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY","")
        if not api_key:
            return None, "לא נמצא ANTHROPIC_API_KEY ב-secrets"
        ai = anthropic.Anthropic(api_key=api_key)
        dte = days_to_expiry(expiry)
        sl, tp1, tp2, total = calc_levels(premium, contracts)
        breakeven = strike + premium/100 if option_type=="Call" else strike - premium/100

        prompt = f"""אתה אנליסט options מקצועי. נתח את הטרייד הבא בעברית — ישיר, קצר, מבוסס עובדות.

טרייד: {ticker} {option_type} ${strike} | פקיעה {expiry} ({dte} ימים) | פרמיה ${premium} x{contracts}
SL: ${sl} | TP1: ${tp1} | TP2: ${tp2} | נקודת איזון: ~${breakeven:.2f}
קטליסט שצוין: {catalyst or 'לא צוין'}

**1. ניתוח טכני** (3-4 שורות)
מגמה, מומנטום, תמיכה/התנגדות קרובות, האם המניה קרובה לסטרייק.

**2. קטליסטים** (2-3 שורות)
Earnings קרובים? חדשות אחרונות? משהו שיזיז את {ticker} תוך {dte} ימים?

**3. המלצה** (חד וברור — בחר אחת):
✅ כדאי להיכנס — [סיבה]
⚠️ כניסה בזהירות — [סיבה]
🚫 לא כדאי להיכנס — [סיבה]

**4. סיכון עיקרי** (שורה אחת)
מה הדבר שיכול להרוג את הטרייד?"""

        resp = ai.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=1000,
            tools=[{"type":"web_search_20250305","name":"web_search"}],
            messages=[{"role":"user","content":prompt}]
        )
        text = "".join(b.text for b in resp.content if hasattr(b,"text"))
        return text, None
    except Exception as e:
        return None, str(e)

def extract_verdict(text):
    if not text: return "pending"
    if "✅" in text and "זהירות" not in (text.split("✅")[1][:40] if "✅" in text else ""): return "go"
    if "⚠️" in text: return "caution"
    if "🚫" in text: return "nogo"
    return "pending"

def dashboard_summary(df_open, df_closed):
    lines = []
    if not df_open.empty:
        lines.append(f"יש לך {len(df_open)} פוזיציות פתוחות.")
        for _, r in df_open.iterrows():
            dte = days_to_expiry(str(r.get("Expiry","")))
            if dte is not None and dte <= 3: lines.append(f"⚠️ {r['Ticker']} פוקעת בעוד {dte} ימים!")
            elif dte is not None and dte <= 7: lines.append(f"📅 {r['Ticker']}: {dte} ימים לפקיעה.")
    if not df_closed.empty:
        try:
            df_closed["P&L $"] = pd.to_numeric(df_closed["P&L $"],errors="coerce").fillna(0)
            w = len(df_closed[df_closed["Status"]=="רווח"])
            l = len(df_closed[df_closed["Status"]=="הפסד"])
            wr = w/(w+l)*100 if (w+l)>0 else 0
            lines.append(f"אחוז הצלחה: {wr:.0f}% ({w}W/{l}L)")
        except: pass
    return "\n".join(lines) if lines else "אין נתונים עדיין — הזן את הטרייד הראשון שלך."

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Options Tracker")
    st.markdown("---")
    page = st.radio("ניווט", ["🏠 דשבורד","➕ טרייד חדש","🔍 נתח טרייד",
                               "📋 פוזיציות פתוחות","✅ סגור טרייד","📈 היסטוריה","📋 העתק לקלוד"],
                    label_visibility="collapsed")
    st.markdown("---")
    st.markdown("<div style='font-size:12px;color:#8b8fa8;'>💡 <b>כלל הבית:</b><br>• מקסימום 10% הון לטרייד<br>• SL = 50% מהפרמיה<br>• מקסימום 3 פוזיציות<br>• לא מ-FOMO</div>", unsafe_allow_html=True)

# ── Connect ────────────────────────────────────────────────────────────────────
client = get_gsheet_client()
if not client: st.stop()
sh, ws = get_or_create_sheet(client)
df_all = load_trades(ws)
df_open   = df_all[df_all["Status"]=="פתוח"].copy()   if not df_all.empty else pd.DataFrame()
df_closed = df_all[df_all["Status"].isin(["רווח","הפסד","פג תוקף"])].copy() if not df_all.empty else pd.DataFrame()

# ══ DASHBOARD ══════════════════════════════════════════════════════════════════
if page == "🏠 דשבורד":
    st.markdown("## דשבורד")
    if not df_open.empty:
        for _, r in df_open.iterrows():
            dte = days_to_expiry(str(r.get("Expiry","")))
            if dte is not None and dte <= 3:
                st.markdown(f"<div class='warning-box'>⚠️ <b>{r['Ticker']}</b> פוקעת בעוד <b>{dte} ימים</b>! שקול יציאה.</div>", unsafe_allow_html=True)

    invested = pnl = wins = losses = 0
    if not df_closed.empty:
        try:
            df_closed["P&L $"] = pd.to_numeric(df_closed["P&L $"],errors="coerce").fillna(0)
            pnl   = df_closed["P&L $"].sum()
            wins  = len(df_closed[df_closed["Status"]=="רווח"])
            losses= len(df_closed[df_closed["Status"]=="הפסד"])
        except: pass
    if not df_open.empty:
        try:
            df_open["Premium"]  = pd.to_numeric(df_open["Premium"],errors="coerce").fillna(0)
            df_open["Contracts"]= pd.to_numeric(df_open["Contracts"],errors="coerce").fillna(1)
            invested = (df_open["Premium"]*df_open["Contracts"]).sum()
        except: pass

    wr = wins/(wins+losses)*100 if (wins+losses)>0 else 0
    c1,c2,c3,c4 = st.columns(4)
    with c1: st.markdown(f"<div class='metric-card'><div class='metric-label'>פוזיציות פתוחות</div><div class='metric-value'>{len(df_open)}</div><div class='metric-sub' style='color:#8b8fa8'>מקסימום: 3</div></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='metric-card'><div class='metric-label'>הון מושקע</div><div class='metric-value'>${invested:,.0f}</div></div>", unsafe_allow_html=True)
    with c3:
        pc = "green" if pnl>=0 else "red"; ps = "+" if pnl>=0 else ""
        st.markdown(f"<div class='metric-card'><div class='metric-label'>P&L סגור</div><div class='metric-value {pc}'>{ps}${pnl:,.0f}</div></div>", unsafe_allow_html=True)
    with c4:
        wc = "green" if wr>=50 else "red"
        st.markdown(f"<div class='metric-card'><div class='metric-label'>אחוז הצלחה</div><div class='metric-value {wc}'>{wr:.0f}%</div><div class='metric-sub' style='color:#8b8fa8'>{wins}W/{losses}L</div></div>", unsafe_allow_html=True)

    st.markdown("### פוזיציות פתוחות")
    if df_open.empty: st.info("אין פוזיציות פתוחות.")
    else:
        for _, r in df_open.iterrows():
            dte = days_to_expiry(str(r.get("Expiry","")))
            icon = "🔴" if dte and dte<=3 else ("🟡" if dte and dte<=7 else "🟢")
            with st.expander(f"{icon} {r['Ticker']} | {r['Type']} ${r['Strike']} | פקיעה: {r['Expiry']} | {dte or '?'} ימים"):
                cc1,cc2,cc3,cc4 = st.columns(4)
                cc1.metric("פרמיה",f"${r.get('Premium','?')}"); cc2.metric("חוזים",r.get("Contracts","?"))
                cc3.metric("SL",f"${r.get('Stop Loss','?')}");   cc4.metric("TP1",f"${r.get('TP1','?')}")

    summ = dashboard_summary(df_open, df_closed)
    st.markdown(f"<div class='claude-box'><div class='claude-title'>📍 סיכום לקלוד</div>{summ.replace(chr(10),'<br>')}</div>", unsafe_allow_html=True)

# ══ NEW TRADE ══════════════════════════════════════════════════════════════════
elif page == "➕ טרייד חדש":
    st.markdown("## ➕ טרייד חדש")
    if len(df_open)>=3:
        st.markdown("<div class='warning-box'>⚠️ כבר 3 פוזיציות פתוחות — שקול לסגור אחת לפני כניסה חדשה.</div>", unsafe_allow_html=True)

    with st.form("new_trade", clear_on_submit=True):
        c1,c2,c3 = st.columns(3)
        with c1: ticker = st.text_input("טיקר", placeholder="NVDA").upper().strip()
        with c2: otype  = st.selectbox("סוג",["Call","Put"])
        with c3: strike = st.number_input("סטרייק ($)",min_value=0.0,step=0.5)
        c4,c5,c6 = st.columns(3)
        with c4: expiry    = st.date_input("פקיעה",min_value=date.today())
        with c5: contracts = st.number_input("חוזים",min_value=1,max_value=10,value=1)
        with c6: premium   = st.number_input("פרמיה ($)",min_value=0.0,step=5.0)

        if premium>0:
            sl,tp1,tp2,total = calc_levels(premium,contracts)
            dte = (expiry-date.today()).days
            st.markdown("---")
            st.markdown("**יעדי יציאה — אוטומטי:**")
            lc1,lc2,lc3,lc4 = st.columns(4)
            lc1.metric("השקעה כוללת",f"${total:.0f}"); lc2.metric("🔴 SL",f"${sl:.0f}")
            lc3.metric("🟢 TP1",f"${tp1:.0f}");        lc4.metric("🎯 TP2",f"${tp2:.0f}")
            if dte<=7: st.markdown(f"<div class='warning-box'>⏰ {dte} ימים לפקיעה — Theta גבוה!</div>", unsafe_allow_html=True)

        st.markdown("---")
        c7,c8 = st.columns(2)
        with c7: ttype    = st.selectbox("סוג טרייד",["יומי","מולטי-יום"])
        with c8: max_days = st.number_input("מקסימום ימים",min_value=1,max_value=30,value=3) if ttype=="מולטי-יום" else 1
        catalyst = st.text_input("קטליסט",placeholder="earnings, breakout, המלצת קהילה")

        st.markdown("---")
        st.markdown("**✅ צ'קליסט חובה:**")
        ok = all([
            st.checkbox("יש קטליסט ברור"),
            st.checkbox("אין אירוע מאקרו היום"),
            st.checkbox("לא יותר מ-3 פוזיציות"),
            st.checkbox("פרמיה לא עולה על 10% מהון"),
            st.checkbox("לא נכנס מ-FOMO")
        ])
        if not ok: st.markdown("<div class='warning-box'>🚫 לא כל כללי החובה עברו.</div>", unsafe_allow_html=True)

        if st.form_submit_button("💾 שמור טרייד"):
            if not ticker or strike==0 or premium==0:
                st.error("מלא: טיקר, סטרייק, פרמיה")
            else:
                sl,tp1,tp2,_ = calc_levels(premium,contracts)
                save_trade(ws,{"id":int(datetime.now().timestamp()),"date":date.today().strftime("%Y-%m-%d"),
                    "ticker":ticker,"type":otype,"strike":strike,"expiry":expiry.strftime("%Y-%m-%d"),
                    "contracts":contracts,"premium":premium,"stop_loss":sl,"tp1":tp1,"tp2":tp2,
                    "catalyst":catalyst,"trade_type":ttype,"max_days":max_days if ttype=="מולטי-יום" else ""})
                st.success(f"✅ נשמר! SL:${sl} | TP1:${tp1} | TP2:${tp2}")
                st.info("💡 לך ל-'🔍 נתח טרייד' לניתוח AI מלא.")
                st.cache_resource.clear()

# ══ ANALYZE TRADE ══════════════════════════════════════════════════════════════
elif page == "🔍 נתח טרייד":
    st.markdown("## 🔍 ניתוח טרייד עם AI")
    st.markdown("<div class='info-box'>🤖 קלוד מחפש בזמן אמת — טכני + קטליסטים + המלצה ברורה.</div>", unsafe_allow_html=True)

    mode = st.radio("מה לנתח?",["טרייד שהזנתי","טרייד חדש (לפני כניסה)"],horizontal=True)

    if mode=="טרייד שהזנתי" and not df_open.empty:
        opts = {f"{r['Ticker']} | {r['Type']} ${r['Strike']} | {r['Expiry']}": idx for idx,r in df_open.iterrows()}
        sel  = st.selectbox("בחר פוזיציה",list(opts.keys()))
        row  = df_open.loc[opts[sel]]
        ticker=str(row["Ticker"]); otype=str(row["Type"]); strike=float(row["Strike"])
        expiry=str(row["Expiry"]); premium=float(row["Premium"]); contracts=int(row["Contracts"])
        catalyst=str(row.get("Catalyst",""))
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("טיקר",ticker); c2.metric("סטרייק",f"${strike}")
        c3.metric("פקיעה",expiry); c4.metric("ימים",days_to_expiry(expiry) or "?")
    else:
        c1,c2,c3 = st.columns(3)
        with c1: ticker    = st.text_input("טיקר",placeholder="NVDA").upper().strip()
        with c2: otype     = st.selectbox("סוג",["Call","Put"])
        with c3: strike    = st.number_input("סטרייק ($)",min_value=0.0,step=0.5)
        c4,c5,c6 = st.columns(3)
        with c4: expiry    = str(st.date_input("פקיעה",min_value=date.today()))
        with c5: contracts = st.number_input("חוזים",min_value=1,max_value=10,value=1)
        with c6: premium   = st.number_input("פרמיה ($)",min_value=0.0,step=5.0)
        catalyst = st.text_input("קטליסט (אופציונלי)")

    st.markdown("---")
    if st.button("🔍 נתח עכשיו", type="primary"):
        if not ticker or strike==0 or premium==0:
            st.error("מלא טיקר, סטרייק ופרמיה")
        else:
            with st.spinner(f"מחפש מידע על {ticker} ומנתח..."):
                analysis, err = analyze_trade(ticker,otype,strike,expiry,premium,contracts,catalyst)
            if err:
                st.error(f"שגיאה: {err}")
                if "ANTHROPIC_API_KEY" in err:
                    st.markdown("<div class='warning-box'>💡 הוסף ANTHROPIC_API_KEY ל-Streamlit Secrets.</div>", unsafe_allow_html=True)
            elif analysis:
                v = extract_verdict(analysis)
                if v=="go":      st.markdown("<div class='verdict-go'>✅ המלצה: כדאי להיכנס</div>", unsafe_allow_html=True)
                elif v=="caution":st.markdown("<div class='verdict-caution'>⚠️ המלצה: כניסה בזהירות</div>", unsafe_allow_html=True)
                elif v=="nogo":  st.markdown("<div class='verdict-nogo'>🚫 המלצה: לא כדאי להיכנס</div>", unsafe_allow_html=True)

                st.markdown(f"<div class='analysis-box'><div class='analysis-title'>🤖 ניתוח AI — {ticker} {otype} ${strike}</div>{analysis.replace(chr(10),'<br>')}</div>", unsafe_allow_html=True)

                sl,tp1,tp2,_ = calc_levels(premium,contracts)
                copy_text = f"ניתחתי {ticker} {otype} ${strike} פקיעה {expiry}:\n\n{analysis}\n\nפרמיה: ${premium} | SL: ${sl} | TP1: ${tp1} | TP2: ${tp2}\nמשהו שפספסתי?"
                st.text_area("📋 העתק לקלוד:", copy_text, height=180)

# ══ OPEN POSITIONS ═════════════════════════════════════════════════════════════
elif page == "📋 פוזיציות פתוחות":
    st.markdown("## 📋 פוזיציות פתוחות")
    if df_open.empty: st.info("אין פוזיציות פתוחות.")
    else:
        cols = ["Ticker","Type","Strike","Expiry","Contracts","Premium","Stop Loss","TP1","TP2","Catalyst","Date"]
        st.dataframe(df_open[[c for c in cols if c in df_open.columns]], use_container_width=True, hide_index=True)

# ══ CLOSE TRADE ════════════════════════════════════════════════════════════════
elif page == "✅ סגור טרייד":
    st.markdown("## ✅ סגור טרייד")
    if df_open.empty: st.info("אין פוזיציות פתוחות.")
    else:
        opts     = {f"{r['Ticker']} | {r['Type']} ${r['Strike']} | {r['Expiry']}": r["ID"] for _,r in df_open.iterrows()}
        sel      = st.selectbox("בחר פוזיציה",list(opts.keys()))
        tid      = opts[sel]
        trow     = df_open[df_open["ID"]==tid].iloc[0]
        ep       = float(trow.get("Premium",0))
        ctrs     = int(trow.get("Contracts",1))
        c1,c2    = st.columns(2)
        with c1: exit_p = st.number_input("מחיר יציאה ($)",min_value=0.0,step=1.0)
        with c2: status = st.selectbox("סטטוס",["רווח","הפסד","פג תוקף"])
        if exit_p>0:
            pnl_d = (exit_p-ep)*ctrs; pnl_p = (exit_p-ep)/ep*100 if ep>0 else 0
            col = "green" if pnl_d>=0 else "red"; s = "+" if pnl_d>=0 else ""
            st.markdown(f"<div class='metric-card'><div class='metric-label'>P&L</div><div class='metric-value {col}'>{s}${pnl_d:.0f} ({s}{pnl_p:.0f}%)</div></div>", unsafe_allow_html=True)
        notes = st.text_area("מה למדתי?",placeholder="FOMO? יצאתי מוקדם? קטליסט לא התממש?")
        if st.button("💾 סגור טרייד"):
            if exit_p==0: st.error("הכנס מחיר יציאה")
            else:
                pnl_d=(exit_p-ep)*ctrs; pnl_p=(exit_p-ep)/ep*100 if ep>0 else 0
                update_trade_exit(ws,tid,exit_p,date.today().strftime("%Y-%m-%d"),status,round(pnl_d,2),round(pnl_p,1),notes)
                st.success("✅ הטרייד נסגר!"); st.cache_resource.clear()

# ══ HISTORY ════════════════════════════════════════════════════════════════════
elif page == "📈 היסטוריה":
    st.markdown("## 📈 היסטוריה וסטטיסטיקות")
    if df_closed.empty: st.info("אין היסטוריה עדיין.")
    else:
        try:
            df_closed["P&L $"] = pd.to_numeric(df_closed["P&L $"],errors="coerce").fillna(0)
            df_closed["P&L %"] = pd.to_numeric(df_closed["P&L %"],errors="coerce").fillna(0)
            wins=df_closed[df_closed["Status"]=="רווח"]; losses=df_closed[df_closed["Status"]=="הפסד"]
            total=len(df_closed); wr=len(wins)/total*100 if total>0 else 0
            avg_w=wins["P&L $"].mean() if len(wins)>0 else 0
            avg_l=losses["P&L $"].mean() if len(losses)>0 else 0
            tot_pnl=df_closed["P&L $"].sum()
            c1,c2,c3,c4=st.columns(4)
            wc="green" if wr>=50 else "red"; pc="green" if tot_pnl>=0 else "red"; ps="+" if tot_pnl>=0 else ""
            with c1: st.markdown(f"<div class='metric-card'><div class='metric-label'>אחוז הצלחה</div><div class='metric-value {wc}'>{wr:.0f}%</div><div class='metric-sub' style='color:#8b8fa8'>{len(wins)}W/{len(losses)}L</div></div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='metric-card'><div class='metric-label'>רווח ממוצע</div><div class='metric-value green'>+${avg_w:.0f}</div></div>", unsafe_allow_html=True)
            with c3: st.markdown(f"<div class='metric-card'><div class='metric-label'>הפסד ממוצע</div><div class='metric-value red'>${avg_l:.0f}</div></div>", unsafe_allow_html=True)
            with c4: st.markdown(f"<div class='metric-card'><div class='metric-label'>P&L כולל</div><div class='metric-value {pc}'>{ps}${tot_pnl:.0f}</div></div>", unsafe_allow_html=True)
            st.markdown("---")
            show=["Date","Ticker","Type","Strike","Expiry","Premium","Exit Price","Status","P&L $","P&L %","Notes"]
            st.dataframe(df_closed[[c for c in show if c in df_closed.columns]],use_container_width=True,hide_index=True)
        except Exception as e: st.error(f"שגיאה: {e}")

# ══ COPY TO CLAUDE ═════════════════════════════════════════════════════════════
elif page == "📋 העתק לקלוד":
    st.markdown("## 📋 העתק לקלוד")
    st.markdown("<div class='info-box'>💡 העתק ושלח לקלוד בתחילת כל שיחה חדשה.</div>", unsafe_allow_html=True)
    lines = [f"**עדכון תיק — {date.today().strftime('%d/%m/%Y')}**\n","**פוזיציות פתוחות:**"]
    if df_open.empty: lines.append("• אין פוזיציות פתוחות")
    else:
        for _,r in df_open.iterrows():
            dte=days_to_expiry(str(r.get("Expiry","")))
            lines.append(f"• {r['Ticker']} {r['Type']} ${r['Strike']} | פקיעה {r['Expiry']} ({dte} ימים) | כניסה:${r['Premium']} | SL:${r.get('Stop Loss','?')} | TP:${r.get('TP1','?')}")
    if not df_closed.empty:
        try:
            df_closed["P&L $"]=pd.to_numeric(df_closed["P&L $"],errors="coerce").fillna(0)
            w=len(df_closed[df_closed["Status"]=="רווח"]); l=len(df_closed[df_closed["Status"]=="הפסד"])
            tp=df_closed["P&L $"].sum(); wr=w/(w+l)*100 if (w+l)>0 else 0; s="+" if tp>=0 else ""
            lines.append(f"\n**סטטיסטיקות:** {wr:.0f}% הצלחה | P&L: {s}${tp:.0f}")
        except: pass
    st.text_area("העתק לקלוד:", "\n".join(lines), height=250)
    st.success("✅ העתק ושלח לקלוד בתחילת שיחה חדשה!")
