import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from PIL import Image
import pytesseract
import io
import unicodedata

st.set_page_config(page_title="Analyse Cosmident + Desmos", layout="wide")
st.title("📄 Analyse des actes dentaires Cosmident + Desmos")

uploaded_cosmident = st.file_uploader(
    "Upload le fichier Cosmident (PDF ou image)", type=["pdf", "png", "jpg", "jpeg"]
)
uploaded_desmos = st.file_uploader(
    "Upload le fichier Desmos (PDF)", type=["pdf"], key="desmos"
)

# ============================
# 🔧 UTILITAIRES
# ============================

def normalize_name(name: str):
    """Normalise fortement un nom pour comparaison : minuscules, sans accents, sans espaces, sans ponctuation."""
    if not isinstance(name, str):
        return ""
    name = name.lower()
    name = ''.join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )
    name = re.sub(r"[^a-z]", "", name)
    return name


def levenshtein(a, b):
    """Distance de Levenshtein classique."""
    if len(a) < len(b):
        return levenshtein(b, a)

    if len(b) == 0:
        return len(a)

    previous_row = range(len(b) + 1)
    for i, ca in enumerate(a):
        current_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (ca != cb)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def similarity(a, b):
    """Score de similarité entre 0 et 1 basé sur Levenshtein."""
    if not a or not b:
        return 0
    a = normalize_name(a)
    b = normalize_name(b)
    dist = levenshtein(a, b)
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 0
    return 1 - dist / max_len


# ============================
# 🔹 Extraction image Cosmident
# ============================

def extract_text_from_image(image):
    return pytesseract.image_to_string(image)


# ============================
# 🔹 Extraction Cosmident
# ============================

def extract_data_from_cosmident(file):
    file_bytes = file.read()

    # --- PDF
    if file.type == "application/pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            page_text = page.get_text("text")
            stop_pattern = r"(COSMIDENT|IBAN|Siret|BIC|Tél\.|TOTAL TTC|Règlement|Chèque)"
            page_text = re.split(stop_pattern, page_text, flags=re.IGNORECASE)[0]
            text += page_text + "\n"

    # --- IMAGE
    else:
        image = Image.open(io.BytesIO(file_bytes))
        text = extract_text_from_image(image)

    # Option Debug
    with st.expander("Texte brut Cosmident"):
        st.write(text[:2000])

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    results = []
    current_patient = None
    current_act = ""
    current_prices = []

    for i, line in enumerate(lines):

        # Détection patient
        m = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\'\-]+)", line, re.I)
        if m:
            # Sauvegarder acte précédent
            if current_patient and current_act and current_prices:
                results.append({
                    "Patient": current_patient,
                    "Acte Cosmident": current_act.strip(),
                    "Prix Cosmident": current_prices[-1]
                })
            current_patient = m.group(1).strip()
            current_act = ""
            current_prices = []
            continue

        if not current_patient:
            continue

        # Extraction Montants
        prices = re.findall(r"\d+[\.,]\d{2}", line)
        prices = [p.replace(",", ".") for p in prices]

        text_without_prices = re.sub(r"\d+[\.,]\d{2}", " ", line).strip()

        if text_without_prices:
            if current_act and current_prices:
                results.append({
                    "Patient": current_patient,
                    "Acte Cosmident": current_act.strip(),
                    "Prix Cosmident": current_prices[-1]
                })
                current_act = ""
                current_prices = []

            current_act += " " + text_without_prices

        if prices:
            current_prices.extend(prices)

    if current_patient and current_act and current_prices:
        results.append({
            "Patient": current_patient,
            "Acte Cosmident": current_act.strip(),
            "Prix Cosmident": current_prices[-1]
        })

    return pd.DataFrame(results)


# ============================
# 🔹 Extraction Desmos
# ============================

def extract_desmos_acts(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    text = "\n".join([page.get_text() for page in doc])

    lines = text.split("\n")
    results = []
    current_patient = None
    current_act = None
    current_price = None

    for line in lines:
        # Détection patient
        m = re.search(r"Ref\. ([A-Za-zÀ-ÿ\s\'\-]+)", line)
        if m:
            if current_patient and current_act and current_price:
                results.append({
                    "Patient": current_patient,
                    "Acte Desmos": current_act,
                    "Prix Desmos": current_price
                })
            current_patient = m.group(1).strip()
            current_act = ""
            current_price = ""
            continue

        # Détection acte
        if re.search(r"(Couronne|BIOTECH|ZIRCONE|ONLAY|EMAX|ADJONCTION|GOUTTIÈRE|RESINE|HBL\w+)", line, re.I):
            current_act = line.strip()

        # Détection prix
        m_price = re.search(r"(\d+[\.,]\d{2})", line)
        if m_price:
            current_price = m_price.group(1).replace(",", ".")

    if current_patient and current_act and current_price:
        results.append({
            "Patient": current_patient,
            "Acte Desmos": current_act,
            "Prix Desmos": current_price
        })

    return pd.DataFrame(results)


# ============================
# 🔥 MATCHING PERMISSIF
# ============================

def best_match(target_name, df_desmos):
    """Trouve le meilleur match DESMOS basé sur une similarité permissive."""

    best_score = 0
    best_row = None

    for _, row in df_desmos.iterrows():
        score = similarity(target_name, row["Patient"])
        if score > best_score:
            best_score = score
            best_row = row

    if best_score < 0.40:  # Trop faible → pas de correspondance
        return "", "", "", 0

    return (
        best_row["Patient"],
        best_row["Acte Desmos"],
        best_row["Prix Desmos"],
        round(best_score, 3)
    )


# ============================
# 🔹 Interface
# ============================

if uploaded_cosmident and uploaded_desmos:

    uploaded_cosmident.seek(0)
    uploaded_desmos.seek(0)

    df_cosmo = extract_data_from_cosmident(uploaded_cosmident)
    df_desmos = extract_desmos_acts(uploaded_desmos)

    st.subheader("📌 Table Cosmident")
    st.dataframe(df_cosmo, use_container_width=True)

    st.subheader("📌 Table Desmos")
    st.dataframe(df_desmos, use_container_width=True)

    # ======================
    # 🚀 Fusion avec matching permissif
    # ======================

    merged = df_cosmo.copy()
    merged["Patient Desmos"] = ""
    merged["Acte Desmos"] = ""
    merged["Prix Desmos"] = ""
    merged["Score Similarité"] = 0.0

    for i, pat in enumerate(merged["Patient"]):
        pat_desmos, act, price, score = best_match(pat, df_desmos)
        merged.at[i, "Patient Desmos"] = pat_desmos
        merged.at[i, "Acte Desmos"] = act
        merged.at[i, "Prix Desmos"] = price
        merged.at[i, "Score Similarité"] = score

    st.subheader("🧩 Résultat Final (Fusion Permissive)")
    st.dataframe(merged, use_container_width=True)

    st.success("✅ Analyse complète !")

else:
    st.info("Veuillez charger les fichiers Cosmident et Desmos.")
