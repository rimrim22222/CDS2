
import streamlit as st
import pandas as pd
import re
import io
import unicodedata
import fitz  # PyMuPDF
from pathlib import Path

# ==================== CONFIG & LOGO ====================
st.set_page_config(page_title="Comparaison Résultats vs Cosmident/Desmos", page_icon="🔍", layout="wide")

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
    st.title("Comparaison des patients")
    st.caption("✓ Résultat (CSV/Excel) vs Desmos (Excel) et Cosmident (PDF) — Matching uniquement sur le nom du patient")

st.divider()

# ==================== UTILITAIRES NOM ====================
def strip_accents(s: str) -> str:
    """Remove diacritics (é → e) and keep letters/spaces only."""
    s_norm = unicodedata.normalize("NFD", str(s))
    s_no_accents = "".join(ch for ch in s_norm if unicodedata.category(ch) != "Mn")
    s_clean = re.sub(r"[^a-zA-Z\s]", " ", s_no_accents)
    s_clean = re.sub(r"\s+", " ", s_clean).strip().lower()
    return s_clean

def canonical_tokens(name: str) -> list:
    """Lower, de-accent and split into tokens, remove very short tokens."""
    tokens = [t for t in strip_accents(name).split() if len(t) >= 2]
    # tri pour ignorer inversion nom/prénom
    return sorted(tokens)

def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0

def names_match(name_a: str, name_b: str, threshold: float = 0.75) -> bool:
    """Robuste au changement d'ordre, casse, accents et petites variations."""
    ta = set(canonical_tokens(name_a))
    tb = set(canonical_tokens(name_b))
    if not ta or not tb:
        return False
    # égalité stricte après normalisation
    if ta == tb:
        return True
    # forte similarité de set
    return jaccard(ta, tb) >= threshold

# ==================== EXTRACTION COSMIDENT (PDF) ====================
def extract_cosmident_pdf(uploaded_pdf) -> pd.DataFrame:
    """
    Retourne DataFrame: Patient | Acte Cosmident | Prix Cosmident
    En se basant sur 'Ref. Patient' comme ancre et en prenant le dernier nombre format XX,XX / XXX,XX comme prix.
    """
    try:
        file_bytes = uploaded_pdf.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Erreur ouverture PDF Cosmident : {e}")
        return pd.DataFrame(columns=["Patient", "Acte Cosmident", "Prix Cosmident"])

    results = []
    full_text = ""
    for page in doc:
        # texte brut
        txt = page.get_text("text")

        # coupe bas de page administratif pour éviter bruit
        stop_pattern = r"(COSMIDENT|IBAN|Siret|BIC|Tél\.|Total \(Euros\)|TOTAL TTC|Règlement|Chèque|NOS COORDONNÉES BANCAIRES)"
        txt = re.split(stop_pattern, txt, flags=re.IGNORECASE)[0]

        full_text += txt + "\n"

    # Option debug
    with st.expander("🧩 Aperçu du texte extrait (Cosmident brut)", expanded=False):
        st.write(full_text[:2000])

    # Nettoyage lignes (on ignore teintes/couleurs et infos bancaires)
    lines = [ln.strip() for ln in full_text.split("\n")]
    clean_lines = []
    for line in lines:
        if not line:
            continue
        if re.search(r"(teinte|couleur|A[1-3]|B[1-3]|C[1-3]|D[1-3])", line, re.IGNORECASE):
            continue
        if re.search(r"(IBAN|Siret|BIC|€|TOTAL TTC|CHÈQUE|NOS COORDONNÉES|COSMIDENT)", line, re.IGNORECASE):
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

        # Détection robuste du patient (Ref. Patient : NOM PRENOM)
        ref_match = re.search(r"Ref\.?\s*(?:Patient)?\s*:?\s*([\w\s\-'’]+)", line, re.IGNORECASE)
        if ref_match:
            # enregistrer l'acte précédent si complet
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

        # ignorer tant qu'on n'a pas un patient courant
        if current_patient is None:
            continue

        # récupérer nombres (prix) au format 123,45
        found_numbers = re.findall(r"\d+[\.,]\d{2}", line)
        norm_numbers = [n.replace(",", ".") for n in found_numbers]

        # texte descriptif de l'acte (sans les nombres)
        text_wo_numbers = re.sub(r"\s*\d+[\.,]\d{2}\s*", " ", line).strip()

        # Si nouvelle description non vide et on avait déjà de la description + des nombres, clôturer l'acte précédent
        if text_wo_numbers:
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

            current_description = (current_description + " " + text_wo_numbers).strip()

        # accumulate numbers
        if norm_numbers:
            current_numbers.extend(norm_numbers)

    # dernier acte en fin de fichier
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
    # dédoublonnage basique par patient + acte + prix
    if not df.empty:
        df = df.drop_duplicates(subset=["Patient", "Acte Cosmident", "Prix Cosmident"])
    return df

# ==================== LECTURE DESMOS (EXCEL) ====================
def read_desmos_excel(uploaded_excel) -> pd.DataFrame:
    """Lit l'Excel Desmos sans hypothèse forte de schéma."""
    try:
        df = pd.read_excel(
            uploaded_excel,
            header=0,
            engine="openpyxl" if uploaded_excel.name.endswith(".xlsx") else "xlrd"
        )
    except Exception as e:
        st.error(f"Erreur de lecture Desmos : {e}")
        return pd.DataFrame()
    return df

def auto_detect_col(df: pd.DataFrame, keywords: list) -> str | None:
    """Retourne le nom de la colonne dont le libellé contient un des keywords (insensible casse)."""
    low_cols = {c: str(c).lower() for c in df.columns}
    for c, lc in low_cols.items():
        if any(k in lc for k in keywords):
            return c
    return None

# ==================== CHARGEMENT TABLEAU RESULTAT ====================
st.subheader("1) Charge les fichiers")
col_a, col_b, col_c = st.columns(3)

with col_a:
    uploaded_result = st.file_uploader("📥 Tableau Résultat (CSV ou Excel)", type=["csv", "xls", "xlsx"])
with col_b:
    uploaded_desmos = st.file_uploader("📥 Desmos (Excel)", type=["xls", "xlsx"])
with col_c:
    uploaded_cosmident = st.file_uploader("📥 Cosmident (PDF)", type=["pdf"])

if not uploaded_result:
    st.info("➡️ Charge d’abord le tableau Résultat (CSV/Excel) contenant les colonnes Patient / Dent / Code / Acte / Tarif.")
    st.stop()

# Lire résultat
try:
    if uploaded_result.name.lower().endswith(".csv"):
        df_result = pd.read_csv(uploaded_result, sep=";", encoding="utf-8-sig")
    else:
        df_result = pd.read_excel(
            uploaded_result,
            header=0,
            engine="openpyxl" if uploaded_result.name.endswith(".xlsx") else "xlrd"
        )
except Exception as e:
    st.error(f"Erreur de lecture du tableau Résultat : {e}")
    st.stop()

if "Patient" not in df_result.columns:
    st.error("Le tableau Résultat doit contenir une colonne 'Patient'.")
    st.stop()

st.success(f"✔ Résultat chargé — {len(df_result)} lignes")
with st.expander("Voir le tableau Résultat"):
    st.dataframe(df_result, use_container_width=True, hide_index=True)

# ==================== EXTRACTIONS SECONDAIRES ====================
df_cos = pd.DataFrame()
if uploaded_cosmident:
    uploaded_cosmident.seek(0)
    df_cos = extract_cosmident_pdf(uploaded_cosmident)
    if df_cos.empty:
        st.warning("Cosmident : aucune ligne extraite.")
    else:
        st.success(f"✔ Cosmident (PDF) extrait — {len(df_cos)} lignes")
        st.dataframe(df_cos, use_container_width=True, hide_index=True)

df_des = pd.DataFrame()
patient_col_desmos = acte_col_desmos = prix_col_desmos = None
if uploaded_desmos:
    uploaded_desmos.seek(0)
    df_des = read_desmos_excel(uploaded_desmos)
    if df_des.empty:
        st.warning("Desmos : fichier lu mais aucune donnée exploitable.")
    else:
        st.success(f"✔ Desmos (Excel) lu — {len(df_des)} lignes")
        # détection auto des colonnes
        patient_col_desmos = auto_detect_col(df_des, ["patient", "nom", "ref", "name"])
        acte_col_desmos = auto_detect_col(df_des, ["acte", "soin", "libelle", "description"])
        prix_col_desmos = auto_detect_col(df_des, ["prix", "hono", "montant", "tarif"])

        st.write("Sélectionne les colonnes (si auto-détection incorrecte) :")
        col1, col2, col3 = st.columns(3)
        with col1:
            patient_col_desmos = st.selectbox(
                "Colonne Patient (Desmos)", options=df_des.columns.tolist(),
                index=(df_des.columns.tolist().index(patient_col_desmos) if patient_col_desmos in df_des.columns else 0)
            )
        with col2:
            acte_col_desmos = st.selectbox(
                "Colonne Acte (Desmos)", options=df_des.columns.tolist(),
                index=(df_des.columns.tolist().index(acte_col_desmos) if acte_col_desmos in df_des.columns else 0)
            )
        with col3:
            prix_col_desmos = st.selectbox(
                "Colonne Prix (Desmos)", options=df_des.columns.tolist(),
                index=(df_des.columns.tolist().index(prix_col_desmos) if prix_col_desmos in df_des.columns else 0)
            )
        # sélectionner et renommer
        df_des = df_des[[patient_col_desmos, acte_col_desmos, prix_col_desmos]].copy()
        df_des.columns = ["Patient", "Acte Desmos", "Prix Desmos"]
        # normaliser prix
        df_des["Prix Desmos"] = df_des["Prix Desmos"].astype(str).str.replace(",", ".").str.extract(r"(\d+(?:\.\d{1,2})?)", expand=False)
        st.dataframe(df_des, use_container_width=True, hide_index=True)

# ==================== MATCHING ====================
st.subheader("2) Matching des Patients (nom uniquement)")
st.caption("Tolérant aux accents, majuscules/minuscules, inversions Nom/Prénom, petites variations — seuil Jaccard: 0.75")

# Préparer maps (Patient normalisé -> lignes)
def make_index(df: pd.DataFrame, col_name: str) -> dict:
    index = {}
    for _, row in df.iterrows():
        key = " ".join(canonical_tokens(str(row[col_name])))
        if not key:
            continue
        index.setdefault(key, []).append(row)
    return index

index_res = make_index(df_result, "Patient")
index_des = make_index(df_des, "Patient") if not df_des.empty else {}
index_cos = make_index(df_cos, "Patient") if not df_cos.empty else {}

# Fonction pour trouver meilleur match dans un index
def best_match(target_name: str, index: dict) -> tuple[str, dict | None]:
    target_key = " ".join(canonical_tokens(target_name))
    if not target_key:
        return "", None
    # priorité: clé exacte
    if target_key in index:
        return target_key, index[target_key][0]
    # sinon chercher par similarité de set
    best_key = ""
    best_score = 0.0
    target_set = set(target_key.split())
    for cand_key in index.keys():
        cand_set = set(cand_key.split())
        score = jaccard(target_set, cand_set)
        if score > best_score:
            best_score = score
            best_key = cand_key
    if best_score >= 0.75:
        return best_key, index.get(best_key, [None])[0]
    return "", None

# Construire le tableau fusionné
df_merged = df_result.copy()
df_merged["Match Desmos"] = False
df_merged["Acte Desmos"] = ""
df_merged["Prix Desmos"] = ""
df_merged["Match Cosmident"] = False
df_merged["Acte Cosmident"] = ""
df_merged["Prix Cosmident"] = ""

for i, row in df_merged.iterrows():
    pname = str(row["Patient"])

    # Desmos
    if index_des:
        _, match_row_des = best_match(pname, index_des)
        if match_row_des is not None:
            df_merged.at[i, "Match Desmos"] = True
            df_merged.at[i, "Acte Desmos"] = str(match_row_des.get("Acte Desmos", ""))
            df_merged.at[i, "Prix Desmos"] = str(match_row_des.get("Prix Desmos", ""))

    # Cosmident
    if index_cos:
        _, match_row_cos = best_match(pname, index_cos)
        if match_row_cos is not None:
            df_merged.at[i, "Match Cosmident"] = True
            df_merged.at[i, "Acte Cosmident"] = str(match_row_cos.get("Acte Cosmident", ""))
            df_merged.at[i, "Prix Cosmident"] = str(match_row_cos.get("Prix Cosmident", ""))

st.success(f"✅ Matching terminé — {len(df_merged)} lignes")

# ==================== MISE EN COULEUR ====================
def color_row(row):
    both = row["Match Desmos"] and row["Match Cosmident"]
    any_one = row["Match Desmos"] ^ row["Match Cosmident"]
    colors = {}
    base_color = ""
    if both:
        base_color = "background-color: #c6f6d5;"  # vert clair
    elif any_one:
        base_color = "background-color: #cfe8ff;"  # bleu clair
    else:
        base_color = "background-color: #ffd6d6;"  # rouge clair

    for c in df_merged.columns:
        colors[c] = base_color
    return pd.Series(colors)

styled = df_merged.style.apply(color_row, axis=1)
st.subheader("3) Tableau comparé et coloré")
st.caption("🟩 match Desmos + Cosmident | 🟦 match d’un seul | 🟥 aucun match")
st.dataframe(styled, use_container_width=True, hide_index=True)

# ==================== TELECHARGEMENT ====================
csv_out = df_merged.to_csv(index=False, sep=";", encoding="utf-8-sig")
st.download_button(
    label="⬇️ Télécharger le tableau fusionné (CSV)",
    data=csv_out,
    file_name="Fusion_Resultat_Desmos_Cosmident.csv",
    mime="text/csv",
)

st.divider()
st.info("Astuce: si Desmos a des colonnes atypiques, utilise les sélecteurs pour préciser Patient/Acte/Prix. Le matching ne dépend que du nom du patient.")
