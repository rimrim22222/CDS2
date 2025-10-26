import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import io

# Configuration Streamlit
st.set_page_config(page_title="Récapitulatif des Patients et Tarifs", layout="wide")
st.title("📊 Récapitulatif des Patients et Tarifs du fichier Desmos")


def extract_patient_totals(file):
    """Extrait patients, actes, totaux et Cot.+Coef. depuis le PDF Desmos."""
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
        full_text += page.get_text("text") + "\n"

    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    patient_data = []
    current_patient = None
    current_actes = []
    current_total = 0.0
    current_coef = []
    capture_acte = False
    has_HBL = False  # Flag pour filtrer les patients avec code HBL

    for line in lines:
        # --- Détection patient ---
        match_patient = re.match(r"([A-ZÉÈÀÙÂÊÎÔÛÇ'\- ]+) N°INSEE\s*:\s*([\d ]+)", line)
        if match_patient:
            # Sauvegarder le précédent si valide
            if current_patient and has_HBL:
                patient_data.append({
                    "Nom Patient": current_patient,
                    "Actes": "; ".join(current_actes) if current_actes else "Aucun acte trouvé",
                    "Cot.+Coef.": "; ".join(current_coef) if current_coef else "",
                    "Total Tarif (Hono.)": round(current_total, 2)
                })

            current_patient = match_patient.group(1).strip()
            current_actes = []
            current_total = 0.0
            current_coef = []
            capture_acte = False
            has_HBL = False
            continue

        # --- Début d’un bloc d’actes ---
        if re.match(r"^\d{2}/\d{2}/\d{4}", line):
            capture_acte = True
            continue

        # --- Fin d’un bloc d’actes ---
        if "Total Facture" in line or "Total des Factures et Avoirs" in line:
            capture_acte = False
            continue

        # --- Lecture des lignes d’actes ---
        if capture_acte:
            # Si la ligne contient un code d’acte (HB...)
            if re.match(r"^HB[A-Z0-9]+", line):
                code = line.strip()
                if code.startswith("HBL"):
                    has_HBL = True  # Patient à conserver
                current_actes.append(code)
                continue

            # Si la ligne contient une valeur Cot.+Coef.
            coef_match = re.findall(r"\b\d+,\d{2}\b", line)
            if coef_match:
                # On prend la première valeur comme Cot.+Coef.
                current_coef.append(coef_match[0].replace(",", "."))

            # Si la ligne contient un montant Hono (souvent le dernier nombre sur la ligne)
            montant_match = re.findall(r"\d+,\d{2}", line)
            if montant_match:
                try:
                    montant = float(montant_match[-1].replace(",", "."))
                    current_total += montant
                except ValueError:
                    pass

    # Sauvegarder le dernier patient si HBL présent
    if current_patient and has_HBL:
        patient_data.append({
            "Nom Patient": current_patient,
            "Actes": "; ".join(current_actes) if current_actes else "Aucun acte trouvé",
            "Cot.+Coef.": "; ".join(current_coef) if current_coef else "",
            "Total Tarif (Hono.)": round(current_total, 2)
        })

    # --- Conversion en DataFrame ---
    if patient_data:
        df = pd.DataFrame(patient_data)
        return df
    return pd.DataFrame()


# --- Exécution principale ---
desmos_file = st.file_uploader("📄 Upload le fichier Desmos PDF", type=["pdf"])

if desmos_file:
    df = extract_patient_totals(desmos_file)

    if not df.empty:
        st.success(f"✅ {len(df)} patients trouvés avec actes HBL")
        st.dataframe(df, use_container_width=True)

        # Téléchargement CSV
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Télécharger le récapitulatif HBL en CSV",
            csv,
            "recapitulatif_patients_HBL.csv",
            "text/csv"
        )
    else:
        st.warning("⚠️ Aucun patient avec un acte commençant par HBL n’a été trouvé.")
