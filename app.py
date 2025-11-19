import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from PIL import Image
import pytesseract
import io

st.set_page_config(page_title="Analyse Cosmident + Desmos", layout="wide")
st.title("📄 Analyse des actes dentaires Cosmident + Desmos")

uploaded_cosmident = st.file_uploader(
    "Upload le fichier Cosmident (PDF ou image)", type=["pdf", "png", "jpg", "jpeg"]
)
uploaded_desmos = st.file_uploader(
    "Upload le fichier Desmos (PDF)", type=["pdf"], key="desmos"
)

# =====================
# 🔹 Extraction Cosmident robuste
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
            stop_pattern = r"(COSMIDENT|IBAN|Siret|BIC|Tél\.|Total \(Euros\)|TOTAL TTC|Règlement|Chèque|NOS COORDONNÉES BANCAIRES)"
            page_text = re.split(stop_pattern, page_text, flags=re.IGNORECASE)[0]
            full_text += page_text + "\n"
    else:
        try:
            image = Image.open(io.BytesIO(file_bytes))
            full_text = pytesseract.image_to_string(image)
        except Exception as e:
            st.error(f"Erreur lecture image : {e}")
            return pd.DataFrame()
    
    # Aperçu du texte brut
    with st.expander("🧩 Aperçu du texte extrait (Cosmident brut)"):
        st.write(full_text[:2000])
    
    # Nettoyage du texte
    lines = full_text.split("\n")
    clean_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Ignorer uniquement les lignes qui sont purement des teintes (sans acte)
        if re.match(r"^(Teinte dentine|Vitapan|A[1-3]|B[1-3]|C[1-3]|D[1-3])\s*:?", line, re.IGNORECASE):
            continue
        # Ignorer les mentions bancaires ou totaux
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

        # Détection du patient
        ref_match = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-]+)", line, re.IGNORECASE)
        if ref_match:
            if current_patient and current_description and len(current_numbers) > 0:
                total = float(current_numbers[-1])
                if total > 0:
                    results.append({
                        "Patient": current_patient,
                        "Acte Cosmident": current_description.strip(),
                        "Prix Cosmident": f"{total:.2f}",
                    })
            current_patient = ref_match.group(1).strip()
            current_description = ""
            current_numbers = []
            continue
        
        # Détection via Bon n° ... Prescription ...
        bon_match = re.match(r"Bon n°\d+ du [\w\d/]+.*Prescription \d+", line)
        if bon_match and i < len(clean_lines):
            next_line = clean_lines[i].strip()
            ref_match = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-]+)", next_line, re.IGNORECASE)
            if ref_match:
                if current_patient and current_description and len(current_numbers) > 0:
                    total = float(current_numbers[-1])
                    if total > 0:
                        results.append({
                            "Patient": current_patient,
                            "Acte Cosmident": current_description.strip(),
                            "Prix Cosmident": f"{total:.2f}",
                        })
                current_patient = ref_match.group(1).strip()
                current_description = ""
                current_numbers = []
                i += 1
                continue
        
        if current_patient is None:
            continue

        # Séparer texte et nombres
        all_numbers = re.findall(r"\d+[\.,]\d{2}", line)
        # Ne garder que ceux >48 → prix
        prices = [n.replace(",", ".") for n in all_numbers if float(n.replace(",", ".")) > 48]
        if prices:
            current_numbers.extend(prices)
        
        # Texte de l'acte : retirer uniquement les prix (laisser dents et parenthèses)
        text_only = re.sub(r"\b\d+[\.,]\d{2}\b", "", line).strip()
        if text_only:
            if current_description:
                current_description += " " + text_only
            else:
                current_description = text_only
    
    # Ajouter le dernier acte
    if current_patient and current_description and len(current_numbers) > 0:
        total = float(current_numbers[-1])
        if total > 0:
            results.append({
                "Patient": current_patient,
                "Acte Cosmident": current_description.strip(),
                "Prix Cosmident": f"{total:.2f}",
            })
    
    return pd.DataFrame(results)

# =====================
# 🔹 Extraction Desmos
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
    for idx, line in enumerate(lines):
        patient_match = re.search(
            r"Ref\. ([A-ZÉÈÇÂÊÎÔÛÄËÏÖÜÀÙa-zéèçâêîôûäëïöüàù\s\-]+)", line
        )
        if patient_match:
            if current_patient and current_acte and current_hono:
                data.append({
                    "Patient": current_patient,
                    "Acte Desmos": current_acte.strip(),
                    "Prix Desmos": current_hono,
                })
            current_patient = patient_match.group(1).strip()
            current_acte = ""
            current_hono = ""
        elif re.search(
            r"(BIOTECH|Couronne transvissée|HBL\w+|ZIRCONE|GOUTTIÈRE SOUPLE|EMAX|ONLAY|PLAQUE|ADJONCTION|MONTAGE|DENT RESINE)",
            line,
            re.IGNORECASE,
        ):
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
            "Prix Desmos": current_hono,
        })
    return pd.DataFrame(data)

# =====================
# 🔹 Matching Cosmident / Desmos
# =====================
def match_patient_and_acte(cosmident_patient, df_desmos):
    cosmident_parts = set(cosmident_patient.lower().split())
    for idx, row in df_desmos.iterrows():
        desmos_patient = row["Patient"]
        desmos_parts = set(desmos_patient.lower().split())
        if (
            cosmident_patient.lower() == desmos_patient.lower()
            or len(cosmident_parts & desmos_parts) > 0
        ):
            return row["Acte Desmos"], row["Prix Desmos"]
    return "", ""

# =====================
# 🔹 Interface principale
# =====================
if uploaded_cosmident and uploaded_desmos:
    uploaded_cosmident.seek(0)
    uploaded_desmos.seek(0)
    
    df_cosmident = extract_data_from_cosmident(uploaded_cosmident)
    df_desmos = extract_desmos_acts(uploaded_desmos)
    
    st.subheader("1. Table issue du fichier PDF Cosmident (originale)")
    st.dataframe(df_cosmident, use_container_width=True)
    
    st.subheader("2. Table issue du fichier PDF Desmos")
    st.dataframe(df_desmos, use_container_width=True)
    
    # Fusion
    actes_desmos = []
    prix_desmos = []
    for patient in df_cosmident["Patient"]:
        acte, prix = match_patient_and_acte(patient, df_desmos)
        actes_desmos.append(acte)
        prix_desmos.append(prix)
    
    df_merged = df_cosmident.copy()
    df_merged["Acte Desmos"] = actes_desmos
    df_merged["Prix Desmos"] = prix_desmos
    
    st.subheader("3. Table issue de la fusion")
    st.dataframe(df_merged, use_container_width=True)
    
    st.success(f"✅ Extraction et fusion terminées — {len(df_merged)} actes trouvés")
else:
    st.info(
        "Veuillez charger les deux fichiers PDF (Cosmident et Desmos) pour lancer l'analyse."
    )
