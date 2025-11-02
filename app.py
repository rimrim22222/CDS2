import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

st.set_page_config(page_title="Récap HBL - Extraction Fiable", layout="wide")
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

    # --- 1. Trouver les positions X des colonnes sur la page 1 ---
    col_x = {}
    for page_num in range(min(2, doc.page_count)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block: continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    x = span["bbox"][0]
                    if text == "Hono.":
                        col_x["Hono."] = x
                    elif text == "AMO":
                        col_x["AMO"] = x
                    elif text == "Cot.+Coef.":
                        col_x["Cot.+Coef."] = x
        if "Hono." in col_x:
            break

    if "Hono." not in col_x:
        st.error("Colonne 'Hono.' non trouvée dans le PDF.")
        return pd.DataFrame(), pd.DataFrame()

    hono_x = col_x["Hono."]
    TOLERANCE = 35  # Ajusté pour ton PDF

    # --- 2. Parcourir toutes les pages ---
    current_patient = None

    for page_num in range(doc.page_count):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if "lines" not in block: continue

            # Reconstruire les lignes avec leurs spans
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

                # --- Code HBL ---
                hbl_match = None
                hbl_text = None
                for text, x in line_spans:
                    if re.match(r"^HBL[A-Z0-9]+$", text):
                        hbl_match = text
                        hbl_text = text
                        break

                if not hbl_match:
                    i += 1
                    continue

                if hbl_match in {"HBLD073", "HBLD490", "HBLD724"}:
                    i += 1
                    continue

                # --- Chercher Hono. dans la même ligne ---
                hono_value = None
                hono_source = "même ligne"
                for text, x in line_spans:
                    if abs(x - hono_x) <= TOLERANCE:
                        m = re.search(r"\d{1,4}(?:,\d{2})", text)
                        if m:
                            val = float(m.group().replace(",", "."))
                            if val > 0:
                                hono_value = val
                                break

                # --- Si pas trouvé → ligne suivante ---
                if hono_value is None and i + 1 < len(lines):
                    next_line = lines[i + 1]
                    for text, x in next_line:
                        if abs(x - hono_x) <= TOLERANCE:
                            m = re.search(r"\d{1,4}(?:,\d{2})", text)
                            if m:
                                val = float(m.group().replace(",", "."))
                                if val > 0:
                                    hono_value = val
                                    hono_source = "ligne suivante"
                                    break

                # --- Description ---
                desc = []
                j = i + 1
                while j < len(lines):
                    next_text = " ".join([s[0] for s in lines[j]])
                    if re.match(r"^\d{2}/\d{2}/\d{4}|^Total|^\d{7}$|^HBL", next_text):
                        break
                    if next_text.strip():
                        desc.append(next_text.strip())
                    j += 1
                description = " ".join(desc).strip() or "(non trouvée)"

                # --- Debug ---
                if debug:
                    debug_info.append({
                        "Patient": current_patient,
                        "Code": hbl_match,
                        "Hono.": hono_value,
                        "Source": hono_source,
                        "Ligne": line_text[:100],
                        "Description": description[:100]
                    })

                if hono_value is not None and hono_value > 0:
                    data.append({
                        "Nom Patient": current_patient,
                        "Code HBL": hbl_match,
                        "Description": description,
                        "Hono.": hono_value
                    })

                i = j

    # --- DataFrames ---
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values(by=["Nom Patient", "Code HBL"]).reset_index(drop=True)

    df_debug = pd.DataFrame(debug_info) if debug else pd.DataFrame()
    return df, df_debug


# --- Interface Streamlit ---
uploaded_file = st.file_uploader("Upload le PDF Desmos", type=["pdf"])
debug_mode = st.checkbox("Mode debug (détails)", value=True)

if uploaded_file:
    df, df_debug = extract_hbl_from_pdf(uploaded_file, debug=debug_mode)

    if not df.empty:
        st.success(f"{len(df)} actes HBL extraits pour {df['Nom Patient'].nunique()} patients")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "Télécharger CSV",
            csv,
            "recapitulatif_HBL.csv",
            "text/csv"
        )

        if debug_mode and not df_debug.empty:
            st.divider()
            st.subheader("Debug : Source du Hono.")
            st.dataframe(df_debug, use_container_width=True)
            st.info("Vérifie que **Hono. > 0** et **Source = même ligne ou ligne suivante**")
    else:
        st.warning("Aucun acte HBL trouvé. Vérifie le PDF.")
