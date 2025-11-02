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
    if file.type == "application/pdf":
        doc = fitz.open(stream=file.read(), filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
    else:
        image = Image.open(file)
        full_text = extract_text_from_image(image)
    lines = full_text.split('\n')
    results = []
    current_patient = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        ref_match = re.search(r'Ref\. ([\w\s\-]+)', line)
        if not ref_match:
            bon_match = re.match(r'Bon n°\d+ du [\w\d/]+.*Prescription \d+', line)
            if bon_match and i < len(lines):
                next_line = lines[i].strip()
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
        description = line
        while i < len(lines):
            next_line = lines[i].strip()
            i += 1
            if not next_line:
                continue
            if re.match(r'^\d+\.\d{2}$', next_line):
                quantity = next_line
                price = ""
                while i < len(lines):
                    price_line = lines[i].strip()
                    i += 1
                    if price_line and re.match(r'^\d+\.\d{2}$', price_line):
                        price = price_line
                        break
                remise = ""
                while i < len(lines):
                    remise_line = lines[i].strip()
                    i += 1
                    remise = remise_line if remise_line else "0.00"
                    break
                total = ""
                while i < len(lines):
                    total_line = lines[i].strip()
                    i += 1
                    if total_line and re.match(r'^\d+\.\d{2}$', total_line):
                        total = total_line
                        break
                dents_match = re.findall(r'\b\d{2}\b', description)
                dents = ", ".join(dents_match) if dents_match else ""
                try:
                    price_float = float(price)
                    total_float = float(total)
                    if price_float > 0 and total_float > 0:
                        results.append({
                            'Patient': current_patient,
                            'Acte Cosmident': description,
                            'Prix Cosmident': price
                        })
                except ValueError:
                    pass
                break
            else:
                description += " " + next_line
    return pd.DataFrame(results)

def extract_desmos_acts(file):
    """Extrait uniquement les actes pour les patients HBL, sans prix."""
    doc = fitz.open(stream=file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    lines = full_text.split('\n')
    data = []
    current_patient = None
    current_acte = ""
    for line in lines:
        patient_match = re.search(r'Ref\. (HBL\w+)', line)  # Seulement HBL
        if patient_match:
            if current_patient and current_acte:
                data.append({'Patient': current_patient, 'Acte Desmos': current_acte.strip()})
            current_patient = patient_match.group(1).strip()
            current_acte = ""
        elif current_patient and re.search(r'(BIOTECH|Couronne transvissée|ZIRCONE|GOUTTIÈRE SOUPLE|EMAX|ONLAY|PLAQUE|ADJONCTION|MONTAGE|DENT RESINE|HBL\w+)', line, re.IGNORECASE):
            current_acte = line.strip()
    if current_patient and current_acte:
        data.append({'Patient': current_patient, 'Acte Desmos': current_acte.strip()})
    return pd.DataFrame(data)

def match_patient_and_acte(cosmident_patient, df_desmos):
    for idx, row in df_desmos.iterrows():
        if cosmident_patient.lower() == row['Patient'].lower():
            return row['Acte Desmos']
    return ""

if uploaded_cosmident and uploaded_desmos:
    df_cosmident = extract_data_from_cosmident(uploaded_cosmident)
    df_desmos = extract_desmos_acts(uploaded_desmos)
    actes_desmos = [match_patient_and_acte(patient, df_desmos) for patient in df_cosmident['Patient']]
    df_cosmident['Acte Desmos'] = actes_desmos
    st.success("✅ Extraction et fusion terminées")
    st.dataframe(df_cosmident, use_container_width=True)
else:
    st.info("Veuillez charger les deux fichiers PDF (Cosmident et Desmos) pour lancer l'analyse.")
