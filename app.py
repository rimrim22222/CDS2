import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

st.set_page_config(page_title="Récapitulatif HBL Patients et Tarifs", layout="wide")
st.title("🏥 Récapitulatif précis des actes HBL et montants totaux du fichier Desmos")


def extract_hbl_data(file):
    """Extrait les actes HBL (une ligne par acte) avec le bon montant total correspondant."""
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

    # Lecture de tout le texte
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n"

    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

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
            if code in excluded_codes:
                continue

            # Description (souvent la ligne précédente)
            desc_line = ""
            if i > 0:
                desc_line = lines[i - 1].strip()
                if re.match(r"^\d", desc_line):
                    desc_line = ""

            hono_value = None

            # --- Recherche du montant total ("Total Facture") ---
            for k in range(i, min(i + 10, len(lines))):
                if "Total Facture" in lines[k]:
                    montant_match = re.findall(r"\d+,\d{2}", lines[k])
                    if montant_match:
                        hono_value = float(montant_match[-1].replace(",", "."))
                        break

            # --- Si pas trouvé, on cherche le plus grand montant dans les 5 lignes suivantes ---
            if hono_value is None:
                all_amounts = []
                for k in range(i, min(i + 5, len(lines))):
                    montant_match = re.findall(r"\d+,\d{2}", lines[k])
                    all_amounts += [float(m.replace(",", ".")) for m in montant_match]
                if all_amounts:
                    hono_value = max(all_amounts)

            # --- Enregistrement ---
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
            "⬇️ Télécharger le récapitulatif HBL (montants totaux) en CSV",
            csv,
            "recapitulatif_HBL_montants_totaux.csv",
            "text/csv"
        )
    else:
        st.warning("⚠️ Aucun acte HBL trouvé dans le fichier.")
