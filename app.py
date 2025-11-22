import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
from PIL import Image
import pytesseract
import io

# ==================== CONFIG & EN-TÊTE ====================
st.set_page_config(
    page_title="Comparatif Cosmident ↔ Desmos",
    page_icon="tooth",
    layout="wide"
)

# Titre + Logo à droite
col1, col2 = st.columns([6, 1])
with col1:
    st.title("Comparatif Cosmident ↔ Desmos")
    st.caption("Extraction automatique des devis Cosmident + matching avec l'Excel Desmos")
with col2:
    st.image("https://i.imgur.com/8j2iK8C.png", width=140)  # Ton logo permanent

# ==================== UPLOADS ====================
col_a, col_b = st.columns(2)

with col_a:
    uploaded_cosmident = st.file_uploader(
        "Fichier Cosmident (PDF ou image)",
        type=["pdf", "png", "jpg", "jpeg"],
        key="cosmident"
    )

with col_b:
    uploaded_desmos_excel = st.file_uploader(
        "Excel Desmos (liste patients + prix)",
        type=["xlsx", "xls"],
        key="desmos_excel"
    )

# ===================== TON CODE COSMIDENT (100% CONSERVÉ) =====================
def extract_text_from_image(image):
    return pytesseract.image_to_string(image, lang='fra')

def extract_data_from_cosmident(file):
    file_bytes = file.read()
    if file.type == "application/pdf":
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as e:
            st.error(f"Erreur ouverture PDF : {e}")
            return pd.DataFrame()
        full_text = ""
        for page in doc:
            page_text = page.get_text("text")
            stop_pattern = r"(COSMIDENT|IBAN|Siret|BIC|Tél\.|Total \(Euros\)|TOTAL TTC|Règlement|Chèque|NOS COORDONNÉES BANCAIRES)"
            page_text = re.split(stop_pattern, page_text, flags=re.IGNORECASE)[0]
            full_text += page_text + "\n"
    else:
        try:
            image = Image.open(io.BytesIO(file_bytes))
            full_text = extract_text_from_image(image)
        except Exception as e:
            st.error(f"Erreur lecture image : {e}")
            return pd.DataFrame()

    # Option debug (tu peux garder ou supprimer)
    with st.expander("Aperçu texte brut Cosmident", expanded=False):
        st.write(full_text[:3000])

    lines = full_text.split("\n")
    clean_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.search(r"(teinte|couleur|A[1-3]|B[1-3]|C[1-3]|D[1-3])", line, re.IGNORECASE):
            continue
        if re.search(r"(COSMIDENT|IBAN|Siret|BIC|€|TOTAL TTC|CHÈQUE)", line, re.IGNORECASE):
            continue
        clean_lines.append(line)

    results = []
    current_patient = None
    current_description = ""
    current_numbers = []
    i = 0
    while i < len(clean_lines):
        line = clean_lines[i]
        i += 1

        ref_match = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-]+)", line, re.IGNORECASE)
        if ref_match:
            if current_patient and current_description and current_numbers:
                try:
                    total = float(current_numbers[-1].replace(",", "."))
                    if total > 0:
                        results.append({
                            "Patient": current_patient.strip(),
                            "Acte Cosmident": current_description.strip(),
                            "Prix Cosmident": f"{total:.2f}".replace(".", ",")
                        })
                except:
                    pass
            current_description = ""
            current_numbers = []
            current_patient = ref_match.group(1).strip()
            continue

        if current_patient is None:
            continue

        this_numbers = re.findall(r"\d+[\.,]\d{2}", line)
        norm_numbers = [n.replace(",", ".") for n in this_numbers]
        this_text = re.sub(r"\s*\d+[\.,]\d{2}\s*", " ", line).strip()

        if this_text:
            if current_description and current_numbers:
                try:
                    total = float(current_numbers[-1])
                    if total > 0:
                        results.append({
                            "Patient": current_patient.strip(),
                            "Acte Cosmident": current_description.strip(),
                            "Prix Cosmident": f"{total:.2f}".replace(".", ",")
                        })
                except:
                    pass
                current_description = this_text
                current_numbers = []
            else:
                current_description = this_text if not current_description else current_description + " " + this_text

        if norm_numbers:
            current_numbers.extend(norm_numbers)

    # Dernier acte
    if current_patient and current_description and current_numbers:
        try:
            total = float(current_numbers[-1])
            if total > 0:
                results.append({
                    "Patient": current_patient.strip(),
                    "Acte Cosmident": current_description.strip(),
                    "Prix Cosmident": f"{total:.2f}".replace(".", ",")
                })
        except:
            pass

    return pd.DataFrame(results)

# ===================== TRAITEMENT PRINCIPAL =====================
if uploaded_cosmident and uploaded_desmos_excel:
    uploaded_cosmident.seek(0)
    uploaded_desmos_excel.seek(0)

    with st.spinner("Analyse Cosmident + matching Desmos en cours..."):
        df_cosmident = extract_data_from_cosmident(uploaded_cosmident)
        df_desmos = pd.read_excel(uploaded_desmos_excel)

    if df_cosmident.empty:
        st.error("Aucun patient détecté dans le fichier Cosmident.")
        st.stop()

    # Normalisation colonne Patient dans Desmos
    df_desmos.columns = [c.strip().lower() for c in df_desmos.columns]
    if "patient" not in df_desmos.columns:
        st.error("L'Excel Desmos doit avoir une colonne nommée 'Patient' (ou 'patient')")
        st.stop()

    # Matching intelligent
    resultats = df_cosmident.copy()
    resultats["Patient Desmos"] = ""
    resultats["Acte Desmos"] = ""
    resultats["Prix Desmos"] = ""
    resultats["Trouvé"] = "Non"

    for idx, row in resultats.iterrows():
        patient_cosmi = row["Patient"].lower().strip()
        mots_cosmi = set(patient_cosmi.split())

        for _, row_desmos in df_desmos.iterrows():
            patient_desmos = str(row_desmos["patient"]).lower().strip()
            mots_desmos = set(patient_desmos.split())

            if (patient_cosmi in patient_desmos or
                patient_desmos in patient_cosmi or
                len(mots_cosmi.intersection(mots_desmos)) >= 2):

                resultats.loc[idx, "Patient Desmos"] = row_desmos["patient"]
                resultats.loc[idx, "Acte Desmos"] = str(row_desmos.get("acte", row_desmos.get("Acte", "")))
                resultats.loc[idx, "Prix Desmos"] = str(row_desmos.get("prix", row_desmos.get("Prix", row_desmos.get("hono", ""))))
                resultats.loc[idx, "Trouvé"] = "Oui"
                break

    # Affichage final
    st.success(f"Analyse terminée ! {len(resultats)} patients Cosmident → {resultats['Trouvé'].value_counts().get('Oui', 0)} trouvés dans Desmos")

    st.subheader("Comparatif Cosmident ↔ Desmos")
    cols_to_show = ["Patient", "Acte Cosmident", "Prix Cosmident", "Trouvé", "Patient Desmos", "Acte Desmos", "Prix Desmos"]
    st.dataframe(resultats[cols_to_show], use_container_width=True, hide_index=True)

    # Téléchargement
    csv = resultats.to_csv(index=False, sep=";", encoding="utf-8-sig")
    st.download_button(
        label="Télécharger le comparatif complet",
        data=csv,
        file_name=f"Comparatif_Cosmident_Desmos_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )

else:
    st.info("Charge ton fichier Cosmident (PDF/image) + ton Excel Desmos pour lancer le comparatif")
