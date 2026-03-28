import streamlit as st
import pandas as pd
import os
from reportlab.pdfgen import canvas

BASE_DIR = os.path.dirname(__file__)
DATABASE_FILE = os.path.join(BASE_DIR, "TRYOUT1a.xlsx")

st.set_page_config(page_title="EU Voedingslabel Generator", page_icon="🍴", layout="wide")
st.title("🍴 EU Voedingslabel Generator")
st.caption("Genereer conforme voedingslabels volgens EU Verordening 1169/2011")

@st.cache_data
def load_database():
    if os.path.exists(DATABASE_FILE):
        return pd.read_excel(DATABASE_FILE)
    return pd.DataFrame()

df_db = load_database()

if 'ingredients' not in st.session_state:
    st.session_state['ingredients'] = []

ALLERGENEN = [
    "Gluten (tarwe, rogge, gerst, haver...)",
    "Schaaldieren", "Eieren", "Vis", "Pinda's", "Soja", "Melk/lactose",
    "Noten (amandelen, hazelnoten, walnoten...)", "Selderij", "Mosterd",
    "Sesamzaad", "Zwaveldioxide/sulfiet (>10 mg/kg)", "Lupine", "Weekdieren",
]

RI = {'Energy_kcal': 2000, 'Energy_kJ': 8400, 'Fat': 70, 'SatFat': 20,
      'Carbs': 260, 'Sugar': 90, 'Protein': 50, 'Salt': 6}

def get_pts(val, thresholds):
    return sum(1 for t in thresholds if val > t)

def calc_nutriscore(v):
    neg = (get_pts(v['Energy_kcal'], [335,670,1005,1340,1675,2010,2345,2680,3015,3350]) +
           get_pts(v['Sugar'],       [4.5,9,13.5,18,22.5,27,31,36,40,45]) +
           get_pts(v['SatFat'],      [1,2,3,4,5,6,7,8,9,10]) +
           get_pts(v['Salt'],        [0.2,0.4,0.6,0.8,1.0,1.2,1.4,1.6,1.8,2.0]))
    fib = get_pts(v['Fibres'],  [0.9,1.9,2.8,3.7,4.7])
    pro = get_pts(v['Protein'], [1.6,3.2,4.8,6.4,8.0])
    score = neg - fib if neg >= 11 else neg - fib - pro
    if score <= -1:   return "A"
    elif score <= 2:  return "B"
    elif score <= 10: return "C"
    elif score <= 18: return "D"
    else:             return "E"

def nutriscore_html(active_letter):
    colors  = {'A':'#1e7e34','B':'#85bb2f','C':'#f5c100','D':'#f07921','E':'#dc3a20'}
    txt_clr = {'A':'#fff','B':'#fff','C':'#333','D':'#fff','E':'#fff'}
    html = (
        '<div style="display:inline-flex;flex-direction:column;align-items:center;'
        'background:#ebebeb;border-radius:10px;padding:8px 12px 8px;">'
        '<div style="font-size:11px;font-weight:700;color:#555;letter-spacing:1px;margin-bottom:5px;">'
        'NUTRI-SCORE</div>'
        '<div style="display:flex;align-items:flex-end;gap:2px;">'
    )
    for letter in ['A','B','C','D','E']:
        active = letter == active_letter
        bg = colors[letter]
        tc = txt_clr[letter]
        if active:
            html += (
                f'<div style="display:flex;align-items:center;justify-content:center;'
                f'background:{bg};border-radius:50px;width:46px;height:54px;'
                f'border:3px solid white;box-shadow:0 0 0 2px {bg};'
                f'margin-bottom:-3px;position:relative;z-index:2;">'
                f'<span style="font-size:28px;font-weight:900;color:{tc};line-height:1;">{letter}</span>'
                f'</div>'
            )
        else:
            html += (
                f'<div style="display:flex;align-items:center;justify-content:center;'
                f'background:{bg};border-radius:5px;width:34px;height:38px;opacity:0.7;">'
                f'<span style="font-size:18px;font-weight:700;color:{tc};line-height:1;">{letter}</span>'
                f'</div>'
            )
    html += '</div></div>'
    return html

# =============================================
# UI
# =============================================
col_left, col_right = st.columns([1, 1])

with col_left:
    st.header("1. Productinformatie")
    product_name = st.text_input("Productnaam (verplicht op label)", placeholder="bv. Mueslikoek Bosbes")
    product_weight = st.text_input(
        "Netto hoeveelheid van de verpakking",
        placeholder="bv. 200 g  of  6 stuks × 33 g",
        help="De totale inhoud van de verpakking zoals op de voorkant staat — bv. '200 g' of '6 stuks'. Niet het gewicht van ingrediënten in het recept."
    )

    st.header("2. Ingrediënten toevoegen")
    st.caption("Voeg elk ingrediënt apart toe. Vul het **gewicht in het recept** in — hoeveel gram je ervan gebruikt.")

    ingredient_name = st.text_input("Zoek ingrediënt in database", placeholder="bv. tomato")
    selected_name   = ingredient_name
    default_values  = {}

    if ingredient_name and not df_db.empty:
        matches = df_db[df_db['Name'].str.contains(ingredient_name, case=False, na=False)]['Name'].tolist()
        if matches:
            choice = st.selectbox("Overeenkomsten:", matches + ["➕ Handmatig invoeren"])
            selected_name = ingredient_name if choice == "➕ Handmatig invoeren" else choice
        else:
            st.info("Geen match gevonden — vul handmatig in.")

    if selected_name and not df_db.empty and selected_name in df_db['Name'].values:
        row_data = df_db[df_db['Name'] == selected_name].iloc[0]
        default_values = {
            'Energy_kJ':   row_data.get('Energy, kilojoules (kJ)', 0),
            'Energy_kcal': row_data.get('Energy, kilocalories (kcal)', 0),
            'Fat':         row_data.get('Fat, total (g)', 0),
            'SatFat':      row_data.get('Fatty acids, saturated (g)', 0),
            'Monounsat':   row_data.get('Fatty acids, monounsaturated (g)', 0),
            'Polyunsat':   row_data.get('Fatty acids, polyunsaturated (g)', 0),
            'Carbs':       row_data.get('Carbohydrates, available (g)', 0),
            'Sugar':       row_data.get('Sugars (g)', 0),
            'Fibres':      row_data.get('Dietary fibres (g)', 0),
            'Protein':     row_data.get('Protein (g)', 0),
            'Salt':        row_data.get('Salt (NaCl) (g)', 0),
        }

    if ingredient_name:
        with st.expander(f"📝 Voedingswaarden voor: {selected_name}  (per 100 g)", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                energy_kj   = st.number_input("Energie (kJ)",           min_value=0.0, value=float(default_values.get('Energy_kJ',   0)))
                energy_kcal = st.number_input("Energie (kcal)",         min_value=0.0, value=float(default_values.get('Energy_kcal', 0)))
                fat         = st.number_input("Vet totaal (g)",         min_value=0.0, value=float(default_values.get('Fat',         0)))
                satfat      = st.number_input("  w.v. verzadigd (g)",   min_value=0.0, value=float(default_values.get('SatFat',      0)))
                monounsat   = st.number_input("  w.v. enkelvoudig (g)", min_value=0.0, value=float(default_values.get('Monounsat',   0)))
                polyunsat   = st.number_input("  w.v. meervoudig (g)",  min_value=0.0, value=float(default_values.get('Polyunsat',   0)))
            with c2:
                carbs   = st.number_input("Koolhydraten (g)",           min_value=0.0, value=float(default_values.get('Carbs',   0)))
                sugar   = st.number_input("  w.v. suikers (g)",         min_value=0.0, value=float(default_values.get('Sugar',   0)))
                fibres  = st.number_input("Vezels (g)",                 min_value=0.0, value=float(default_values.get('Fibres',  0)))
                protein = st.number_input("Eiwit (g)",                  min_value=0.0, value=float(default_values.get('Protein', 0)))
                salt    = st.number_input("Zout (g)",                   min_value=0.0, value=float(default_values.get('Salt',    0)))
                st.markdown("---")
                weight = st.number_input(
                    "⚖️ Gewicht in recept (g)",
                    min_value=0.0, value=100.0,
                    help="Hoeveel gram gebruik je van dit ingrediënt in jouw recept? Bv. 250 g tarwebloem → vul 250 in."
                )
            selected_allergenen = st.multiselect(
                "⚠️ Allergenen aanwezig in dit ingrediënt", ALLERGENEN,
                key=f"allerg_{ingredient_name}"
            )

        if st.button("➕ Ingrediënt toevoegen aan lijst", type="primary"):
            st.session_state['ingredients'].append({
                'Name': selected_name, 'Energy_kJ': energy_kj, 'Energy_kcal': energy_kcal,
                'Fat': fat, 'SatFat': satfat, 'Monounsat': monounsat, 'Polyunsat': polyunsat,
                'Carbs': carbs, 'Sugar': sugar, 'Fibres': fibres, 'Protein': protein,
                'Salt': salt, 'Weight': weight, 'Allergenen': selected_allergenen,
            })
            st.success(f"✅ {selected_name} ({weight} g) toegevoegd!")
            st.rerun()

    if st.session_state['ingredients']:
        st.subheader("Toegevoegde ingrediënten")
        for i, ing in enumerate(st.session_state['ingredients']):
            ca, cb = st.columns([4, 1])
            with ca:
                allerg_str = f" ⚠️ {', '.join(ing['Allergenen'])}" if ing['Allergenen'] else ""
                st.write(f"**{ing['Name']}** — {ing['Weight']} g{allerg_str}")
            with cb:
                if st.button("🗑️", key=f"del_{i}"):
                    st.session_state['ingredients'].pop(i)
                    st.rerun()

with col_right:
    if not st.session_state['ingredients']:
        st.info("👈 Voeg ingrediënten toe via de linkerkolom.")
    else:
        total_weight = sum(i['Weight'] for i in st.session_state['ingredients'])
        f100 = 100 / total_weight if total_weight else 1
        keys = ['Energy_kJ','Energy_kcal','Fat','SatFat','Monounsat','Polyunsat',
                'Carbs','Sugar','Fibres','Protein','Salt']
        totals = {k: 0.0 for k in keys}
        for ing in st.session_state['ingredients']:
            for k in keys:
                totals[k] += ing[k] * ing['Weight'] / 100
        per100 = {k: round(v * f100, 1) for k, v in totals.items()}

        use_portion = st.checkbox("Ook per portie berekenen?")
        portion_size = 100
        per_portion  = None
        if use_portion:
            portion_size = st.number_input("Portiegrootte (g)", value=100, min_value=1)
            per_portion  = {k: round(v * portion_size / 100, 1) for k, v in per100.items()}

        ns_letter = calc_nutriscore(per100)
        st.header("3. Voedingswaarden & Nutri-Score")
        st.markdown(nutriscore_html(ns_letter), unsafe_allow_html=True)
        st.write("")

        label_names = [
            ('Energy_kJ',   'Energie (kJ)'),
            ('Energy_kcal', 'Energie (kcal)'),
            ('Fat',         'Vet'),
            ('SatFat',      '  w.v. verzadigd'),
            ('Monounsat',   '  w.v. enkelvoudig onverzadigd'),
            ('Polyunsat',   '  w.v. meervoudig onverzadigd'),
            ('Carbs',       'Koolhydraten'),
            ('Sugar',       '  w.v. suikers'),
            ('Fibres',      'Vezels'),
            ('Protein',     'Eiwitten'),
            ('Salt',        'Zout'),
        ]
        rows = []
        for k, name in label_names:
            row = {'Nutriënt': name, 'Per 100 g': per100[k]}
            if per_portion:
                row[f'Per {portion_size} g'] = per_portion[k]
                if k in RI:
                    row['%RI*'] = f"{round(per_portion[k]/RI[k]*100)}%"
            rows.append(row)
        st.dataframe(pd.DataFrame(rows).set_index('Nutriënt'), use_container_width=True)
        st.caption("*RI = Referentie-inname gemiddelde volwassene (8400 kJ / 2000 kcal)")

        alle_allergenen = set()
        for ing in st.session_state['ingredients']:
            alle_allergenen.update(ing.get('Allergenen', []))
        if alle_allergenen:
            st.subheader("⚠️ Allergenen")
            st.warning(", ".join(sorted(alle_allergenen)))

        sorted_ings  = sorted(st.session_state['ingredients'], key=lambda x: x['Weight'], reverse=True)
        ing_list_str = ", ".join([i['Name'] for i in sorted_ings])
        st.subheader("Ingrediëntenlijst (aflopend gewicht)")
        st.info(ing_list_str)

        # =============================================
        # PDF
        # =============================================
        st.header("4. Genereer EU-label PDF")
        if not product_name:
            st.warning("Vul eerst een productnaam in (linkerkolom).")
        else:
            if st.button("📄 Genereer EU-label PDF", type="primary"):
                pdf_path = os.path.join(BASE_DIR, "eu_label.pdf")

                # ── Paginagrootte & vaste kolomposities ──────────────────────
                W, H    = 300, 600
                MARGIN  = 14
                RR      = W - MARGIN          # rechterrand inhoud

                # Vier kolommen rechts uitgelijnd:
                # [naam nutriënt] ... [per 100g] [per portie] [%RI]
                # Bij geen portie: alleen [per 100g]
                if per_portion:
                    C_100  = 175   # rechts uitgelijnd "per 100g" waarde
                    C_PORT = 230   # rechts uitgelijnd "per portie" waarde
                    C_RI   = RR    # rechts uitgelijnd "%RI" waarde
                else:
                    C_100  = RR
                    C_PORT = None
                    C_RI   = None

                ROW_H  = 13        # rijhoogte in de tabel
                FSUB   = 7         # kleine subletters

                # ── Hulpfuncties ─────────────────────────────────────────────
                def hline(cv, y, lw=0.5, gray=0.0):
                    cv.setLineWidth(lw)
                    cv.setStrokeColorRGB(gray, gray, gray)
                    cv.line(MARGIN, y, RR, y)
                    cv.setStrokeColorRGB(0, 0, 0)

                def wrap_and_draw(cv, text, x, y, max_w, font, size, lh):
                    cv.setFont(font, size)
                    words = text.split(" ")
                    line = ""
                    for word in words:
                        test = (line + " " + word).strip()
                        if cv.stringWidth(test, font, size) <= max_w:
                            line = test
                        else:
                            cv.drawString(x, y, line)
                            y -= lh
                            line = word
                    if line:
                        cv.drawString(x, y, line)
                        y -= lh
                    return y

                def tabel_rij(cv, label, v100, vport=None, ri_pct=None,
                               bold=False, y_pos=0, indent=False):
                    """Één tabelrij met vaste kolomposities en dunne scheidingslijn."""
                    font = "Helvetica-Bold" if bold else "Helvetica"
                    cv.setFont(font, 8)
                    cv.setFillColorRGB(0, 0, 0)
                    cv.drawString(MARGIN + (10 if indent else 0), y_pos, label)
                    cv.drawRightString(C_100, y_pos, str(v100))
                    if C_PORT and vport is not None:
                        cv.setFont("Helvetica", 8)
                        cv.drawRightString(C_PORT, y_pos, str(vport))
                    if C_RI and ri_pct is not None:
                        cv.setFont("Helvetica", 8)
                        cv.drawRightString(C_RI, y_pos, ri_pct)
                    # dunne scheidingslijn 3pt onder baseline
                    hline(cv, y_pos - 3, lw=0.3, gray=0.75)
                    return y_pos - ROW_H

                # ── Canvas aanmaken ───────────────────────────────────────────
                c = canvas.Canvas(pdf_path, pagesize=(W, H))
                c.setFillColorRGB(1, 1, 1)
                c.rect(0, 0, W, H, fill=1, stroke=0)
                c.setFillColorRGB(0, 0, 0)

                # ══════════════════════════════════════════════════════════════
                # NUTRI-SCORE BALK
                # Conform referentie: gekleurde blokken naast elkaar,
                # actieve letter in een witte pill die uitsteekt.
                # ══════════════════════════════════════════════════════════════
                NS_COLORS = {
                    'A': (0.102, 0.494, 0.224),   # donkergroen
                    'B': (0.416, 0.671, 0.125),   # lichtgroen
                    'C': (0.961, 0.753, 0.0),     # geel
                    'D': (0.910, 0.447, 0.047),   # oranje
                    'E': (0.753, 0.224, 0.169),   # rood
                }
                NS_DARK_TXT = {'C'}   # geel → donkere letter

                # Label "NUTRI-SCORE"
                c.setFont("Helvetica-Bold", 7)
                c.setFillColorRGB(0.3, 0.3, 0.3)
                c.drawCentredString(W / 2, H - 12, "NUTRI-SCORE")
                c.setFillColorRGB(0, 0, 0)

                # Blokafmetingen — alle blokken zijn even breed/hoog,
                # de actieve letter krijgt een witte pill-rand die uitsteekt
                BLK_W   = 38    # breedte elk blok
                BLK_H   = 34    # hoogte inactieve blokken
                ACT_H   = 44    # hoogte actieve pill (steekt 5pt boven en onder uit)
                GAP     = 3
                total_w = 5 * BLK_W + 4 * GAP
                bx0     = (W - total_w) / 2
                # Onderkant van alle blokken gelijklijnen
                BAR_BOTTOM = H - 58

                x_cur = bx0
                for letter in ['A', 'B', 'C', 'D', 'E']:
                    active = letter == ns_letter
                    r, g, b = NS_COLORS[letter]

                    if active:
                        # 1. Witte pill iets groter → geeft witte rand
                        c.setFillColorRGB(1, 1, 1)
                        c.roundRect(x_cur - 3, BAR_BOTTOM - 5,
                                    BLK_W + 6, ACT_H + 4, 8, fill=1, stroke=0)
                        # 2. Gekleurde pill
                        c.setFillColorRGB(r, g, b)
                        c.roundRect(x_cur, BAR_BOTTOM - 3,
                                    BLK_W, ACT_H, 6, fill=1, stroke=0)
                        fs = 20
                        letter_y = BAR_BOTTOM - 3 + ACT_H / 2 - fs * 0.35
                    else:
                        # Inactief blok: iets transparant via lichtere kleur (mix met wit)
                        # ReportLab kent geen opacity, dus we mengen de kleur met wit
                        alpha = 0.72
                        rc = r + (1 - r) * (1 - alpha)
                        gc = g + (1 - g) * (1 - alpha)
                        bc = b + (1 - b) * (1 - alpha)
                        c.setFillColorRGB(rc, gc, bc)
                        c.roundRect(x_cur, BAR_BOTTOM, BLK_W, BLK_H, 5, fill=1, stroke=0)
                        fs = 14
                        letter_y = BAR_BOTTOM + BLK_H / 2 - fs * 0.35

                    # Letter tekenen
                    if letter in NS_DARK_TXT:
                        tc = (0.15, 0.15, 0.15)
                    else:
                        tc = (1.0, 1.0, 1.0) if active else (0.95, 0.95, 0.95)
                    c.setFillColorRGB(*tc)
                    c.setFont("Helvetica-Bold", fs)
                    c.drawCentredString(x_cur + BLK_W / 2, letter_y, letter)

                    x_cur += BLK_W + GAP

                c.setFillColorRGB(0, 0, 0)

                # ══════════════════════════════════════════════════════════════
                # PRODUCTNAAM
                # ══════════════════════════════════════════════════════════════
                y = BAR_BOTTOM - 14
                hline(c, y + 2, lw=1.5)
                y -= 13
                c.setFont("Helvetica-Bold", 12)
                c.drawCentredString(W / 2, y, product_name)
                y -= 11
                if product_weight:
                    c.setFont("Helvetica", 8)
                    c.drawCentredString(W / 2, y, f"Netto hoeveelheid: {product_weight}")
                    y -= 10

                # ══════════════════════════════════════════════════════════════
                # VOEDINGSWAARDEN — KOLOMKOPPEN
                # ══════════════════════════════════════════════════════════════
                y -= 4
                hline(c, y, lw=1.5)
                y -= 13

                c.setFont("Helvetica-Bold", 10)
                c.setFillColorRGB(0, 0, 0)
                c.drawString(MARGIN, y, "Voedingswaarde")

                # Kolomkoppen uitgelijnd op dezelfde kolommen als de waarden
                c.setFont("Helvetica", FSUB)
                c.drawRightString(C_100, y, "per 100 g")
                if per_portion:
                    c.drawRightString(C_PORT, y, f"per portie ({portion_size} g)")
                    c.drawRightString(C_RI,   y, "%RI*")

                y -= 5
                hline(c, y, lw=0.8)
                y -= ROW_H

                # ══════════════════════════════════════════════════════════════
                # ENERGIE — twee aparte regels (kJ en kcal) zodat geen overlap
                # ══════════════════════════════════════════════════════════════
                ri_e = f"{round(per_portion['Energy_kcal'] / RI['Energy_kcal'] * 100)}%" if per_portion else None

                # Regel 1: kJ
                c.setFont("Helvetica-Bold", 8)
                c.setFillColorRGB(0, 0, 0)
                c.drawString(MARGIN, y, "Energie")
                c.drawRightString(C_100, y, f"{per100['Energy_kJ']} kJ")
                if per_portion:
                    c.setFont("Helvetica", 8)
                    c.drawRightString(C_PORT, y, f"{per_portion['Energy_kJ']} kJ")
                    if C_RI:
                        c.drawRightString(C_RI, y, ri_e)
                y -= ROW_H - 2

                # Regel 2: kcal (inspringen, geen label)
                c.setFont("Helvetica", 8)
                c.drawRightString(C_100, y, f"{per100['Energy_kcal']} kcal")
                if per_portion:
                    c.drawRightString(C_PORT, y, f"{per_portion['Energy_kcal']} kcal")
                hline(c, y - 3, lw=0.3, gray=0.75)
                y -= ROW_H

                # ══════════════════════════════════════════════════════════════
                # OVERIGE TABELRIJEN
                # ══════════════════════════════════════════════════════════════
                rows_def = [
                    ("Vet",                          'Fat',       True,  False),
                    ("w.v. verzadigde vetzuren",     'SatFat',    False, True),
                    ("w.v. enkelvoudig onverzadigd", 'Monounsat', False, True),
                    ("w.v. meervoudig onverzadigd",  'Polyunsat', False, True),
                    ("Koolhydraten",                 'Carbs',     True,  False),
                    ("w.v. suikers",                 'Sugar',     False, True),
                    ("Vezels",                       'Fibres',    True,  False),
                    ("Eiwitten",                     'Protein',   True,  False),
                    ("Zout",                         'Salt',      True,  False),
                ]
                for lbl, key, bold, indent in rows_def:
                    v100_str  = f"{per100[key]} g"
                    vport_str = f"{per_portion[key]} g" if per_portion else None
                    ri_str    = (f"{round(per_portion[key]/RI[key]*100)}%"
                                 if per_portion and key in RI else None)
                    y = tabel_rij(c, lbl, v100_str, vport_str, ri_str,
                                  bold=bold, y_pos=y, indent=indent)

                # ══════════════════════════════════════════════════════════════
                # RI-VOETNOOT
                # ══════════════════════════════════════════════════════════════
                y -= 3
                hline(c, y, lw=0.6)
                y -= 9
                c.setFont("Helvetica", 6)
                c.setFillColorRGB(0, 0, 0)
                c.drawString(MARGIN, y,
                             "*RI = Referentie-inname gemiddelde volwassene (8400 kJ / 2000 kcal)")
                y -= 12

                # ══════════════════════════════════════════════════════════════
                # ALLERGENEN  — lijn BOVEN de sectie, niet door de tekst
                # ══════════════════════════════════════════════════════════════
                hline(c, y, lw=0.8)
                y -= 11
                c.setFont("Helvetica-Bold", 8)
                c.setFillColorRGB(0, 0, 0)
                c.drawString(MARGIN, y, "Bevat:")
                y -= 10
                allerg_str = (", ".join(sorted(alle_allergenen))
                              if alle_allergenen else "Geen allergenen")
                y = wrap_and_draw(c, allerg_str, MARGIN, y,
                                  RR - MARGIN, "Helvetica", 7, 9)

                # ══════════════════════════════════════════════════════════════
                # INGREDIËNTEN  — lijn BOVEN de sectie, niet door de tekst
                # ══════════════════════════════════════════════════════════════
                y -= 3
                hline(c, y, lw=0.8)
                y -= 11
                c.setFont("Helvetica-Bold", 8)
                c.setFillColorRGB(0, 0, 0)
                c.drawString(MARGIN, y, "Ingrediënten:")
                y -= 10
                y = wrap_and_draw(c, ing_list_str, MARGIN, y,
                                  RR - MARGIN, "Helvetica", 7, 9)

                # ══════════════════════════════════════════════════════════════
                # BUITENRAND
                # ══════════════════════════════════════════════════════════════
                bottom = max(y - 8, 6)
                c.setStrokeColorRGB(0, 0, 0)
                c.setLineWidth(1.2)
                c.rect(6, bottom, W - 12, H - bottom - 6)

                c.save()
                st.success("✅ PDF aangemaakt!")
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        label="⬇️ Download EU-label PDF",
                        data=f,
                        file_name=f"{product_name.replace(' ','_')}_label.pdf",
                        mime="application/pdf"
                    )
