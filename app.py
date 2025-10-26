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

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
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
            i += 1
            continue

        # Extraire les actes et tarifs après une date
        if current_patient and re.match(r'^\d{2}/\d{2}/\d{4}$', line):  # Date
            j = i + 1
            acte = None
            hono = None
            
            # Parcourir jusqu'à la 5e colonne non vide
            column_count = 0
            current_columns = []
            while j < len(lines) and column_count < 5:
                next_line = lines[j].strip()
                if next_line and not re.match(r'^\s*$', next_line):
                    current_columns.append(next_line)
                    if column_count == 4:  # 5e colonne = Acte
                        acte = next_line
                        if acte:
                            current_actes.append(acte)
                    j += 1
                    column_count += 1
                else:
                    j += 1
            
            # Afficher les colonnes pour débogage (optionnel, à commenter si pas nécessaire)
            # st.write(f"Colonnes pour date {line}: {current_columns}")
            
            # Chercher le tarif Hono dans les lignes suivantes
            k = j
            while k < min(j + 6, len(lines)):
                hono_line = lines[k].strip()
                if re.match(r'^\d+,\d{2}$', hono_line):
                    try:
                        hono_value = float(hono_line.replace(',', '.'))
                        current_hono += hono_value
                    except ValueError:
                        pass
                    break
                k += 1
            
            i = k if hono else j
        else:
            i += 1

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
            st.text(full_text[:2000])  # Afficher les 2000 premiers caractères pour débogage
        except Exception as e:
            st.error(f"Erreur lors de l'extraction du texte : {e}")
