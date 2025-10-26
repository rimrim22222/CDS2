import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

st.set_page_config(page_title="Récapitulatif HBL Patients et Tarifs", layout="wide")
st.title("🏥 Récapitulatif précis des actes HBL (montants réels) du fichier Desmos")


def extract_hbl_data(file):
    """Extrait les actes HBL (une ligne par acte) avec le montant juste après le code."""
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

    # Lecture complète du texte
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n"

    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    # Codes HBL à exclure
    excluded_codes = {"HBLD073", "HBLD490", "HBLD724"}

    data = []
    current_patient = None
    capture_acte = False

    for i, line in enumerate(lines):
        # --- Détection patient ---
        match_patient = re.match(r"([A-ZÉÈÀÙÂÊÎÔÛÇ'\- ]+) N°INSEE\s*:\s*([\d ]+)", line)
        if match_patient:
            current_patient = match_patient.group(1).strip()
            capture_acte = False
            continue

        # --- Début bloc actes ---
        if re.match(r"^\d{2}/\d{2}/\d{4}", line):
            capture_acte = True
            continue

        # --- Fin bloc actes ---
        if "Total Facture" in line or "Total des Factures et Avoirs" in line:
            capture_acte = False
            continue

        if not capture_acte or not current_patient:
            continue

        # --- Détection d’un code HBL ---
        match_hbl = re.match(r"^(HBL[A-Z0-9]+)", line)
        if match_hbl:
            code = match_hbl.group(1)
            if code in excluded_codes:
                continue

            # Description juste avant le code
            desc_line = ""
            if i > 0:
                desc_line = lines[i - 1].strip()
                if re.match(r"^\d", desc_line):
                    desc_line = ""

            # --- Recherche du montant : même ligne ou ligne suivante ---
            hono_value = None

            # Regarder sur la même ligne après le code
            montant_match_same = re.findall(r"\d+,\d{2}", line)
            montant_match_next = re.findall(r"\d+,\d{2}", lines[i + 1]) if i + 1 < len(lines) else []

            all_amounts = [float(m.replace(",", ".")) for m in montant_match_same + montant_match_next]
            if all_amounts:
                # On prend le plus grand nombre trouvé → correspond au total (ex: 472,50)
                hono_value = max(all_amounts)

            # Ajouter la ligne
            data.append({
                "Nom Patient": current_patient,
                "Code HBL": code,
                "Description": desc_line if desc_line else "(non trouvée)",
                "Hono.": hono_value if hono_value else None
            })

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
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
            "⬇️ Télécharger le récapitulatif HBL (montants réels) en CSV",
            csv,
            "recapitulatif_HBL_montants_reels.csv",
            "text/csv"
        )
    else:
        st.warning("⚠️ Aucun acte HBL trouvé dans le fichier.")
