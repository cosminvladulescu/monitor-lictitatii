"""
Script rulat automat zilnic prin GitHub Actions.
Preia contractele din SICAP si le salveaza in Supabase.
"""
import os
import time
import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

SUPABASE_URL    = os.environ["SUPABASE_URL"]
SUPABASE_KEY    = os.environ["SUPABASE_KEY"]

# 45 = Lucrari de constructii, 71 = Servicii de arhitectura/inginerie (de ex.)
CPV_CONSTRUCTII = ["45", "71"]
VALOARE_MINIMA  = 50_000


def _post_cu_retry(url: str, payload: dict, headers: dict, timeout_sec: int = 45, incercari: int = 4):
    """
    Trimite cererea catre SICAP cu mai multe incercari.
    Daca nu merge, returneaza None (in loc sa "pice" tot scriptul).
    """
    last_err = None
    for i in range(1, incercari + 1):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=timeout_sec)
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            # pauza mica intre incercari (creste treptat)
            time.sleep(2 * i)

    print(f"[EROARE] Nu am reusit sa obtin raspuns de la: {url}")
    print(f"Ultima eroare: {last_err}")
    return None


def preia_contracte():
    ieri = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    azi  = datetime.now().strftime("%Y-%m-%d")

    # IMPORTANT:
    # Incearca 2 variante de adresa. Uneori 443 e blocat/timeout, iar 8881 merge.
    urluri_posibile = [
        "https://sicap-prod.e-licitatie.ro/pub/reports/awardNotices/filter",
        "https://sicap-prod.e-licitatie.ro:8881/ca/reports/awardNotices/filter",
    ]

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://sicap-prod.e-licitatie.ro",
        "Referer": "https://sicap-prod.e-licitatie.ro/pub/reports/awardNotices",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    }

    payload = {
        "pageSize": 500,
        "pageNumber": 1,
        "awardDateStart": ieri,
        "awardDateEnd": azi,
        "cpvCode": None,
        "valueFrom": VALOARE_MINIMA,
        "valueTo": None,
        "sysProcedureTypeId": None,
        "sysAwardCriteriaId": None,
        "contractingAuthorityId": None,
        "supplierId": None
    }

    # incearca pe rand URL-urile pana merge unul
    raspuns = None
    url_folosit = None
    for u in urluri_posibile:
        print(f"[INFO] Incerc sa ma conectez la SICAP: {u}")
        raspuns = _post_cu_retry(u, payload, headers, timeout_sec=45, incercari=4)
        if raspuns is not None:
            url_folosit = u
            break

    # daca nu a mers niciun URL, returnam lista goala (nu mai "pica" scriptul)
    if raspuns is None:
        print("[ATENTIE] Nu am putut prelua date de la SICAP (timeout/blocat).")
        print("=> Nu se salveaza nimic in Supabase azi.")
        return []

    # daca a mers, continuam normal
    data = raspuns.json()
    items = data.get("items", []) or []
    print(f"[OK] Conectat. URL folosit: {url_folosit}")
    print(f"[INFO] Total rezultate primite (brut): {len(items)}")

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

    print(f"[INFO] Contracte dupa filtrul de constructii (CPV 45/71): {len(contracte)}")
    return contracte


def salveaza_in_supabase(contracte):
    if not contracte:
        print("[INFO] Nimic de salvat in Supabase.")
        return

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    url = f"{SUPABASE_URL}/rest/v1/contracte"

    salvate = 0
    for i in range(0, len(contracte), 100):
        batch = contracte[i:i+100]
        r = requests.post(url, headers=headers, json=batch, timeout=30)
        if r.status_code in (200, 201):
            salvate += len(batch)
        else:
            print(f"[EROARE] Batch {i}: {r.status_code} - {r.text[:200]}")

    print(f"[OK] Salvate in Supabase: {salvate}")


def trimite_email(contracte):
    EMAIL_EXPEDITOR  = os.environ.get("EMAIL_EXPEDITOR")
    EMAIL_PAROLA_APP = os.environ.get("EMAIL_PAROLA_APP")
    EMAIL_DESTINATAR = os.environ.get("EMAIL_DESTINATAR")

    # daca nu ai setat email sau nu avem contracte, sarim peste
    if not all([EMAIL_EXPEDITOR, EMAIL_PAROLA_APP, EMAIL_DESTINATAR]) or not contracte:
        print("[INFO] Email: skip (nu e setat sau nu exista contracte).")
        return

    ieri = (datetime.now() - timedelta(days=1)).strftime("%d.%m.%Y")
    nr = len(contracte)
    total = f"{sum(c['valoare'] for c in contracte):,.0f}".replace(",", ".")

    randuri = ""
    for i, c in enumerate(contracte[:50]):
        bg = "#f9f9f9" if i % 2 == 0 else "#ffffff"
        val = f"{c['valoare']:,.0f} lei".replace(",", ".")
        randuri += (
            f'<tr style="background:{bg}">'
            f'<td style="padding:8px;font-weight:bold">{c["firma"]}</td>'
            f'<td style="padding:8px;color:#e67e22">{val}</td>'
            f'<td style="padding:8px;font-size:13px">{(c["obiect"] or "")[:80]}</td>'
            f'<td style="padding:8px;font-size:12px;color:#666">{(c["autoritate"] or "")[:50]}</td>'
            f"</tr>"
        )

    html = f"""<html><body style="font-family:Arial,sans-serif;max-width:900px;margin:0 auto;padding:20px">
    <div style="background:linear-gradient(135deg,#2c3e50,#3498db);padding:25px;border-radius:10px;margin-bottom:25px">
        <h1 style="color:white;margin:0">🏗️ Raport Licitații Construcții — {ieri}</h1>
        <p style="color:#bde3ff;margin:5px 0 0">{nr} contracte noi | {total} lei total</p>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
        <thead><tr style="background:#2c3e50;color:white">
            <th style="padding:10px;text-align:left">Firma</th>
            <th style="padding:10px;text-align:left">Valoare</th>
            <th style="padding:10px;text-align:left">Obiect</th>
            <th style="padding:10px;text-align:left">Autoritate</th>
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

    print(f"[OK] Email trimis la {EMAIL_DESTINATAR}")


if __name__ == "__main__":
    print(f"Start: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    contracte = preia_contracte()
    salveaza_in_supabase(contracte)
    trimite_email(contracte)
    print("Gata!")
