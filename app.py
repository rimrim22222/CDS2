import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import io

st.set_page_config(page_title="Extraction HBL de Desmos", layout="wide")
st.title("📄 Extraction des actes HBL du fichier Desmos")

desmos_file = st.file_uploader("Upload le fichier Desmos PDF", type=["pdf"])

def extract_hbl_data(file):
    if not file:
        return pd.DataFrame()
    
    file_content = file.read()
    if not file_content or len(file_content) == 0:
        st.error("Le fichier uploadé est vide ou corrompu.")
        return pd.DataFrame()
    
    file.seek(0)
    
    try:
        doc = fitz.open(stream=file_content, filetype="pdf")
    except Exception as e:
        st.error(f"Erreur lors de l'ouverture du fichier : {e}")
        return pd.DataFrame()
    
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    lines = full_text.split('\n')
    
    results = []
    current_patient = None
    state = "looking_for_patient"
    current_block = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if state == "looking_for_patient":
            patient_match = re.match(r'([A-Z\s]+) N°INSEE : ([\d ]+)', line)
            if patient_match:
                current_patient = patient_match.group(1).strip()
                state = "looking_for_data"
                current_block = []
            continue

        if state == "looking_for_data" and current_patient:
            if line == "Total des Factures et Avoirs" or re.match(r'^\d{2}/\d{2}/\d{4}$', line):
                if current_block:
                    process_block(current_block, current_patient, results)
                current_block = []
            else:
                current_block.append(line)

        if line == "Total des Factures et Avoirs":
            state = "looking_for_patient"

    if current_block and current_patient:
        process_block(current_block, current_patient, results)

    df = pd.DataFrame(results)
    if not df.empty:
        df['Tarif (Hono.)'] = df['Tarif (Hono.)'].str.replace(',', '.').astype(float)
    return df

def process_block(block, patient, results):
    i = 0
    while i < len(block):
        line = block[i].strip()
        if re.match(r'^\d{2}/\d{2}/\d{4}$', line):  # Date
            i += 1
            if i < len(block):
                fact_num = block[i].strip()  # N° Fact.
                i += 1
            if i < len(block):
                fse_type = block[i].strip()  # Type et N° FSE
                i += 1
            if i < len(block):
                dents = block[i].strip()  # Dent(s)
                i += 1
            if i < len(block):
                cot_coef = block[i].strip()  # Cot.+Coef.
                i += 1
                if re.match(r'^HBL[A-Z]\d{3}$', cot_coef):  # Adjusted regex for HBLD474, etc.
                    act_lines = []
                    hono = None
                    while i < len(block):
                        next_line = block[i].strip()
                        if re.match(r'^\d+,\d{2}$', next_line):
                            hono = next_line
                            break
                        act_lines.append(next_line)
                        i += 1
                    if hono:
                        act = ' '.join(act_lines).strip() if act_lines else cot_coef
                        results.append({
                            'Nom Patient': patient,
                            'Acte': act,
                            'Code': cot_coef,
                            'Tarif (Hono.)': hono
                        })
        i += 1

if desmos_file:
    df = extract_hbl_data(desmos_file)
    if not df.empty:
        st.success("✅ Extraction terminée")
        for patient, group in df.groupby('Nom Patient'):
            st.subheader(f"Tableau pour {patient}")
            st.dataframe(group[['Acte', 'Code', 'Tarif (Hono.)']], use_container_width=True)
    else:
        st.warning("Aucune donnée HBL trouvée dans le fichier.")
        st.subheader("Texte extrait pour débogage :")
        desmos_file.seek(0)
        try:
            doc = fitz.open(stream=desmos_file.read(), filetype="pdf")
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            st.text(full_text)
        except Exception as e:
            st.error(f"Erreur lors de l'extraction du texte : {e}")
