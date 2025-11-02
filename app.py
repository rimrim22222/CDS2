# -*- coding: utf-8 -*-
"""
Extraction des colonnes : Nom | Acte | Cot.+Coef. | Hono.
Usage: python extract_pdf_factures.py
"""

import pdfplumber
import re
import pandas as pd
from typing import List, Tuple

PDF_PATH = "1506 3008.pdf"   # <-- chemin vers ton PDF
OUT_CSV = "extraction_factures.csv"
OUT_XLSX = "extraction_factures.xlsx"

# Regex utiles
HEADER_RE = re.compile(r"([A-ZÉÈÊËÎÏÔÖÙÛÜÇ' \-]{3,})\s+N° Dossier\s*:\s*(\d+)", re.MULTILINE)
CODE_RE = re.compile(r"(H[A-Z]{2,4}\d{3})")  # ex: HBLD112, HBMD049
NUM_RE = re.compile(r"-?\d{1,3}(?:[ \u00A0]\d{3})*(?:,\d{2})")  # nombres format français (1 500,00)
NBSP = '\u00A0'


def norm_num_str(s: str) -> str:
    """Normalise la chaîne numérique française vers un format '1500.00' (string)."""
    if not isinstance(s, str) or s.strip() == "":
        return ""
    s = s.replace(NBSP, " ").replace(" ", "").replace(",", ".")
    # retirer plus d'un signe éventuel
    s = re.sub(r"^([+-])\s*", r"\1", s)
    return s


def read_full_text(pdf_path: str) -> str:
    """Ouvre le PDF et renvoie tout le texte (pages concaténées)."""
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            # remplacer NBSP pour faciliter les regex
            text = text.replace(NBSP, " ")
            full_text += "\n" + text
    return full_text


def find_headers(full_text: str) -> List[Tuple[int, str]]:
    """Retourne une liste (position, nom) pour chaque header 'N° Dossier' trouvé."""
    headers = [(m.start(), m.group(1).strip()) for m in HEADER_RE.finditer(full_text)]
    if not headers:
        # fallback simple si le motif précédent échoue
        for m in re.finditer(r"^(.*?)\s+N° Dossier", full_text, re.MULTILINE):
            headers.append((m.start(), m.group(1).strip()))
    headers.sort()
    return headers


def extract_rows(full_text: str, headers: List[Tuple[int, str]]) -> List[List[str]]:
    """
    Parcourt les codes d'acte (CODE_RE) et, pour chaque occurrence,
    associe le nom le plus proche en amont, extrait les nombres proches
    et construit une ligne [Nom, Acte, Cot.+Coef., Hono.].
    """
    rows = []
    for m in CODE_RE.finditer(full_text):
        code = m.group(1)
        pos = m.start()
        # trouver le header (nom) le plus proche avant pos
        name = ""
        for hp, hn in reversed(headers):
            if hp < pos:
                name = hn
                break

        # fenêtre avant / après l'acte
        before = full_text[max(0, pos - 220):pos]
        after = full_text[pos: pos + 140]

        nums_before = NUM_RE.findall(before)
        nums_after = NUM_RE.findall(after)

        # garder les nombres les plus proches (ordre gauche -> droite)
        nums = [n.replace(NBSP, " ").strip() for n in nums_before[-8:]] + [n.replace(NBSP, " ").strip() for n in nums_after[:4]]

        # heuristique d'association : si on a >=4 nombres, on suppose
        #   run = last 4..6 nombres, où hono = run[0] et cotcoef = run[3]
        hono = ""
        cotcoef = ""
        if len(nums) >= 6:
            run = nums[-6:]
            hono = run[0]
            cotcoef = run[3]
        elif len(nums) >= 4:
            run = nums[-4:]
            hono = run[0]
            cotcoef = run[3]
        elif len(nums) == 3:
            hono = nums[0]
            cotcoef = nums[2]
        elif len(nums) == 2:
            hono = nums[0]
            cotcoef = nums[1]
        elif len(nums) == 1:
            hono = nums[0]
            cotcoef = ""
        else:
            hono = ""
            cotcoef = ""

        # extraire une description courte derrière le code (jusqu'au saut de ligne)
        desc_match = re.search(re.escape(code) + r"([^\n\r]{0,120})", full_text[pos: pos + 200])
        acte_desc = code + (desc_match.group(1).strip() if desc_match else "")

        rows.append([name, acte_desc, cotcoef, hono])

    return rows


def cleanup_dataframe(rows: List[List[str]]) -> pd.DataFrame:
    """Construct DataFrame et normalise les champs numériques (reste string pour affichage)."""
    df = pd.DataFrame(rows, columns=["Nom", "Acte", "Cot.+Coef.", "Hono."])
    # retirer lignes vides d'acte
    df = df[df["Acte"].str.strip() != ""].copy()
    # normaliser les nombres (format '1500.00' en string) ; si impossible, garder vide
    df["Cot.+Coef."] = df["Cot.+Coef."].apply(norm_num_str)
    df["Hono."] = df["Hono."].apply(norm_num_str)
    # supprimer doublons exacts
    df = df.drop_duplicates().reset_index(drop=True)
    return df


def main():
    print("Lecture du PDF...")
    full_text = read_full_text(PDF_PATH)
    print("Recherche des en-têtes (noms)...")
    headers = find_headers(full_text)
    print(f"{len(headers)} en-têtes trouvés (ex : {headers[:3]} )")
    print("Extraction des lignes d'actes...")
    rows = extract_rows(full_text, headers)
    print(f"Lignes brutes extraites : {len(rows)}")
    df = cleanup_dataframe(rows)
    print(f"Lignes nettoyées : {len(df)}")

    # affichage console (quelques lignes)
    pd.set_option("display.max_colwidth", 200)
    print("\n--- Aperçu (20 premières lignes) ---")
    print(df.head(20).to_string(index=False))

    # sauvegardes
    df.to_csv(OUT_CSV, index=False, encoding="utf-8")
    df.to_excel(OUT_XLSX, index=False, engine="openpyxl")
    print(f"\nFichiers sauvegardés : {OUT_CSV} , {OUT_XLSX}")


if __name__ == "__main__":
    main()
