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
    """Extraction Cosmident : garde tous les prix mais ignore les descriptions en petite police (<8.5)."""
    if file.type == "application/pdf":
        doc = fitz.open(stream=file.read(), filetype="pdf")
        full_text = ""
        all_lines = []

        # On extrait tout, mais on note la taille de police de chaque span
        for page in doc:
            page_dict = page.get_text("dict")
            for block in page_dict["blocks"]:
                for line in block.get("lines", []):
                    line_text = ""
                    max_size = 0
                    for span in line.get("spans", []):
                        line_text += span["text"]
                        if span["size"] > max_size:
                            max_size = span["size"]
                    if line_text.strip():
                        all_lines.append((line_text.strip(), max_size))
        # On garde toutes les lignes (pour ne pas perdre les prix),
        # mais on utilisera la taille pour ignorer les petites lignes descriptives
        lines = [l for l, _ in all_lines]
        line_sizes = dict(all_lines)
    else:
        image = Image.open(file)
        full_text = extract_text_from_image(image)
        lines = full_text.split('\n')
        line_sizes = {l: 10 for l in lines}  # Valeur arbitraire pour l’OCR

    results = []
    current_patient = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue

        # Détection du patient
        ref_match = re.search(r'Ref\. ([\w\s\-]+)', line)
        if ref_match:
            current_patient = ref_match.group(1).strip()
            continue
        if current_patient is None:
            continue

        # On ignore les lignes en petit texte (<8.5)
        if line_sizes.get(line, 10) < 8.5:
            continue

        description = line
        # Si la ligne semble être un acte dentaire
        if re.search(r'(ZIRCONE|EMAX|ONLAY|GOUTTIÈRE|PLAQUE|MONTAGE|ADJONCTION|DENT RESINE|HBL|COURONNE)', description, re.IGNORECASE):
            # On cherche les prix dans les lignes suivantes
            price = ""
            while i < len(lines):
                next_line = lines[i].strip()
                i += 1
                if not next_line:
                    continue
                # Cherche une valeur numérique de type 00.00
                price_match = re.search(r'(\d+\.\d{2})', next_line)
                if price_match:
                    price = price_match.group(1)
                    break
            if price:
                results.append({
                    'Patient': current_patient,
                    'Acte Cosmident': description,
                    'Prix Cosmident': price
                })
    return pd.DataFrame(results)

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
