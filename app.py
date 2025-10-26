import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import io

st.set_page_config(page_title="Récapitulatif des Patients et Tarifs", layout="wide")
st.title("📊 Récapitulatif des Patients et Tarifs du fichier Desmos")

desmos_file = st.file_uploader("Upload le fichier Desmos PDF", type=["pdf"])

def extract_patient_totals(file):
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
    
    patient_data = {}
    current_patient = None
    current_hono = 0.0
    current_actes = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Détecter le patient
        patient_match = re.match(r'([A-Z\s]+) N°INSEE : ([\d ]+)', line)
        if patient_match:
            if current_patient and (current_hono > 0 or current_actes):
                patient_data[current_patient] = {
                    'Total Tarif (Hono.)': current_hono,
                    'Actes': '; '.join(current_actes) if current_actes else "Aucun acte trouvé"
                }
            current_patient = patient_match.group(1).strip()
            current_hono = 0.0
            current_actes = []
            continue

        # Accumuler les tarifs Hono pour le patient actuel
        if current_patient and re.match(r'^\d+,\d{2}$', line):
            try:
                hono_value = float(line.replace(',', '.'))
                current_hono += hono_value
            except ValueError:
                continue

        # Accumuler les actes (lignes non vides entre patient et tarif ou code HBL)
        if current_patient and not re.match(r'^\d+,\d{2}$', line) and not re.match(r'^\d{2}/\d{2}/\d{4}$', line):
            if re.match(r'^HBL[A-Z]\d{3}$', line) or (line and not re.match(r'^[A-Z\s]+ N°INSEE :', line)):
                current_actes.append(line)

    # Ajouter le dernier patient s'il a des données
    if current_patient and (current_hono > 0 or current_actes):
        patient_data[current_patient] = {
            'Total Tarif (Hono.)': current_hono,
            'Actes': '; '.join(current_actes) if current_actes else "Aucun acte trouvé"
        }

    # Convertir en DataFrame
    if patient_data:
        df = pd.DataFrame.from_dict(patient_data, orient='index').reset_index()
        df = df.rename(columns={'index': 'Nom Patient'})
        return df
    return pd.DataFrame()

if desmos_file:
    df = extract_patient_totals(desmos_file)
    if not df.empty:
        st.success("✅ Récapitulatif terminé")
        st.dataframe(df[['Nom Patient', 'Actes', 'Total Tarif (Hono.)']], width='stretch')
    else:
        st.warning("Aucune donnée de patient ou tarif trouvée dans le fichier.")
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
