import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

# Configuration Streamlit
st.set_page_config(page_title="Récapitulatif HBL Patients et Tarifs", layout="wide")
st.title("🏥 Récapitulatif détaillé des actes HBL (montants exacts) du fichier Desmos")


def extract_hbl_data(file):
    """Extrait les actes HBL (une ligne par acte) avec le montant exact associé."""
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

    # Extraction texte complet
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n"

    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    # --- Codes HBL à exclure ---
    excluded_codes = {"HBLD073", "HBLD490", "HBLD724"}

    data = []
    current_patient = None
    capture_acte = False

    for i, line in enumerate(lines):
        # --- Détection du patient ---
        match_patient = re.match(r"([A-ZÉÈÀÙÂÊÎÔÛÇ'\- ]+) N°INSEE\s*:\s*([\d ]+)", line)
        if match_patient:
            current_patient = match_patient.group(1).strip()
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

        if not capture_acte or not current_patient:
            continue

        # --- Recherche d’un code HBL ---
        match_hbl = re.match(r"^(HBL[A-Z0-9]+)", line)
        if match_hbl:
            code = match_hbl.group(1)

            # ⚠️ Exclure les codes indésirables
            if code in excluded_codes:
                continue

            # Cherche description juste avant
            desc_line = ""
            if i > 0:
                desc_line = lines[i - 1].strip()
                if re.match(r"^\d", desc_line):
                    desc_line = ""

            # --- Recherche du montant Hono. ---
            hono_value = None

            # Regarder sur la même ligne puis dans les 3 suivantes
            for k in range(i, min(i + 5, len(lines))):
                montant_match = re.findall(r"\d+,\d{2}", lines[k])
                if montant_match:
                    # On prend le plus grand montant de la ligne comme "Hono."
                    montant_floats = [float(m.replace(",", ".")) for m in montant_match]
                    if montant_floats:
                        hono_value = max(montant_floats)
                        break

            # Ajout d'une ligne par acte HBL
            data.append({
                "Nom Patient": current_patient,
                "Code HBL": code,
                "Description": desc_line if desc_line else "(non trouvée)",
                "Hono.": hono_value if hono_value else None
            })

    # --- Conversion en DataFrame ---
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    # Nettoyage : suppression des lignes sans montant
    df = df[df["Hono."].notnull()]
    df = df.sort_values(by=["Nom Patient"]).reset_index(drop=True)
    return df


# --- Interface principale ---
desmos_file = st.file_uploader("📄 Upload le fichier Desmos PDF", type=["pdf"])

if desmos_file:
    df = extract_hbl_data(desmos_file)

    if not df.empty:
        st.success(f"✅ {len(df)} actes HBL trouvés pour {df['Nom Patient'].nunique()} patients")
        st.dataframe(df, use_container_width=True)

        # Téléchargement CSV
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Télécharger le récapitulatif HBL (montants exacts) en CSV",
            csv,
            "recapitulatif_HBL_montants.csv",
            "text/csv"
        )
    else:
        st.warning("⚠️ Aucun acte HBL valide trouvé dans le fichier.")
