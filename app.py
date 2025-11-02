import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

# Configuration Streamlit
st.set_page_config(page_title="Récapitulatif HBL Patients et Tarifs", layout="wide")
st.title("Récapitulatif détaillé des actes HBL (mode DEBUG)")

def extract_hbl_data(file, debug=False):
    """Extrait les actes HBL (une ligne par acte) – Hono. est pris juste avant le code."""
    if not file:
        return pd.DataFrame(), pd.DataFrame()

    file_content = file.read()
    if not file_content or len(file_content) == 0:
        st.error("Le fichier uploadé est vide ou corrompu.")
        return pd.DataFrame(), pd.DataFrame()

    file.seek(0)
    try:
        doc = fitz.open(stream=file_content, filetype="pdf")
    except Exception as e:
        st.error(f"Erreur lors de l'ouverture du fichier : {e}")
        return pd.DataFrame(), pd.DataFrame()

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
        match_hbl = re.search(r"(HBL[A-Z0-9]+)", line)
        if not match_hbl:
            continue

        code = match_hbl.group(1)
        if code in excluded_codes:
            continue

        # --- Recherche du montant Hono. juste avant le code (même ligne ou ligne précédente) ---
        hono_value = None
        hono_source = ""

        # 1. Même ligne, avant le code
        before_code = line[:match_hbl.start()].strip()
        hono_match = re.findall(r"\b\d{1,4}(?:,\d{2})\b", before_code)
        if hono_match:
            hono_value = float(hono_match[-1].replace(",", "."))  # dernier montant = Hono.
            hono_source = line
        else:
            # 2. Ligne précédente (souvent le cas quand le code est en début de ligne)
            if i > 0:
                prev_line = lines[i - 1].strip()
                hono_match_prev = re.findall(r"\b\d{1,4}(?:,\d{2})\b", prev_line)
                if hono_match_prev:
                    hono_value = float(hono_match_prev[-1].replace(",", "."))
                    hono_source = prev_line

        # --- Description : lignes suivantes jusqu’à un montant ou un autre code ---
        desc_lines = []
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if re.match(r"^\d{1,3}(?:,\d{2})$|^HBL|^[0-9]{7}$|^Total|^FSE", nxt):
                break
            if nxt:
                desc_lines.append(nxt)
            j += 1
        description = " ".join(desc_lines).strip() or "(description manquante)"

        # --- Debug ---
        if debug:
            debug_info.append({
                "Patient": current_patient,
                "Code": code,
                "Ligne code": line,
                "Source Hono.": hono_source,
                "Hono. trouvé": hono_value,
                "Description": description
            })

        # --- Ajout ---
        if hono_value is not None:
            data.append({
                "Nom Patient": current_patient,
                "Code HBL": code,
                "Description": description,
                "Hono.": hono_value
            })

    # --- DataFrames ---
    if not data:
        return pd.DataFrame(), pd.DataFrame()

    df = pd.DataFrame(data)
    df = df.sort_values(by=["Nom Patient", "Code HBL"]).reset_index(drop=True)

    df_debug = pd.DataFrame(debug_info) if debug else pd.DataFrame()
    return df, df_debug


# ==================== INTERFACE STREAMLIT ====================
desmos_file = st.file_uploader("Upload le fichier Desmos PDF", type=["pdf"])
debug_mode = st.checkbox("Activer le mode debug (affiche les lignes sources)", value=True)

if desmos_file:
    df, df_debug = extract_hbl_data(desmos_file, debug=debug_mode)

    if not df.empty:
        st.success(f"{len(df)} actes HBL trouvés pour {df['Nom Patient'].nunique()} patients")
        st.dataframe(df, use_container_width=True)

        # Téléchargement CSV
        csv = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "Télécharger le récapitulatif HBL en CSV",
            csv,
            "recapitulatif_HBL.csv",
            "text/csv"
        )

        # Debug
        if debug_mode and not df_debug.empty:
            st.divider()
            st.subheader("Détails du mode DEBUG")
            st.dataframe(df_debug, use_container_width=True)
            st.info("Vérifiez que **Hono.** (et non AMO) est bien extrait.")
    else:
        st.warning("Aucun acte HBL trouvé.")
