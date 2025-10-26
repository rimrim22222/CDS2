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

            desc_line = ""
            if i > 0:
                desc_line = lines[i - 1].strip()
                if re.match(r"^\d", desc_line):
                    desc_line = ""

            # --- Recherche du montant ---
            hono_value = None
            source_line = ""
            source_next = ""

            # Même ligne ou la suivante
            montant_match_same = re.findall(r"\d+,\d{2}", line)
            montant_match_next = re.findall(r"\d+,\d{2}", lines[i + 1]) if i + 1 < len(lines) else []

            all_amounts = [float(m.replace(",", ".")) for m in montant_match_same + montant_match_next]
            if all_amounts:
                hono_value = max(all_amounts)

            # Enregistrer les lignes brutes pour le mode debug
            if debug:
                source_line = line
                source_next = lines[i + 1] if i + 1 < len(lines) else ""
                debug_info.append({
                    "Patient": current_patient,
                    "Code": code,
                    "Ligne code": source_line,
                    "Ligne suivante": source_next,
                    "Montants trouvés": ", ".join(montant_match_same + montant_match_next),
                    "Hono extrait": hono_value if hono_value else "❌ Non trouvé"
                })

            # Ajouter au tableau principal
            data.append({
                "Nom Patient": current_patient,
                "Code HBL": code,
                "Description": desc_line if desc_line else "(non trouvée)",
                "Hono.": hono_value if hono_value else None
            })

    if not data:
        return pd.DataFrame(), pd.DataFrame()

    df = pd.DataFrame(data)
    df = df[df["Hono."].notnull()]
    df = df.sort_values(by=["Nom Patient"]).reset_index(drop=True)

    df_debug = pd.DataFrame(debug_info) if debug else pd.DataFrame()
    return df, df_debug


# --- Interface Streamlit ---
desmos_file = st.file_uploader("📄 Upload le fichier Desmos PDF", type=["pdf"])
debug_mode = st.checkbox("🧩 Activer le mode debug (affiche les lignes sources)", value=True)

if desmos_file:
    df, df_debug = extract_hbl_data(desmos_file, debug=debug_mode)

    if not df.empty:
        st.success(f"✅ {len(df)} actes HBL trouvés pour {df['Nom Patient'].nunique()} patients")
        st.dataframe(df, use_container_width=True)

        # Téléchargement du CSV principal
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Télécharger le récapitulatif HBL en CSV",
            csv,
            "recapitulatif_HBL_debug.csv",
            "text/csv"
        )

        # Mode debug
        if debug_mode and not df_debug.empty:
            st.divider()
            st.subheader("🔍 Détails du mode DEBUG (lignes brutes du PDF)")
            st.dataframe(df_debug, use_container_width=True)
            st.info("💡 Vérifie ici si le montant correct (ex: 472,50) apparaît bien sur la même ligne ou la suivante.")
    else:
        st.warning("⚠️ Aucun acte HBL trouvé dans le fichier.")
