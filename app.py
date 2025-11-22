import streamlit as st
import pandas as pd
import re
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import io

# ==================== CONFIG & EN-TÊTE ====================
st.set_page_config(
    page_title="Comparatif Cosmident ↔ Desmos",
    page_icon="tooth",
    layout="wide"
)

# Logo + Titre
col1, col2 = st.columns([5, 1])
with col1:
    st.title("Comparatif Cosmident ↔ Desmos")
    st.caption("Extraction automatique des patients Cosmident + correspondance avec l'Excel Desmos")
with col2:
    st.image("https://i.imgur.com/8j2iK8C.png", width=140)  # Ton logo permanent

# ==================== UPLOADS ====================
col_a, col_b = st.columns(2)

with col_a:
    uploaded_cosmident = st.file_uploader(
        "PDF ou image Cosmident (devis prothèse)",
        type=["pdf", "png", "jpg", "jpeg"],
        key="cosmident"
    )

with col_b:
    uploaded_desmos_excel = st.file_uploader(
        "Excel Desmos (liste patients + prix)",
        type=["xlsx", "xls"],
        key="desmos_excel"
    )

# ==================== FONCTIONS ====================
def extract_text_from_image(image):
    return pytesseract.image_to_string(image, lang='fra')

def extract_cosmident_patients(file):
    """Extrait les patients + actes + prix du PDF/image Cosmident"""
    file_bytes = file.read()
    
    if file.type == "application/pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        full_text = ""
        for page in doc:
            text = page.get_text("text")
            # Coupe après les coordonnées bancaires
            stop = re.search(r"(COSMIDENT|IBAN|SIRET|BIC|Tél|Total|TOTAL|TTC|€)", text, re.I)
            if stop:
                text = text[:stop.start()]
            full_text += text + "\n"
    else:
        image = Image.open(io.BytesIO(file_bytes))
        full_text = extract_text_from_image(image)

    lines = [l.strip() for l in full_text.split("\n") if l.strip()]
    results = []
    current_patient = None
    current_acte = ""
    current_prix = None

    for line in lines:
        # Détection patient
        patient_match = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([A-Za-z\s\-\é\è\ê\à\ç]+)", line, re.I)
        if patient_match:
            if current_patient and current_acte and current_prix:
                results.append({
                    "Patient": current_patient.strip(),
                    "Acte Cosmident": current_acte.strip(),
                    "Prix Cosmident": current_prix
                })
            current_patient = patient_match.group(1)
            current_acte = ""
            current_prix = None
            continue

        # Prix (ex: 1250,00 ou 1.250,00)
        prix_match = re.search(r"(\d{1,4}[,\.\s]?\d{2,3}(?:[,\.]\d{2})?)", line)
        if prix_match and current_patient:
            prix_str = prix_match.group(1).replace(" ", "").replace(".", ",")
            try:
                current_prix = f"{float(prix_str.replace(',', '.')):.2f}".replace(".", ",")
            except:
                current_prix = prix_str

        # Acte (tout ce qui n'est pas prix ou ref)
        if current_patient and not patient_match and not prix_match:
            if len(line) > 10:
                current_acte += " " + line

    # Dernier patient
    if current_patient and current_acte and current_prix:
        results.append({
            "Patient": current_patient.strip(),
            "Acte Cosmident": current_acte.strip(),
            "Prix Cosmident": current_prix
        })

    return pd.DataFrame(results)

def load_desmos_excel(file):
    """Charge l'Excel Desmos → doit avoir au moins une colonne 'Patient'"""
    df = pd.read_excel(file)
    # Normalisation des noms de colonnes
    df.columns = [c.strip().lower() for c in df.columns]
    if "patient" not in df.columns:
        st.error("L'Excel Desmos doit contenir une colonne nommée 'Patient'")
        return pd.DataFrame()
    return df

# ==================== TRAITEMENT ====================
if uploaded_cosmident and uploaded_desmos_excel:
    uploaded_cosmident.seek(0)
    uploaded_desmos_excel.seek(0)

    with st.spinner("Analyse en cours..."):
        df_cosmident = extract_cosmident_patients(uploaded_cosmident)
        df_desmos = load_desmos_excel(uploaded_desmos_excel)

    if df_cosmident.empty:
        st.error("Aucun patient trouvé dans le fichier Cosmident.")
    elif df_desmos.empty:
        st.error("Problème avec l'Excel Desmos.")
    else:
        st.success(f"Analyse terminée : {len(df_cosmident)} patients Cosmident • {len(df_desmos)} dans Desmos")

        # Correspondance intelligente par nom (même partiel)
        df_final = df_cosmident.copy()
        df_final["Trouvé dans Desmos"] = "Non"
        df_final["Acte Desmos"] = ""
        df_final["Prix Desmos"] = ""

        for idx, row in df_final.iterrows():
            patient_cosmi = row["Patient"].lower().strip()
            words_cosmi = set(patient_cosmi.split())

            for _, row_desmos in df_desmos.iterrows():
                patient_desmos = str(row_desmos["Patient"]).lower().strip()
                words_desmos = set(patient_desmos.split())

                # Match si au moins 2 mots en commun ou nom exact
                if (patient_cosmi in patient_desmos or 
                    patient_desmos in patient_cosmi or 
                    len(words_cosmi.intersection(words_desmos)) >= 2):
                    
                    df_final.loc[idx, "Trouvé dans Desmos"] = "Oui"
                    df_final.loc[idx, "Acte Desmos"] = str(row_desmos.get("acte", row_desmos.get("Acte", "")))
                    df_final.loc[idx, "Prix Desmos"] = str(row_desmos.get("prix", row_desmos.get("Prix", row_desmos.get("hono", ""))))
                    break

        # Affichage
        st.subheader("Résultat du comparatif Cosmident ↔ Desmos")
        st.dataframe(
            df_final[["Patient", "Acte Cosmident", "Prix Cosmident", "Trouvé dans Desmos", "Acte Desmos", "Prix Desmos"]],
            use_container_width=True,
            hide_index=True
        )

        # Stats
        trouves = df_final["Trouvé dans Desmos"].value_counts().get("Oui", 0)
        st.info(f"Patients trouvés dans Desmos : **{trouves} / {len(df_final)}**")

        # Téléchargement
        csv = df_final.to_csv(index=False, sep=";", encoding="utf-8-sig")
        st.download_button(
            label="Télécharger le comparatif complet (CSV)",
            data=csv,
            file_name=f"Comparatif_Cosmident_Desmos_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

else:
    st.info("Charge le PDF/Image Cosmident + l'Excel Desmos pour lancer le comparatif")
