import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import io

# Configuration Streamlit
st.set_page_config(page_title="Récapitulatif HBL Patients et Tarifs", layout="wide")
st.title("🏥 Récapitulatif des Actes HBL (Couronnes, Bridges, etc.) du fichier Desmos")


def extract_hbl_data(file):
    """Extrait uniquement les actes dont le code commence par HBL, avec Cot.+Coef. et total Hono."""
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

    # Nettoyage
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    patients = []
    current_patient = None
    current_hbl_actes = []
    current_hbl_coef = []
    current_hbl_total = 0.0
    capture_acte = False

    for i, line in enumerate(lines):
        # --- Détection patient ---
        match_patient = re.match(r"([A-ZÉÈÀÙÂÊÎÔÛÇ'\- ]+) N°INSEE\s*:\s*([\d ]+)", line)
        if match_patient:
            # Sauvegarde du précédent patient
            if current_patient and current_hbl_actes:
                patients.append({
                    "Nom Patient": current_patient,
                    "Actes HBL": "; ".join(current_hbl_actes),
                    "Cot.+Coef.": "; ".join(current_hbl_coef),
                    "Total Tarif (Hono.)": round(current_hbl_total, 2)
                })

            # Initialisation pour le nouveau patient
            current_patient = match_patient.group(1).strip()
            current_hbl_actes = []
            current_hbl_coef = []
            current_hbl_total = 0.0
            capture_acte = False
            continue

        # --- Début d’un bloc d’actes ---
        if re.match(r"^\d{2}/\d{2}/\d{4}", line):
            capture_acte = True
            continue

        # --- Fin d’un bloc ---
        if "Total Facture" in line or "Total des Factures et Avoirs" in line:
            capture_acte = False
            continue

        if not capture_acte:
            continue

        # --- Recherche d’un code HBL ---
        if re.match(r"^(HBL[A-Z0-9]+)", line):
            code = re.match(r"^(HBL[A-Z0-9]+)", line).group(1)
            current_hbl_actes.append(code)

            # Recherche du texte précédent (description acte)
            if i > 0:
                desc_line = lines[i - 1].strip()
                if len(desc_line) > 5 and not re.match(r"^\d", desc_line):
                    current_hbl_actes[-1] += f" - {desc_line}"

            # Recherche de Cot.+Coef. dans les lignes précédentes
            j = i - 3
            coef_value = None
            while j < i and j >= 0:
                coef_match = re.findall(r"\b\d+,\d{2}\b", lines[j])
                if coef_match:
                    coef_value = coef_match[0].replace(",", ".")
                    break
                j += 1

            if coef_value:
                current_hbl_coef.append(coef_value)

            # Recherche du montant Hono (souvent sur la même ligne ou juste après)
            montant_match = re.findall(r"\d+,\d{2}", line)
            if montant_match:
                try:
                    montant = float(montant_match[-1].replace(",", "."))
                    current_hbl_total += montant
                except ValueError:
                    pass

    # Sauvegarde du dernier patient
    if current_patient and current_hbl_actes:
        patients.append({
            "Nom Patient": current_patient,
            "Actes HBL": "; ".join(current_hbl_actes),
            "Cot.+Coef.": "; ".join(current_hbl_coef),
            "Total Tarif (Hono.)": round(current_hbl_total, 2)
        })

    if patients:
        df = pd.DataFrame(patients)
        return df
    return pd.DataFrame()


# --- Interface principale ---
desmos_file = st.file_uploader("📄 Upload le fichier Desmos PDF", type=["pdf"])

if desmos_file:
    df = extract_hbl_data(desmos_file)

    if not df.empty:
        st.success(f"✅ {len(df)} patients avec actes HBL trouvés")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Télécharger le récapitulatif HBL en CSV",
            csv,
            "recapitulatif_HBL.csv",
            "text/csv"
        )
    else:
        st.warning("⚠️ Aucun acte HBL trouvé dans le fichier.")
