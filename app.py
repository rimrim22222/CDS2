import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

st.set_page_config(page_title="Extraction HBL de Desmos", layout="wide")
st.title("📄 Extraction des actes HBL du fichier Desmos")

desmos_file = st.file_uploader("Upload le fichier Desmos PDF", type=["pdf"])

def extract_hbl_data(file):
    if not file:
        return pd.DataFrame()  # Retourner un DataFrame vide si aucun fichier n'est uploadé
    
    # Ouvrir le PDF et extraire le texte
    doc = fitz.open(stream=file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    lines = full_text.split('\n')
    
    results = []
    current_patient = None
    current_act = []
    current_hono = None

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # Détecter le patient
        patient_match = re.match(r'([A-Z\s]+) N°INSEE : ([\d ]+)', line)
        if patient_match:
            current_patient = patient_match.group(1).strip()
            current_act = []
            continue

        # Vérifier si la ligne contient un code HBL dans Cot.+Coef.
        hbl_match = re.match(r'^HBL\d{3}$', line)
        if hbl_match and current_patient:
            current_act = [line]  # Commencer un nouvel acte avec le code HBL
            # Chercher le tarif Hono dans les lignes suivantes
            for j in range(i + 1, min(i + 6, len(lines))):  # Limiter la recherche à 5 lignes
                hono_line = lines[j].strip()
                if re.match(r'^\d+,\d{2}$', hono_line):  # Format avec virgule (ex. 72,00)
                    current_hono = hono_line
                    break
            if current_hono:
                # Rassembler la description de l'acte
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if re.match(r'^\d+,\d{2}$', next_line) or next_line == 'Total Facture':
                        break
                    current_act.append(next_line)
                act = ' '.join(current_act).strip()
                results.append({
                    'Nom Patient': current_patient,
                    'Acte': act,
                    'Tarif (Hono.)': current_hono
                })
                current_hono = None  # Réinitialiser pour le prochain acte

        # Réinitialiser si on atteint un nouveau patient ou Total Facture
        if line == 'Total Facture' or patient_match:
            current_act = []
            current_hono = None

    df = pd.DataFrame(results)
    if not df.empty:
        df['Tarif (Hono.)'] = df['Tarif (Hono.)'].str.replace(',', '.').astype(float)
    return df

if desmos_file:
    df = extract_hbl_data(desmos_file)
    if not df.empty:
        st.success("✅ Extraction terminée")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("Aucune donnée HBL trouvée dans le fichier.")
