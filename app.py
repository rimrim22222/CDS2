import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import io

# Configuration de la page
st.set_page_config(page_title="Récapitulatif des Patients et Tarifs", layout="wide")
st.title("📊 Récapitulatif des Patients et Tarifs du fichier Desmos")

# Upload du fichier PDF
desmos_file = st.file_uploader("📄 Upload le fichier Desmos PDF", type=["pdf"])


def extract_patient_totals(file):
    """Extrait les patients, actes et totaux honoraires du PDF Desmos."""
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

    # Nettoyage du texte
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    patient_data = {}
    current_patient = None
    current_actes = []
    current_total = 0.0
    capture_acte = False

    for line in lines:
        # --- Détection du patient ---
        match_patient = re.match(r"([A-ZÉÈÀÙÂÊÎÔÛÇ'\- ]+) N°INSEE\s*:\s*([\d ]+)", line)
        if match_patient:
            # Sauvegarder le patient précédent avant de passer au suivant
            if current_patient:
                patient_data[current_patient] = {
                    "Actes": "; ".join(current_actes) if current_actes else "Aucun acte trouvé",
                    "Total Tarif (Hono.)": round(current_total, 2)
                }
            current_patient = match_patient.group(1).strip()
            current_actes = []
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

        # --- Si on est dans un bloc d’actes ---
        if capture_acte:
            # Recherche d’un montant
            montant_match = re.findall(r"\d+,\d{2}", line)
            if montant_match:
                try:
                    # On prend la dernière valeur numérique trouvée
                    montant = float(montant_match[-1].replace(",", "."))
                    current_total += montant
                except ValueError:
                    pass

            # Détection d’un libellé d’acte (ligne textuelle sans code ni montant)
            if not re.match(r"^[\d,\. ]+$", line) and len(line) > 3 and not line.startswith("HB"):
                if not any(word in line.lower() for word in ["total facture", "facture", "sécurisée", "fse"]):
                    current_actes.append(line)

    # --- Sauvegarder le dernier patient ---
    if current_patient:
        patient_data[current_patient] = {
            "Actes": "; ".join(current_actes) if current_actes else "Aucun acte trouvé",
            "Total Tarif (Hono.)": round(current_total, 2)
        }

    # --- Conversion en DataFrame ---
    if patient_data:
        df = pd.DataFrame.from_dict(patient_data, orient="index").reset_index()
        df = df.rename(columns={"index": "Nom Patient"})
        return df
    return pd.DataFrame()


# --- Exécution principale ---
if desmos_file:
    df = extract_patient_totals(desmos_file)

    if not df.empty:
        st.success("✅ Extraction terminée avec succès")
        st.dataframe(df[['Nom Patient', 'Actes', 'Total Tarif (Hono.)']], use_container_width=True)

        # Téléchargement CSV
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Télécharger le récapitulatif en CSV", csv, "recapitulatif_patients.csv", "text/csv")

    else:
        st.warning("⚠️ Aucune donnée de patient ou d'acte trouvée dans le fichier.")
        st.subheader("🧩 Texte extrait pour débogage :")
        desmos_file.seek(0)
        try:
            doc = fitz.open(stream=desmos_file.read(), filetype="pdf")
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            st.text(full_text[:2000])  # Afficher les 2000 premiers caractères pour inspection
        except Exception as e:
            st.error(f"Erreur lors de l'extraction du texte : {e}")
