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
# 🔹 Extraction Cosmident robuste avec gestion multi-actes
# =====================
def extract_data_from_cosmident(file):
    file_bytes = file.read()
    if file.type == "application/pdf":
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as e:
            st.error(f"Erreur ouverture PDF : {e}")
            return pd.DataFrame(columns=["Patient", "Acte Cosmident", "Prix Cosmident"])
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
            return pd.DataFrame(columns=["Patient", "Acte Cosmident", "Prix Cosmident"])

    # Nettoyage du texte
    lines = full_text.split("\n")
    clean_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.search(r"Teinte dentine|teinte|Vitapan|A[1-3]|B[1-3]|C[1-3]|D[1-3]", line, re.IGNORECASE):
            continue
        if re.search(r"(COSMIDENT|IBAN|Siret|BIC|€|TOTAL TTC|CHÈQUE)", line, re.IGNORECASE):
            continue
        clean_lines.append(line)

    results = []
    debug_lines = []

    current_patient = None
    total_lines = len(clean_lines)
    debug_max_lines = 2 * 50  # approx 2 dernières pages

    for idx, line in enumerate(clean_lines):
        # Détection du patient
        ref_match = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-]+)", line, re.IGNORECASE)
        if ref_match:
            current_patient = ref_match.group(1).strip()
            continue

        if current_patient is None:
            continue

        # --- Gestion lignes avec plusieurs actes/prix ---
        groups = re.findall(r"([A-ZÉÈÇÂÊÎÔÛÄËÏÖÜa-zéèçâêîôûäëïöü0-9\(\)\s\-,]+?)\s((?:\d+[\.,]\d{2}\s?)+)", line)
        for desc, prix_str in groups:
            prix_list = [p.replace(",", ".") for p in prix_str.strip().split()]
            if prix_list:
                total_prix = prix_list[-1]  # dernier montant = prix final
                results.append({
                    "Patient": current_patient,
                    "Acte Cosmident": desc.strip(),
                    "Prix Cosmident": total_prix
                })

        # --- Debug : 2 dernières pages ---
        if idx >= total_lines - debug_max_lines:
            debug_lines.append({
                "Ligne relative": idx+1,
                "Patient courant": current_patient,
                "Texte brut": line,
                "Actes trouvés": groups
            })

    # Affichage debug
    st.subheader("DEBUG : Aperçu des 2 dernières pages Cosmident")
    for d in debug_lines:
        st.markdown(f"**Ligne {d['Ligne relative']}** | Patient : `{d['Patient courant']}`")
        st.text(f"Texte brut : {d['Texte brut']}")
        st.text(f"Actes trouvés : {d['Actes trouvés']}")
        st.markdown("---")

    # Forcer les colonnes même si résultats vides
    df = pd.DataFrame(results)
    if df.empty:
        df = pd.DataFrame(columns=["Patient", "Acte Cosmident", "Prix Cosmident"])
    return df

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
