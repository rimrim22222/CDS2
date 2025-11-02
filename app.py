import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

# Configuration Streamlit
st.set_page_config(page_title="Récapitulatif HBL Patients et Tarifs", layout="wide")
st.title("🏥 Récapitulatif détaillé des actes HBL (mode DEBUG)")

def extract_hbl_data(file, debug=False):
    """Extrait les actes HBL (une ligne par acte) et montre les lignes sources si debug=True."""
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

    # Lecture du texte complet
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n"

    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    excluded_codes = {"HBLD073", "HBLD490", "HBLD724"}
    data = []
    debug_info = []

    current_patient = None
    capture_acte = False

    for i, line in enumerate(lines):
        # --- Détection du patient ---
        match_patient = re.match(r"([A-ZÉÈÀÙÂÊÎÔÛÇ'\- ]+) N° Dossier : \d+ N°INSEE : ([\d ]*)", line)
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

            # --- Collecter la description (lignes suivantes) ---
            desc_lines = []
            j = i + 1
            while j < len(lines) and not re.match(r"^\d{1,2}$|^\d{2}/\d{2}/\d{4}$|^\d{1,3}(?:,\d{2})$|^Total|^FSE|^[0-9]{7}$|^\(FSE|HBL[A-Z0-9]+", lines[j]):
                desc_lines.append(lines[j].strip())
                j += 1
            description = " ".join(desc_lines).strip() or "(non trouvée)"

            # --- Rechercher le montant Hono (lignes précédentes) ---
            hono_value = None
            prev_lines = []  # Pour debug

            # Commencer à partir de la ligne précédente
            k = i - 1
            skip = 0
            if k >= 0 and re.match(r"^\d+$", lines[k]):  # N° FSE
                k -= 1  # Skip Type (FSE Séc.)
                skip = 2

            # Maintenant, k pointe sur PP (dernière amount)
            # Remonter 6 lignes pour Hono (PP, AES, Cot, AMC, AMC2, AMO, Hono)
            hono_index = k - 6
            if hono_index >= 0:
                hono_line = lines[hono_index]
                montant_match = re.search(r"^\d{1,3}(?:,\d{2})$", hono_line)
                if montant_match:
                    hono_value = float(montant_match.group().replace(",", "."))

            # Collecter les lignes précédentes pour debug (les 10 dernières avant le code)
            start_debug = max(0, i - 10)
            prev_lines = lines[start_debug:i]

            if debug:
                debug_info.append({
                    "Patient": current_patient,
                    "Code": code,
                    "Lignes précédentes": "\n".join(prev_lines),
                    "Hono extrait": hono_value if hono_value else "❌ Non trouvé",
                    "Description extraite": description
                })

            # Ajouter au tableau principal
            data.append({
                "Nom Patient": current_patient,
                "Code HBL": code,
                "Description": description,
                "Hono.": hono_value
            })

    if not data:
        return pd.DataFrame(), pd.DataFrame()

    df = pd.DataFrame(data)
    df = df[df["Hono."].notnull()]  # Filtrer les lignes sans montant
    df = df.sort_values(by=["Nom Patient", "Code HBL"]).reset_index(drop=True)

    df_debug = pd.DataFrame(debug_info) if debug else pd.DataFrame()
    return df, df_debug

# --- Interface Streamlit ---
desmos_file = st.file_uploader("📄 Upload le fichier Desmos PDF", type=["pdf"])
debug_mode = st.checkbox("🧩 Activer le mode debug (affiche les lignes sources)", value=True)

if desmos_file:
    df, df_debug = extract_hbl_data(desmos_file, debug=debug_mode)

    if not df.empty:
        st.success(f"✅ {len(df)} actes HBL trouvés pour {df['Nom Patient'].nunique()} patients")
        st.dataframe(df)

        # Téléchargement du CSV principal
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Télécharger le récapitulatif HBL en CSV",
            csv,
            "recapitulatif_HBL.csv",
            "text/csv"
        )

        # Mode debug
        if debug_mode and not df_debug.empty:
            st.divider()
            st.subheader("🔍 Détails du mode DEBUG (lignes brutes du PDF)")
            st.dataframe(df_debug)
            st.info("💡 Vérifie ici si le montant et la description sont correctement extraits.")
    else:
        st.warning("⚠️ Aucun acte HBL trouvé dans le fichier.")
