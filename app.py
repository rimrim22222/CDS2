import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import io

st.set_page_config(page_title="Récapitulatif HBL - Patients et Tarifs", layout="wide")
st.title("💎 Récapitulatif des Patients (Actes HBL uniquement)")

desmos_file = st.file_uploader("📄 Upload le fichier Desmos PDF", type=["pdf"])


def extract_patient_totals(file):
    """Extrait les patients, actes HBL, cotations et totaux honoraires du PDF Desmos."""
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

    # Récupération du texte complet
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n"

    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    # Variables de travail
    patient_data = {}
    current_patient = None
    current_actes = []
    current_total = 0.0
    current_cotcoef = []
    capture_acte = False

    for i, line in enumerate(lines):
        # --- Détection d’un patient ---
        match_patient = re.match(r"([A-ZÉÈÀÙÂÊÎÔÛÇ'\- ]+) N°INSEE\s*:\s*([\d ]+)", line)
        if match_patient:
            # Sauvegarder le précédent patient
            if current_patient and current_actes:
                patient_data[current_patient] = {
                    "Actes": "; ".join(current_actes),
                    "Cot.+Coef.": "; ".join(current_cotcoef),
                    "Total Tarif (Hono.)": round(current_total, 2)
                }
            # Réinitialiser
            current_patient = match_patient.group(1).strip()
            current_actes = []
            current_cotcoef = []
            current_total = 0.0
            capture_acte = False
            continue

        # --- Début d’un bloc d’actes ---
        if re.match(r"^\d{2}/\d{2}/\d{4}", line):
            capture_acte = True
            continue

        # --- Fin d’un bloc d’actes ---
        if "Total Facture" in line or "Total des Factures et Avoirs" in line:
            capture_acte = False
            continue

        # --- Lecture des actes HBL ---
        if capture_acte and line.startswith("HBL"):
            code = line.strip()
            # Rechercher la ligne précédente (description + cotation)
            prev_line = lines[i - 1].strip() if i > 0 else ""
            description = prev_line if not re.match(r"^\d+[,.]\d+", prev_line)
