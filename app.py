import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from PIL import Image
import pytesseract
import io

st.set_page_config(page_title="Analyse Cosmident + Desmos", layout="wide")
st.title("📄 Analyse des actes dentaires Cosmident + Desmos")

uploaded_cosmident = st.file_uploader("Upload le fichier Cosmident (PDF ou image)", type=["pdf", "png", "jpg", "jpeg"])
uploaded_desmos = st.file_uploader("Upload le fichier Desmos (PDF)", type=["pdf"], key="desmos")


# =====================
# 🔹 Extraction image
# =====================
def extract_text_from_image(image):
    return pytesseract.image_to_string(image)


# =====================
# 🔹 Extraction Cosmident
# =====================
def extract_data_from_cosmident(file):
    file_bytes = file.read()

    if file.type == "application/pdf":
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as e:
            st.error(f"Erreur ouverture PDF : {e}")
            return pd.DataFrame()

        full_text = ""
        for page in doc:
            page_text = page.get_text("text")

            # Supprime tout ce qui se trouve après certaines mentions typiques du bas de page
            stop_pattern = r'(COSMIDENT|IBAN|Siret|BIC|Tél\.|Total \(Euros\)|TOTAL TTC|Règlement|Chèque|NOS COORDONNÉES BANCAIRES)'
            cut = re.split(stop_pattern, page_text, flags=re.IGNORECASE)
            page_text = cut[0] if cut else page_text

            full_text += page_text + "\n"
    else:
        try:
            image = Image.open(io.BytesIO(file_bytes))
            full_text = extract_text_from_image(image)
        except Exception as e:
            st.error(f"Erreur lecture image : {e}")
            return pd.DataFrame()

    # Debug : aperçu du texte brut
    st.expander("🧩 Aperçu du texte extrait (Cosmident brut)").write(full_text[:2000])

    # Nettoyage
    lines = full_text.split('\n')
    clean_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Ignore teintes, mentions inutiles et bas de page
        if re.search(r'(teinte|couleur|A[1-3]|B[1-3]|C[1-3]|D[1-3])', line, re.IGNORECASE):
            continue
        if re.search(r'(COSMIDENT|IBAN|Siret|BIC|€|Total \(Euros\)|TOTAL TTC|CHÈQUE)', line, re.IGNORECASE):
            continue
        clean_lines.append(line)

    results = []
    current_patient = None
    i = 0

    while i < len(clean_lines):
        line = clean_lines[i]
        i += 1

        # Détection du patient
        ref_match = re.search(r'Ref\. ([\w\s\-]+)', line)
        if not ref_match:
            bon_match = re.match(r'Bon n°\d+ du [\w\d/]+.*Prescription \d+', line)
            if bon_match and i < len(clean_lines):
                next_line = clean_lines[i].strip()
                ref_match = re.search(r'Ref\. ([\w\s\-]+)', next_line)
                if ref_match:
                    current_patient = ref_match.group(1).strip()
                    i += 1
                    continue
        if ref_match:
            current_patient = ref_match.group(1).strip()
            continue
        if current_patient is None:
            continue

        # =====================
        # 🔧 Correction Dominique : détection prix total
        # =====================
        description = line
        found_total = None
        found_price = None
        quantity = 1

        while i < len(clean_lines):
            next_line = clean_lines[i].strip()
            i += 1
            if not next_line:
                continue

            # Si nouvelle section ou patient détecté → stop
            if re.search(r'(Ref\.|Bon n°|Prescription|Total \(Euros\))', next_line, re.IGNORECASE):
                break

            # Si la ligne contient un prix numérique
            if re.match(r'^\d+[\.,]\d{2}$', next_line):
                if found_price is None:
                    found_price = float(next_line.replace(',', '.'))
                    continue
                elif found_total is None:
                    found_total = float(next_line.replace(',', '.'))
                    continue
            else:
                description += " " + next_line

        # Déduit la quantité de dents mentionnées
        dents_match = re.findall(r'\b\d{2}\b', description)
        if dents_match:
            quantity = len(dents_match)

        # Si pas de total explicite, on le calcule
        if found_price and not found_total:
            found_total = found_price * quantity

        # Ajout de la ligne si cohérente
        if found_total and found_total > 0 and found_price and found_price > 0:
            results.append({
                'Patient': current_patient,
                'Acte Cosmident': description.strip(),
                'Prix Cosmident': f"{found_total:.2f}"
            })

    return pd.DataFrame(results)


# =====================
# 🔹 Extraction Desmos
# =====================
def extract_desmos_acts(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    lines = full_text.split('\n')
    data = []
    current_patient = None
    current_acte = ""
    current_hono = ""
    for idx, line in enumerate(lines):
        patient_match = re.search(r'Ref\. ([A-ZÉÈÇÂÊÎÔÛÄËÏÖÜÀÙa-zéèçâêîôûäëïöüàù\s\-]+)', line)
        if patient_match:
            if current_patient and current_acte and current_hono:
                data.append({'Patient': current_patient, 'Acte Desmos': current_acte.strip(), 'Prix Desmos': current_hono})
            current_patient = patient_match.group(1).strip()
            current_acte = ""
            current_hono = ""
        elif re.search(r'(BIOTECH|Couronne transvissée|HBL\w+|ZIRCONE|GOUTTIÈRE SOUPLE|EMAX|ONLAY|PLAQUE|ADJONCTION|MONTAGE|DENT RESINE)', line, re.IGNORECASE):
            current_acte = line.strip()
            current_hono = ""
        elif "Hono" in line:
            hono_match = re.search(r'Hono\.?\s*:?\s*([\d,\.]+)', line)
            if hono_match:
                current_hono = hono_match.group(1).replace(',', '.')
        elif current_acte and re.match(r'^\d+[\.,]\d{2}$', line):
            current_hono = line.replace(',', '.')
    if current_patient and current_acte and current_hono:
        data.append({'Patient': current_patient, 'Acte Desmos': current_acte.strip(), 'Prix Desmos': current_hono})
    return pd.DataFrame(data)


# =====================
# 🔹 Matching Cosmident / Desmos
# =====================
def match_patient_and_acte(cosmident_patient, df_desmos):
    cosmident_parts = set(cosmident_patient.lower().split())
    for idx, row in df_desmos.iterrows():
        desmos_patient = row['Patient']
        desmos_parts = set(desmos_patient.lower().split())
        if cosmident_patient.lower() == desmos_patient.lower() or len(cosmident_parts & desmos_parts) > 0:
            return row['Acte Desmos'], row['Prix Desmos']
    return "", ""


# =====================
# 🔹 Interface principale
# =====================
if uploaded_cosmident and uploaded_desmos:
    df_cosmident = extract_data_from_cosmident(uploaded_cosmident)
    df_desmos = extract_desmos_acts(uploaded_desmos)

    actes_desmos = []
    prix_desmos = []
    for patient in df_cosmident['Patient']:
        acte, prix = match_patient_and_acte(patient, df_desmos)
        actes_desmos.append(acte)
        prix_desmos.append(prix)

    df_cosmident['Acte Desmos'] = actes_desmos
    df_cosmident['Prix Desmos'] = prix_desmos

    st.success("✅ Extraction et fusion terminées")
    st.dataframe(df_cosmident, use_container_width=True)
else:
    st.info("Veuillez charger les deux fichiers PDF (Cosmident et Desmos) pour lancer l'analyse.")
