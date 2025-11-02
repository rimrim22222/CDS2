import streamlit as st
import pdfplumber
import pandas as pd
import re

st.set_page_config(page_title="Extraction PDF Factures", layout="wide")

st.title("📄 Extraction de données de facturation à partir d’un PDF")

uploaded_file = st.file_uploader("📂 Choisis un fichier PDF", type=["pdf"])

# Fonctions utilitaires
def norm_num(s):
    return s.replace("\u00A0", "").replace(" ", "").replace(",", ".") if isinstance(s, str) else s

def extract_data_from_pdf(pdf_file):
    rows = []
    with pdfplumber.open(pdf_file) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text() or ""
            full_text += "\n" + text.replace("\xa0", " ")

    header_re = re.compile(r"([A-ZÉÈÊËÎÏÔÖÙÛÜÇ' \-]{3,})\s+N° Dossier", re.MULTILINE)
    code_re = re.compile(r"(H[A-Z]{2,4}\d{3})")
    num_re = re.compile(r"-?\d{1,3}(?:[ \u00A0]\d{3})*(?:,\d{2})")

    headers = [(m.start(), m.group(1).strip()) for m in header_re.finditer(full_text)]
    headers.sort()

    for m in code_re.finditer(full_text):
        code = m.group(1)
        pos = m.start()
        name = ""
        for hp, hn in reversed(headers):
            if hp < pos:
                name = hn
                break

        before = full_text[max(0, pos - 220):pos]
        after = full_text[pos: pos + 120]
        nums_before = num_re.findall(before)
        nums_after = num_re.findall(after)
        nums = [n.replace("\u00A0", " ").strip() for n in nums_before[-8:]] + [n.replace("\u00A0", " ").strip() for n in nums_after[:4]]

        hono, cotcoef = "", ""
        if len(nums) >= 6:
            run = nums[-6:]
            hono, cotcoef = run[0], run[3]
        elif len(nums) >= 4:
            run = nums[-4:]
            hono, cotcoef = run[0], run[3]
        elif len(nums) == 3:
            hono, cotcoef = nums[0], nums[2]
        elif len(nums) == 2:
            hono, cotcoef = nums[0], nums[1]
        elif len(nums) == 1:
            hono = nums[0]

        desc_match = re.search(re.escape(code) + r"([^\n\r]{0,120})", full_text[pos: pos + 200])
        acte_desc = code + (desc_match.group(1).strip() if desc_match else "")

        rows.append([name, acte_desc, cotcoef, hono])

    df = pd.DataFrame(rows, columns=["Nom", "Acte", "Cot.+Coef.", "Hono."])
    df["Cot.+Coef."] = df["Cot.+Coef."].apply(norm_num)
    df["Hono."] = df["Hono."].apply(norm_num)
    df.drop_duplicates(inplace=True)
    return df

# Interface Streamlit
if uploaded_file:
    with st.spinner("🔍 Extraction des données en cours..."):
        df = extract_data_from_pdf(uploaded_file)

    st.success(f"✅ Extraction terminée : {len(df)} lignes trouvées")

    # Afficher le tableau
    st.dataframe(df, use_container_width=True)

    # Téléchargement CSV
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("💾 Télécharger en CSV", csv, "extraction_factures.csv", "text/csv")

else:
    st.info("➡️ Téléverse un fichier PDF pour commencer l’analyse.")
