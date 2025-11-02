import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

st.set_page_config(page_title="Récap HBL - Extraction 100%", layout="wide")
st.title("Récapitulatif HBL – Extraction par colonnes (PDF réel)")

def extract_hbl_from_pdf(file, debug=False):
    if not file:
        return pd.DataFrame(), pd.DataFrame()

    file.seek(0)
    try:
        doc = fitz.open(stream=file.read(), filetype="pdf")
    except Exception as e:
        st.error(f"Erreur PDF : {e}")
        return pd.DataFrame(), pd.DataFrame()

    data = []
    debug_info = []

    # --- 1. Trouver les positions X des colonnes ---
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
                    if text == "Cot.+Coef.":
                        col_x["Cot"] = x
                    elif text == "Hono.":
                        col_x["Hono"] = x
        if "Cot" in col_x and "Hono" in col_x:
            break

    if "Cot" not in col_x or "Hono" not in col_x:
        st.error("Colonnes 'Cot.+Coef.' ou 'Hono.' non trouvées.")
        return pd.DataFrame(), pd.DataFrame()

    cot_x = col_x["Cot"]
    hono_x = col_x["Hono"]
    TOLERANCE = 40

    # --- 2. Parcourir toutes les pages ---
    current_patient = None

    for page_num in range(doc.page_count):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if "lines" not in block: continue

            lines = []
            for line in block["lines"]:
                spans = [(span["text"].strip(), span["bbox"][0]) for span in line["spans"] if span["text"].strip()]
                if spans:
                    lines.append(spans)

            i = 0
            while i < len(lines):
                line_spans = lines[i]
                line_text = " ".join([s[0] for s in line_spans])

                # --- Patient ---
                match_patient = re.search(r"([A-ZÉÈÀÙÂÊÎÔÛÇ'\- ]+) N° Dossier : \d+", line_text)
                if match_patient:
                    current_patient = match_patient.group(1).strip()
                    i += 1
                    continue

                # --- Ignorer les lignes "Total" ---
                if any(word in line_text for word in ["Total Facture", "Total des Factures", "Total Avoir"]):
                    i += 1
                    continue

                # --- Chercher le code HBL dans Cot.+Coef. ---
                hbl_match = None
                for text, x in line_spans:
                    if abs(x - cot_x) <= TOLERANCE and re.match(r"^HBL[A-Z0-9]+$", text):
                        hbl_match = text
                        break

                if not hbl_match:
                    i += 1
                    continue

                if hbl_match in {"HBLD073", "HBLD490", "HBLD724"}:
                    i += 1
                    continue

                # --- Extraire Hono. ---
                hono_value = None
                for text, x in line_spans:
                    if abs(x - hono_x) <= TOLERANCE:
                        m = re.search(r"\d{1,4}(?:,\d{2})", text)
                        if m:
                            val = float(m.group().replace(",", "."))
                            if val > 0:
                                hono_value = val
                                break

                # Ligne suivante si nécessaire
                if hono_value is None and i + 1 < len(lines):
                    next_line = lines[i + 1]
                    for text, x in next_line:
                        if abs(x - hono_x) <= TOLERANCE:
                            m = re.search(r"\d{1,4}(?:,\d{2})", text)
                            if m:
                                val = float(m.group().replace(",", "."))
                                if val > 0:
                                    hono_value = val
                                    break

                # --- Description (tout à gauche) ---
                desc = []
                for text, x in line_spans:
                    if x < cot_x - 50 and not re.match(r"^\d{1,2}$|^\d{2}/\d{2}/\d{4}$|^FSE|^[0-9]{7}$", text):
                        desc.append(text)

                # Ajouter lignes suivantes pour description longue
                j = i + 1
                while j < len(lines):
                    next_text = " ".join([s[0] for s in lines[j]])
                    if re.match(r"^HBL|^\d{2}/\d{2}/\d{4}|^Total|^\d{7}$", next_text):
                        break
                    desc.append(next_text)
                    j += 1
                description = " ".join(desc).strip() or "(non trouvée)"

                # --- Debug ---
                if debug:
                    debug_info.append({
                        "Patient": current_patient,
                        "Code": hbl_match,
                        "Hono.": hono_value,
                        "Description": description[:100]
                    })

                if hono_value:
                    data.append({
                        "Nom Patient": current_patient,
                        "Code HBL": hbl_match,
                        "Description": description,
                        "Hono.": hono_value
                    })

                i += 1

    # --- Créer le DataFrame ---
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values(by=["Nom Patient", "Code HBL"]).reset_index(drop=True)

    df_debug = pd.DataFrame(debug_info) if debug else pd.DataFrame()
    return df, df_debug


# --- Interface Streamlit ---
uploaded_file = st.file_uploader("Upload le PDF Desmos", type=["pdf"])
debug_mode = st.checkbox("Mode debug", value=True)

if uploaded_file:
    df, df_debug = extract_hbl_from_pdf(uploaded_file, debug=debug_mode)

    if not df.empty:
        st.success(f"{len(df)} actes HBL extraits pour {df['Nom Patient'].nunique()} patients")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("Télécharger CSV", csv, "recap_HBL.csv", "text/csv")

        if debug_mode and not df_debug.empty:
            st.divider()
            st.subheader("Debug : Source du Hono.")
            st.dataframe(df_debug, use_container_width=True)
    else:
        st.warning("Aucun acte HBL trouvé.")
