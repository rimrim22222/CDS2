import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

st.set_page_config(page_title="Récap HBL - Extraction 100%", layout="wide")
st.title("Récapitulatif HBL – Extraction par colonnes (COT.+COEF.)")

def extract_hbl(file, debug=False):
    if not file:
        return pd.DataFrame(), pd.DataFrame()

    file.seek(0)
    doc = fitz.open(stream=file.read(), filetype="pdf")

    # --- Trouver les positions X des colonnes ---
    col_x = {}
    for page_num in range(min(3, doc.page_count)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block: continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    x = span["bbox"][0]
                    if text == "Cot.+Coef.": col_x["cot"] = x
                    if text == "Hono.": col_x["hono"] = x
                    if text == "AMO": col_x["amo"] = x
        if len(col_x) >= 2: break

    if "cot" not in col_x or "hono" not in col_x:
        st.error("Colonnes non trouvées !")
        return pd.DataFrame(), pd.DataFrame()

    cot_x = col_x["cot"]
    hono_x = col_x["hono"]
    TOL = 40

    data = []
    debug_info = []
    patient = None

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block: continue
            lines = []
            for line in block["lines"]:
                spans = [(span["text"].strip(), span["bbox"][0]) for span in line["spans"] if span["text"].strip()]
                if spans: lines.append(spans)

            i = 0
            while i < len(lines):
                line_spans = lines[i]
                line_text = " ".join([s[0] for s in line_spans])

                # --- Patient ---
                if re.search(r"N° Dossier", line_text):
                    patient = re.search(r"([A-ZÉÈÀÙÂÊÎÔÛÇ'\- ]+) N° Dossier", line_text)
                    patient = patient.group(1).strip() if patient else patient
                    i += 1
                    continue

                # --- Ignorer totaux ---
                if any(t in line_text for t in ["Total Facture", "Total des Factures", "Total Avoir"]):
                    i += 1
                    continue

                # --- Code HBL dans Cot.+Coef. ---
                code = None
                for text, x in line_spans:
                    if abs(x - cot_x) < TOL and re.match(r"HBL[A-Z0-9]+", text):
                        code = text
                        break

                if not code or code in {"HBLD073", "HBLD490", "HBLD724"}:
                    i += 1
                    continue

                # --- Hono. ---
                hono = None
                for text, x in line_spans:
                    if abs(x - hono_x) < TOL:
                        m = re.search(r"\d{1,4}(,\d{2})", text)
                        if m:
                            hono = float(m.group().replace(",", "."))
                            break

                # --- Description ---
                desc = []
                for text, x in line_spans:
                    if x < cot_x - 50 and text not in ["FSE", "Séc.", "non Séc."]:
                        desc.append(text)
                description = " ".join(desc).strip()

                # --- Debug ---
                if debug:
                    debug_info.append({
                        "Patient": patient,
                        "Code": code,
                        "Hono.": hono,
                        "Description": description[:80]
                    })

                if hono and hono > 0:
                    data.append({
                        "Patient": patient,
                        "Code HBL": code,
                        "Description": description,
                        "Hono.": hono
                    })

                i += 1

    df = pd.DataFrame(data)
    df = df.sort_values(by=["Patient", "Code HBL"]).reset_index(drop=True)
    df_debug = pd.DataFrame(debug_info) if debug else pd.DataFrame()
    return df, df_debug


# --- Interface ---
st.markdown("### Upload ton PDF Desmos")
file = st.file_uploader("", type="pdf")
debug = st.checkbox("Mode debug", True)

if file:
    df, df_debug = extract_hbl(file, debug)

    if not df.empty:
        st.success(f"**{len(df)} actes HBL extraits** pour **{df['Patient'].nunique()} patients**")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("Télécharger CSV", csv, "HBL_recap.csv", "text/csv")

        if debug and not df_debug.empty:
            st.divider()
            st.subheader("Debug")
            st.dataframe(df_debug, use_container_width=True)
    else:
        st.error("Aucun acte HBL trouvé. Vérifie le PDF.")
