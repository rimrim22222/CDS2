import streamlit as st
import pandas as pd
import re
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import io
from difflib import SequenceMatcher

st.set_page_config(page_title="Fusion HBL + Cosmident/Desmos", layout="wide")
st.title("📊 Fusion des actes HBL et Cosmident/Desmos par patient")

# =====================
# 🔹 Uploads
# =====================
uploaded_excel = st.file_uploader("Upload ton fichier Excel HBL", type=["xls", "xlsx"])
uploaded_cosmident = st.file_uploader("Upload le fichier Cosmident (PDF ou image)", type=["pdf", "png", "jpg", "jpeg"])
uploaded_desmos = st.file_uploader("Upload le fichier Desmos (PDF)", type=["pdf"])

# =====================
# 🔹 Fonction utilitaire pour comparer noms avec tolérance
# =====================
def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# =====================
# 🔹 Extraction HBL ciblée
# =====================
def extract_hbl(file):
    try:
        if file.name.lower().endswith(".xls"):
            df_raw = pd.read_excel(file, header=None, engine="xlrd")
        else:
            df_raw = pd.read_excel(file, header=None)
    except Exception as e:
        st.error(f"Erreur de lecture du fichier Excel : {e}")
        return pd.DataFrame(columns=["Patient","Dent","Code","Acte","Tarif"])

    results = []
    current_patient = None
    for idx, row in df_raw.iterrows():
        row = row.astype(str).str.strip()
        values = [str(v).strip() for v in row.tolist()]
        row_text = " ".join([v for v in values if v not in ["nan","None",""]])

        # --- Detection patient ---
        patient_match = re.search(r"([A-ZÉÈÊËÀÂÄÔÖÙÛÜÇ][A-ZÉÈÊËÀÂÄÔÖÙÛÜÇ'\- ]{4,80})\s+N°\s*Dossier", row_text, re.I)
        if patient_match:
            current_patient = patient_match.group(1).strip()
            continue

        # --- Recherche du code ciblé ---
        code = None
        code_idx = -1
        for i, cell in enumerate(values):
            if cell.startswith("HBLD") or cell == "HBMD351" or cell == "HBLD634":
                code = cell
                code_idx = i
                break
        if not code or code=="HBLD490":  # ignore HBLD490
            continue

        # --- Tarif ---
        tarif = "?"
        for offset in [1,2]:
            if code_idx + offset < len(values):
                val = values[code_idx+offset].replace(" ","")
                if re.match(r"^\d+[\.,]?\d*$", val.replace(",",".")):
                    tarif = val.replace(".",",")
                    break

        # --- Dent ---
        dent = "?"
        for i in range(code_idx-1,max(-1,code_idx-20),-1):
            m = re.search(r"\b([1-4]?\d)\b", str(values[i]))
            if m and 1<=int(m.group(1))<=48:
                dent = m.group(1).zfill(2)
                break

        # --- Acte ---
        acte = "?"
        for i in range(code_idx-1,max(-1,code_idx-30),-1):
            v = str(values[i]).strip()
            if v not in ["nan","None",""]:
                acte = v
                break

        if current_patient:
            results.append({"Patient": current_patient,"Dent":dent,"Code":code,"Acte":acte,"Tarif":tarif})

    df = pd.DataFrame(results)
    return df

# =====================
# 🔹 Extraction Cosmident
# =====================
def extract_cosmident(file):
    file_bytes = file.read()
    full_text = ""
    if file.type=="application/pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page in doc:
            page_text = page.get_text("text")
            stop_pattern = r"(COSMIDENT|IBAN|Siret|BIC|Tél\.|Total \(Euros\)|TOTAL TTC|Règlement|Chèque)"
            page_text = re.split(stop_pattern,page_text,flags=re.IGNORECASE)[0]
            full_text += page_text + "\n"
    else:
        image = Image.open(io.BytesIO(file_bytes))
        full_text = pytesseract.image_to_string(image)

    lines = full_text.split("\n")
    clean_lines = []
    for l in lines:
        l = l.strip()
        if not l: continue
        if re.search(r"Teinte|Vitapan|COSMIDENT|IBAN|€|TOTAL TTC|CHÈQUE", l, re.I): continue
        clean_lines.append(l)

    results = []
    current_patient = None
    current_description = ""
    current_numbers = []

    for line in clean_lines:
        ref = re.search(r"Ref\.?\s*Patient\s*:?(.+)",line,re.I)
        if ref:
            current_patient = ref.group(1).strip()
            current_description=""
            current_numbers=[]
            continue

        nums = re.findall(r"\d+[\.,]\d{2}",line)
        norm_nums = [n.replace(",",".") for n in nums]
        text = re.sub(r"\d+[\.,]\d{2}","",line).strip()
        if text: current_description = text
        if norm_nums: current_numbers.extend(norm_nums)
        if current_patient and current_description and current_numbers:
            results.append({
                "Patient": current_patient,
                "Acte Cosmident": current_description,
                "Prix Cosmident": current_numbers[-1]
            })
            current_description=""
            current_numbers=[]

    df = pd.DataFrame(results)
    return df

# =====================
# 🔹 Extraction Desmos
# =====================
def extract_desmos(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    full_text=""
    for page in doc: full_text+=page.get_text()+"\n"
    lines = full_text.split("\n")
    data=[]
    current_patient=None
    current_acte=""
    current_hono=""
    for line in lines:
        pm = re.search(r"Ref\. ([A-ZÉÈÇÂÊÎÔÛÄËÏÖÜÀÙa-zéèçâêîôûäëïöüàù\s\-]+)",line)
        if pm:
            current_patient=pm.group(1).strip()
            current_acte=""
            current_hono=""
        elif re.search(r"(BIOTECH|Couronne|HBL\w+|ZIRCONE|EMAX|ONLAY|PLAQUE|ADJONCTION)",line,re.I):
            current_acte=line.strip()
        elif "Hono" in line:
            hm = re.search(r"Hono\.?\s*:?\s*([\d,\.]+)",line)
            if hm: current_hono=hm.group(1).replace(",",".")

        elif current_acte and re.match(r"^\d+[\.,]\d{2}$",line):
            current_hono=line.replace(",",".")

        if current_patient and current_acte and current_hono:
            data.append({"Patient":current_patient,"Acte Desmos":current_acte,"Prix Desmos":current_hono})

    return pd.DataFrame(data)

# =====================
# 🔹 Fusion intelligente
# =====================
def fuse_patients(df_hbl, df_cosm, df_desmos):
    all_patients = set(df_hbl["Patient"].unique()) | set(df_cosm["Patient"].unique()) | set(df_desmos["Patient"].unique())
    fusion = []
    for pat in all_patients:
        # Match HBL
        hbl_rows = df_hbl[df_hbl["Patient"].apply(lambda x: similar(x,pat)>0.85)]
        cosm_rows = df_cosm[df_cosm["Patient"].apply(lambda x: similar(x,pat)>0.85)]
        desmos_rows = df_desmos[df_desmos["Patient"].apply(lambda x: similar(x,pat)>0.85)]

        fusion.append({
            "Patient": pat,
            "HBL": hbl_rows.to_dict(orient="records"),
            "Cosmident": cosm_rows.to_dict(orient="records"),
            "Desmos": desmos_rows.to_dict(orient="records")
        })
    return fusion

# =====================
# 🔹 Interface principale
# =====================
if uploaded_excel and uploaded_cosmident and uploaded_desmos:
    uploaded_excel.seek(0)
    uploaded_cosmident.seek(0)
    uploaded_desmos.seek(0)

    df_hbl = extract_hbl(uploaded_excel)
    df_cosm = extract_cosmident(uploaded_cosmident)
    df_desmos = extract_desmos(uploaded_desmos)

    st.subheader("Table HBL")
    st.dataframe(df_hbl)
    st.subheader("Table Cosmident")
    st.dataframe(df_cosm)
    st.subheader("Table Desmos")
    st.dataframe(df_desmos)

    fusion = fuse_patients(df_hbl, df_cosm, df_desmos)

    st.subheader("Fusion par patient (HBL + Cosmident + Desmos)")
    for f in fusion:
        st.markdown(f"### Patient : {f['Patient']}")
        st.markdown("**HBL**")
        st.json(f['HBL'])
        st.markdown("**Cosmident**")
        st.json(f['Cosmident'])
        st.markdown("**Desmos**")
        st.json(f['Desmos'])
        st.markdown("---")
else:
    st.info("Charge les 3 fichiers pour lancer la fusion.")
