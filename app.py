
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import re
import io
import unicodedata
from pathlib import Path
import fitz  # PyMuPDF

# ==================== CONFIG & LOGO ====================
st.set_page_config(page_title="Gestion + Comparaison Prothèses", page_icon="🦷", layout="wide")

logo_path = Path("logo.png")
col_logo, col_title = st.columns([1, 4])
with col_logo:
    if logo_path.exists():
        st.image(str(logo_path), width=160)
    else:
        st.image(
            "https://scontent-mrs2-1.xx.fbcdn.net/v/t39.30808-6/305157485_519313286862181_9045589531882558278_n.png",
            width=160,
        )
        st.caption("Logo manquant → place logo.png à la racine de l’app")
with col_title:
    st.title("Gestion des Prothèses + Comparaison Cosmident / Desmos")
    st.caption("Matching patient ultra-permissif (inversions, tokens supplémentaires, petites fautes)")

st.divider()

# ==================== PARAMÈTRES (barre latérale) ====================
with st.sidebar:
    st.header("Paramètres de matching")
    FUZZY_REL_ERR = st.slider("Tolérance aux fautes (édition, %)", 5, 40, 20) / 100.0  # 0.20 par défaut
    SCORE_THRESHOLD = st.slider("Seuil de score global (0.30–0.80)", 0.30, 0.80, 0.50)
    st.caption("Plus la tolérance et le score seuil sont bas, plus le matching est permissif.")
    ORPHANS_ONLY_ABSENT_IN_RESULT = st.checkbox(
        "🟧 Orphelins Cosmident = Absents dans Résultat (peu importe Desmos)",
        value=False
    )

# ==================== UTILITAIRES NOM (ULTRA-PERMISSIF, corrigés) ====================
COMMON_WORDS = {"de","du","des","la","le","les","d","l","mr","mme","m","monsieur","madame"}

def strip_accents(s: str) -> str:
    s_norm = unicodedata.normalize("NFD", str(s))
    s_no = "".join(ch for ch in s_norm if unicodedata.category(ch) != "Mn")
    s_clean = re.sub(r"[^a-zA-Z\s\-']", " ", s_no)
    s_clean = re.sub(r"\s+", " ", s_clean).strip().lower()
    return s_clean

def canonical_tokens(name: str) -> list:
    raw = strip_accents(name)
    toks = []
    for t in re.split(r"[ \-]+", raw):
        t = t.strip()
        if not t or len(t) < 2:
            continue
        if t in COMMON_WORDS:
            continue
        toks.append(t)
    return sorted(toks)  # tri pour ignorer inversion nom/prénom

def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    n, m = len(a), len(b)
    if n == 0:
        return m
    if m == 0:
        return n
    prev_row = list(range(m + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            insert_cost = curr[j - 1] + 1
            delete_cost = prev_row[j] + 1
            subst_cost  = prev_row[j - 1] + (0 if ca == cb else 1)
            curr.append(min(insert_cost, delete_cost, subst_cost))
        prev_row = curr
    return prev_row[-1]

def fuzzy_equal(a: str, b: str) -> bool:
    if a == b:
        return True
    if not a or not b:
        return False
    L = max(len(a), len(b))
    return (levenshtein(a, b) / L) <= FUZZY_REL_ERR

def match_tokens_count(ta: list, tb: list) -> int:
    used_b = set()
    k = 0
    for a in ta:
        for j, b in enumerate(tb):
            if j in used_b:
                continue
            if a == b or fuzzy_equal(a, b):
                used_b.add(j)
                k += 1
                break
    return k

def core_tokens(tokens: list, n: int = 2) -> list:
    return sorted(tokens, key=len, reverse=True)[:n]

def names_match_permissive(name_a: str, name_b: str) -> tuple[bool, float]:
    ta = canonical_tokens(name_a)
    tb = canonical_tokens(name_b)
    if not ta or not tb:
        return (False, 0.0)
    if set(ta) == set(tb):
        return (True, 1.0)

    k = match_tokens_count(ta, tb)
    minlen = min(len(ta), len(tb)) or 1
    union = len(set(ta) | set(tb)) or 1
    coverage = k / minlen
    jacc = k / union

    ca = core_tokens(ta, 2)
    cb = core_tokens(tb, 2)

    def core_hit(cside, other):
        hits = 0
        for c in cside:
            if any(c == o or fuzzy_equal(c, o) for o in other):
                hits += 1
        return hits >= 2

    core_bonus = 1.0 if (core_hit(ca, tb) or core_hit(cb, ta)) else 0.0
    score = 0.6 * coverage + 0.4 * jacc + 0.15 * core_bonus
    match = (coverage >= 0.66) or (k >= 2) or (core_bonus > 0.0)
    return (match, score)

def make_index(df: pd.DataFrame, col_name: str) -> dict:
    idx = {}
    if df is None or df.empty or col_name not in df.columns:
        return idx
    for _, r in df.iterrows():
        key_tokens = canonical_tokens(str(r[col_name]))
        key = " ".join(key_tokens)
        if key:
            idx.setdefault(key, []).append(r)
    return idx

def best_match_row(target_name: str, index: dict, score_threshold: float):
    target_key = " ".join(canonical_tokens(target_name))
    if not target_key or not index:
        return None
    if target_key in index:
        return index[target_key][0]
    best = None
    best_score = 0.0
    for cand_key, rows in index.items():
        match, score = names_match_permissive(target_key, cand_key)
        if match and score > best_score:
            best = rows[0]
            best_score = score
    return best if best_score >= score_threshold else None

# ---------- NEW: toutes les correspondances ----------
def find_all_matches(target_name: str, index: dict, score_threshold: float) -> list[dict]:
    """
    Retourne toutes les lignes correspondant au patient 'target_name'
    selon le score permissif (>= score_threshold).
    """
    target_key = " ".join(canonical_tokens(target_name))
    if not target_key or not index:
        return []
    matches = []
    for cand_key, rows in index.items():
        match, score = names_match_permissive(target_key, cand_key)
        if match and score >= score_threshold:
            matches.extend(rows)
    if matches:
        df_tmp = pd.DataFrame(matches).drop_duplicates()
        return df_tmp.to_dict(orient="records")
    return []

# ==================== 1) EXTRACTION DES ACTES (Excel de facturation) ====================
st.subheader("1) Extraction des actes prothétiques (Excel de facturation)")
uploaded_facturation = st.file_uploader("📥 Charge le fichier Excel (facturation)", type=["xls", "xlsx"])

df_result = pd.DataFrame()
if uploaded_facturation:
    try:
        df_raw = pd.read_excel(
            uploaded_facturation,
            header=None,
            engine="openpyxl" if uploaded_facturation.name.endswith(".xlsx") else "xlrd"
        )
    except Exception as e:
        st.error(f"Erreur de lecture du fichier : {e}")
        st.stop()

    results = []
    current_patient = None

    for idx, row in df_raw.iterrows():
        row = row.astype(str).str.strip()
        values = [str(v).strip() for v in row.tolist()]
        row_text = " ".join([v for v in values if v and v not in ["nan", "None", ""]])

        if re.search(r"Factures et Avoirs CENTRE DE SANTÉ DES LAURIERS", row_text, re.I):
            current_patient = None
            continue

        if re.search(r"N°\s*Dossier", row_text, re.I):
            m = re.search(r"([A-ZÉÈÊËÀÂÄÔÖÙÛÜÇ][A-ZÉÈÊËÀÂÄÔÖÙÛÜÇ'\- ]{4,80})\s+N°\s*Dossier", row_text, re.I)
            if m:
                current_patient = m.group(1).strip()
            continue

        header_patterns = [
            r"^DATE[\s:]", r"^N°\s*FACT", r"^DENT\(S\)", r"^ACTE$", r"^HONO", r"^AMO$",
            r"^TOTAL DES FACTURES", r"^IMPRIMÉ LE"
        ]
        if any(re.search(p, row_text.upper()) for p in header_patterns):
            continue

        code = None
        code_idx = -1
        for i, cell in enumerate(values):
            cell = cell.strip()
            if cell and (cell.startswith("HBLD") or cell in ["HBMD351", "HBLD634"]):
                code = cell
                code_idx = i
                break
        if not code:
            continue
        if code in ("HBLD490", "HBLD045"):
            continue

        tarif = "?"
        for offset in [1, 2]:
            if code_idx + offset < len(values):
                val = values[code_idx + offset].replace(" ", "")
                if re.match(r"^\d{1,6}[,.]?\d{0,2}$", val.replace(",", ".")):
                    tarif = val.replace(".", ",")
                    break

        dent = "?"
        for i in range(code_idx - 1, max(-1, code_idx - 20), -1):
            m = re.search(r"\b([1-4]?\d)\b", str(values[i]))
            if m and 1 <= int(m.group(1)) <= 48:
                dent = m.group(1).zfill(2)
                break

        acte = "?"
        for i in range(code_idx - 1, max(-1, code_idx - 30), -1):
            v = str(values[i]).strip()
            if v and v not in ["nan", "None", ""]:
                acte = v
                break

        if not current_patient:
            continue

        results.append({
            "Patient": current_patient,
            "Dent": dent,
            "Code": code,
            "Acte": acte,
            "Tarif": tarif
        })

    if results:
        df_result = pd.DataFrame(results)[["Patient", "Dent", "Code", "Acte", "Tarif"]]
        st.success(f"**{len(df_result)} actes prothétiques extraits !**")
        st.dataframe(df_result, use_container_width=True, hide_index=True)
        csv = df_result.to_csv(index=False, sep=";", encoding="utf-8-sig")
        st.download_button("⬇️ Télécharger le Résultat (CSV)", data=csv,
                           file_name="Protheses_HBLD_HBMD351_HBLD634.csv", mime="text/csv")
    else:
        st.warning("Aucun acte prothétique trouvé.")
else:
    st.info("En attente du fichier Excel de facturation…")

st.divider()

# ==================== 2) EXTRACTIONS COSMIDENT (PDF) & DESMOS (Excel) ====================
st.subheader("2) Charge Cosmident (PDF) et Desmos (Excel) pour la comparaison")

col_b, col_c = st.columns(2)
with col_b:
    uploaded_cosmident = st.file_uploader("📥 Cosmident (PDF)", type=["pdf"])
with col_c:
    uploaded_desmos = st.file_uploader("📥 Desmos (Excel)", type=["xls", "xlsx"])

def extract_data_from_cosmident(file):
    file_bytes = file.read()
    full_text = ""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page in doc:
            page_text = page.get_text("text")
            stop_pattern = r"(COSMIDENT|IBAN|Siret|BIC|Tél\.|Total \(Euros\)|TOTAL TTC|Règlement|Chèque|NOS COORDONNÉES BANCAIRES)"
            page_text = re.split(stop_pattern, page_text, flags=re.IGNORECASE)[0]
            full_text += page_text + "\n"
    except Exception as e:
        st.error(f"Erreur ouverture PDF Cosmident : {e}")
        return pd.DataFrame()

    with st.expander("🧩 Aperçu du texte extrait (Cosmident brut)", expanded=False):
        st.write(full_text[:2000])

    lines = full_text.split("\n")
    clean_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.search(r"(teinte|couleur|A[1-3]|B[1-3]|C[1-3]|D[1-3])", line, re.IGNORECASE):
            continue
        if re.search(r"(COSMIDENT|IBAN|Siret|BIC|€|TOTAL TTC|CHÈQUE|NOS COORDONNÉES|BANCAIRES)", line, re.IGNORECASE):
            continue
        clean_lines.append(line)

    results = []
    current_patient = None
    current_description = ""
    current_numbers = []

    i = 0
    while i < len(clean_lines):
        line = clean_lines[i]
        i += 1

        ref_match = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-'’]+)", line, re.IGNORECASE)
        if ref_match:
            if current_patient and current_description and current_numbers:
                try:
                    total = float(str(current_numbers[-1]).replace(",", "."))
                    if total > 0:
                        results.append({
                            "Patient": current_patient.strip(),
                            "Acte Cosmident": current_description.strip(),
                            "Prix Cosmident": f"{total:.2f}",
                        })
                except ValueError:
                    pass
            current_patient = ref_match.group(1).strip()
            current_description = ""
            current_numbers = []
            continue

        if current_patient is None:
            continue

        this_numbers = re.findall(r"\d+[\.,]\d{2}", line)
        norm_numbers = [n.replace(",", ".") for n in this_numbers]
        this_text = re.sub(r"\s*\d+[\.,]\d{2}\s*", " ", line).strip()

        if this_text:
            if current_description and current_numbers:
                try:
                    total = float(str(current_numbers[-1]).replace(",", "."))
                    if total > 0:
                        results.append({
                            "Patient": current_patient.strip(),
                            "Acte Cosmident": current_description.strip(),
                            "Prix Cosmident": f"{total:.2f}",
                        })
                except ValueError:
                    pass
                current_description = ""
                current_numbers = []
            current_description = (current_description + " " + this_text).strip()

        if norm_numbers:
            current_numbers.extend(norm_numbers)

    if current_patient and current_description and current_numbers:
        try:
            total = float(str(current_numbers[-1]).replace(",", "."))
            if total > 0:
                results.append({
                    "Patient": current_patient.strip(),
                    "Acte Cosmident": current_description.strip(),
                    "Prix Cosmident": f"{total:.2f}",
                })
        except ValueError:
            pass

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.drop_duplicates(subset=["Patient", "Acte Cosmident", "Prix Cosmident"])
    return df

def read_desmos_excel(file) -> pd.DataFrame:
    try:
        df = pd.read_excel(
            file,
            header=0,
            engine="openpyxl" if str(getattr(file, "name", "")).lower().endswith(".xlsx") else "xlrd"
        )
    except Exception as e:
        st.error(f"Erreur de lecture Desmos (Excel) : {e}")
        return pd.DataFrame()

    df.columns = [str(c).strip() for c in df.columns]

    def pick(keywords):
        for c in df.columns:
            lc = c.lower()
            if any(k in lc for k in keywords):
                return c
        return None

    pcol = pick(["patient", "nom", "ref", "name"])
    acol = pick(["acte", "soin", "libelle", "description"])
    prcol = pick(["prix", "hono", "montant", "tarif"])

    if pcol and acol and prcol:
        df = df[[pcol, acol, prcol]].copy()
        df.columns = ["Patient", "Acte Desmos", "Prix Desmos"]
        df["Prix Desmos"] = (
            df["Prix Desmos"].astype(str)
            .str.replace(",", ".")
            .str.extract(r"(\d+(?:\.\d{1,2})?)", expand=False)
        )
    return df

df_cos = pd.DataFrame()
df_des = pd.DataFrame()

if uploaded_cosmident:
    uploaded_cosmident.seek(0)
    df_cos = extract_data_from_cosmident(uploaded_cosmident)
    if df_cos.empty:
        st.warning("Cosmident : aucune ligne extraite.")
    else:
        st.success(f"✔ Cosmident (PDF) extrait — {len(df_cos)} lignes")
        st.dataframe(df_cos, use_container_width=True, hide_index=True)

if uploaded_desmos:
    uploaded_desmos.seek(0)
    df_des = read_desmos_excel(uploaded_desmos)
    if df_des.empty:
        st.warning("Desmos : fichier lu mais colonnes Patient/Acte/Prix non détectées automatiquement.")
        st.dataframe(df_des, use_container_width=True, hide_index=True)
        if not df_des.empty:
            cols = df_des.columns.tolist()
            col1, col2, col3 = st.columns(3)
            with col1: pcol = st.selectbox("Colonne Patient (Desmos)", options=cols)
            with col2: acol = st.selectbox("Colonne Acte (Desmos)", options=cols)
            with col3: prcol = st.selectbox("Colonne Prix (Desmos)", options=cols)
            df_des = df_des[[pcol, acol, prcol]].copy()
            df_des.columns = ["Patient", "Acte Desmos", "Prix Desmos"]
            df_des["Prix Desmos"] = (
                df_des["Prix Desmos"].astype(str)
                .str.replace(",", ".")
                .str.extract(r"(\d+(?:\.\d{1,2})?)", expand=False)
            )
    else:
        st.success(f"✔ Desmos (Excel) chargé — {len(df_des)} lignes")
        st.dataframe(df_des, use_container_width=True, hide_index=True)

st.divider()

# ==================== 3) INDICES DE MATCH ====================
if df_result.empty:
    st.info("⚠️ Le tableau Résultat n’est pas encore disponible. Charge l’Excel de facturation au §1.")
    st.stop()

index_res = make_index(df_result, "Patient")
index_des = make_index(df_des, "Patient") if not df_des.empty else {}
index_cos = make_index(df_cos, "Patient") if not df_cos.empty else {}

# ==================== 3bis) PRÉFIXE : ORPHELINS COSMIDENT (en orange) ====================
cos_orphans_rows = []
if not df_cos.empty:
    for _, r in df_cos.iterrows():
        pname_cos = str(r["Patient"])
        m_res = best_match_row(pname_cos, index_res, SCORE_THRESHOLD)
        if ORPHANS_ONLY_ABSENT_IN_RESULT:
            is_orphan = (m_res is None)
        else:
            m_des = best_match_row(pname_cos, index_des, SCORE_THRESHOLD)
            is_orphan = (m_res is None and m_des is None)
        if is_orphan:
            prix_src = str(r.get("Prix Cosmident", "")).replace(",", ".")
            cos_orphans_rows.append({
                "Patient": pname_cos,
                "Source": "Cosmident (orphelin)",
                "Dent (Résultat)": "",
                "Code (Résultat)": "",
                "Acte (Résultat)": "",
                "Tarif (Résultat)": "",
                "Acte (Source)": str(r.get("Acte Cosmident", "")),
                "Prix (Source)": str(r.get("Prix Cosmident", "")),
                "Prix_num": pd.to_numeric(prix_src, errors="coerce"),
                "Statut Desmos": "aucun match Desmos",
                "Statut Cosmident": "orphan Cosmident",
                "Statut Global": "🟧 Cosmident sans correspondance",
            })

# ==================== 4) TABLEAU COMPARÉ & COLORÉ (TOUTES LES CORRESPONDANCES, TRI PAR PRIX) ====================
st.subheader("4) Tableau comparé et coloré — toutes les correspondances (triées par prix croissant)")

rows_main = []
for _, base in df_result.iterrows():
    p = str(base["Patient"])
    des_list = find_all_matches(p, index_des, SCORE_THRESHOLD)
    cos_list = find_all_matches(p, index_cos, SCORE_THRESHOLD)
    has_des = len(des_list) > 0
    has_cos = len(cos_list) > 0

    statut_global = "🟥 aucun match"
    if has_des and has_cos:
        statut_global = "🟩 match Desmos + Cosmident"
    elif has_des ^ has_cos:
        statut_global = "🟦 match d’un seul"

    # Cosmident: une ligne par acte trouvé
    for r in cos_list:
        prix_src = str(r.get("Prix Cosmident", "")).replace(",", ".")
        rows_main.append({
            "Patient": p,
            "Source": "Cosmident",
            "Dent (Résultat)": str(base.get("Dent", "")),
            "Code (Résultat)": str(base.get("Code", "")),
            "Acte (Résultat)": str(base.get("Acte", "")),
            "Tarif (Résultat)": str(base.get("Tarif", "")),
            "Acte (Source)": str(r.get("Acte Cosmident", "")),
            "Prix (Source)": str(r.get("Prix Cosmident", "")),
            "Prix_num": pd.to_numeric(prix_src, errors="coerce"),
            "Statut Desmos": ("match" if has_des else "aucun match Desmos"),
            "Statut Cosmident": "match",
            "Statut Global": statut_global,
        })

    # Desmos: une ligne par acte trouvé
    for r in des_list:
        prix_src = str(r.get("Prix Desmos", "")).replace(",", ".")
        rows_main.append({
            "Patient": p,
            "Source": "Desmos",
            "Dent (Résultat)": str(base.get("Dent", "")),
            "Code (Résultat)": str(base.get("Code", "")),
            "Acte (Résultat)": str(base.get("Acte", "")),
            "Tarif (Résultat)": str(base.get("Tarif", "")),
            "Acte (Source)": str(r.get("Acte Desmos", "")),
            "Prix (Source)": str(r.get("Prix Desmos", "")),
            "Prix_num": pd.to_numeric(prix_src, errors="coerce"),
            "Statut Desmos": "match",
            "Statut Cosmident": ("match" if has_cos else "aucun match Cosmident"),
            "Statut Global": statut_global,
        })

# Concaténer: orphelins en tête + correspondances étendues
df_main = pd.DataFrame(rows_main)
if not df_main.empty:
    df_main = df_main.sort_values(by=["Patient", "Prix_num", "Source"], ascending=[True, True, True])
df_final = pd.concat([pd.DataFrame(cos_orphans_rows), df_main], ignore_index=True)

st.success(f"✅ Affichage terminé — {len(df_final)} lignes (incluant {len(cos_orphans_rows)} orphelins Cosmident en tête)")

# ==================== COULEURS ====================
def color_row(row):
    val = str(row.get("Statut Global", ""))
    if val.startswith("🟩"):
        base = "background-color: #c6f6d5;"  # vert clair
    elif val.startswith("🟦"):
        base = "background-color: #cfe8ff;"  # bleu clair
    elif val.startswith("🟧"):
        base = "background-color: #ffe5b4;"  # orange pâle (orphelins)
    else:
        base = "background-color: #ffd6d6;"  # rouge clair

    styles = [base] * len(row)

    if "aucun match Desmos" in str(row.get("Statut Desmos", "")):
        try:
            col_idx = df_final.columns.get_loc("Statut Desmos")
            styles[col_idx] = "background-color: #fff3cd;"  # jaune pâle
        except Exception:
            pass

    stat_cos = str(row.get("Statut Cosmident", ""))
    if ("aucun match Cosmident" in stat_cos) or ("orphan Cosmident" in stat_cos):
        try:
            col_idx = df_final.columns.get_loc("Statut Cosmident")
            styles[col_idx] = "background-color: #ffe5b4;"  # orange pâle
        except Exception:
            pass

    return styles

styled = df_final.style.apply(color_row, axis=1)
st.dataframe(styled.drop(columns=["Prix_num"]), use_container_width=True, hide_index=True)

# ==================== FILTRES RAPIDES (optionnels) ====================
st.markdown("**Filtres rapides :**")
col_f1, col_f2, col_f3, col_f4 = st.columns(4)
with col_f1:
    show_only_both = st.checkbox("🟩 Double match")
with col_f2:
    show_only_one = st.checkbox("🟦 Un seul match")
with col_f3:
    show_only_none = st.checkbox("🟥 Aucun match")
with col_f4:
    show_only_orphans = st.checkbox("🟧 Orphelins Cosmident")

df_filtered = df_final.copy()
if show_only_both:
    df_filtered = df_filtered[df_filtered["Statut Global"].str.startswith("🟩")]
if show_only_one:
    df_filtered = df_filtered[df_filtered["Statut Global"].str.startswith("🟦")]
if show_only_none:
    df_filtered = df_filtered[df_filtered["Statut Global"].str.startswith("🟥")]
if show_only_orphans:
    df_filtered = df_filtered[df_filtered["Statut Global"].str.startswith("🟧")]

if show_only_both or show_only_one or show_only_none or show_only_orphans:
    st.dataframe(df_filtered.drop(columns=["Prix_num"]), use_container_width=True, hide_index=True)

# ==================== TÉLÉCHARGEMENT ====================
csv_out = df_final.drop(columns=["Prix_num"]).to_csv(index=False, sep=";", encoding="utf-8-sig")
st.download_button(
    label="⬇️ Télécharger le tableau (CSV)",
    data=csv_out,
    file_name="Comparaison_ToutesCorrespondances_TriPrix.csv",
    mime="text/csv",
)

st.divider()
st.info("Le tableau comparé et coloré affiche désormais TOUTES les correspondances Cosmident et Desmos pour chaque patient, triées par prix croissant. Les orphelins Cosmident sont en tête (🟧).")
