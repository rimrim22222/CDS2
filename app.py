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
        return pd.DataFrame()  # Retourner un DataFrame vide si aucun fichier n'est uploadé
    
    # Vérifier si le fichier est vide
    file_content = file.read()
    if not file_content or len(file_content) == 0:
        st.error("Le fichier uploadé est vide ou corrompu.")
        return pd.DataFrame()
    
    # Réinitialiser le pointeur du fichier pour fitz
    file.seek(0)
    
    # Ouvrir le PDF et extraire le texte
    doc = fitz.open(stream=file_content, filetype="pdf")
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

        # Détecter le patient
        if state == "looking_for_patient":
            patient_match = re.match(r'([A-Z\s]+) N°INSEE : ([\d ]+)', line)
            if patient_match:
                current_patient = patient_match.group(1).strip()
                state = "looking_for_data"
                current_block = []
            continue

        # Collecter les lignes du bloc de données
        if state == "looking_for_data" and current_patient:
            if line == "Total des Factures et Avoirs" or re.match(r'^\d{2}/\d{2}/\d{4}$', line):
                # Fin du bloc ou nouvelle date, traiter le bloc précédent
                if current_block:
                    process_block(current_block, current_patient, results)
                current_block = []
            else:
                current_block.append(line)

        # Réinitialiser si fin de section
        if line == "Total des Factures et Avoirs":
            state = "looking_for_patient"

    # Traiter le dernier bloc s'il existe
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
        # Chercher un code HBL dans Cot.+Coef. (5e colonne après Date, N° Fact., Type, Dent(s))
        if re.match(r'^\d{2}/\d{2}/\d{4}$', line):  # Début d'une nouvelle entrée (Date)
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
                if re.match(r'^HBL\d{3}$', cot_coef):
                    # Rassembler l'acte (lignes suivantes jusqu'à Hono)
                    act_lines = []
                    hono = None
                    while i < len(block):
                        next_line = block[i].strip()
                        if re.match(r'^\d+,\d{2}$', next_line):  # Trouver Hono
                            hono = next_line
                            break
                        act_lines.append(next_line)
                        i += 1
                    if hono:
                        act = ' '.join(act_lines).strip() if act_lines else cot_coef
                        results.append({
                            'Nom Patient': patient,
                            'Acte': act,
                            'Tarif (Hono.)': hono
                        })
        i += 1

if desmos_file:
    df = extract_hbl_data(desmos_file)
    if not df.empty:
        st.success("✅ Extraction terminée")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("Aucune donnée HBL trouvée dans le fichier.")
        st.subheader("Texte extrait pour débogage :")
        # Réinitialiser le fichier pour le débogage
        desmos_file.seek(0)
        doc = fitz.open(stream=desmos_file.read(), filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
        st.text(full_text)  # Afficher le texte brut pour débogage
