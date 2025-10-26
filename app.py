import streamlit as st
import fitz
import re
import pandas as pd

st.set_page_config(page_title="Analyse actes Desmos", layout="wide")
st.title("📄 Extraction des actes du fichier Desmos")

uploaded_desmos = st.file_uploader("Upload le fichier Desmos (PDF)", type=["pdf"], key="desmos")

def extract_desmos_acts(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    lines = full_text.split('\n')
    data = []
    current_patient = None
    for idx, line in enumerate(lines):
        patient_match = re.search(r'Ref\. ([A-ZÉÈÇÂÊÎÔÛÄËÏÖÜÀÙa-zéèçâêîôûäëïöüàù\s\-]+)', line)
        if patient_match:
            current_patient = patient_match.group(1).strip()
        # Cherche un intitulé d'acte (ex : BIOTECH, Couronne, HBL, ZIRCONE, etc.)
        if current_patient and re.search(r'(BIOTECH|Couronne|HBL\w+|ZIRCONE|GOUTTIÈRE SOUPLE|EMAX|ONLAY|PLAQUE|ADJONCTION|MONTAGE|DENT RESINE)', line, re.IGNORECASE):
            acte = line.strip()
            # Cherche prix sur la même ligne ou la suivante
            price_match = re.search(r'(\d+\.\d{2}|\d+,\d{2})', line)
            prix = price_match.group(1).replace(',', '.') if price_match else ""
            if not prix and idx + 1 < len(lines):
                next_line = lines[idx + 1]
                price_match = re.search(r'(\d+\.\d{2}|\d+,\d{2})', next_line)
                if price_match:
                    prix = price_match.group(1).replace(',', '.')
            data.append({'Patient': current_patient, 'Acte': acte, 'Prix': prix})
    return pd.DataFrame(data)

if uploaded_desmos:
    df_desmos = extract_desmos_acts(uploaded_desmos)
    st.success("✅ Extraction terminée")
    st.dataframe(df_desmos, use_container_width=True)
else:
    st.info("Veuillez charger le fichier PDF Desmos pour lancer l'analyse.")
