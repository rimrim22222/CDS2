def extract_data_from_cosmident(file):
    import io
    from PIL import Image
    import fitz
    import re
    import streamlit as st
    import pandas as pd
    import pytesseract

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
            stop_pattern = r"(COSMIDENT|IBAN|Siret|BIC|Tél\.|Total \(Euros\)|TOTAL TTC|Règlement|Chèque|NOS COORDONNÉES BANCAIRES)"
            page_text = re.split(stop_pattern, page_text, flags=re.IGNORECASE)[0]
            full_text += page_text + "\n"
    else:
        try:
            image = Image.open(io.BytesIO(file_bytes))
            full_text = pytesseract.image_to_string(image)
        except Exception as e:
            st.error(f"Erreur lecture image : {e}")
            return pd.DataFrame()
    
    # Aperçu du texte brut
    with st.expander("🧩 Aperçu du texte extrait (Cosmident brut)"):
        st.write(full_text[:2000])
    
    # Nettoyage du texte
    lines = full_text.split("\n")
    clean_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Ignorer uniquement les lignes qui sont purement des teintes (sans acte)
        if re.match(r"^(Teinte dentine|Vitapan|A[1-3]|B[1-3]|C[1-3]|D[1-3])\s*:?", line, re.IGNORECASE):
            continue
        # Ignorer les mentions bancaires ou totaux
        if re.search(r"(COSMIDENT|IBAN|Siret|BIC|€|TOTAL TTC|CHÈQUE)", line, re.IGNORECASE):
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

        # Détection du patient
        ref_match = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-]+)", line, re.IGNORECASE)
        if ref_match:
            if current_patient and current_description and len(current_numbers) > 0:
                total = float(current_numbers[-1])
                if total > 0:
                    results.append({
                        "Patient": current_patient,
                        "Acte Cosmident": current_description.strip(),
                        "Prix Cosmident": f"{total:.2f}",
                    })
            current_patient = ref_match.group(1).strip()
            current_description = ""
            current_numbers = []
            continue
        
        # Détection via Bon n° ... Prescription ...
        bon_match = re.match(r"Bon n°\d+ du [\w\d/]+.*Prescription \d+", line)
        if bon_match and i < len(clean_lines):
            next_line = clean_lines[i].strip()
            ref_match = re.search(r"Ref\.?\s*(?:Patient\s*)?:?\s*([\w\s\-]+)", next_line, re.IGNORECASE)
            if ref_match:
                if current_patient and current_description and len(current_numbers) > 0:
                    total = float(current_numbers[-1])
                    if total > 0:
                        results.append({
                            "Patient": current_patient,
                            "Acte Cosmident": current_description.strip(),
                            "Prix Cosmident": f"{total:.2f}",
                        })
                current_patient = ref_match.group(1).strip()
                current_description = ""
                current_numbers = []
                i += 1
                continue
        
        if current_patient is None:
            continue

        # Séparer texte et nombres
        all_numbers = re.findall(r"\d+[\.,]\d{2}", line)
        # Ne garder que ceux >48 → prix
        prices = [n.replace(",", ".") for n in all_numbers if float(n.replace(",", ".")) > 48]
        if prices:
            current_numbers.extend(prices)
        
        # Texte de l'acte : retirer uniquement les prix (laisser dents et parenthèses)
        text_only = re.sub(r"\b\d+[\.,]\d{2}\b", "", line).strip()
        if text_only:
            if current_description:
                current_description += " " + text_only
            else:
                current_description = text_only
    
    # Ajouter le dernier acte
    if current_patient and current_description and len(current_numbers) > 0:
        total = float(current_numbers[-1])
        if total > 0:
            results.append({
                "Patient": current_patient,
                "Acte Cosmident": current_description.strip(),
                "Prix Cosmident": f"{total:.2f}",
            })
    
    return pd.DataFrame(results)
