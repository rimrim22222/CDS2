
import streamlit as st
import pandas as pd
import re
from pathlib import Path
from io import BytesIO
import unicodedata

# --- PDF ---
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

# --- Fuzzy matching (optionnel) ---
try:
    from rapidfuzz import process, fuzz
    RF_AVAILABLE = True
except Exception:
    import difflib
    RF_AVAILABLE = False

# ==================== CONFIG & LOGO ====================
st.set_page_config(page_title="Prothèses — Desmos (Excel) + Cosmident (PDF)", page_icon="tooth", layout="wide")

logo_path = Path("logo.png")
if logo_path.exists():
    st.image(str(logo_path), width=200)
else:
    st.image("https://scontent-mrs2-1.xx.fbcdn.net/v/t39.30808-6/305157485_519313286862181_9045589531882558278_n.png?_nc_cat=100&ccb=1-7&_nc_sid=6ee11a&_nc_ohc=WmCLobUhHXQQ7kNvwG_zWEI&_nc_oc=AdmF6xVu1OGEDHjp38eLgP6dtj_6hX5t4xOgz62mTkiw5CGLqZ7l_9EfyAEsQxrkpg4&_nc_zt=23&_nc_ht=scontent-mrs2-1.xx&_nc_gid=TmQOYLQQlH7bir12EkULdA&oh=00_AfiQ_BGtg7ADnPgQAPRIKAB1u1GCtPvDMuPhikiTouGQHg&oe=6927DD2F", width=200)
    st.caption("Logo manquant → place logo.png à la racine de l’app")

st.title("Gestion des Prothèses — Desmos (Excel) + Cosmident (PDF)")
st.caption("Comparaison **uniquement** sur le nom du patient (normalisation + option floue). Ajout des colonnes Cosmident (Acte, €).")

# ==================== SIDEBAR PARAMS ====================
with st.sidebar:
    st.subheader("Paramètres")
    # Debug
    debug_desmos = st.toggle("Debug Desmos (premières lignes)", value=False)
    max_debug_rows_desmos = st.number_input("Lignes debug Desmos", min_value=10, max_value=2000, value=150, step=10)

    debug_pdf = st.toggle("Debug Cosmident PDF (texte des pages)", value=False)
    max_debug_pages_pdf = st.number_input("Pages debug PDF", min_value=1, max_value=100, value=4, step=1)

    st.markdown("---")
    st.caption("Filtres Codes (appliqués aux deux sources)")
    keep_hbmd351 = st.checkbox("Conserver HBMD351", value=True)
    keep_hbld634 = st.checkbox("Conserver HBLD634", value=True)
    keep_all_hbld = st.checkbox("Conserver tous les HBLD*", value=True)
    exclude_hbld490 = st.checkbox("Exclure HBLD490 (transitoire)", value=True)
    exclude_hbld045 = st.checkbox("Exclure HBLD045", value=True)

    st.markdown("---")
    st.caption("Cosmident : dents multiples (ex. '11-12')")
    duplicate_multi_dents = st.checkbox("Dupliquer l'acte pour chaque dent détectée", value=False)

    st.markdown("---")
    st.caption("Agrégation Cosmident par patient (si plusieurs actes)")
    cosmident_strategy = st.selectbox("Stratégie", ["Premier acte", "Concat actes", "Somme des tarifs"], index=0)

    st.markdown("---")
    st.caption("Correspondance par patient")
    use_fuzzy = st.checkbox("Activer la correspondance floue", value=True)
    fuzzy_threshold = st.slider("Seuil de similarité (0–100)", min_value=50, max_value=100, value=85, step=1)

    st.markdown("---")
    search_text = st.text_input("Recherche plein texte (toutes colonnes)", "")

# ==================== UPLOADS ====================
col_up1, col_up2 = st.columns(2)
with col_up1:
    desmos_file = st.file_uploader("Excel Desmos (xls/xlsx)", type=["xls", "xlsx"], key="desmos")
with col_up2:
    cosmi_pdf = st.file_uploader("PDF Cosmident", type=["pdf"], key="cosmi_pdf")

# ==================== UTILITAIRES ====================
def normalize_patient(name: str) -> str:
    """
    Normalise le nom patient pour une comparaison robuste :
    - supprime accents
    - met en MAJ
    - supprime ponctuation, double espaces
    - découpe en tokens et les trie (gère inversion NOM/PRENOM)
    """
    if not isinstance(name, str):
        name = str(name) if name is not None else ""
    # accents -> ascii
    name = unicodedata.normalize("NFD", name)
    name = "".join(ch for ch in name if unicodedata.category(ch) != "Mn")
    # maj, ponctuation -> espaces
    name = name.upper()
    name = re.sub(r"[^A-Z ]", " ", name)
    # tokens -> tri (gère 'DUVAL ERIC' == 'ERIC DUVAL')
    tokens = [t for t in name.split() if t]
    tokens.sort()
    # option: éviter tokens ultra courts isolés (mais on les garde pour ne pas perdre 'DE', 'LE')
    return " ".join(tokens)

def sanitize_number(val: str) -> str:
    v = str(val).strip().replace(" ", "").replace(",", ".")
    if re.match(r"^\d{1,6}(\.\d{1,2})?$", v):
        return v.replace(".", ",")
    return "?"

def to_float_eu(x):
    try:
        if isinstance(x, str):
            x = x.replace(" ", "").replace(",", ".")
        return float(x)
    except Exception:
        return 0.0

def style_dataframe_to_excel(df: pd.DataFrame, money_columns=None, sheet_name="Actes") -> BytesIO:
    from openpyxl.styles import PatternFill, Font, Alignment, numbers
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.book[sheet_name]
        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center
        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            max_len = 0
            letter = col[0].column_letter
            for cell in col:
                v = str(cell.value) if cell.value is not None else ""
                max_len = max(max_len, len(v))
            ws.column_dimensions[letter].width = min(max_len + 2, 60)
        if money_columns:
            money_fmt = numbers.FORMAT_CURRENCY_EUR_SIMPLE
            for col_name in money_columns:
                if col_name in df.columns:
                    idx = list(df.columns).index(col_name) + 1
                    for row in ws.iter_rows(min_row=2, min_col=idx, max_col=idx, max_row=ws.max_row):
                        for cell in row:
                            try:
                                if isinstance(cell.value, str) and re.match(r"^\d{1,6}([,]\d{1,2})?$", cell.value):
                                    cell.value = float(cell.value.replace(",", "."))
                                cell.number_format = money_fmt
                            except Exception:
                                pass
    output.seek(0)
    return output

def style_summary_to_excel(df_sum: pd.DataFrame, sheet_name="Récap") -> BytesIO:
    from openpyxl.styles import PatternFill, Font, Alignment, numbers
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_sum.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.book[sheet_name]
        header_fill = PatternFill(start_color="2F528F", end_color="2F528F", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        center = Alignment(horizontal="center", vertical="center")
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center
        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            max_len = 0
            letter = col[0].column_letter
            for cell in col:
                v = str(cell.value) if cell.value is not None else ""
                max_len = max(max_len, len(v))
            ws.column_dimensions[letter].width = min(max_len + 2, 50)
        if "Total (€)" in df_sum.columns:
            idx = list(df_sum.columns).index("Total (€)") + 1
            for row in ws.iter_rows(min_row=2, min_col=idx, max_col=idx, max_row=ws.max_row):
                for cell in row:
                    try:
                        if isinstance(cell.value, str) and re.match(r"^\d{1,6}([,]\d{1,2})?$", cell.value):
                            cell.value = float(cell.value.replace(",", "."))
                        cell.number_format = numbers.FORMAT_CURRENCY_EUR_SIMPLE
                    except Exception:
                        pass
    output.seek(0)
    return output

# ==================== PARSING DESMOS (Excel) ====================
def is_header_line(text_upper: str) -> bool:
    patterns = [
        r"^DATE[\s:]", r"^N°\s*FACT", r"^DENT\(S\)", r"^ACTE$", r"^HONO", r"^AMO$",
        r"^TOTAL DES FACTURES", r"^IMPRIMÉ LE"
    ]
    return any(re.search(p, text_upper) for p in patterns)

def detect_patient_desmos(row_text: str):
    m = re.search(r"([A-ZÉÈÊËÀÂÄÔÖÙÛÜÇ][A-ZÉÈÊËÀÂÄÔÖÙÛÜÇ'\- ]{4,80})\s+N°\s*Dossier", row_text, re.I)
    return m.group(1).strip() if m else None

def find_code_cell(values):
    for i, cell in enumerate(values):
        cell = str(cell).strip()
        if not cell:
            continue
        if cell.startswith("HBLD") or cell in ["HBMD351", "HBLD634"]:
            return cell, i
    return None, -1

def sanitize_number_right(values, code_idx, span=5):
    for offset in range(1, span+1):
        j = code_idx + offset
        if j < len(values):
            v = sanitize_number(values[j])
            if v != "?":
                return v
    return "?"

def find_dent_left(values, code_idx, span=25):
    for i in range(code_idx - 1, max(-1, code_idx - span), -1):
        m = re.search(r"\b([1-4]?\d)\b", str(values[i]))
        if m:
            n = int(m.group(1))
            if 1 <= n <= 48:
                return str(n).zfill(2)
    return "?"

def find_acte_left(values, code_idx, span=40):
    for i in range(code_idx - 1, max(-1, code_idx - span), -1):
        v = str(values[i]).strip()
        if v and v.lower() not in ["nan", "none", ""]:
            return v
    return "?"

def parse_desmos_excel(desmos_file, debug=False, max_debug_rows=150,
                       exclude_hbld490=True, exclude_hbld045=True):
    try:
        df_raw = pd.read_excel(
            desmos_file, header=None,
            engine="openpyxl" if desmos_file.name.endswith(".xlsx") else "xlrd"
        )
    except Exception as e:
        st.error(f"Erreur de lecture Desmos : {e}")
        return pd.DataFrame()

    results = []
    current_patient = None

    for idx, row in df_raw.iterrows():
        row = row.astype(str).str.strip()
        values = [str(v).strip() for v in row.tolist()]
        row_text = " ".join([v for v in values if v and v.lower() not in ["nan", "none", ""]])

        if debug and idx < max_debug_rows:
            st.write(f"**Desmos Ligne {idx}** | Patient courant : {current_patient or '(aucun)'}")
            st.code(row_text)

        if re.search(r"Factures et Avoirs\s+CENTRE DE SANTÉ DES LAURIERS", row_text, re.I):
            current_patient = None
            continue

        m_patient = detect_patient_desmos(row_text)
        if m_patient:
            current_patient = m_patient.strip()
            continue

        if is_header_line(row_text.upper()):
            continue

        code, code_idx = find_code_cell(values)
        if not code:
            continue
        if exclude_hbld490 and code == "HBLD490":
            continue
        if exclude_hbld045 and code == "HBLD045":
            continue

        tarif = sanitize_number_right(values, code_idx, span=5)
        dent = find_dent_left(values, code_idx, span=25)
        acte = find_acte_left(values, code_idx, span=40)

        if not current_patient:
            continue

        results.append({
            "Patient": current_patient,
            "Dent": dent,
            "Code": code,
            "Acte": acte,
            "Tarif": tarif
        })

    df = pd.DataFrame(results)
    if not df.empty:
        df["Patient_norm"] = df["Patient"].map(normalize_patient)
        df["Tarif_float"] = df["Tarif"].apply(to_float_eu)
    return df

# ==================== PARSING COSMIDENT (PDF) ====================
CODE_RE = re.compile(r"\b(HBLD\d{3}|HBMD351|HBLD634)\b", re.I)
MONEY_RE = re.compile(r"(\d{1,6}[,.]\d{2})")

def detect_patient_pdf(lines, i):
    """
    Cherche: 'Patient : NOM PRENOM' ou la ligne MAJ avant 'N° Dossier'
    """
    m = re.search(r"Patient\s*[:\-]\s*(.+)", lines[i], re.I)
    if m:
        return m.group(1).strip()
    if re.search(r"N°\s*Dossier", lines[i], re.I):
        for back in range(1, 6):
            if i - back >= 0:
                cand = lines[i - back].strip()
                if re.match(r"^[A-ZÉÈÊËÀÂÄÔÖÙÛÜÇ][A-ZÉÈÊËÀÂÄÔÖÙÛÜÇ' \-]{4,80}$", cand):
                    return cand
    return None

def find_acte_pdf(lines, i_code):
    for back in range(1, 8):
        j = i_code - back
        if j >= 0:
            cand = lines[j].strip()
            if cand and not CODE_RE.search(cand) and not MONEY_RE.fullmatch(cand.replace(" ", "")):
                return cand
    return "?"

def find_tarif_pdf(lines, i_code):
    inline = MONEY_RE.findall(lines[i_code].replace(" ", ""))
    if inline:
        return inline[0].replace(".", ",")
    for fwd in range(1, 6):
        j = i_code + fwd
        if j < len(lines):
            m = MONEY_RE.search(lines[j].replace(" ", ""))
            if m:
                return m.group(1).replace(".", ",")
    return "?"

def find_dent_pdf(lines, i_code):
    # multiple dents (11-12; 11/12)
    for back in range(1, 6):
        j = i_code - back
        if j >= 0:
            cand = lines[j]
            m_multi = re.search(r"\b(\d{1,2})(?:\s*[-;,/]\s*(\d{1,2}))+\b", cand)
            if m_multi:
                return cand.strip()
    # simple dent
    for back in range(1, 6):
        j = i_code - back
        if j >= 0:
            cand = lines[j]
            m = re.search(r"\b([1-4]?\d)\b", cand)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 48:
                    return f"{n:02d}"
    return "?"

def expand_multi_dents(dent_str):
    s = str(dent_str)
    if re.search(r"[-;,/]", s):
        parts = re.split(r"[-;,/]\s*", s)
        out = []
        for p in parts:
            if p.isdigit():
                n = int(p)
                if 1 <= n <= 48:
                    out.append(f"{n:02d}")
        return list(dict.fromkeys(out)) if out else [s]
    return [s]

def parse_cosmident_pdf(cosmi_pdf_bytes: bytes,
                        exclude_hbld490=True, exclude_hbld045=True,
                        duplicate_multi_dents=False,
                        debug=False, max_debug_pages=4):
    if fitz is None:
        st.error("PyMuPDF (fitz) n'est pas installé. Installe-le pour parser le PDF Cosmident.")
        return pd.DataFrame()

    doc = fitz.open(stream=cosmi_pdf_bytes, filetype="pdf")
    results = []

    for pno in range(len(doc)):
        page = doc[pno]
        text = page.get_text("text")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        if debug and pno < max_debug_pages:
            st.write(f"**Cosmident Page {pno+1}/{len(doc)}** — aperçu texte")
            st.code("\n".join(lines[:150]))

        current_patient = None
        for i, line in enumerate(lines):
            if re.search(r"Total des Factures et Avoirs|Factures et Avoirs", line, re.I):
                current_patient = None
                continue

            m_pat = detect_patient_pdf(lines, i)
            if m_pat:
                current_patient = m_pat
                continue

            m_code = CODE_RE.search(line)
            if not m_code or not current_patient:
                continue

            code = m_code.group(1).upper()
            if exclude_hbld490 and code == "HBLD490":
                continue
            if exclude_hbld045 and code == "HBLD045":
                continue

            acte = find_acte_pdf(lines, i)
            tarif = find_tarif_pdf(lines, i)
            dent = find_dent_pdf(lines, i)

            dents_list = expand_multi_dents(dent) if duplicate_multi_dents else [dent]
            for d in dents_list:
                results.append({
                    "Patient": current_patient,
                    "Dent": d,
                    "Code": code,
                    "Acte_Cosmident": acte,
                    "Tarif_Cosmident": tarif
                })

    df = pd.DataFrame(results)
    if not df.empty:
        df["Patient_norm"] = df["Patient"].map(normalize_patient)
        df["Tarif_Cosmident_float"] = df["Tarif_Cosmident"].apply(to_float_eu)
    return df

# ==================== CORRESPONDANCE UNIQUEMENT PAR PATIENT ====================
def build_cosmident_agg_by_patient(df_cos: pd.DataFrame, strategy: str) -> pd.DataFrame:
    """
    Agrège Cosmident au niveau Patient_norm uniquement.
    strategy: 'Premier acte' | 'Concat actes' | 'Somme des tarifs'
    """
    if df_cos.empty:
        return pd.DataFrame(columns=["Patient_norm", "Acte_Cosmident", "Tarif_Cosmident", "Nb_actes_Cosmi"])

    if strategy == "Premier acte":
        df_cos_agg = df_cos.sort_index().groupby("Patient_norm").agg({
            "Acte_Cosmident": "first",
            "Tarif_Cosmident": "first"
        }).reset_index()
        df_cos_agg["Nb_actes_Cosmi"] = df_cos.groupby("Patient_norm").size().values

    elif strategy == "Concat actes":
        df_cos_agg = df_cos.groupby("Patient_norm").agg({
            "Acte_Cosmident": lambda s: " | ".join(map(str, s)),
            "Tarif_Cosmident": "first",
            "Tarif_Cosmident_float": "sum"
        }).reset_index()
        df_cos_agg["Nb_actes_Cosmi"] = df_cos.groupby("Patient_norm").size().values
        # Option: garder 'Tarif_Cosmident' du premier acte ; somme dispo via colonne float si besoin

    else:  # Somme des tarifs
        df_cos_agg = df_cos.groupby("Patient_norm").agg({
            "Acte_Cosmident": "first",
            "Tarif_Cosmident_float": "sum"
        }).reset_index()
        df_cos_agg["Tarif_Cosmident"] = df_cos_agg["Tarif_Cosmident_float"].map(
            lambda v: f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
        )
        df_cos_agg["Nb_actes_Cosmi"] = df_cos.groupby("Patient_norm").size().values

    df_cos_agg.rename(columns={"Tarif_Cosmident_float": "Total_Cosmi_float"}, inplace=True)
    return df_cos_agg

def fuzzy_match_patients(des_keys, cos_keys, threshold=85):
    """
    Retourne un dict {des_key: matched_cos_key or None} + DataFrame des scores.
    Utilise RapidFuzz si disponible, sinon difflib.
    """
    mapping = {}
    rows = []
    cos_list = list(cos_keys)

    for dk in des_keys:
        best_key = None
        best_score = 0

        if RF_AVAILABLE:
            match = process.extractOne(dk, cos_list, scorer=fuzz.token_sort_ratio)
            if match:
                best_key, best_score, _ = match
        else:
            # difflib ratio 0..1 -> 0..100
            match = difflib.get_close_matches(dk, cos_list, n=1, cutoff=0.0)
            if match:
                best_key = match[0]
                best_score = int(difflib.SequenceMatcher(None, dk, best_key).ratio() * 100)

        if best_score >= threshold:
            mapping[dk] = best_key
        else:
            mapping[dk] = None

        rows.append({"Patient_norm_Desmos": dk, "Match_Cosmi": best_key or "", "Score": best_score})

    df_scores = pd.DataFrame(rows).sort_values(by="Score", ascending=False)
    return mapping, df_scores

# ==================== PIPELINE ====================
if desmos_file and cosmi_pdf:
    # --- DESMOS ---
    df_des = parse_desmos_excel(desmos_file,
                                debug=debug_desmos, max_debug_rows=max_debug_rows_desmos,
                                exclude_hbld490=exclude_hbld490, exclude_hbld045=exclude_hbld045)
    if df_des.empty:
        st.warning("Desmos n’a produit aucun acte.")
        st.stop()

    # Filtres codes Desmos
    mask = pd.Series(True, index=df_des.index)
    codes = df_des["Code"].astype(str)
    if not keep_all_hbld:
        mask &= ~codes.str.startswith("HBLD")
    if keep_hbmd351:
        mask |= (codes == "HBMD351")
    if keep_hbld634:
        mask |= (codes == "HBLD634")
    if keep_all_hbld:
        mask |= codes.str.startswith("HBLD")
    df_des = df_des[mask].copy()

    # --- COSMIDENT PDF ---
    cosmi_pdf_bytes = cosmi_pdf.read()
    df_cos = parse_cosmident_pdf(cosmi_pdf_bytes,
                                 exclude_hbld490=exclude_hbld490,
                                 exclude_hbld045=exclude_hbld045,
                                 duplicate_multi_dents=duplicate_multi_dents,
                                 debug=debug_pdf, max_debug_pages=max_debug_pages_pdf)

    # --- Agrégation Cosmident par NOM PATIENT uniquement ---
    df_cos_agg = build_cosmident_agg_by_patient(df_cos, cosmident_strategy)

    # --- Jointure stricte par Patient_norm (exacte) ---
    df_des["Patient_norm"] = df_des["Patient"].map(normalize_patient)
    df_merge = df_des.merge(df_cos_agg, left_on="Patient_norm", right_on="Patient_norm", how="left")
    df_merge["Cosmident_match_exact"] = df_merge["Acte_Cosmident"].notna()

    # --- Correspondance floue (optionnel) ---
    df_scores = pd.DataFrame(columns=["Patient_norm_Desmos", "Match_Cosmi", "Score"])
    if use_fuzzy and not df_cos_agg.empty:
        des_keys = df_des["Patient_norm"].unique().tolist()
        cos_keys = df_cos_agg["Patient_norm"].unique().tolist()
        mapping, df_scores = fuzzy_match_patients(des_keys, cos_keys, threshold=fuzzy_threshold)

        # Applique mapping uniquement pour ceux sans match exact
        no_exact_mask = ~df_merge["Cosmident_match_exact"]
        df_no_exact = df_merge[no_exact_mask].copy()

        # Prepare dict -> Series pour merge
        df_map = pd.DataFrame({
            "Patient_norm": list(mapping.keys()),
            "Cosmident_norm_mapped": [mapping[k] for k in mapping.keys()]
        })

        # Ajoute clé mappée
        df_no_exact = df_no_exact.merge(df_map, on="Patient_norm", how="left")

        # Merge flou vers agg Cosmident
        df_no_exact = df_no_exact.merge(
            df_cos_agg.rename(columns={"Patient_norm": "Cosmident_norm_mapped"}),
            on="Cosmident_norm_mapped",
            how="left",
            suffixes=("", "_fuzzy")
        )

        # Remplit champs manquants par fuzzy
        for col in ["Acte_Cosmident", "Tarif_Cosmident", "Nb_actes_Cosmi"]:
            df_no_exact[col] = df_no_exact[col].fillna(df_no_exact[f"{col}_fuzzy"])

        # Re-intègre dans df_merge
        df_merge.loc[no_exact_mask, ["Acte_Cosmident", "Tarif_Cosmident", "Nb_actes_Cosmi"]] = \
            df_no_exact[["Acte_Cosmident", "Tarif_Cosmident", "Nb_actes_Cosmi"]].values

    # --- Indicateur final de match (exact ou flou) ---
    df_merge["Cosmident_match"] = df_merge["Acte_Cosmident"].notna()

    # --- Recherche plein texte ---
    if search_text.strip():
        q = search_text.strip().lower()
        cols = ["Patient", "Dent", "Code", "Acte", "Tarif", "Acte_Cosmident", "Tarif_Cosmident"]
        mask = pd.Series(False, index=df_merge.index)
        for c in cols:
            if c in df_merge.columns:
                mask |= df_merge[c].astype(str).str.lower().str.contains(q, na=False)
        df_merge = df_merge[mask].copy()

    # --- Affichage principal ---
    affichage_cols = ["Patient", "Dent", "Code", "Acte", "Tarif", "Acte_Cosmident", "Tarif_Cosmident", "Nb_actes_Cosmi", "Cosmident_match"]
    affichage_cols = [c for c in affichage_cols if c in df_merge.columns]
    st.success(f"**{len(df_merge)} actes rapprochés (jointure par NOM PATIENT)**")
    st.dataframe(df_merge[affichage_cols], use_container_width=True, hide_index=True)

    # --- Tableau des scores (si fuzzy activé) ---
    if use_fuzzy and not df_scores.empty:
        st.subheader("Scores de correspondance floue (par patient normalisé)")
        st.caption("Token-sort ratio (RapidFuzz si disponible, sinon approximation via difflib).")
        st.dataframe(df_scores, use_container_width=True, hide_index=True)

    # --- Exports ---
    csv = df_merge[affichage_cols].to_csv(index=False, sep=";", encoding="utf-8-sig")
    st.download_button("Télécharger le CSV", data=csv, file_name="Protheses_Desmos_Cosmident_byPatient.csv", mime="text/csv")

    xls = style_dataframe_to_excel(df_merge[affichage_cols], money_columns=["Tarif", "Tarif_Cosmident"], sheet_name="Actes rapprochés (par patient)")
    st.download_button("Télécharger l'Excel (.xlsx)", data=xls, file_name="Protheses_Desmos_Cosmident_byPatient.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # --- Récap par patient (Desmos) ---
    df_merge["Tarif_float"] = df_merge["Tarif"].apply(to_float_eu)
    recap = df_merge.groupby("Patient").agg(
        Actes=("Code", "count"),
        Total_float=("Tarif_float", "sum"),
        Cosmident_trouvé=("Cosmident_match", "max")
    ).reset_index()
    recap["Total (€)"] = recap["Total_float"].map(lambda v: f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", " "))
    recap = recap[["Patient", "Actes", "Total (€)", "Cosmident_trouvé"]]
    st.subheader("Récapitulatif par patient (Desmos, match Cosmident oui/non)")
    st.dataframe(recap, use_container_width=True, hide_index=True)

    xls_sum = style_summary_to_excel(recap, sheet_name="Récap par patient")
    st.download_button("Télécharger le récap (.xlsx)", data=xls_sum, file_name="Recap_Desmos_byPatient.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.info("Charge **l’Excel Desmos** et **le PDF Cosmident** pour lancer l’extraction.")
