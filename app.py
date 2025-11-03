def extract_data_from_cosmident(file):
    if file.type == "application/pdf":
        doc = fitz.open(stream=file.read(), filetype="pdf")
        full_text = ""
        for page in doc:
            # Texte brut de chaque page
            page_text = page.get_text("text")

            # Supprime tout ce qui se trouve après certaines mentions typiques du bas de page
            page_text = re.split(
                r'(COSMIDENT|IBAN|Siret|BIC|Tél\.|NOS COORDONNÉES BANCAIRES|Total \(Euros\)|TOTAL TTC|Règlement|Chèque|Par chèque)',
                page_text,
                flags=re.IGNORECASE
            )[0]

            full_text += page_text + "\n"
    else:
        image = Image.open(file)
        full_text = extract_text_from_image(image)

    # Nettoyage général du texte
    lines = full_text.split('\n')
    clean_lines = []
    for line in lines:
        line = line.strip()
        # Ignore les lignes inutiles ou décoratives
        if not line:
            continue
        if re.search(r'(teinte|couleur|A1|A2|A3|B1|B2|C1|C2|D2|ZIRCONE\s*A\d?)', line, re.IGNORECASE):
            continue
        if re.search(r'(COSMIDENT|IBAN|Siret|BIC|Tél\.|€|Total \(Euros\)|TOTAL TTC)', line, re.IGNORECASE):
            continue
        clean_lines.append(line)

    results = []
    current_patient = None
    i = 0
    while i < len(clean_lines):
        line = clean_lines[i]
        i += 1

        ref_match = re.search(r'Ref\. ([\w\s\-]+)', line)
        if not ref_match:
            bon_match = re.match(r'Bon n°\d+ du [\w\d/]+.*Prescription \d+', line)
            if bon_match and i < len(clean_lines):
                next_line = clean_lines[i].strip()
                ref_match = re.search(r'Ref\. ([\w\s\-]+)', next_line)
                if ref_match:
                    current_patient = ref_match.group(1).strip()
                    i += 1
                    continue
        if ref_match:
            current_patient = ref_match.group(1).strip()
            continue
        if current_patient is None:
            continue

        description = line
        while i < len(clean_lines):
            next_line = clean_lines[i].strip()
            i += 1
            if not next_line:
                continue
            if re.match(r'^\d+\.\d{2}$', next_line):
                quantity = next_line
                price = ""
                while i < len(clean_lines):
                    price_line = clean_lines[i].strip()
                    i += 1
                    if price_line and re.match(r'^\d+\.\d{2}$', price_line):
                        price = price_line
                        break
                remise = ""
                while i < len(clean_lines):
                    remise_line = clean_lines[i].strip()
                    i += 1
                    remise = remise_line if remise_line else "0.00"
                    break
                total = ""
                while i < len(clean_lines):
                    total_line = clean_lines[i].strip()
                    i += 1
                    if total_line and re.match(r'^\d+\.\d{2}$', total_line):
                        total = total_line
                        break
                dents_match = re.findall(r'\b\d{2}\b', description)
                dents = ", ".join(dents_match) if dents_match else ""
                try:
                    price_float = float(price)
                    total_float = float(total)
                    if price_float > 0 and total_float > 0:
                        results.append({
                            'Patient': current_patient,
                            'Acte Cosmident': description,
                            'Prix Cosmident': price
                        })
                except ValueError:
                    pass
                break
            else:
                description += " " + next_line

    return pd.DataFrame(results)
