import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import io

st.set_page_config(page_title="Récapitulatif des Patients, Codes et Tarifs", layout="wide")
st.title("📊 Récapitulatif des Patients, Codes et Tarifs du fichier Desmos")

desmos_file = st.file_uploader("Upload le fichier Desmos PDF", type=["pdf"])

def extract_patient_data(file):
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
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    
    patient_data = {}
    current_patient = None
    current_hono = 0.0
    current_codes = []

    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Détecter le patient
        patient_match = re.match(r'([A-Z\s]+) N°INSEE : ([\d ]+)', line)
        if patient_match:
            if current_patient and (current_hono > 0 or current_codes):
                patient_data[current_patient] = {
                    'Total Tarif (Hono.)': current_hono,
                    'Codes Cot.+Coef.': '; '.join(current_codes) if current_codes else "Aucun code trouvé"
                }
            current_patient = patient_match.group(1).strip()
            current_hono = 0.0
            current_codes = []
            i += 1
            continue

        # Rechercher les codes HBL et tarifs Hono pour le patient actuel
        if current_patient:
            # Vérifier si la ligne contient un code HBL
            if re.match(r'^HBL[A-Z]\d{3}$', line):
                current_codes.append(line)
            
            # Accumuler les tarifs Hono
            if re.match(r'^\d+,\d{2}$', line):
                try:
                    hono_value = float(line.replace(',', '.'))
                    current_hono += hono_value
                except ValueError:
                    pass
            
            i += 1

    # Ajouter le dernier patient s'il a des données
    if current_patient and (current_hono > 0 or current_codes):
        patient_data[current_patient] = {
            'Total Tarif (Hono.)': current_hono,
            'Codes Cot.+Coef.': '; '.join(current_codes) if current_codes else "Aucun code trouvé"
        }

    # Convertir en DataFrame
    if patient_data:
        df = pd.DataFrame.from_dict(patient_data, orient='index').reset_index()
        df = df.rename(columns={'index': 'Nom Patient'})
        return df
    return pd.DataFrame()

if desmos_file:
    df = extract_patient_data(desmos_file)
    if not df.empty:
        st.success("✅ Récapitulatif terminé")
        st.dataframe(df[['Nom Patient', 'Codes Cot.+Coef.', 'Total Tarif (Hono.)']], width='stretch')
    else:
        st.warning("Aucune donnée de patient ou tarif trouvée dans le fichier.")
        st.subheader("Texte extrait pour débogage :")
        desmos_file.seek(0)
        try:
            doc = fitz.open(stream=desmos_file.read(), filetype="pdf")
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            st.text(full_text[:2000])  # Afficher les 2000 premiers caractères pour plus de contexte
        except Exception as e:
            st.error(f"Erreur lors de l'extraction du texte : {e}")
