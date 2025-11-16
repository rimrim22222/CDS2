import unicodedata
from difflib import SequenceMatcher

def normalize_name(name):
    name = name.lower().strip()
    name = "".join(
        c for c in unicodedata.normalize("NFD", name)
        if unicodedata.category(c) != "Mn"
    )
    return name

def name_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def match_patient_and_acte(cosmident_patient, df_desmos):
    if not isinstance(cosmident_patient, str):
        return "", ""
    
    cosmident_norm = normalize_name(cosmident_patient)

    for idx, row in df_desmos.iterrows():
        desmos_norm = normalize_name(row["Patient"])

        # 1) Match exact
        if cosmident_norm == desmos_norm:
            return row["Acte Desmos"], row["Prix Desmos"]

        # 2) Match partiel (prénom ou nom)
        if any(word in desmos_norm for word in cosmident_norm.split()):
            return row["Acte Desmos"], row["Prix Desmos"]

        # 3) Match prénom ↔ nom inversé
        cosmident_parts = cosmident_norm.split()
        desmos_parts = desmos_norm.split()
        if set(cosmident_parts) & set(desmos_parts):
            return row["Acte Desmos"], row["Prix Desmos"]

        # 4) Similarité globale (80% ou plus)
        if name_similarity(cosmident_norm, desmos_norm) >= 0.80:
            return row["Acte Desmos"], row["Prix Desmos"]

    return "", ""
