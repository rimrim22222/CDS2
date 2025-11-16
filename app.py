import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from PIL import Image
import pytesseract
import io
import unicodedata
from difflib import SequenceMatcher

st.set_page_config(page_title="Analyse Cosmident + Desmos", layout="wide")
st.title("📄 Analyse des actes dentaires Cosmident + Desmos")

uploaded_cosmident = st.file_uploader(
    "Upload le fichier Cosmident (PDF ou image)", type=["pdf", "png", "jpg", "jpeg"]
)
uploaded_desmos = st.file_uploader(
    "Upload le fichier Desmos (PDF)", type=["pdf"], key="desmos"
)

# =====================
# 🔹 Extraction image
# =====================
def extract_text_from_image(image):
    return pytesseract.image_to_string(image)

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
            full_text = extract_text_from_image(image)
        except Exception as e:
            st.error(f"Erreur lecture image : {e}")
            return pd.DataFrame()
    
    with st.expander("🧩 Aperçu du texte extrait (Cosmident brut)"):
        st.write(full_text[:2000])
    
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

        ref_match = re.search(
            r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-]+)",
            line,
            re.IGNORECASE,
        )
        if ref_match:
            if current_patient and current_description and len(current_numbers) > 0:
                try:
                    total = float(current_numbers[-1])
                    if total > 0:
                        results.append(
                            {
                                "Patient": current_patient,
                                "Acte Cosmident": current_description.strip(),
                                "Prix Cosmident": f"{total:.2f}",
                            }
                        )
                except ValueError:
                    pass
            current_description = ""
            current_numbers = []
            current_patient = ref_match.group(1).strip()
            continue
        
        bon_match = re.match(r"Bon n°\d+ du [\w\d/]+.*Prescription \d+", line)
        if bon_match and i < len(clean_lines):
            next_line = clean_lines[i].strip()
            ref_match = re.search(
                r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-]+)",
                next_line,
                re.IGNORECASE,
            )
            if ref_match:
                if current_patient and current_description and len(current_numbers) > 0:
                    try:
                        total = float(current_numbers[-1])
                        if total > 0:
                            results.append(
                                {
                                    "Patient": current_patient,
                                    "Acte Cosmident": current_description.strip(),
                                    "Prix Cosmident": f"{total:.2f}",
                                }
                            )
                    except ValueError:
                        pass
                current_description = ""
                current_numbers = []
                current_patient = ref_match.group(1).strip()
                i += 1
                continue
        
        if current_patient is None:
            continue
        
        this_numbers = re.findall(r"\d+[\.,]\d{2}", line)
        norm_numbers = [n.replace(",", ".") for n in this_numbers]
        this_text = re.sub(r"\s*\d+[\.,]\d{2}\s*", " ", line).strip()
        
        if this_text:
            if current_description and len(current_numbers) > 0:
                try:
                    total = float(current_numbers[-1])
                    if total > 0:
                        results.append(
                            {
                                "Patient": current_patient,
                                "Acte Cosmident": current_description.strip(),
                                "Prix Cosmident": f"{total:.2f}",
                            }
                        )
                except ValueError:
                    pass
                current_description = ""
                current_numbers = []
            if current_description:
                current_description += " " + this_text
            else:
                current_description = this_text
        
        if norm_numbers:
            current_numbers.extend(norm_numbers)
    
    if current_patient and current_description and len(current_numbers) > 0:
        try:
            total = float(current_numbers[-1])
            if total > 0:
                results.append(
                    {
                        "Patient": current_patient,
                        "Acte Cosmident": current_description.strip(),
                        "Prix Cosmident": f"{total:.2f}",
                    }
                )
        except ValueError:
            pass
    
    return pd.DataFrame(results)

# =====================
# 🔹 Extraction DESMOS (ROBUSTE)
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
        l = line.strip()

        # Patient
        patient_match = re.search(r"Ref\.?\s*([A-Za-zÀ-ÖØ-öø-ÿ\s\-]+)", l)
        if patient_match:
            if current_patient and current_acte and current_hono:
                data.append({
                    "Patient": current_patient,
                    "Acte Desmos": current_acte,
                    "Prix Desmos": current_hono
                })
            current_patient = patient_match.group(1).strip()
            current_acte = ""
            current_hono = ""
            continue

        # Acte
        if re.search(r"(BIOTECH|HBL|TRANSVISS|ZIRCONE|GOUTTI|EMAX|ONLAY|PLAQUE|MONTAGE|RESINE)", l, re.IGNORECASE):
            current_acte = l
            continue

        # Prix
        price_match = re.search(r"(\d+[.,]\d{2})", l)

        if ("hono" in l.lower() or "honor" in l.lower()) and price_match:
            current_hono = price_match.group(1).replace(",", ".")
            continue
        
        if current_acte and not current_hono and price_match:
            current_hono = price_match.group(1).replace(",", ".")
            continue

    # append last
    if current_patient and current_acte and current_hono:
        data.append({
            "Patient": current_patient,
            "Acte Desmos": current_acte,
            "Prix Desmos": current_hono
        })

    return pd.DataFrame(data)

# =====================
# 🔹 Matching intelligent
# =====================
def normalize_name(name):
    name = name.lower().strip()
    name = "".join(
        c for c in unicodedata.normalize("NFD", name)
        if unicodedata.category(c) != "Mn"
    )
    return name

def name_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def match_patient_and_acte(cosmident_patient, df_desmos):
    if not isinstance(cosmident_patient, str):
        return "", ""
    
    cosmident_norm = normalize_name(cosmident_patient)

    for idx, row in df_desmos.iterrows():
        desmos_norm = normalize_name(row["Patient"])

        if cosmident_norm == desmos_norm:
            return row["Acte Desmos"], row["Prix Desmos"]

        if any(word in desmos_norm for word in cosmident_norm.split()):
            return row["Acte Desmos"], row["Prix Desmos"]

        if set(cosmident_norm.split()) & set(desmos_norm.split()):
            return row["Acte Desmos"], row["Prix Desmos"]

        if name_similarity(cosmident_norm, desmos_norm) >= 0.80:
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

    # ============================
    # 🔍 DEBUG BLOCK AJOUTÉ
    # ============================
    st.subheader("🔍 DEBUG : Correspondance Cosmident → Desmos")

    debug_rows = []

    for patient in df_cosmident["Patient"]:
        acte, prix = match_patient_and_acte(patient, df_desmos)
        debug_rows.append({
            "Patient Cosmident": patient,
            "Acte trouvé dans Desmos": acte if acte else "❌ Aucun acte trouvé",
            "Prix trouvé dans Desmos": prix if prix else "❌ Aucun prix trouvé",
        })

    df_debug = pd.DataFrame(debug_rows)
    st.dataframe(df_debug, use_container_width=True)

    # ============================
    # 🔹 Fusion finale
    # ============================
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
    st.info("Veuillez charger les deux fichiers PDF (Cosmident et Desmos) pour lancer l'analyse.")
