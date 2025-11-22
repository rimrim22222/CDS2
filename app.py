import streamlit as st
import pandas as pd
import re
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import io

# ==================== CONFIG GÉNÉRALE ====================
st.set_page_config(
    page_title="Centre Dentaire - Outils Prothèses",
    page_icon="tooth",
    layout="wide"
)

# ==================== EN-TÊTE AVEC LOGO À DROITE ====================
col1, col2 = st.columns([5, 1])
with col1:
    st.title("Outils Prothèses & Cosmident")
    st.caption("Analyse Cosmident/Desmos • Extraction actes HBLD • Comparaison prix")
with col2:
    st.image("https://i.imgur.com/8j2iK8C.png", width=140)  # Ton logo permanent

# ==================== ONGLET PRINCIPAL ====================
tab1, tab2 = st.tabs(["Analyse Cosmident + Desmos", "Gestion des Prothèses (Excel)"])

# ==================================================================
# ========================= TAB 1 : COSMIDENT + DESMOS =====================
# ==================================================================
with tab1:
    st.header("Analyse des devis Cosmident + Desmos")

    col_a, col_b = st.columns(2)
    with col_a:
        uploaded_cosmident = st.file_uploader(
            "PDF ou image Cosmident", type=["pdf", "png", "jpg", "jpeg"], key="cosmi"
        )
    with col_b:
        uploaded_desmos = st.file_uploader(
            "PDF Desmos", type=["pdf"], key="desmos"
        )

    def extract_text_from_image(image):
        return pytesseract.image_to_string(image, lang='fra')

    def extract_data_from_cosmident(file):
        file_bytes = file.read()
        if file.type == "application/pdf":
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            full_text = ""
            for page in doc:
                page_text = page.get_text("text")
                stop_pattern = r"(COSMIDENT|IBAN|Siret|BIC|Tél\.|Total \(Euros\)|TOTAL TTC|Règlement|Chèque|NOS COORDONNÉES)"
                page_text = re.split(stop_pattern, page_text, flags=re.IGNORECASE)[0]
                full_text += page_text + "\n"
        else:
            image = Image.open(io.BytesIO(file_bytes))
            full_text = extract_text_from_image(image)

        lines = full_text.split("\n")
        clean_lines = [l.strip() for l in lines if l.strip()]
        clean_lines = [l for l in clean_lines if not re.search(r"(teinte|couleur|A[1-3]|B[1-3]|C[1-3]|D[1-3]|COSMIDENT|IBAN|Siret|BIC|€|TOTAL TTC)", l, re.I)]

        results = []
        current_patient = None
        current_description = ""
        current_numbers = []

        i = 0
        while i < len(clean_lines):
            line = clean_lines[i]
            i += 1

            ref_match = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-\é\è\ê\à\ç\ë]+)", line, re.I)
            if ref_match:
                if current_patient and current_description and current_numbers:
                    try:
                        prix = float(current_numbers[-1].replace(",", "."))
                        if prix > 0:
                            results.append({"Patient": current_patient, "Acte Cosmident": current_description.strip(), "Prix Cosmident": f"{prix:.2f}"})
                    except:
                        pass
                current_patient = ref_match.group(1).strip()
                current_description = ""
                current_numbers = []
                continue

            if current_patient is None:
                continue

            numbers = re.findall(r"\d+[\.,]\d{2}", line)
            text = re.sub(r"\s*\d+[\.,]\d{2}\s*", " ", line).strip()

            if text:
                if current_description and current_numbers:
                    try:
                        prix = float(current_numbers[-1].replace(",", "."))
                        if prix > 0:
                            results.append({"Patient": current_patient, "Acte Cosmident": current_description.strip(), "Prix Cosmident": f"{prix:.2f}"})
                    except:
                        pass
                    current_description = text
                    current_numbers = []
                else:
                    current_description = text if not current_description else current_description + " " + text

            if numbers:
                current_numbers.extend([n.replace(",", ".") for n in numbers])

        # Dernier acte
        if current_patient and current_description and current_numbers:
            try:
                prix = float(current_numbers[-1])
                if prix > 0:
                    results.append({"Patient": current_patient, "Acte Cosmident": current_description.strip(), "Prix Cosmident": f"{prix:.2f}"})
            except:
                pass

        return pd.DataFrame(results)

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
            patient_match = re.search(r"Ref\. ([A-ZÉÈÇÂÊÎÔÛÄËÏÖÜÀÙa-zéèçâêîôûäëïöüàù\s\-]+)", line)
            if patient_match:
                if current_patient and current_acte and current_hono:
                    data.append({"Patient": current_patient, "Acte Desmos": current_acte.strip(), "Prix Desmos": current_hono.replace(",", ".")})
                current_patient = patient_match.group(1).strip()
                current_acte = ""
                current_hono = ""

            elif re.search(r"(Couronne|HBL\w+|ZIRCONE|EMAX|ONLAY|PLAQUE|ADJONCTION|GOUTTIÈRE)", line, re.I):
                current_acte = line.strip()

            elif "Hono" in line:
                m = re.search(r"Hono\.?\s*:?\s*([\d,\.]+)", line)
                if m:
                    current_hono = m.group(1)

        if current_patient and current_acte and current_hono:
            data.append({"Patient": current_patient, "Acte Desmos": current_acte.strip(), "Prix Desmos": current_hono.replace(",", ".")})

        return pd.DataFrame(data)

    if uploaded_cosmident and uploaded_desmos:
        uploaded_cosmident.seek(0)
        uploaded_desmos.seek(0)

        with st.spinner("Analyse en cours..."):
            df_cosmi = extract_data_from_cosmident(uploaded_cosmident)
            df_desmos = extract_desmos_acts(uploaded_desmos)

        st.success("Analyse terminée !")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Cosmident")
            st.dataframe(df_cosmi, use_container_width=True)
        with col2:
            st.subheader("Desmos")
            st.dataframe(df_desmos, use_container_width=True)

        # Fusion simple par nom
        if not df_cosmi.empty and not df_desmos.empty:
            merged = df_cosmi.copy()
            merged["Acte Desmos"] = ""
            merged["Prix Desmos"] = ""
            for i, row in merged.iterrows():
                patient = row["Patient"]
                match = df_desmos[df_desmos["Patient"].str.contains(patient, case=False, na=False)]
                if not match.empty:
                    merged.loc[i, "Acte Desmos"] = match.iloc[0]["Acte Desmos"]
                    merged.loc[i, "Prix Desmos"] = match.iloc[0]["Prix Desmos"]

            st.subheader("Fusion Cosmident ↔ Desmos")
            st.dataframe(merged, use_container_width=True)

            csv = merged.to_csv(index=False, sep=";", encoding="utf-8-sig")
            st.download_button("Télécharger le comparatif CSV", csv, "comparatif_cosmident_desmos.csv", "text/csv")

# ==================================================================
# ========================= TAB 2 : GESTION PROTHÈSES EXCEL ================
# ==================================================================
with tab2:
    st.header("Extraction actes prothétiques (fichier Excel)")

    uploaded_excel = st.file_uploader("Charge ton fichier Excel (factures)", type=["xls", "xlsx"], key="excel")

    if uploaded_excel:
        try:
            df_raw = pd.read_excel(uploaded_excel, header=None, engine="openpyxl")
        except Exception as e:
            st.error(f"Erreur lecture Excel : {e}")
            st.stop()

        results = []
        current_patient = None

        for _, row in df_raw.iterrows():
            values = [str(v).strip() for v in row.tolist() if str(v).strip() not in ["nan", "None", ""]]
            row_text = " ".join(values)

            if re.search(r"Factures et Avoirs CENTRE DE SANTÉ DES LAURIERS", row_text, re.I):
                current_patient = None
                continue

            if re.search(r"N°\s*Dossier", row_text, re.I):
                m = re.search(r"([A-ZÉÈÊËÀÂÄÔÖÙÛÜÇ'\- ]{4,80})\s+N°\s*Dossier", row_text, re.I)
                if m:
                    current_patient = m.group(1).strip()
                continue

            if any(re.search(p, row_text.upper()) for p in [r"^DATE", r"^N°\s*FACT", r"^DENT", r"^ACTE", r"^HONO", r"^AMO", r"^TOTAL", r"^IMPRIMÉ"]):
                continue

            code = None
            code_idx = -1
            for i, cell in enumerate(values):
                if cell.startswith("HBLD") or cell in ["HBMD351", "HBLD634"]:
                    code = cell
                    code_idx = i
                    break

            if not code or code in ("HBLD490", "HBLD045"):
                continue

            # Tarif
            tarif = "?"
            for offset in [1, 2]:
                if code_idx + offset < len(values):
                    val = values[code_idx + offset].replace(" ", "")
                    if re.match(r"^\d{1,6}[,.]?\d{0,2}$", val.replace(",", ".")):
                        tarif = val.replace(".", ",")
                        break

            # Dent
            dent = "?"
            for i in range(code_idx - 1, max(-1, code_idx - 20), -1):
                m = re.search(r"\b([1-4]?\d)\b", str(values[i]))
                if m and 1 <= int(m.group(1)) <= 48:
                    dent = m.group(1).zfill(2)
                    break

            # Acte
            acte = "?"
            for i in range(code_idx - 1, max(-1, code_idx - 30), -1):
                v = str(values[i]).strip()
                if v and v not in ["nan", "None", ""]:
                    acte = v
                    break

            if current_patient:
                results.append({
                    "Patient": current_patient,
                    "Dent": dent,
                    "Code": code,
                    "Acte": acte,
                    "Tarif": tarif
                })

        if results:
            df = pd.DataFrame(results)
            st.success(f"**{len(df)} actes prothétiques extraits !**")
            st.dataframe(df[["Patient", "Dent", "Code", "Acte", "Tarif"]], use_container_width=True, hide_index=True)

            csv = df.to_csv(index=False, sep=";", encoding="utf-8-sig")
            st.download_button(
                label="Télécharger le CSV prothèses",
                data=csv,
                file_name="Protheses_extraites.csv",
                mime="text/csv"
            )
        else:
            st.warning("Aucun acte HBLD trouvé.")
