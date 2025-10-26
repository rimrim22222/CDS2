import fitz
import re
import pandas as pd

def extract_desmos_acts(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    lines = full_text.split('\n')
    data = []
    current_patient = None
    for idx, line in enumerate(lines):
        patient_match = re.search(r'Ref\. ([A-ZÉÈÇÂÊÎÔÛÄËÏÖÜÀÙa-zéèçâêîôûäëïöüàù\s\-]+)', line)
        if patient_match:
            current_patient = patient_match.group(1).strip()
        # Cherche actes BIOTECH/Couronne/HBL
        if current_patient and re.search(r'(BIOTECH|Couronne|HBL\w+)', line, re.IGNORECASE):
            acte = line.strip()
            # Cherche prix sur la même ligne ou la suivante
            price_match = re.search(r'(\d+\.\d{2}|\d+,\d{2})', line)
            prix = price_match.group(1).replace(',', '.') if price_match else ""
            if not prix and idx + 1 < len(lines):
                next_line = lines[idx + 1]
                price_match = re.search(r'(\d+\.\d{2}|\d+,\d{2})', next_line)
                if price_match:
                    prix = price_match.group(1).replace(',', '.')
            data.append({'Patient': current_patient, 'Acte Desmos': acte, 'Prix Desmos': prix})
    return pd.DataFrame(data)

# Utilisation :
# df_desmos = extract_desmos_acts(open("last demos.pdf", "rb"))
# print(df_desmos)
