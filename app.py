import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from PIL import Image
import pytesseract
import io
import unicodedata
from pathlib import Path

# ======================
# CONFIG + LOGO
# ======================
st.set_page_config(page_title="Analyse Cosmident + Desmos", layout="wide")

logo_path = Path("logo.png")
st.sidebar.title("🦷 Cosmident + Desmos")

if logo_path.exists():
    st.sidebar.image(str(logo_path), width=200)
else:
    st.sidebar.image(
        "https://scontent-mrs2-1.xx.fbcdn.net/v/t39.30808-6/305157485_519313286862181_9045589531882558278_n.png",
        width=200,
    )
    st.sidebar.caption("Logo manquant → place logo.png à la racine de l’app")

st.title("📄 Analyse des actes dentaires Cosmident + Desmos (Excel)")

# ======================
# UPLOAD
# ======================
uploaded_cosmident = st.file_uploader(
    "📤 Charge le fichier Cosmident (PDF ou image)", type=["pdf", "png", "jpg", "jpeg"]
)
uploaded_desmos = st.file_uploader(
    "📤 Charge le fichier Desmos (Excel)", type=["xls", "xlsx"], key="desmos"
)

# ======================
# OUTILS
# ======================

def normalize_name(name: str):
    """Normalise fortement un nom : minuscules, sans accents, alphanum uniquement."""
    if not isinstance(name, str):
        return ""
    name = name.lower()
    name = "".join(
        c for c in unicodedata.normalize("NFD", name)
        if unicodedata.category(c) != "Mn"
    )
    name = re.sub(r"[^a-z]", "", name)
    return name


def levenshtein(a, b):
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
    """Score 0–1 basé sur Levenshtein."""
    if not a or not b:
        return 0
    a = normalize_name(a)
    b = normalize_name(b)
    if not a or not b:
        return 0
    dist = levenshtein(a, b)
    max_len = max(len(a), len(b))
    return 1 - dist / max_len


# ======================
# EXTRACTION COSMIDENT
# ======================

def extract_text_from_image(image):
    return pytesseract.image_to_string(image)


def extract_data_from_cosmident(file):
    file_bytes = file.read()

    # PDF
    if file.type == "application/pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            page_text = page.get_text("text")
            stop_pattern = r"(COSMIDENT|IBAN|Siret|BIC|Tél\.|TOTAL TTC|Règlement|Chèque)"
            page_text = re.split(stop_pattern, page_text, flags=re.IGNORECASE)[0]
            text += page_text + "\n"
    else:
        # IMAGE
        image = Image.open(io.BytesIO(file_bytes))
        text = extract_text_from_image(image)

    with st.expander("🔎 Texte Cosmident (debug)"):
        st.write(text[:2000])

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    results = []
    current_patient = None
    current_act = ""
    current_prices = []

    for line in lines:

        # Patient
        m = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\'\-]+)", line, re.I)
        if m:
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


# ======================
# EXTRACTION DESMOS EXCEL
# ======================

def extract_desmos_acts_excel(file):
    try:
        df = pd.read_excel(file)
    except Exception as e:
        st.error(f"❌ Erreur lecture Excel Desmos : {e}")
        return pd.DataFrame()

    df.columns = [c.strip().lower() for c in df.columns]

    col_patient = next((c for c in df.columns if "patient" in c), None)
    col_acte = next((c for c in df.columns if "acte" in c), None)
    col_prix = next((c for c in df.columns if "prix" in c or "hono" in c), None)

    if not (col_patient and col_acte and col_prix):
        st.error("❌ Le fichier Desmos doit contenir : Patient / Acte / Prix")
        return pd.DataFrame()

    df[col_prix] = df[col_prix].astype(str).str.replace(",", ".")
    df[col_prix] = df[col_prix].str.extract(r"(\d+[\.,]?\d*)")[0]

    df = df[[col_patient, col_acte, col_prix]].copy()
    df.columns = ["Patient", "Acte Desmos", "Prix Desmos"]

    return df


# ======================
# MATCH PERMISSIF
# ======================

def best_match(target_name, df_desmos):
    best_score = 0
    best_row = None

    for _, row in df_desmos.iterrows():
        score = similarity(target_name, row["Patient"])
        if score > best_score:
            best_score = score
            best_row = row

    if best_score < 0.40:
        return "", "", "", 0

    return (
        best_row["Patient"],
        best_row["Acte Desmos"],
        best_row["Prix Desmos"],
        round(best_score, 3)
    )


# ======================
# INTERFACE
# ======================

if uploaded_cosmident and uploaded_desmos:

    uploaded_cosmident.seek(0)

    df_cosmo = extract_data_from_cosmident(uploaded_cosmident)
    df_desmos = extract_desmos_acts_excel(uploaded_desmos)

    st.subheader("📌 Table Cosmident")
    st.dataframe(df_cosmo, use_container_width=True)

    st.subheader("📌 Table Desmos (Excel)")
    st.dataframe(df_desmos, use_container_width=True)

    # Fusion
    merged = df_cosmo.copy()
    merged["Patient Desmos"] = ""
    merged["Acte Desmos"] = ""
    merged["Prix Desmos"] = ""
    merged["Score Similarité"] = 0.0

    for i, pat in enumerate(merged["Patient"]):
        pdes, acte, prix, score = best_match(pat, df_desmos)
        merged.at[i, "Patient Desmos"] = pdes
        merged.at[i, "Acte Desmos"] = acte
        merged.at[i, "Prix Desmos"] = prix
        merged.at[i, "Score Similarité"] = score

    st.subheader("🧩 Résultat Final (Fusion Permissive)")
    st.dataframe(merged, use_container_width=True)

    st.success("✅ Analyse complète !")

else:
    st.info("Veuillez charger les fichiers Cosmident et Desmos.")
