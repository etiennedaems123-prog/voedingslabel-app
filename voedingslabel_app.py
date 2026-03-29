import streamlit as st
import pandas as pd
import os, json, bcrypt, uuid
from datetime import datetime
from reportlab.pdfgen import canvas
from supabase import create_client

# =============================================
# CONFIGURATIE
# =============================================
BASE_DIR      = os.path.dirname(__file__)
DATABASE_FILE = os.path.join(BASE_DIR, "TRYOUT1a.xlsx")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(
    page_title="LabelMaker — EU Voedingslabels",
    page_icon="🏷️",
    layout="wide"
)

# =============================================
# SESSION STATE
# =============================================
for key, default in [
    ("logged_in", False),
    ("username", ""),
    ("page", "home"),
    ("ingredients", []),
    ("edit_label_id", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# =============================================
# DATABASE HELPERS
# =============================================
@st.cache_data
def load_food_db():
    if os.path.exists(DATABASE_FILE):
        return pd.read_excel(DATABASE_FILE)
    return pd.DataFrame()

df_db = load_food_db()

def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def check_pw(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())

def register_user(username, email, password):
    existing = sb.table("users_data").select("username").eq("username", username).execute()
    if existing.data:
        return False, "Gebruikersnaam al in gebruik."
    existing_email = sb.table("users_data").select("email").eq("email", email).execute()
    if existing_email.data:
        return False, "E-mailadres al geregistreerd."
    sb.table("users_data").insert({
        "username": username,
        "email": email,
        "password_hash": hash_pw(password)
    }).execute()
    return True, "Account aangemaakt!"

def login_user(username, password):
    result = sb.table("users_data").select("*").eq("username", username).execute()
    if not result.data:
        return False, "Gebruikersnaam niet gevonden."
    user = result.data[0]
    if not check_pw(password, user["password_hash"]):
        return False, "Ongeldig wachtwoord."
    return True, "Ingelogd!"

def save_label(label_data: dict):
    """Sla een nieuw label op of update een bestaand."""
    if label_data.get("id"):
        sb.table("labels").update({
            "product_name":  label_data["product_name"],
            "product_weight": label_data["product_weight"],
            "nutriscore":    label_data["nutriscore"],
            "ingredients":   label_data["ingredients"],
            "per100":        label_data["per100"],
            "portion_size":  label_data["portion_size"],
            "allergenen":    label_data["allergenen"],
            "updated_at":    datetime.utcnow().isoformat(),
        }).eq("id", label_data["id"]).execute()
    else:
        sb.table("labels").insert({
            "username":      st.session_state["username"],
            "product_name":  label_data["product_name"],
            "product_weight": label_data["product_weight"],
            "nutriscore":    label_data["nutriscore"],
            "ingredients":   label_data["ingredients"],
            "per100":        label_data["per100"],
            "portion_size":  label_data["portion_size"],
            "allergenen":    label_data["allergenen"],
        }).execute()

def get_labels():
    result = sb.table("labels")\
        .select("*")\
        .eq("username", st.session_state["username"])\
        .order("updated_at", desc=True)\
        .execute()
    return result.data or []

def delete_label(label_id: str):
    sb.table("labels").delete().eq("id", label_id).execute()

# =============================================
# NUTRI-SCORE
# =============================================
ALLERGENEN_LIJST = [
    "Gluten (tarwe, rogge, gerst, haver...)",
    "Schaaldieren", "Eieren", "Vis", "Pinda's", "Soja", "Melk/lactose",
    "Noten (amandelen, hazelnoten, walnoten...)", "Selderij", "Mosterd",
    "Sesamzaad", "Zwaveldioxide/sulfiet (>10 mg/kg)", "Lupine", "Weekdieren",
]

RI = {"Energy_kcal":2000,"Energy_kJ":8400,"Fat":70,"SatFat":20,
      "Carbs":260,"Sugar":90,"Protein":50,"Salt":6}

def get_pts(val, thresholds):
    return sum(1 for t in thresholds if val > t)

def calc_nutriscore(v):
    neg = (get_pts(v["Energy_kcal"],[335,670,1005,1340,1675,2010,2345,2680,3015,3350]) +
           get_pts(v["Sugar"],      [4.5,9,13.5,18,22.5,27,31,36,40,45]) +
           get_pts(v["SatFat"],     [1,2,3,4,5,6,7,8,9,10]) +
           get_pts(v["Salt"],       [0.2,0.4,0.6,0.8,1.0,1.2,1.4,1.6,1.8,2.0]))
    fib = get_pts(v["Fibres"], [0.9,1.9,2.8,3.7,4.7])
    pro = get_pts(v["Protein"],[1.6,3.2,4.8,6.4,8.0])
    score = neg - fib if neg >= 11 else neg - fib - pro
    if score <= -1:   return "A"
    elif score <= 2:  return "B"
    elif score <= 10: return "C"
    elif score <= 18: return "D"
    else:             return "E"

def nutriscore_html(active):
    colors  = {"A":"#1e7e34","B":"#85bb2f","C":"#f5c100","D":"#f07921","E":"#dc3a20"}
    txt_clr = {"A":"#fff","B":"#fff","C":"#333","D":"#fff","E":"#fff"}
    html = ('<div style="display:inline-flex;flex-direction:column;align-items:center;'
            'background:#ebebeb;border-radius:10px;padding:8px 12px;">'
            '<div style="font-size:11px;font-weight:700;color:#555;letter-spacing:1px;margin-bottom:5px;">NUTRI-SCORE</div>'
            '<div style="display:flex;align-items:flex-end;gap:2px;">')
    for l in ["A","B","C","D","E"]:
        bg, tc = colors[l], txt_clr[l]
        if l == active:
            html += (f'<div style="display:flex;align-items:center;justify-content:center;'
                     f'background:{bg};border-radius:50px;width:46px;height:54px;'
                     f'border:3px solid white;box-shadow:0 0 0 2px {bg};margin-bottom:-3px;z-index:2;">'
                     f'<span style="font-size:28px;font-weight:900;color:{tc};">{l}</span></div>')
        else:
            html += (f'<div style="display:flex;align-items:center;justify-content:center;'
                     f'background:{bg};border-radius:5px;width:34px;height:38px;opacity:0.7;">'
                     f'<span style="font-size:18px;font-weight:700;color:{tc};">{l}</span></div>')
    html += "</div></div>"
    return html

# =============================================
# PDF GENEREREN
# =============================================
def generate_pdf(product_name, product_weight, per100, per_portion,
                 portion_size, ns_letter, alle_allergenen, ing_list_str):
    pdf_path = os.path.join(BASE_DIR, "eu_label.pdf")
    W, H    = 300, 600
    MARGIN  = 14
    RR      = W - MARGIN
    if per_portion:
        C_100 = 175; C_PORT = 230; C_RI = RR
    else:
        C_100 = RR;  C_PORT = None; C_RI = None
    ROW_H = 13

    def hline(cv, y, lw=0.5, gray=0.0):
        cv.setLineWidth(lw); cv.setStrokeColorRGB(gray,gray,gray)
        cv.line(MARGIN, y, RR, y); cv.setStrokeColorRGB(0,0,0)

    def wrap_draw(cv, text, x, y, max_w, font, size, lh):
        cv.setFont(font, size)
        words, line = text.split(" "), ""
        for w in words:
            test = (line+" "+w).strip()
            if cv.stringWidth(test, font, size) <= max_w: line = test
            else:
                cv.drawString(x, y, line); y -= lh; line = w
        if line: cv.drawString(x, y, line); y -= lh
        return y

    def trow(cv, label, v100, vport=None, ri=None, bold=False, y_pos=0, indent=False):
        cv.setFont("Helvetica-Bold" if bold else "Helvetica", 8)
        cv.setFillColorRGB(0,0,0)
        cv.drawString(MARGIN+(10 if indent else 0), y_pos, label)
        cv.drawRightString(C_100, y_pos, str(v100))
        if C_PORT and vport: cv.setFont("Helvetica",8); cv.drawRightString(C_PORT, y_pos, str(vport))
        if C_RI and ri:      cv.setFont("Helvetica",8); cv.drawRightString(C_RI,   y_pos, str(ri))
        hline(cv, y_pos-3, lw=0.3, gray=0.75)
        return y_pos - ROW_H

    c = canvas.Canvas(pdf_path, pagesize=(W,H))
    c.setFillColorRGB(1,1,1); c.rect(0,0,W,H,fill=1,stroke=0); c.setFillColorRGB(0,0,0)

    NS_RGB = {"A":(0.102,0.494,0.224),"B":(0.416,0.671,0.125),
              "C":(0.961,0.753,0.0),"D":(0.910,0.447,0.047),"E":(0.753,0.224,0.169)}
    c.setFont("Helvetica-Bold",7); c.setFillColorRGB(0.3,0.3,0.3)
    c.drawCentredString(W/2, H-12, "NUTRI-SCORE"); c.setFillColorRGB(0,0,0)
    BW,AW,GAP = 38,44,3
    total_w = AW+4*BW+4*GAP; bx0=(W-total_w)/2
    BAR_BOT=H-58; IH=34; AH=44
    x_cur=bx0
    for letter in ["A","B","C","D","E"]:
        act = letter==ns_letter; r,g,b=NS_RGB[letter]
        if act:
            c.setFillColorRGB(1,1,1); c.roundRect(x_cur-3,BAR_BOT-5,AW+6,AH+4,8,fill=1,stroke=0)
            c.setFillColorRGB(r,g,b); c.roundRect(x_cur,BAR_BOT-3,AW,AH,6,fill=1,stroke=0)
            fs=20; ly=BAR_BOT-3+AH/2-fs*0.35
        else:
            alpha=0.72; rc=r+(1-r)*(1-alpha); gc=g+(1-g)*(1-alpha); bc=b+(1-b)*(1-alpha)
            c.setFillColorRGB(rc,gc,bc); c.roundRect(x_cur,BAR_BOT+(AH-IH)/2,BW,IH,5,fill=1,stroke=0)
            fs=14; ly=BAR_BOT+(AH-IH)/2+IH/2-fs*0.35
        tc=(0.15,0.15,0.15) if letter=="C" else ((1,1,1) if act else (0.95,0.95,0.95))
        c.setFillColorRGB(*tc); c.setFont("Helvetica-Bold",fs)
        c.drawCentredString(x_cur+(AW if act else BW)/2, ly, letter)
        x_cur += (AW if act else BW)+GAP
    c.setFillColorRGB(0,0,0)

    y=BAR_BOT-14; hline(c,y+2,lw=1.5); y-=13
    c.setFont("Helvetica-Bold",12); c.drawCentredString(W/2,y,product_name); y-=11
    if product_weight:
        c.setFont("Helvetica",8); c.drawCentredString(W/2,y,f"Netto hoeveelheid: {product_weight}"); y-=10

    y-=4; hline(c,y,lw=1.5); y-=13
    c.setFont("Helvetica-Bold",10); c.drawString(MARGIN,y,"Voedingswaarde")
    c.setFont("Helvetica",7); c.drawRightString(C_100,y,"per 100 g")
    if per_portion:
        c.drawRightString(C_PORT,y,f"per portie ({portion_size} g)")
        c.drawRightString(C_RI,y,"%RI*")
    y-=5; hline(c,y,lw=0.8); y-=ROW_H

    ri_e = f"{round(per_portion['Energy_kcal']/RI['Energy_kcal']*100)}%" if per_portion else None
    c.setFont("Helvetica-Bold",8); c.setFillColorRGB(0,0,0)
    c.drawString(MARGIN,y,"Energie")
    c.drawRightString(C_100,y,f"{per100['Energy_kJ']} kJ")
    if per_portion:
        c.setFont("Helvetica",8)
        c.drawRightString(C_PORT,y,f"{per_portion['Energy_kJ']} kJ")
        if C_RI: c.drawRightString(C_RI,y,ri_e)
    y-=ROW_H-2
    c.setFont("Helvetica",8); c.drawRightString(C_100,y,f"{per100['Energy_kcal']} kcal")
    if per_portion: c.drawRightString(C_PORT,y,f"{per_portion['Energy_kcal']} kcal")
    hline(c,y-3,lw=0.3,gray=0.75); y-=ROW_H

    for lbl,key,bold,indent in [
        ("Vet","Fat",True,False),("w.v. verzadigde vetzuren","SatFat",False,True),
        ("w.v. enkelvoudig onverzadigd","Monounsat",False,True),
        ("w.v. meervoudig onverzadigd","Polyunsat",False,True),
        ("Koolhydraten","Carbs",True,False),("w.v. suikers","Sugar",False,True),
        ("Vezels","Fibres",True,False),("Eiwitten","Protein",True,False),
        ("Zout","Salt",True,False),
    ]:
        v100s = f"{per100[key]} g"
        vps   = f"{per_portion[key]} g" if per_portion else None
        ris   = f"{round(per_portion[key]/RI[key]*100)}%" if per_portion and key in RI else None
        y = trow(c,lbl,v100s,vps,ris,bold=bold,y_pos=y,indent=indent)

    y-=3; hline(c,y,lw=0.6); y-=8
    c.setFont("Helvetica",6); c.setFillColorRGB(0,0,0)
    c.drawString(MARGIN,y,"*RI = Referentie-inname gemiddelde volwassene (8400 kJ / 2000 kcal)"); y-=12

    hline(c,y,lw=0.8); y-=11
    c.setFont("Helvetica-Bold",8); c.drawString(MARGIN,y,"Bevat:"); y-=10
    allerg_str = ", ".join(sorted(alle_allergenen)) if alle_allergenen else "Geen allergenen"
    y = wrap_draw(c,allerg_str,MARGIN,y,RR-MARGIN,"Helvetica",7,9)

    y-=3; hline(c,y,lw=0.8); y-=11
    c.setFont("Helvetica-Bold",8); c.drawString(MARGIN,y,"Ingrediënten:"); y-=10
    y = wrap_draw(c,ing_list_str,MARGIN,y,RR-MARGIN,"Helvetica",7,9)

    bottom=max(y-8,6)
    c.setStrokeColorRGB(0,0,0); c.setLineWidth(1.2)
    c.rect(6,bottom,W-12,H-bottom-6); c.save()
    return pdf_path

# =============================================
# NAVIGATIE SIDEBAR
# =============================================
def sidebar_nav():
    with st.sidebar:
        st.markdown("## 🏷️ LabelMaker")
        st.markdown("---")
        if st.session_state["logged_in"]:
            st.markdown(f"Ingelogd als **{st.session_state['username']}**")
            st.markdown("---")
            if st.button("🏠 Home",          use_container_width=True): st.session_state["page"]="home";      st.rerun()
            if st.button("🏷️ Labels maken",  use_container_width=True): st.session_state["page"]="maker";    st.rerun()
            if st.button("📁 Mijn labels",   use_container_width=True): st.session_state["page"]="my_labels";st.rerun()
            if st.button("📖 Kennisbank",    use_container_width=True): st.session_state["page"]="kennis";   st.rerun()
            st.markdown("---")
            if st.button("🚪 Uitloggen",     use_container_width=True):
                st.session_state["logged_in"]=False
                st.session_state["username"]=""
                st.session_state["page"]="home"
                st.session_state["ingredients"]=[]
                st.rerun()
        else:
            if st.button("🏠 Home",       use_container_width=True): st.session_state["page"]="home";  st.rerun()
            if st.button("🔑 Inloggen",   use_container_width=True): st.session_state["page"]="login"; st.rerun()
            if st.button("📖 Kennisbank", use_container_width=True): st.session_state["page"]="kennis";st.rerun()

# =============================================
# PAGINA: HOME
# =============================================
def page_home():
    st.title("🏷️ LabelMaker")
    st.subheader("EU-conforme voedingslabels in minuten")
    st.markdown("""
Genereer voedingslabels die voldoen aan **EU Verordening 1169/2011** — inclusief
Nutri-Score, allergenen, ingrediëntenlijst en voedingswaardentabel.
""")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### ✅ Wat je krijgt")
        st.markdown("""
- Volledige voedingswaardentabel
- Automatische Nutri-Score berekening
- Allergenen markering (alle 14 EU-allergenen)
- Ingrediëntenlijst op gewicht gesorteerd
- Downloadbare PDF in EU-formaat
""")
    with col2:
        st.markdown("### 🔒 Jouw labels")
        st.markdown("""
- Sla al je producten op in de cloud
- Bewerk en hergebruik eerdere labels
- Altijd toegankelijk, op elk apparaat
- Veilig opgeslagen per account
""")
    with col3:
        st.markdown("### 📖 Kennisbank")
        st.markdown("""
- Wanneer is een label verplicht?
- Wat moet er op het label staan?
- Regels rond allergenen
- Nutri-Score uitleg
""")

    st.markdown("---")
    if not st.session_state["logged_in"]:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔑 Inloggen", use_container_width=True, type="primary"):
                st.session_state["page"]="login"; st.rerun()
        with c2:
            if st.button("📝 Account aanmaken", use_container_width=True):
                st.session_state["page"]="register"; st.rerun()
    else:
        if st.button("🏷️ Nieuw label maken", type="primary"):
            st.session_state["page"]="maker"
            st.session_state["ingredients"]=[]
            st.session_state["edit_label_id"]=None
            st.rerun()

# =============================================
# PAGINA: LOGIN / REGISTER
# =============================================
def page_login():
    st.title("🔑 Inloggen")
    with st.form("login_form"):
        username = st.text_input("Gebruikersnaam")
        password = st.text_input("Wachtwoord", type="password")
        submitted = st.form_submit_button("Inloggen", type="primary", use_container_width=True)
        if submitted:
            ok, msg = login_user(username, password)
            if ok:
                st.session_state["logged_in"] = True
                st.session_state["username"]  = username
                st.session_state["page"]      = "home"
                st.rerun()
            else:
                st.error(msg)
    st.markdown("Nog geen account?")
    if st.button("Account aanmaken"):
        st.session_state["page"]="register"; st.rerun()

def page_register():
    st.title("📝 Account aanmaken")
    with st.form("reg_form"):
        username = st.text_input("Gebruikersnaam")
        email    = st.text_input("E-mailadres")
        pw       = st.text_input("Wachtwoord", type="password")
        pw2      = st.text_input("Herhaal wachtwoord", type="password")
        submitted = st.form_submit_button("Account aanmaken", type="primary", use_container_width=True)
        if submitted:
            if pw != pw2:
                st.error("Wachtwoorden komen niet overeen.")
            elif len(pw) < 6:
                st.error("Wachtwoord moet minstens 6 tekens zijn.")
            elif not username or not email:
                st.error("Vul alle velden in.")
            else:
                ok, msg = register_user(username, email, pw)
                if ok:
                    st.success(msg + " Je kan nu inloggen.")
                    st.session_state["page"]="login"; st.rerun()
                else:
                    st.error(msg)
    if st.button("Terug naar inloggen"):
        st.session_state["page"]="login"; st.rerun()

# =============================================
# PAGINA: MIJN LABELS
# =============================================
def page_my_labels():
    st.title("📁 Mijn labels")
    labels = get_labels()
    if not labels:
        st.info("Je hebt nog geen labels opgeslagen. Maak je eerste label aan!")
        if st.button("🏷️ Nieuw label maken", type="primary"):
            st.session_state["page"]="maker"
            st.session_state["ingredients"]=[]
            st.session_state["edit_label_id"]=None
            st.rerun()
        return

    if st.button("➕ Nieuw label maken", type="primary"):
        st.session_state["page"]="maker"
        st.session_state["ingredients"]=[]
        st.session_state["edit_label_id"]=None
        st.rerun()

    st.markdown(f"**{len(labels)} label(s) opgeslagen**")
    st.markdown("---")

    for label in labels:
        with st.container():
            col_info, col_ns, col_btns = st.columns([4, 1, 2])
            with col_info:
                updated = label["updated_at"][:10] if label.get("updated_at") else ""
                st.markdown(f"### {label['product_name']}")
                st.caption(f"Netto: {label.get('product_weight','—')}  ·  Laatst bewerkt: {updated}")
            with col_ns:
                ns = label.get("nutriscore","?")
                ns_colors = {"A":"#1e7e34","B":"#85bb2f","C":"#f5c100","D":"#f07921","E":"#dc3a20"}
                tc = "#333" if ns=="C" else "#fff"
                bg = ns_colors.get(ns,"#aaa")
                st.markdown(
                    f'<div style="background:{bg};color:{tc};font-weight:900;font-size:24px;'
                    f'border-radius:50px;width:44px;height:44px;display:flex;'
                    f'align-items:center;justify-content:center;margin-top:8px;">{ns}</div>',
                    unsafe_allow_html=True
                )
            with col_btns:
                st.write("")
                if st.button("✏️ Bewerken", key=f"edit_{label['id']}"):
                    # Laad label terug in de maker
                    st.session_state["edit_label_id"]  = label["id"]
                    st.session_state["ingredients"]    = label.get("ingredients") or []
                    st.session_state["page"]           = "maker"
                    st.rerun()
                if st.button("🗑️ Verwijderen", key=f"del_{label['id']}"):
                    delete_label(label["id"])
                    st.rerun()
            st.markdown("---")

# =============================================
# PAGINA: LABEL MAKER
# =============================================
def page_maker():
    edit_id = st.session_state.get("edit_label_id")
    st.title("✏️ Label bewerken" if edit_id else "🏷️ Nieuw label maken")

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.header("1. Productinformatie")
        product_name   = st.text_input("Productnaam", placeholder="bv. Mueslikoek Bosbes")
        product_weight = st.text_input(
            "Netto hoeveelheid van de verpakking",
            placeholder="bv. 200 g of 6 stuks × 33 g",
            help="De totale inhoud van de verpakking — niet het gewicht van ingrediënten in het recept."
        )

        st.header("2. Ingrediënten toevoegen")
        st.caption("Voeg elk ingrediënt apart toe. Vul het **gewicht in het recept** in.")

        ingredient_name = st.text_input("Zoek ingrediënt in database", placeholder="bv. tomato")
        selected_name   = ingredient_name
        default_values  = {}

        if ingredient_name and not df_db.empty:
            matches = df_db[df_db["Name"].str.contains(ingredient_name,case=False,na=False)]["Name"].tolist()
            if matches:
                choice = st.selectbox("Overeenkomsten:", matches+["➕ Handmatig invoeren"])
                selected_name = ingredient_name if choice=="➕ Handmatig invoeren" else choice
            else:
                st.info("Geen match — vul handmatig in.")

        if selected_name and not df_db.empty and selected_name in df_db["Name"].values:
            r = df_db[df_db["Name"]==selected_name].iloc[0]
            default_values = {
                "Energy_kJ":   r.get("Energy, kilojoules (kJ)",0),
                "Energy_kcal": r.get("Energy, kilocalories (kcal)",0),
                "Fat":         r.get("Fat, total (g)",0),
                "SatFat":      r.get("Fatty acids, saturated (g)",0),
                "Monounsat":   r.get("Fatty acids, monounsaturated (g)",0),
                "Polyunsat":   r.get("Fatty acids, polyunsaturated (g)",0),
                "Carbs":       r.get("Carbohydrates, available (g)",0),
                "Sugar":       r.get("Sugars (g)",0),
                "Fibres":      r.get("Dietary fibres (g)",0),
                "Protein":     r.get("Protein (g)",0),
                "Salt":        r.get("Salt (NaCl) (g)",0),
            }

        if ingredient_name:
            with st.expander(f"📝 Voedingswaarden voor: {selected_name} (per 100 g)", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    energy_kj   = st.number_input("Energie (kJ)",          min_value=0.0,value=float(default_values.get("Energy_kJ",0)))
                    energy_kcal = st.number_input("Energie (kcal)",        min_value=0.0,value=float(default_values.get("Energy_kcal",0)))
                    fat         = st.number_input("Vet totaal (g)",        min_value=0.0,value=float(default_values.get("Fat",0)))
                    satfat      = st.number_input("  w.v. verzadigd (g)",  min_value=0.0,value=float(default_values.get("SatFat",0)))
                    monounsat   = st.number_input("  w.v. enkelvoudig (g)",min_value=0.0,value=float(default_values.get("Monounsat",0)))
                    polyunsat   = st.number_input("  w.v. meervoudig (g)", min_value=0.0,value=float(default_values.get("Polyunsat",0)))
                with c2:
                    carbs   = st.number_input("Koolhydraten (g)",          min_value=0.0,value=float(default_values.get("Carbs",0)))
                    sugar   = st.number_input("  w.v. suikers (g)",        min_value=0.0,value=float(default_values.get("Sugar",0)))
                    fibres  = st.number_input("Vezels (g)",                min_value=0.0,value=float(default_values.get("Fibres",0)))
                    protein = st.number_input("Eiwit (g)",                 min_value=0.0,value=float(default_values.get("Protein",0)))
                    salt    = st.number_input("Zout (g)",                  min_value=0.0,value=float(default_values.get("Salt",0)))
                    st.markdown("---")
                    weight  = st.number_input("⚖️ Gewicht in recept (g)",  min_value=0.0,value=100.0,
                                              help="Hoeveel gram gebruik je van dit ingrediënt in je recept?")
                sel_allerg = st.multiselect("⚠️ Allergenen", ALLERGENEN_LIJST, key=f"allerg_{ingredient_name}")

            if st.button("➕ Ingrediënt toevoegen", type="primary"):
                st.session_state["ingredients"].append({
                    "Name":selected_name,"Energy_kJ":energy_kj,"Energy_kcal":energy_kcal,
                    "Fat":fat,"SatFat":satfat,"Monounsat":monounsat,"Polyunsat":polyunsat,
                    "Carbs":carbs,"Sugar":sugar,"Fibres":fibres,"Protein":protein,
                    "Salt":salt,"Weight":weight,"Allergenen":sel_allerg,
                })
                st.success(f"✅ {selected_name} ({weight} g) toegevoegd!")
                st.rerun()

        if st.session_state["ingredients"]:
            st.subheader("Toegevoegde ingrediënten")
            for i, ing in enumerate(st.session_state["ingredients"]):
                ca, cb = st.columns([4,1])
                with ca:
                    al = f" ⚠️ {', '.join(ing['Allergenen'])}" if ing["Allergenen"] else ""
                    st.write(f"**{ing['Name']}** — {ing['Weight']} g{al}")
                with cb:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state["ingredients"].pop(i); st.rerun()

    with col_right:
        if not st.session_state["ingredients"]:
            st.info("👈 Voeg ingrediënten toe om te beginnen.")
        else:
            # Berekeningen
            total_w = sum(i["Weight"] for i in st.session_state["ingredients"])
            f100    = 100/total_w if total_w else 1
            keys    = ["Energy_kJ","Energy_kcal","Fat","SatFat","Monounsat","Polyunsat",
                       "Carbs","Sugar","Fibres","Protein","Salt"]
            totals  = {k:0.0 for k in keys}
            for ing in st.session_state["ingredients"]:
                for k in keys:
                    totals[k] += ing[k]*ing["Weight"]/100
            per100 = {k:round(v*f100,1) for k,v in totals.items()}

            use_portion  = st.checkbox("Ook per portie berekenen?")
            portion_size = 100; per_portion = None
            if use_portion:
                portion_size = st.number_input("Portiegrootte (g)",value=100,min_value=1)
                per_portion  = {k:round(v*portion_size/100,1) for k,v in per100.items()}

            ns_letter = calc_nutriscore(per100)
            st.header("3. Voedingswaarden & Nutri-Score")
            st.markdown(nutriscore_html(ns_letter),unsafe_allow_html=True)
            st.write("")

            # Tabel
            label_names = [
                ("Energy_kJ","Energie (kJ)"),("Energy_kcal","Energie (kcal)"),
                ("Fat","Vet"),("SatFat","  w.v. verzadigd"),
                ("Monounsat","  w.v. enkelvoudig onverzadigd"),
                ("Polyunsat","  w.v. meervoudig onverzadigd"),
                ("Carbs","Koolhydraten"),("Sugar","  w.v. suikers"),
                ("Fibres","Vezels"),("Protein","Eiwitten"),("Salt","Zout"),
            ]
            rows = []
            for k,name in label_names:
                row = {"Nutriënt":name,"Per 100 g":per100[k]}
                if per_portion:
                    row[f"Per {portion_size} g"] = per_portion[k]
                    if k in RI: row["%RI*"] = f"{round(per_portion[k]/RI[k]*100)}%"
                rows.append(row)
            st.dataframe(pd.DataFrame(rows).set_index("Nutriënt"),use_container_width=True)
            st.caption("*RI = Referentie-inname gemiddelde volwassene (8400 kJ / 2000 kcal)")

            alle_allergenen = set()
            for ing in st.session_state["ingredients"]:
                alle_allergenen.update(ing.get("Allergenen",[]))
            if alle_allergenen:
                st.subheader("⚠️ Allergenen"); st.warning(", ".join(sorted(alle_allergenen)))

            sorted_ings  = sorted(st.session_state["ingredients"],key=lambda x:x["Weight"],reverse=True)
            ing_list_str = ", ".join([i["Name"] for i in sorted_ings])
            st.subheader("Ingrediëntenlijst"); st.info(ing_list_str)

            st.header("4. Opslaan & PDF")
            if not product_name:
                st.warning("Vul eerst een productnaam in.")
            else:
                col_save, col_pdf = st.columns(2)
                with col_save:
                    if st.button("💾 Label opslaan", type="primary", use_container_width=True):
                        save_label({
                            "id":            st.session_state.get("edit_label_id"),
                            "product_name":  product_name,
                            "product_weight":product_weight,
                            "nutriscore":    ns_letter,
                            "ingredients":   st.session_state["ingredients"],
                            "per100":        per100,
                            "portion_size":  portion_size if use_portion else None,
                            "allergenen":    list(alle_allergenen),
                        })
                        st.success("✅ Label opgeslagen!")
                        st.session_state["edit_label_id"] = None

                with col_pdf:
                    if st.button("📄 Genereer PDF", use_container_width=True):
                        pdf_path = generate_pdf(
                            product_name, product_weight, per100, per_portion,
                            portion_size, ns_letter, alle_allergenen, ing_list_str
                        )
                        with open(pdf_path,"rb") as f:
                            st.download_button(
                                "⬇️ Download PDF", f,
                                file_name=f"{product_name.replace(' ','_')}_label.pdf",
                                mime="application/pdf", use_container_width=True
                            )

# =============================================
# PAGINA: KENNISBANK
# =============================================
def page_kennisbank():
    st.title("📖 Kennisbank — EU Voedingslabelregels")
    st.caption("Gebaseerd op EU Verordening nr. 1169/2011")

    with st.expander("📋 Wanneer is een voedingslabel verplicht?", expanded=True):
        st.markdown("""
**Bijna altijd** — elk voorverpakt voedingsmiddel dat in de EU verkocht wordt, moet een voedingslabel hebben.

**Verplicht voor:**
- Alle voorverpakte voedingsproducten (in een verpakking gesloten vóór verkoop)
- Producten verkocht via webshops
- Producten verkocht op markten als ze voorverpakt zijn

**Uitzonderingen (geen label verplicht):**
- Producten verkocht per stuk en ter plekke verpakt op verzoek van de klant
- Kleine verpakkingen met een grootste oppervlak kleiner dan 10 cm² (beperkte info verplicht)
- Alcohol boven 1,2% (geen volledige voedingswaardentabel verplicht)
- Producten van één ingrediënt waarvan de naam gelijk is aan het ingrediënt (bv. een zak appelen)
""")

    with st.expander("📝 Wat moet er verplicht op het label staan?"):
        st.markdown("""
Volgens EU 1169/2011 zijn deze **14 verplichte vermeldingen**:

1. **Naam van het levensmiddel** — de wettelijke of gebruikelijke naam
2. **Ingrediëntenlijst** — in aflopende volgorde van gewicht (grootste eerst)
3. **Allergenen** — vetgedrukt in de ingrediëntenlijst
4. **Netto hoeveelheid** — in gewicht (g/kg) of volume (ml/l)
5. **Minimale houdbaarheidsdatum** — "THT" of "te gebruiken tot"
6. **Bewaaromstandigheden** — indien nodig (bv. "koel bewaren")
7. **Naam en adres van de exploitant** — verantwoordelijke producent/importeur
8. **Land van oorsprong** — voor bepaalde producten (vlees, honing, olijfolie...)
9. **Gebruiksaanwijzing** — indien nodig
10. **Alcoholgehalte** — indien > 1,2%
11. **Voedingswaardentabel** — energie, vet, verzadigd vet, koolhydraten, suikers, eiwitten, zout
12. **Hoeveelheid specifieke ingrediënten** — als benadrukt in naam of afbeelding
13. **Lot- of partijnummer** — voor traceerbaarheid
14. **Verkoopomstandigheden** — indien van toepassing
""")

    with st.expander("⚠️ Regels rond allergenen"):
        st.markdown("""
De **14 verplichte allergenen** moeten altijd duidelijk worden aangegeven:

| Allergeen | Voorbeelden |
|-----------|-------------|
| Gluten | Tarwe, rogge, gerst, haver, spelt |
| Schaaldieren | Garnalen, kreeft, krab |
| Eieren | Ei, eidooier, eiwit |
| Vis | Alle vissoorten |
| Pinda's | Pindakaas, arachideolie |
| Soja | Sojamelk, tofu, miso |
| Melk | Lactose, boter, room, kaas |
| Noten | Amandelen, hazelnoten, cashews, walnoten, pistaches... |
| Selderij | Selderijzaad, -wortel, -blad |
| Mosterd | Mosterdzaad, -poeder |
| Sesamzaad | Tahin, sesamolie |
| Sulfiet/zwaveldioxide | > 10 mg/kg of mg/l |
| Lupine | Lupinebloem, -zaden |
| Weekdieren | Mosselen, oesters, inktvis |

**Hoe aanduiden?** Allergenen moeten **vetgedrukt**, cursief of onderstreept staan in de ingrediëntenlijst zodat ze duidelijk herkenbaar zijn.

**Kruisbesmetting:** Als er risico op kruisbesmetting is, voeg dan toe: *"Kan sporen van X bevatten"*.
""")

    with st.expander("🔢 Voedingswaardentabel — verplichte indeling"):
        st.markdown("""
De voedingswaardentabel moet **altijd per 100 g of 100 ml** worden uitgedrukt.
Optioneel mag je ook waarden per portie toevoegen.

**Verplichte volgorde:**

| Nutriënt | Eenheid |
|----------|---------|
| Energie | kJ én kcal |
| Vet | g |
| waarvan verzadigde vetzuren | g |
| Koolhydraten | g |
| waarvan suikers | g |
| Eiwitten | g |
| Zout | g |

**Optioneel (maar toegestaan):**
- Enkelvoudig en meervoudig onverzadigde vetzuren
- Polyolen
- Zetmeel
- Vezels
- Vitamines en mineralen (alleen als significant aanwezig ≥ 15% RI)

**Minimumlettergrootte:** 1,2 mm voor de x-hoogte (kleine letters). Op verpakkingen < 80 cm² mag dit 0,9 mm zijn.
""")

    with st.expander("🟢 Nutri-Score — wat is het en is het verplicht?"):
        st.markdown("""
**Nutri-Score is momenteel vrijwillig** in België, Nederland en de meeste EU-landen.
De Europese Commissie onderzoekt een verplichte invoering, maar dit is nog niet beslist.

**Hoe werkt de berekening?**

De Nutri-Score kent punten toe op basis van:

*Negatieve punten (meer = slechter):*
- Energie (kcal per 100g)
- Suikers (g per 100g)
- Verzadigde vetzuren (g per 100g)
- Zout (g per 100g)

*Positieve punten (meer = beter):*
- Vezels (g per 100g)
- Eiwitten (g per 100g)
- Groenten, fruit, noten (% per 100g)

**Eindklasse:**
- **A** (donkergroen) = score ≤ -1 → meest gezond
- **B** (lichtgroen) = score 0 t/m 2
- **C** (geel) = score 3 t/m 10
- **D** (oranje) = score 11 t/m 18
- **E** (rood) = score ≥ 19 → minst gezond

**Let op:** er zijn aparte algoritmes voor kaas, vetten/oliën, dranken en water. Deze app berekent het algemene algoritme voor vaste voedingsmiddelen.
""")

    with st.expander("📏 Minimumeisen qua formaat en leesbaarheid"):
        st.markdown("""
- **Taal:** verplicht in de officiële taal van het verkoopland (NL voor België/Nederland)
- **Lettergrootte:** minimaal 1,2 mm x-hoogte; 0,9 mm voor kleine verpakkingen (< 80 cm²)
- **Contrast:** tekst moet leesbaar zijn t.o.v. de achtergrond
- **Locatie:** voedingswaardentabel moet in hetzelfde gezichtsveld als de naam en de netto hoeveelheid staan, of op de achterkant
- **Niet misleidend:** afbeeldingen, namen en beschrijvingen mogen de consument niet misleiden over de aard, samenstelling of herkomst
""")

    st.info("💡 Twijfel je of jouw label compliant is? Raadpleeg altijd een gecertificeerde voedingsdeskundige of het FAVV (België) / NVWA (Nederland) voor definitieve goedkeuring.")

# =============================================
# MAIN ROUTER
# =============================================
sidebar_nav()

page = st.session_state["page"]

if page == "home":
    page_home()
elif page == "login":
    page_login()
elif page == "register":
    page_register()
elif page == "my_labels":
    if not st.session_state["logged_in"]:
        st.warning("Je moet ingelogd zijn om je labels te bekijken.")
        st.session_state["page"]="login"; st.rerun()
    else:
        page_my_labels()
elif page == "maker":
    if not st.session_state["logged_in"]:
        st.warning("Je moet ingelogd zijn om labels te maken.")
        st.session_state["page"]="login"; st.rerun()
    else:
        page_maker()
elif page == "kennis":
    page_kennisbank()
