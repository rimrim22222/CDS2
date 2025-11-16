import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from PIL import Image
import pytesseract
import io

st.set_page_config(page_title="Analyse Cosmident + Desmos", layout="wide")
st.title("Analyse des actes dentaires Cosmident + Desmos")

uploaded_cosmident = st.file_uploader(
    "Upload le fichier Cosmident (PDF ou image)", type=["pdf", "png", "jpg", "jpeg"]
)
uploaded_desmos = st.file_uploader(
    "Upload le fichier Desmos (PDF)", type=["pdf"], key="desmos"
)

# =====================
# Extraction image
# =====================
def extract_text_from_image(image):
    return pytesseract.image_to_string(image)

# =====================
# Extraction Cosmident robuste (version finale corrigée)
# =====================
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
            # Coupe après le bas de page
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
    
    # Debug : texte brut
    with st.expander("Aperçu du texte extrait (Cosmident brut)"):
        st.write(full_text[:3000] + "..." if len(full_text) > 3000 else full_text)
    
    lines = [line.strip() for line in full_text.split("\n") if line.strip()]
    clean_lines = []
    for line in lines:
        # Exclure les lignes inutiles
        if re.search(r"(teinte|couleur|A[1-3]|B[1-3]|C[1-3]|D[1-3])", line, re.IGNORECASE):
            continue
        if re.search(r"(COSMIDENT|IBAN|Siret|BIC|€|TOTAL TTC|CHÈQUE)", line, re.IGNORECASE):
            continue
        clean_lines.append(line)
    
    results = []
    current_patient = None
    current_acte = ""
    current_numbers = []
    i = 0

    while i < len(clean_lines):
        line = clean_lines[i]
        i += 1

        # Détection du patient via Ref.
        ref_match = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-\.]+)", line, re.IGNORECASE)
        if ref_match:
            # Sauvegarde de l'acte précédent
            if current_patient and current_acte and current_numbers:
                try:
                    total = float(current_numbers[-1])
                    if total > 0:
                        results.append({
                            "Patient": current_patient,
                            "Acte Cosmident": current_acte.strip(),
                            "Prix Cosmident": f"{total:.2f}"
                        })
                except:
                    pass
            # Reset
            current_patient = ref_match.group(1).strip()
            current_acte = ""
            current_numbers = []
            continue

        # Cas Bon n° + Ref. sur ligne suivante
        if re.match(r"Bon n°\d+ du [\d/]+", line) and i < len(clean_lines):
            next_line = clean_lines[i]
            ref_match = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-\.]+)", next_line, re.IGNORECASE)
            if ref_match:
                if current_patient and current_acte and current_numbers:
                    try:
                        total = float(current_numbers[-1])
                        if total > 0:
                            results.append({
                                "Patient": current_patient,
                                "Acte Cosmident": current_acte.strip(),
                                "Prix Cosmident": f"{total:.2f}"
                            })
                    except:
                        pass
                current_patient = ref_match.group(1).strip()
                current_acte = ""
                current_numbers = []
                i += 1
                continue

        if not current_patient:
            continue

        # Extraction des nombres dans la ligne
        numbers_in_line = re.findall(r"\d+[\.,]\d{2}", line)
        norm_numbers = [n.replace(",", ".") for n in numbers_in_line]
        text_part = re.sub(r"\s*\d+[\.,]\d{2}\s*", " ", line).strip()

        # Si la ligne contient du texte significatif → partie de l'acte
        if text_part and not re.match(r"^\d+[\.,]\d{2}$", text_part):
            # Si on avait déjà un acte complet → on le sauvegarde avant d'en commencer un nouveau
            if current_acte and current_numbers:
                try:
                    total = float(current_numbers[-1])
                    if total > 0:
                        results.append({
                            "Patient": current_patient,
                            "Acte Cosmident": current_acte.strip(),
                            "Prix Cosmident": f"{total:.2f}"
                        })
                except:
                    pass
                current_numbers = []
            current_acte = text_part if not current_acte else current_acte + " " + text_part

        # Ajouter les nombres (quantité, prix, remise, total)
        if norm_numbers:
            current_numbers.extend(norm_numbers)

        # Cas spécial : ligne avec seulement un prix → fin d'acte
        if re.match(r"^\d+[\.,]\d{2}$", line.strip()) and current_acte and current_numbers:
            try:
                total = float(norm_numbers[-1])
                if total > 0:
                    results.append({
                        "Patient": current_patient,
                        "Acte Cosmident": current_acte.strip(),
                        "Prix Cosmident": f"{total:.2f}"
                    })
            except:
                pass
            current_acte = ""
            current_numbers = []

    # Dernier acte
    if current_patient and current_acte and current_numbers:
        try:
            total = float(current_numbers[-1])
            if total > 0:
                results.append({
                    "Patient": current_patient,
                    "Acte Cosmident": current_acte.strip(),
                    "Prix Cosmident": f"{total:.2f}"
                })
        except:
            pass

    return pd.DataFrame(results)

# =====================
# Extraction Desmos
# =====================
def extract_desmos_acts(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    lines = full_text.split("\n")
    data = []
    current_patient = None
    current_acte = ""
    current_hono = ""
    for line in lines:
        patient_match = re.search(r"Ref\. ([A-ZÉÈÇÂÊÎÔÛÄËÏÖÜÀÙa-zéèçâêîôûäëïöüàù\s\-\.]+)", line)
        if patient_match:
            if current_patient and current_acte and current_hono:
                data.append({
                    "Patient": current_patient,
                    "Acte Desmos": current_acte.strip(),
                    "Prix Desmos": current_hono
                })
            current_patient = patient_match.group(1).strip()
            current_acte = ""
            current_hono = ""
        elif re.search(r"(BIOTECH|Couronne transvissée|HBL\w+|ZIRCONE|GOUTTIÈRE SOUPLE|EMAX|ONLAY|PLAQUE|ADJONCTION|MONTAGE|DENT RESINE)", line, re.IGNORECASE):
            current_acte = line.strip()
            current_hono = ""
        elif "Hono" in line:
            hono_match = re.search(r"Hono\.?\s*:?\s*([\d,\.]+)", line)
            if hono_match:
                current_hono = hono_match.group(1).replace(",", ".")
        elif current_acte and re.match(r"^\d+[\.,]\d{2}$", line):
            current_hono = line.replace(",", ".")
    if current_patient and current_acte and current_hono:
        data.append({
            "Patient": current_patient,
            "Acte Desmos": current_acte.strip(),
            "Prix Desmos": current_hono
        })
    return pd.DataFrame(data)

# =====================
# Matching
# =====================
def match_patient_and_acte(cosmident_patient, df_desmos):
    cosmident_parts = set(cosmident_patient.lower().split())
    for _, row in df_desmos.iterrows():
        desmos_patient = row["Patient"]
        desmos_parts = set(desmos_patient.lower().split())
        if cosmident_patient.lower() == desmos_patient.lower() or len(cosmident_parts & desmos_parts) >= 1:
            return row["Acte Desmos"], row["Prix Desmos"]
    return "", ""

# =====================
# Interface principale
# =====================
if uploaded_cosmident and uploaded_desmos:
    uploaded_cosmident.seek(0)
    uploaded_desmos.seek(0)
    
    df_cosmident = extract_data_from_cosmident(uploaded_cosmident)
    df_desmos = extract_desmos_acts(uploaded_desmos)
    
    # === DEBUG : 3 TABLES ===
    st.subheader("1. Table Cosmident (extraite)")
    st.dataframe(df_cosmident, use_container_width=True)
    
    st.subheader("2. Table Desmos (extraite)")
    st.dataframe(df_desmos, use_container_width=True)
    
    # Fusion
    actes_desmos, prix_desmos = [], []
    for patient in df_cosmident["Patient"]:
        acte, prix = match_patient_and_acte(patient, df_desmos)
        actes_desmos.append(acte)
        prix_desmos.append(prix)
    
    df_merged = df_cosmident.copy()
    df_merged["Acte Desmos"] = actes_desmos
    df_merged["Prix Desmos"] = prix_desmos
    
    st.subheader("3. Table fusionnée (Cosmident + Desmos)")
    st.dataframe(df_merged, use_container_width=True)
    
    st.success(f"Extraction et fusion terminées — {len(df_merged)} actes trouvés")

else:
    st.info("Veuillez charger les deux fichiers PDF pour lancer l'analyse.")
