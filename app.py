
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import re
from pathlib import Path
import io
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import unicodedata

# ==================== CONFIG & LOGO ====================
st.set_page_config(page_title="Analyse & Comparaison (Résultat vs Desmos & Cosmident)", page_icon="🔍", layout="wide")

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
    st.title("📄 Comparaison des patients")
    st.caption("Conserve le code existant. Ajouts uniquement pour post-traiter les résultats — Matching sur le nom du patient (tolérant inversions, accents, casse)")

st.divider()

# ==================== OUTILS NOM (AJOUT, ne remplace rien) ====================
def strip_accents(s: str) -> str:
    s_norm = unicodedata.normalize("NFD", str(s))
    s_no = "".join(ch for ch in s_norm if unicodedata.category(ch) != "Mn")
    s_clean = re.sub(r"[^a-zA-Z\s]", " ", s_no)
    s_clean = re.sub(r"\s+", " ", s_clean).strip().lower()
    return s_clean

def canonical_tokens(name: str) -> list:
    return sorted([t for t in strip_accents(name).split() if len(t) >= 2])

def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b); union = len(a | b)
    return inter / union if union else 0.0

def names_match(name_a: str, name_b: str, threshold: float = 0.75) -> bool:
    ta = set(canonical_tokens(name_a)); tb = set(canonical_tokens(name_b))
    if not ta or not tb: return False
    if ta == tb: return True
    return jaccard(ta, tb) >= threshold

# ==================== TES FONCTIONS EXISTANTES (CONSERVÉES) ====================
# 🔹 Extraction image Cosmident (OCR uniquement si fichier image)
def extract_text_from_image(image):
    return pytesseract.image_to_string(image)

# 🔹 Extraction Cosmident robuste (CONSERVÉE)
def extract_data_from_cosmident(file):
    file_bytes = file.read()
    if file.type == "application/pdf":
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as e:
            st.error(f"Erreur ouverture PDF : {e}")
            return pd.DataFrame()
        full_text = ""
        for page in doc:
            page_text = page.get_text("text")
            # Coupe tout ce qui est après les mentions du bas de page
            stop_pattern = r"(COSMIDENT|IBAN|Siret|BIC|Tél\.|Total \(Euros\)|TOTAL TTC|Règlement|Chèque|NOS COORDONNÉES BANCAIRES)"
            page_text = re.split(stop_pattern, page_text, flags=re.IGNORECASE)[0]
            full_text += page_text + "\n"
    else:
        # Image: lecture + OCR (optionnel)
        try:
            image = Image.open(io.BytesIO(file_bytes))
            full_text = extract_text_from_image(image)
        except Exception as e:
            st.error(f"Erreur lecture image : {e}")
            return pd.DataFrame()

    # Aperçu debug
    with st.expander("🧩 Aperçu du texte extrait (Cosmident brut)"):
        st.write(full_text[:2000])

    # Nettoyage du texte
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

        # Détection robuste du patient
        ref_match = re.search(
            r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-'’]+)",
            line,
            re.IGNORECASE,
        )
        if ref_match:
            # Append previous act if any
            if current_patient and current_description and len(current_numbers) > 0:
                try:
                    total = float(str(current_numbers[-1]).replace(",", "."))
                    if total > 0:
                        results.append({
                            "Patient": current_patient,
                            "Acte Cosmident": current_description.strip(),
                            "Prix Cosmident": f"{total:.2f}",
                        })
                except ValueError:
                    pass
            current_description = ""
            current_numbers = []
            current_patient = ref_match.group(1).strip()
            continue

        # Bon n° ... Prescription (cas particulier)
        bon_match = re.match(r"Bon n°\d+ du [\w\d/]+.*Prescription \d+", line)
        if bon_match and i < len(clean_lines):
            next_line = clean_lines[i].strip()
            ref_match = re.search(
                r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-'’]+)",
                next_line,
                re.IGNORECASE,
            )
            if ref_match:
                if current_patient and current_description and len(current_numbers) > 0:
                    try:
                        total = float(str(current_numbers[-1]).replace(",", "."))
                        if total > 0:
                            results.append({
                                "Patient": current_patient,
                                "Acte Cosmident": current_description.strip(),
                                "Prix Cosmident": f"{total:.2f}",
                            })
                    except ValueError:
                        pass
                current_description = ""
                current_numbers = []
                current_patient = ref_match.group(1).strip()
                i += 1
                continue

        if current_patient is None:
            continue

        # Nombres (prix)
        this_numbers = re.findall(r"\d+[\.,]\d{2}", line)
        norm_numbers = [n.replace(",", ".") for n in this_numbers]
        # Texte (sans nombres)
        this_text = re.sub(r"\s*\d+[\.,]\d{2}\s*", " ", line).strip()

        if this_text:
            if current_description and len(current_numbers) > 0:
                try:
                    total = float(str(current_numbers[-1]).replace(",", "."))
                    if total > 0:
                        results.append({
                            "Patient": current_patient,
                            "Acte Cosmident": current_description.strip(),
                            "Prix Cosmident": f"{total:.2f}",
                        })
                except ValueError:
                    pass
                current_description = ""
                current_numbers = []
            current_description = this_text if not current_description else (current_description + " " + this_text)

        if norm_numbers:
            current_numbers.extend(norm_numbers)

    # Append last act
    if current_patient and current_description and len(current_numbers) > 0:
        try:
            total = float(str(current_numbers[-1]).replace(",", "."))
            if total > 0:
                results.append({
                    "Patient": current_patient,
                    "Acte Cosmident": current_description.strip(),
                    "Prix Cosmident": f"{total:.2f}",
                })
        except ValueError:
            pass

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.drop_duplicates(subset=["Patient", "Acte Cosmident", "Prix Cosmident"])
    return df

# 🔹 Extraction Desmos (PDF) — CONSERVÉE telle quelle
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
    for idx, line in enumerate(lines):
        patient_match = re.search(
            r"Ref\. ([A-ZÉÈÇÂÊÎÔÛÄËÏÖÜÀÙa-zéèçâêîôûäëïöüàù\s\-]+)",
            line
        )
        if patient_match:
            if current_patient and current_acte and current_hono:
                data.append({
                    "Patient": current_patient,
                    "Acte Desmos": current_acte.strip(),
                    "Prix Desmos": current_hono,
                })
            current_patient = patient_match.group(1).strip()
            current_acte = ""
            current_hono = ""
        elif re.search(
            r"(BIOTECH|Couronne transvissée|HBL\w+|ZIRCONE|GOUTTIÈRE SOUPLE|EMAX|ONLAY|PLAQUE|ADJONCTION|MONTAGE|DENT RESINE)",
            line, re.IGNORECASE,
        ):
            current_acte = line.strip()
            current_hono = ""
        elif "Hono" in line:
            hono_match = re.search(r"Hono\.?\s*:?\s*([\d,\.]+)", line)
            if hono_match:
                current_hono = hono_match.group(1).replace(",", ".")
        elif current_acte and re.match(r"^\d+[\.,]\d{2}$", line):
            current_hono = line.replace(",", ".")
    if current_patient and current_acte and current_hono:
        data.append({
            "Patient": current_patient,
            "Acte Desmos": current_acte.strip(),
            "Prix Desmos": current_hono,
        })
    return pd.DataFrame(data)

# ==================== LECTURE DESMOS EXCEL (AJOUT) ====================
def read_desmos_excel(file) -> pd.DataFrame:
    """Lit l'Excel Desmos et tente de détecter Patient / Acte / Prix. Ne remplace pas la fonction PDF existante."""
    try:
        df = pd.read_excel(
            file,
            header=0,
            engine="openpyxl" if str(getattr(file, "name", "")).lower().endswith(".xlsx") else "xlrd"
        )
    except Exception as e:
        st.error(f"Erreur de lecture Desmos (Excel) : {e}")
        return pd.DataFrame()

    # normalisation légère des noms de colonnes
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

# ==================== CHARGEMENT FICHIERS ====================
st.subheader("1) Charge les fichiers")
col_a, col_b, col_c = st.columns(3)

with col_a:
    uploaded_result = st.file_uploader("📥 Tableau Résultat (CSV ou Excel) — Patient/Dent/Code/Acte/Tarif", type=["csv", "xls", "xlsx"])
with col_b:
    uploaded_desmos = st.file_uploader("📥 Desmos (Excel recommandé)", type=["xls", "xlsx", "pdf"])
with col_c:
    uploaded_cosmident = st.file_uploader("📥 Cosmident (PDF)", type=["pdf"])

if not uploaded_result:
    st.info("➡️ Charge d’abord le tableau Résultat (CSV/Excel) issu de ton extraction HBLD/HBMD351/HBLD634.")
    st.stop()

# Lire tableau Résultat (ne pas ré-extraire, on utilise ce qui a été produit)
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
    # fallback: laisser choisir la colonne Patient
    st.warning("La colonne 'Patient' n’a pas été trouvée. Sélectionne-la ci-dessous.")
    sel = st.selectbox("Colonne à utiliser comme Patient", options=df_result.columns.tolist())
    df_result = df_result.rename(columns={sel: "Patient"})

st.success(f"✔ Résultat chargé — {len(df_result)} lignes")
with st.expander("Voir le tableau Résultat"):
    st.dataframe(df_result, use_container_width=True, hide_index=True)

# ==================== EXTRACTIONS SECONDAIRES ====================
# Cosmident
df_cosmident = pd.DataFrame()
if uploaded_cosmident:
    uploaded_cosmident.seek(0)
    df_cosmident = extract_data_from_cosmident(uploaded_cosmident)
    if df_cosmident.empty:
        st.warning("Cosmident : aucune ligne extraite.")
    else:
        st.success(f"✔ Cosmident (PDF) extrait — {len(df_cosmident)} lignes")
        st.dataframe(df_cosmident, use_container_width=True, hide_index=True)

# Desmos (PDF conservé + Excel ajouté)
df_desmos = pd.DataFrame()
if uploaded_desmos:
    uploaded_desmos.seek(0)
    is_excel = str(getattr(uploaded_desmos, "name", "")).lower().endswith((".xls", ".xlsx"))
    if is_excel:
        df_desmos = read_desmos_excel(uploaded_desmos)
        if df_desmos.empty or "Patient" not in df_desmos.columns:
            st.warning("Desmos Excel : colonnes Patient/Acte/Prix non détectées automatiquement.")
            st.dataframe(df_desmos, use_container_width=True, hide_index=True)
            # Sélecteurs manuels
            cols = df_desmos.columns.tolist()
            if cols:
                col1, col2, col3 = st.columns(3)
                with col1:
                    pcol = st.selectbox("Colonne Patient (Desmos)", options=cols)
                with col2:
                    acol = st.selectbox("Colonne Acte (Desmos)", options=cols)
                with col3:
                    prcol = st.selectbox("Colonne Prix (Desmos)", options=cols)
                df_desmos = df_desmos[[pcol, acol, prcol]].copy()
                df_desmos.columns = ["Patient", "Acte Desmos", "Prix Desmos"]
                df_desmos["Prix Desmos"] = (
                    df_desmos["Prix Desmos"].astype(str)
                    .str.replace(",", ".")
                    .str.extract(r"(\d+(?:\.\d{1,2})?)", expand=False)
                )
        st.success(f"✔ Desmos (Excel) chargé — {len(df_desmos)} lignes")
        st.dataframe(df_desmos, use_container_width=True, hide_index=True)
    else:
        # Conserver ta fonction PDF
        df_desmos = extract_desmos_acts(uploaded_desmos)
        st.success(f"✔ Desmos (PDF) extrait — {len(df_desmos)} lignes")
        st.dataframe(df_desmos, use_container_width=True, hide_index=True)

# ==================== MATCHING (POST-TRAITEMENT AJOUT) ====================
st.subheader("2) Matching des Patients (nom uniquement)")
st.caption("Tolérant aux accents, majuscules/minuscules, inversions Nom/Prénom, petites variations — seuil Jaccard: 0.75")

def make_index(df: pd.DataFrame, col_name: str) -> dict:
    idx = {}
    if df is None or df.empty or col_name not in df.columns:
        return idx
    for _, r in df.iterrows():
        key = " ".join(canonical_tokens(str(r[col_name])))
        if key:
            idx.setdefault(key, []).append(r)
    return idx

index_res = make_index(df_result, "Patient")
index_des = make_index(df_desmos, "Patient") if not df_desmos.empty else {}
index_cos = make_index(df_cosmident, "Patient") if not df_cosmident.empty else {}

def best_match_row(target_name: str, index: dict, threshold: float = 0.75):
    tkey = " ".join(canonical_tokens(target_name))
    if not tkey or not index:
        return None
    if tkey in index:
        return index[tkey][0]
    best = None; best_score = 0.0
    tset = set(tkey.split())
    for k, rows in index.items():
        score = jaccard(tset, set(k.split()))
        if score > best_score:
            best_score = score; best = rows[0]
    return best if best_score >= threshold else None

df_out = df_result.copy()
df_out["Match Desmos"] = False
df_out["Acte Desmos"] = ""
df_out["Prix Desmos"] = ""
df_out["Match Cosmident"] = False
df_out["Acte Cosmident"] = ""
df_out["Prix Cosmident"] = ""

for i, row in df_out.iterrows():
    pname = str(row["Patient"])

    # Desmos
    r_des = best_match_row(pname, index_des)
    if r_des is not None:
        df_out.at[i, "Match Desmos"] = True
        df_out.at[i, "Acte Desmos"] = str(r_des.get("Acte Desmos", ""))
        df_out.at[i, "Prix Desmos"] = str(r_des.get("Prix Desmos", ""))

    # Cosmident
    r_cos = best_match_row(pname, index_cos)
    if r_cos is not None:
        df_out.at[i, "Match Cosmident"] = True
        df_out.at[i, "Acte Cosmident"] = str(r_cos.get("Acte Cosmident", ""))
        df_out.at[i, "Prix Cosmident"] = str(r_cos.get("Prix Cosmident", ""))

st.success(f"✅ Matching terminé — {len(df_out)} lignes")

# ==================== MISE EN COULEUR ====================
def color_row(row):
    both = row["Match Desmos"] and row["Match Cosmident"]
    only_one = row["Match Desmos"] ^ row["Match Cosmident"]
    base = ""
    if both:
        base = "background-color: #c6f6d5;"  # vert clair
    elif only_one:
        base = "background-color: #cfe8ff;"  # bleu clair
    else:
        base = "background-color: #ffd6d6;"  # rouge clair
    return [base] * len(row)

styled = df_out.style.apply(color_row, axis=1)

st.subheader("3) Tableau comparé et coloré")
st.caption("🟩 match Desmos + Cosmident | 🟦 match d’un seul | 🟥 aucun match")
st.dataframe(styled, use_container_width=True, hide_index=True)

# ==================== TÉLÉCHARGEMENT ====================
csv_out = df_out.to_csv(index=False, sep=";", encoding="utf-8-sig")
st.download_button(
    label="⬇️ Télécharger le tableau fusionné (CSV)",
    data=csv_out,
    file_name="Fusion_Resultat_Desmos_Cosmident.csv",
    mime="text/csv",
)

st.divider()
st.info("Astuce : si Desmos Excel a des colonnes atypiques, utilise les sélecteurs pour préciser Patient/Acte/Prix. Le matching ne dépend que du nom du patient.")
