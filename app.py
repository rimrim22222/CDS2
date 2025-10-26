import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import io

# Configuration Streamlit
st.set_page_config(page_title="Récapitulatif HBL Patients et Tarifs", layout="wide")
st.title("🏥 Récapitulatif détaillé des actes HBL (Couronnes, Bridges...) du fichier Desmos")


def extract_hbl_data(file):
    """Extrait les actes dont le code commence par HBL, un acte = une ligne."""
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

    # Extraire le texte
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n"

    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

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

        # --- Fin du bloc d’actes ---
        if "Total Facture" in line or "Total des Factures et Avoirs" in line:
            capture_acte = False
            continue

        if not capture_acte or not current_patient:
            continue

        # --- Recherche d’un code HBL ---
        match_hbl = re.match(r"^(HBL[A-Z0-9]+)", line)
        if match_hbl:
            code = match_hbl.group(1)

            # Cherche description juste avant
            desc_line = ""
            if i > 0:
                desc_line = lines[i - 1].strip()
                # Nettoyage : éviter de récupérer une ligne de montant
                if re.match(r"^\d", desc_line):
                    desc_line = ""

            # Cherche Cot.+Coef. dans les lignes précédentes
            coef_value = None
            for j in range(i - 5, i):
                if j < 0:
                    continue
                coef_match = re.findall(r"\b\d+,\d{2}\b", lines[j])
                if coef_match:
                    coef_value = coef_match[0].replace(",", ".")
                    break

            # Cherche montant Hono (souvent sur même ligne ou juste après)
            hono_value = None
            for k in range(i, min(i + 4, len(lines))):
                montant_match = re.findall(r"\d+,\d{2}", lines[k])
                if montant_match:
                    hono_value = montant_match[-1].replace(",", ".")
                    break

            # Ajoute la ligne
            data.append({
                "Nom Patient": current_patient,
                "Code HBL": code,
                "Description": desc_line if desc_line else "(non trouvée)",
                "Cot.+Coef.": coef_value if coef_value else "",
                "Hono.": float(hono_value) if hono_value else None
            })

    # --- Conversion en DataFrame ---
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    # Trier par patient pour lisibilité
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
            "⬇️ Télécharger le récapitulatif HBL détaillé en CSV",
            csv,
            "recapitulatif_HBL_detail.csv",
            "text/csv"
        )
    else:
        st.warning("⚠️ Aucun acte HBL trouvé dans le fichier.")
