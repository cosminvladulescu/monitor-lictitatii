import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import time

# ─────────────────────────────────────────────
# CONFIGURARE
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Monitor Licitații Construcții",
    page_icon="🏗️",
    layout="wide"
)

# Coduri CPV pentru construcții (ce caută agentul)
CPV_CONSTRUCTII = {
    "45000000": "Lucrări de construcții",
    "45100000": "Lucrări de pregătire a șantierului",
    "45200000": "Lucrări complete sau parțiale de construcții civile",
    "45210000": "Lucrări de construcții de clădiri",
    "45211000": "Construcții civile și locuințe",
    "45213000": "Construcții comerciale, depozite și clădiri industriale",
    "45220000": "Lucrări de inginerie civilă",
    "45230000": "Construcții de conducte, linii, căi, drumuri",
    "45231000": "Lucrări de construcție a conductelor",
    "45232000": "Lucrări auxiliare pentru conducte și cabluri",
    "45233000": "Lucrări de construire, fundare și acoperire a drumurilor",
    "45234000": "Lucrări de construcție feroviară și funicular",
    "45240000": "Lucrări de construcție hidraulică",
    "45250000": "Construcție de uzine și instalații industriale",
    "45260000": "Lucrări de șarpantă și alte lucrări de specialitate",
    "45300000": "Lucrări de instalații",
    "45310000": "Lucrări de instalații electrice",
    "45320000": "Lucrări de izolare",
    "45330000": "Lucrări de instalații sanitare",
    "45340000": "Lucrări de împrejmuire și garduri",
    "45400000": "Lucrări de finisare a construcțiilor",
    "45410000": "Lucrări de tencuire",
    "45420000": "Lucrări de dulgherie și tâmplărie",
    "45430000": "Lucrări de pardoseală și placare",
    "45440000": "Lucrări de vopsire și geamuri",
    "45450000": "Alte lucrări de finisare",
    "71000000": "Servicii de arhitectură, construcții și inginerie",
    "71200000": "Servicii de arhitectură",
    "71300000": "Servicii de inginerie",
    "71310000": "Consultanță de inginerie și construcții",
    "71320000": "Servicii de proiectare tehnică",
    "71500000": "Servicii de construcții",
    "71520000": "Servicii de supraveghere a construcțiilor",
    "71540000": "Servicii de gestiune a construcțiilor",
}

# ─────────────────────────────────────────────
# FUNCȚII DE FETCH DATE
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)  # Cache 1 oră
def fetch_contracte_atribuite(data_start: str, data_sfarsit: str, pagina: int = 1, nr_rezultate: int = 100):
    """
    Preia contractele atribuite din SICAP pentru domeniul construcțiilor.
    Returnează un DataFrame cu firmele câștigătoare.
    """
    # Headere care imită exact un browser real
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://sicap-prod.e-licitatie.ro",
        "Referer": "https://sicap-prod.e-licitatie.ro/pub/reports/awardNotices",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }

    # Încearcă ambele endpoint-uri posibile
    urls = [
        "https://sicap-prod.e-licitatie.ro/pub/reports/awardNotices/filter",
        "https://e-licitatie.ro/pub/reports/awardNotices/filter",
    ]

    payload = {
        "pageSize": nr_rezultate,
        "pageNumber": pagina,
        "cpvCode": None,
        "awardDateStart": data_start,
        "awardDateEnd": data_sfarsit,
        "sysProcedureTypeId": None,
        "sysAwardCriteriaId": None,
        "contractingAuthorityId": None,
        "supplierId": None,
        "valueFrom": None,
        "valueTo": None
    }

    last_error = None
    for url in urls:
        try:
            # Sesiune cu retry automat
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(max_retries=3)
            session.mount("https://", adapter)

            response = session.post(url, json=payload, headers=headers, timeout=45)
            response.raise_for_status()
            data = response.json()

            items = data.get("items", [])
            if items is None:
                return pd.DataFrame(), 0

            total = data.get("total", 0)

            rows = []
            for item in items:
                cpv = item.get("cpvCode", "") or ""
                # Filtru: păstrăm doar construcții (CPV 45xxxxxx sau 71xxxxxx)
                if not (cpv.startswith("45") or cpv.startswith("71")):
                    continue

                rows.append({
                    "🏢 Firmă câștigătoare": item.get("supplierName", "N/A"),
                    "CUI": item.get("supplierId", "N/A"),
                    "💰 Valoare (lei)": item.get("contractValue", 0) or 0,
                    "📋 Obiect contract": item.get("contractTitle", "N/A"),
                    "🏛️ Autoritate contractantă": item.get("contractingAuthorityName", "N/A"),
                    "📅 Data atribuirii": item.get("awardDate", "N/A"),
                    "🔢 Cod CPV": cpv,
                    "📌 Tip lucrare": CPV_CONSTRUCTII.get(cpv[:8], "Construcții"),
                    "ID Anunț": item.get("noticeId", "N/A"),
                })

            return pd.DataFrame(rows), total

        except requests.exceptions.RequestException as e:
            last_error = e
            continue  # Încearcă next URL

    # Dacă ambele au eșuat
    st.error(f"""
    ⚠️ **Nu m-am putut conecta la SICAP.**

    SICAP (site-ul statului) nu răspunde în acest moment. Acest lucru se întâmplă uneori
    când serverele lor sunt supraîncărcate sau în mentenanță.

    **Ce poți face:**
    - Încearcă din nou peste 5-10 minute
    - Verifică dacă [SICAP](https://sicap-prod.e-licitatie.ro) este accesibil din browserul tău

    *Detaliu tehnic: {str(last_error)[:100]}*
    """)
    return pd.DataFrame(), 0


def fetch_detalii_firma(cui: str):
    """Preia datele de contact ale unei firme din ANAF."""
    try:
        url = "https://webservicesp.anaf.ro/PlatitorTvaRest/api/v8/ws/tva"
        payload = [{"cui": int(str(cui).replace("RO", "").strip()), "data": datetime.now().strftime("%Y-%m-%d")}]
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            found = data.get("found", [])
            if found:
                f = found[0]
                return {
                    "Denumire": f.get("date_generale", {}).get("denumire", ""),
                    "Adresă": f.get("date_generale", {}).get("adresa", ""),
                    "Telefon": f.get("date_generale", {}).get("telefon", ""),
                    "Email": f.get("date_generale", {}).get("email", ""),
                    "Stare": "Activ" if f.get("stare_inregistrare", {}).get("stare_inregistrare_tva", False) else "Inactiv TVA",
                    "Cod fiscal": f.get("date_generale", {}).get("cod_fiscal", ""),
                }
    except Exception as e:
        pass
    return None


# ─────────────────────────────────────────────
# INTERFAȚA
# ─────────────────────────────────────────────

st.title("🏗️ Monitor Licitații Construcții România")
st.caption("Urmărești firmele care câștigă contracte publice în construcții pentru a le oferi consultanță")

# ─── FILTRE ───
with st.sidebar:
    st.header("🔍 Filtre")
    
    st.subheader("Perioadă")
    azi = datetime.now().date()
    data_start = st.date_input("De la:", value=azi - timedelta(days=30))
    data_sfarsit = st.date_input("Până la:", value=azi)
    
    st.subheader("Valoare contract")
    valoare_min = st.number_input(
        "Valoare minimă (lei):",
        min_value=0,
        value=100_000,
        step=50_000,
        help="Filtrează contractele mai mari decât această sumă"
    )
    
    st.subheader("Tip lucrare")
    tipuri_disponibile = sorted(set(CPV_CONSTRUCTII.values()))
    tipuri_selectate = st.multiselect(
        "Selectează tipul de lucrare:",
        options=tipuri_disponibile,
        default=[],
        help="Lasă gol = toate tipurile"
    )
    
    st.divider()
    buton_cauta = st.button("🔎 Caută contracte", type="primary", use_container_width=True)
    
    st.caption("📊 Datele vin din SICAP (sistemul oficial al statului)")

# ─── REZULTATE ───
if buton_cauta:
    with st.spinner("⏳ Caut contractele... (poate dura 10-20 secunde)"):
        df, total = fetch_contracte_atribuite(
            data_start.strftime("%Y-%m-%d"),
            data_sfarsit.strftime("%Y-%m-%d")
        )
    
    if df.empty:
        st.warning("Nu am găsit contracte pentru perioada selectată. Încearcă o perioadă mai lungă.")
    else:
        # Aplică filtre locale
        if valoare_min > 0:
            df = df[df["💰 Valoare (lei)"] >= valoare_min]
        
        if tipuri_selectate:
            df = df[df["📌 Tip lucrare"].isin(tipuri_selectate)]
        
        # Sortare după valoare descrescător
        df = df.sort_values("💰 Valoare (lei)", ascending=False)
        
        # Statistici rapide
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📋 Contracte găsite", len(df))
        with col2:
            total_valoare = df["💰 Valoare (lei)"].sum()
            st.metric("💰 Valoare totală", f"{total_valoare:,.0f} lei")
        with col3:
            nr_firme = df["🏢 Firmă câștigătoare"].nunique()
            st.metric("🏢 Firme câștigătoare", nr_firme)
        
        st.divider()
        
        # Formatare valoare
        df_display = df.copy()
        df_display["💰 Valoare (lei)"] = df_display["💰 Valoare (lei)"].apply(
            lambda x: f"{x:,.0f} lei" if x > 0 else "N/A"
        )
        df_display["📅 Data atribuirii"] = pd.to_datetime(
            df_display["📅 Data atribuirii"], errors="coerce"
        ).dt.strftime("%d.%m.%Y")
        
        # Tabel principal
        st.subheader(f"📋 Contracte atribuite ({len(df)} rezultate)")
        
        coloane_afisate = [
            "🏢 Firmă câștigătoare",
            "💰 Valoare (lei)",
            "📋 Obiect contract",
            "🏛️ Autoritate contractantă",
            "📌 Tip lucrare",
            "📅 Data atribuirii"
        ]
        
        st.dataframe(
            df_display[coloane_afisate],
            use_container_width=True,
            height=500,
            hide_index=True
        )
        
        # Export Excel
        st.divider()
        col_export1, col_export2 = st.columns([1, 3])
        with col_export1:
            @st.cache_data
            def convert_to_excel(dataframe):
                return dataframe.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            
            csv_data = convert_to_excel(df[coloane_afisate])
            st.download_button(
                label="📥 Descarcă Excel/CSV",
                data=csv_data,
                file_name=f"contracte_constructii_{data_start}_{data_sfarsit}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        # ─── DETALII FIRMĂ ───
        st.divider()
        st.subheader("🔍 Detalii firmă (date de contact)")
        st.caption("Selectează o firmă din lista de mai jos pentru a vedea datele de contact din ANAF")
        
        firme_lista = sorted(df["🏢 Firmă câștigătoare"].unique().tolist())
        firma_selectata = st.selectbox("Alege firma:", options=["-- Selectează --"] + firme_lista)
        
        if firma_selectata != "-- Selectează --":
            cui_firma = df[df["🏢 Firmă câștigătoare"] == firma_selectata]["CUI"].iloc[0]
            
            with st.spinner("Caut datele de contact..."):
                detalii = fetch_detalii_firma(str(cui_firma))
            
            if detalii:
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.info(f"""
**{detalii['Denumire']}**
- 📍 **Adresă:** {detalii['Adresă']}
- 📞 **Telefon:** {detalii['Telefon'] or 'Nedisponibil'}
- 📧 **Email:** {detalii['Email'] or 'Nedisponibil'}
- 🔢 **CUI:** {detalii['Cod fiscal']}
- ✅ **Stare:** {detalii['Stare']}
                    """)
                with col_d2:
                    contracte_firma = df[df["🏢 Firmă câștigătoare"] == firma_selectata]
                    st.write(f"**Contracte câștigate în perioada selectată: {len(contracte_firma)}**")
                    valoare_totala_firma = contracte_firma["💰 Valoare (lei)"].sum()
                    st.write(f"**Valoare totală: {valoare_totala_firma:,.0f} lei**")
                    
                    st.dataframe(
                        contracte_firma[["📋 Obiect contract", "💰 Valoare (lei)", "🏛️ Autoritate contractantă", "📅 Data atribuirii"]].head(10),
                        hide_index=True,
                        use_container_width=True
                    )
            else:
                st.warning(f"Nu am găsit date de contact pentru CUI: {cui_firma}. Poți căuta manual pe [ANAF](https://www.anaf.ro)")
                
                # Link direct SEAP
                st.link_button(
                    "🔗 Caută firma pe RECOM",
                    f"https://www.recom.ro/index.asp?val={cui_firma}"
                )

# ─── MESAJ INITIAL ───
else:
    st.info("""
    👈 **Cum folosești aplicația:**
    
    1. **Selectează perioada** din meniu (stânga) — ex: ultimele 30 de zile
    2. **Setează valoarea minimă** — ex: 100.000 lei (ca să ignori contractele mici)
    3. **Alege tipul de lucrare** dacă vrei să filtrezi (sau lasă gol pentru toate)
    4. **Apasă "Caută contracte"**
    5. **Vei vedea tabelul** cu toate firmele care au câștigat licitații în construcții
    6. **Click pe o firmă** pentru a vedea datele de contact
    7. **Descarcă Excel** pentru a lucra cu lista offline
    """)
    
    st.divider()
    
    st.subheader("📊 Ce poți face cu aceste informații:")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.success("📞 **Contactezi firma** câștigătoare și îi oferi consultanță pentru derularea contractului")
    with col2:
        st.info("📈 **Analizezi piața** — ce firme domină, ce valori circulă în domeniu")
    with col3:
        st.warning("🗓️ **Monitorizezi zilnic** contractele noi pentru a fi primul care contactează firmele")
