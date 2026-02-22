import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="Monitor Licitații Construcții", page_icon="🏗️", layout="wide")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

CPV_CONSTRUCTII = {
    "45000000": "Lucrări de construcții",
    "45100000": "Lucrări de pregătire șantier",
    "45200000": "Construcții civile",
    "45210000": "Construcții clădiri",
    "45211000": "Construcții civile și locuințe",
    "45213000": "Construcții comerciale și industriale",
    "45220000": "Lucrări de inginerie civilă",
    "45230000": "Drumuri și conducte",
    "45233000": "Construire drumuri",
    "45240000": "Lucrări hidraulice",
    "45300000": "Lucrări de instalații",
    "45310000": "Instalații electrice",
    "45330000": "Instalații sanitare",
    "45400000": "Lucrări de finisare",
    "71000000": "Servicii arhitectură și inginerie",
    "71300000": "Servicii de inginerie",
    "71320000": "Servicii de proiectare",
    "71500000": "Servicii de construcții",
    "71520000": "Supraveghere construcții",
}

@st.cache_data(ttl=1800)
def fetch_contracte(data_start, data_sfarsit):
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("⚙️ **Configurare necesară:** Adaugă credențialele Supabase în Streamlit Secrets.")
        return pd.DataFrame()
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    url = (f"{SUPABASE_URL}/rest/v1/contracte"
           f"?data_atribuirii=gte.{data_start}"
           f"&data_atribuirii=lte.{data_sfarsit}"
           f"&order=valoare.desc&limit=1000&select=*")
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        if not data:
            return pd.DataFrame()
        rows = []
        for item in data:
            cpv = str(item.get("cpv", "") or "")
            rows.append({
                "🏢 Firmă câștigătoare": item.get("firma", "N/A"),
                "CUI": item.get("cui", "N/A"),
                "💰 Valoare (lei)": item.get("valoare", 0) or 0,
                "📋 Obiect contract": item.get("obiect", "N/A"),
                "🏛️ Autoritate contractantă": item.get("autoritate", "N/A"),
                "📅 Data atribuirii": item.get("data_atribuirii", "N/A"),
                "📌 Tip lucrare": CPV_CONSTRUCTII.get(cpv[:8], "Construcții"),
                "🔢 Cod CPV": cpv,
            })
        return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"⚠️ Eroare: {e}")
        return pd.DataFrame()

def fetch_anaf(cui):
    try:
        payload = [{"cui": int(str(cui).replace("RO","").strip()), "data": datetime.now().strftime("%Y-%m-%d")}]
        r = requests.post("https://webservicesp.anaf.ro/PlatitorTvaRest/api/v8/ws/tva", json=payload, timeout=10)
        if r.status_code == 200:
            found = r.json().get("found", [])
            if found:
                dg = found[0].get("date_generale", {})
                return {"Denumire": dg.get("denumire",""), "Adresă": dg.get("adresa",""),
                        "Telefon": dg.get("telefon",""), "Email": dg.get("email",""), "CUI": dg.get("cod_fiscal","")}
    except:
        pass
    return None

st.title("🏗️ Monitor Licitații Construcții România")
st.caption("Urmărești firmele care câștigă contracte publice în construcții pentru a le oferi consultanță")

with st.sidebar:
    st.header("🔍 Filtre")
    azi = datetime.now().date()
    data_start = st.date_input("De la:", value=azi - timedelta(days=30))
    data_sfarsit = st.date_input("Până la:", value=azi)
    valoare_min = st.number_input("Valoare minimă (lei):", min_value=0, value=100_000, step=50_000)
    tipuri_selectate = st.multiselect("Tip lucrare (opțional):", options=sorted(set(CPV_CONSTRUCTII.values())), default=[])
    st.divider()
    buton_cauta = st.button("🔎 Caută contracte", type="primary", use_container_width=True)
    st.caption("📊 Date actualizate zilnic automat din SICAP")

if buton_cauta:
    with st.spinner("⏳ Încarc contractele..."):
        df = fetch_contracte(data_start.strftime("%Y-%m-%d"), data_sfarsit.strftime("%Y-%m-%d"))
    if df.empty:
        st.warning("Nu am găsit contracte pentru perioada selectată.")
    else:
        if valoare_min > 0:
            df = df[df["💰 Valoare (lei)"] >= valoare_min]
        if tipuri_selectate:
            df = df[df["📌 Tip lucrare"].isin(tipuri_selectate)]
        df = df.sort_values("💰 Valoare (lei)", ascending=False)
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("📋 Contracte găsite", len(df))
        with col2: st.metric("💰 Valoare totală", f"{df['💰 Valoare (lei)'].sum():,.0f} lei")
        with col3: st.metric("🏢 Firme câștigătoare", df["🏢 Firmă câștigătoare"].nunique())
        st.divider()
        df_d = df.copy()
        df_d["💰 Valoare (lei)"] = df_d["💰 Valoare (lei)"].apply(lambda x: f"{x:,.0f} lei")
        df_d["📅 Data atribuirii"] = pd.to_datetime(df_d["📅 Data atribuirii"], errors="coerce").dt.strftime("%d.%m.%Y")
        cols = ["🏢 Firmă câștigătoare","💰 Valoare (lei)","📋 Obiect contract","🏛️ Autoritate contractantă","📌 Tip lucrare","📅 Data atribuirii"]
        st.dataframe(df_d[cols], use_container_width=True, height=500, hide_index=True)
        st.divider()
        csv = df[cols].to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button("📥 Descarcă CSV/Excel", data=csv, file_name=f"contracte_{data_start}_{data_sfarsit}.csv", mime="text/csv")
        st.divider()
        st.subheader("🔍 Date de contact firmă")
        firma_sel = st.selectbox("Alege firma:", ["-- Selectează --"] + sorted(df["🏢 Firmă câștigătoare"].unique().tolist()))
        if firma_sel != "-- Selectează --":
            cui = df[df["🏢 Firmă câștigătoare"] == firma_sel]["CUI"].iloc[0]
            with st.spinner("Caut în ANAF..."):
                detalii = fetch_anaf(str(cui))
            if detalii:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.info(f"**{detalii['Denumire']}**\n- 📍 {detalii['Adresă']}\n- 📞 {detalii['Telefon'] or 'Nedisponibil'}\n- 📧 {detalii['Email'] or 'Nedisponibil'}\n- 🔢 CUI: {detalii['CUI']}")
                with col_b:
                    cf = df[df["🏢 Firmă câștigătoare"] == firma_sel]
                    st.metric("Contracte în perioadă", len(cf))
                    st.metric("Valoare totală", f"{cf['💰 Valoare (lei)'].sum():,.0f} lei")
            else:
                st.warning("Date indisponibile în ANAF.")
                st.link_button("🔗 Caută pe RECOM", f"https://www.recom.ro/index.asp?val={cui}")
else:
    st.info("""
👈 **Cum folosești aplicația:**
1. Selectează perioada din meniu (stânga)
2. Setează valoarea minimă
3. Apasă **"Caută contracte"**
4. Vezi tabelul cu firmele câștigătoare
5. Click pe o firmă pentru date de contact
6. Descarcă lista în Excel
    """)
    col1, col2, col3 = st.columns(3)
    with col1: st.success("📞 **Contactezi firma** câștigătoare și îi oferi consultanță")
    with col2: st.info("📈 **Analizezi piața** — ce firme domină domeniul")
    with col3: st.warning("🗓️ **Date actualizate zilnic** automat din SICAP")
