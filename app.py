import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from PIL import Image
import pytesseract

st.set_page_config(page_title="Analyse Cosmident + Desmos", layout="wide")
st.title("📄 Analyse des actes dentaires Cosmident + Desmos")

uploaded_cosmident = st.file_uploader("Upload le fichier Cosmident (PDF ou image)", type=["pdf", "png", "jpg", "jpeg"])
uploaded_desmos = st.file_uploader("Upload le fichier Desmos (PDF)", type=["pdf"], key="desmos")

def extract_text_from_image(image):
    return pytesseract.image_to_string(image)

def extract_data_from_cosmident(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    lines = full_text.split('\n')
    results = []
    current_patient = None
    for line in lines:
        ref_match = re.search(r'Ref\. ([\w\s\-]+)', line)
        if ref_match:
            current_patient = ref_match.group(1).strip()
        price_match = re.search(r'(\d+\.\d{2}|\d+,\d{2})', line)
        if current_patient and price_match:
            price = price_match.group(1).replace(',', '.')
            if float(price) > 0:
                results.append({'Patient': current_patient, 'Acte Cosmident': line.strip(), 'Prix Cosmident': price})
    return pd.DataFrame(results)

def extract_desmos_acts(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    lines = full_text.split('\n')
    st.subheader("Lignes brutes du PDF Desmos")
    st.write(lines)
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
        elif current_patient:
            if re.search(r'(BIOTECH|Couronne transvissée|HBL\w+|ZIRCONE|GOUTTIÈRE SOUPLE|EMAX|ONLAY|PLAQUE|ADJONCTION|MONTAGE|DENT RESINE)', line, re.IGNORECASE):
                current_acte = line.strip()
            hono_match = re.search(r'Hono\.?\s*:?\s*([\d,\.]+)', line)
            if hono_match:
                current_hono = hono_match.group(1).replace(',', '.')
            price_match = re.search(r'(\d+\.\d{2}|\d+,\d{2})', line)
            if not current_hono and price_match:
                price = price_match.group(1).replace(',', '.')
                if float(price) > 0:
                    current_hono = price
    if current_patient and current_acte and current_hono:
        data.append({'Patient': current_patient, 'Acte Desmos': current_acte.strip(), 'Prix Desmos': current_hono})
    return pd.DataFrame(data)

def match_patient_and_acte(cosmident_patient, df_desmos):
    cosmident_parts = set(cosmident_patient.lower().split())
    for idx, row in df_desmos.iterrows():
        desmos_patient = row['Patient']
        desmos_parts = set(desmos_patient.lower().split())
        if cosmident_patient.lower() == desmos_patient.lower() or len(cosmident_parts & desmos_parts) > 0:
            return row['Acte Desmos'], row['Prix Desmos']
    return "", ""

if uploaded_cosmident and uploaded_desmos:
    df_cosmident = extract_data_from_cosmident(uploaded_cosmident)
    st.subheader("Tableau extrait Cosmident")
    st.dataframe(df_cosmident)

    df_desmos = extract_desmos_acts(uploaded_desmos)
    st.subheader("Tableau extrait Desmos (tous actes détectés)")
    st.dataframe(df_desmos)

    actes_desmos = []
    prix_desmos = []
    debug_match = []
    for patient in df_cosmident['Patient']:
        acte, prix = match_patient_and_acte(patient, df_desmos)
        actes_desmos.append(acte)
        prix_desmos.append(prix)
        debug_match.append(f"Patient Cosmident: {patient} | Acte trouvé: {acte} | Prix trouvé: {prix}")
    df_cosmident['Acte Desmos'] = actes_desmos
    df_cosmident['Prix Desmos'] = prix_desmos

    st.subheader("Debug correspondances patient Cosmident / Desmos")
    st.write(debug_match)

    st.success("✅ Extraction et fusion terminées")
    st.subheader("Tableau fusionné final")
    st.dataframe(df_cosmident, use_container_width=True)
else:
    st.info("Veuillez charger les deux fichiers PDF (Cosmident et Desmos) pour lancer l'analyse.")
