import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

st.set_page_config(page_title="Récap HBL - Extraction par colonnes (fiable)", layout="wide")
st.title("Récapitulatif HBL – Extraction précise par colonnes (corrigé)")

def extract_hbl_by_columns(file, debug=False):
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

    # --- 1. Trouver les positions des colonnes (page 1) ---
    col_positions = {}
    for page_num in range(min(3, doc.page_count)):  # Cherche sur les 3 premières pages
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block: continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    x0 = span["bbox"][0]
                    if text == "Hono.":
                        col_positions["Hono."] = x0
                    elif text == "AMO":
                        col_positions["AMO"] = x0
                    elif text == "Cot.+Coef.":
                        col_positions["Cot.+Coef."] = x0
        if len(col_positions) >= 2:
            break

    if "Hono." not in col_positions:
        st.error("Colonne 'Hono.' non trouvée dans le PDF.")
        return pd.DataFrame(), pd.DataFrame()

    hono_x = col_positions["Hono."]
    amo_x = col_positions.get("AMO", hono_x + 100)
    cot_x = col_positions.get("Cot.+Coef.", hono_x - 50)

    TOLERANCE = 18  # Réduit de 30 → 18

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
                match = re.search(r"([A-ZÉÈÀÙÂÊÎÔÛÇ'\- ]+) N° Dossier : \d+ N°INSEE : [\d ]+", line_text)
                if match:
                    current_patient = match.group(1).strip()
                    i += 1
                    continue

                # --- Code HBL ---
                hbl_match = None
                hbl_span = None
                for text, x in line_spans:
                    m = re.match(r"(HBL[A-Z0-9]+)", text)
                    if m:
                        hbl_match = m
                        hbl_span = (text, x)
                        break
                if not hbl_match:
                    i += 1
                    continue

                code = hbl_match.group(1)
                if code in {"HBLD073", "HBLD490", "HBLD724"}:
                    i += 1
                    continue

                # --- Extraire Hono. dans la zone [hono_x ± TOLERANCE] ---
                hono_value = None
                hono_source = ""
                candidates = []

                for text, x in line_spans:
                    if abs(x - hono_x) <= TOLERANCE:
                        m = re.search(r"\d{1,4}(?:,\d{2})", text)
                        if m:
                            val = float(m.group().replace(",", "."))
                            if val > 0:  # Éviter les 0,00
                                candidates.append((val, text, x))

                if candidates:
                    # Prendre le plus à gauche
                    candidates.sort(key=lambda x: x[2])
                    hono_value = candidates[0][0]
                    hono_source = candidates[0][1]

                # --- Fallback : montant juste avant le code ---
                if hono_value is None or hono_value == 0:
                    prev_spans = []
                    if i > 0:
                        prev_spans = lines[i-1]
                    for text, x in prev_spans + line_spans:
                        if x < hbl_span[1]:  # Avant le code
                            m = re.search(r"\d{1,4}(?:,\d{2})", text)
                            if m:
                                val = float(m.group().replace(",", "."))
                                if val > 0:
                                    hono_value = val
                                    hono_source = text + " (fallback)"
                                    break

                # --- Description ---
                desc = []
                j = i + 1
                while j < len(lines) and not re.match(r"^\d{2}/\d{2}/\d{4}|^Total|^\d{7}$", " ".join([s[0] for s in lines[j]])):
                    desc.append(" ".join([s[0] for s in lines[j]]).strip())
                    j += 1
                description = " ".join(desc).strip() or "(non trouvée)"

                # --- Debug ---
                if debug:
                    debug_info.append({
                        "Patient": current_patient,
                        "Code": code,
                        "Hono.": hono_value,
                        "Source": hono_source,
                        "Description": description[:100] + ("..." if len(description) > 100 else "")
                    })

                if hono_value is not None and hono_value > 0:
                    data.append({
                        "Nom Patient": current_patient,
                        "Code HBL": code,
                        "Description": description,
                        "Hono.": hono_value
                    })

                i = j

    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values(by=["Nom Patient", "Code HBL"]).reset_index(drop=True)

    df_debug = pd.DataFrame(debug_info) if debug else pd.DataFrame()
    return df, df_debug


# --- Interface ---
uploaded_file = st.file_uploader("Upload le PDF Desmos", type=["pdf"])
debug_mode = st.checkbox("Mode debug", value=True)

if uploaded_file:
    df, df_debug = extract_hbl_by_columns(uploaded_file, debug=debug_mode)

    if not df.empty:
        st.success(f"{len(df)} actes HBL extraits pour {df['Nom Patient'].nunique()} patients")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("Télécharger CSV", csv, "recap_HBL.csv", "text/csv")

        if debug_mode and not df_debug.empty:
            st.divider()
            st.subheader("Debug : Source du Hono.")
            st.dataframe(df_debug, use_container_width=True)
            st.info("Vérifie que **Hono. > 0** et que **Source ≠ AMO**")
    else:
        st.warning("Aucun acte HBL trouvé.")
