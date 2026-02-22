"""
Script rulat automat zilnic prin GitHub Actions.
Preia contractele din SICAP si le salveaza in Supabase.
"""
import requests, os, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

SUPABASE_URL    = os.environ["SUPABASE_URL"]
SUPABASE_KEY    = os.environ["SUPABASE_KEY"]
CPV_CONSTRUCTII = ["45", "71"]
VALOARE_MINIMA  = 50_000

def preia_contracte():
    ieri = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    azi  = datetime.now().strftime("%Y-%m-%d")
    url  = "https://sicap-prod.e-licitatie.ro/pub/reports/awardNotices/filter"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://sicap-prod.e-licitatie.ro",
        "Referer": "https://sicap-prod.e-licitatie.ro/pub/reports/awardNotices",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    }
    payload = {"pageSize": 500, "pageNumber": 1, "awardDateStart": ieri, "awardDateEnd": azi,
                "cpvCode": None, "valueFrom": VALOARE_MINIMA, "valueTo": None,
                "sysProcedureTypeId": None, "sysAwardCriteriaId": None,
                "contractingAuthorityId": None, "supplierId": None}
    r = requests.post(url, json=payload, headers=headers, timeout=45)
    r.raise_for_status()
    items = r.json().get("items", []) or []
    print(f"Total SICAP: {len(items)}")
    contracte = []
    for item in items:
        cpv = str(item.get("cpvCode", "") or "")
        if not any(cpv.startswith(p) for p in CPV_CONSTRUCTII):
            continue
        contracte.append({
            "firma": item.get("supplierName", "N/A"),
            "cui": str(item.get("supplierId", "") or ""),
            "valoare": item.get("contractValue", 0) or 0,
            "obiect": item.get("contractTitle", "N/A"),
            "autoritate": item.get("contractingAuthorityName", "N/A"),
            "data_atribuirii": (item.get("awardDate") or ieri)[:10],
            "cpv": cpv,
            "id_anunt": str(item.get("noticeId", "") or ""),
        })
    print(f"Constructii filtrate: {len(contracte)}")
    return contracte

def salveaza_in_supabase(contracte):
    if not contracte:
        print("Nimic de salvat.")
        return
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
    url = f"{SUPABASE_URL}/rest/v1/contracte"
    salvate = 0
    for i in range(0, len(contracte), 100):
        batch = contracte[i:i+100]
        r = requests.post(url, headers=headers, json=batch, timeout=30)
        if r.status_code in (200, 201):
            salvate += len(batch)
        else:
            print(f"Eroare batch {i}: {r.status_code} - {r.text[:200]}")
    print(f"Salvate in Supabase: {salvate}")

def trimite_email(contracte):
    EMAIL_EXPEDITOR  = os.environ.get("EMAIL_EXPEDITOR")
    EMAIL_PAROLA_APP = os.environ.get("EMAIL_PAROLA_APP")
    EMAIL_DESTINATAR = os.environ.get("EMAIL_DESTINATAR")
    if not all([EMAIL_EXPEDITOR, EMAIL_PAROLA_APP, EMAIL_DESTINATAR]) or not contracte:
        print("Email skip.")
        return
    ieri = (datetime.now() - timedelta(days=1)).strftime("%d.%m.%Y")
    nr = len(contracte)
    total = f"{sum(c['valoare'] for c in contracte):,.0f}".replace(",", ".")
    randuri = ""
    for i, c in enumerate(contracte[:50]):
        bg = "#f9f9f9" if i % 2 == 0 else "#ffffff"
        val = f"{c['valoare']:,.0f} lei".replace(",", ".")
        randuri += f'<tr style="background:{bg}"><td style="padding:8px;font-weight:bold">{c["firma"]}</td><td style="padding:8px;color:#e67e22">{val}</td><td style="padding:8px;font-size:13px">{c["obiect"][:80]}</td><td style="padding:8px;font-size:12px;color:#666">{c["autoritate"][:50]}</td></tr>'
    html = f"""<html><body style="font-family:Arial,sans-serif;max-width:900px;margin:0 auto;padding:20px">
    <div style="background:linear-gradient(135deg,#2c3e50,#3498db);padding:25px;border-radius:10px;margin-bottom:25px">
        <h1 style="color:white;margin:0">🏗️ Raport Licitații Construcții — {ieri}</h1>
        <p style="color:#bde3ff;margin:5px 0 0">{nr} contracte noi | {total} lei total</p>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
        <thead><tr style="background:#2c3e50;color:white">
            <th style="padding:10px;text-align:left">Firma</th><th style="padding:10px;text-align:left">Valoare</th>
            <th style="padding:10px;text-align:left">Obiect</th><th style="padding:10px;text-align:left">Autoritate</th>
        </tr></thead><tbody>{randuri}</tbody></table>
    {"<p style='color:#666'>...si inca " + str(nr-50) + " contracte.</p>" if nr > 50 else ""}
    </body></html>"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🏗️ {nr} contracte noi constructii — {ieri}"
    msg["From"] = EMAIL_EXPEDITOR
    msg["To"] = EMAIL_DESTINATAR
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_EXPEDITOR, EMAIL_PAROLA_APP)
        s.sendmail(EMAIL_EXPEDITOR, EMAIL_DESTINATAR, msg.as_string())
    print(f"Email trimis la {EMAIL_DESTINATAR}")

if __name__ == "__main__":
    print(f"Start: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    contracte = preia_contracte()
    salveaza_in_supabase(contracte)
    trimite_email(contracte)
    print("Gata!")
