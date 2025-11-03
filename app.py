        # Détection de l’acte et du prix
        description = line
        found_total = None
        found_price = None
        quantity = 1

        # 🔹 Parcours les lignes suivantes pour trouver prix/remise/total
        while i < len(clean_lines):
            next_line = clean_lines[i].strip()
            i += 1
            if not next_line:
                continue

            # Si la ligne contient des mots du bas de section, on arrête
            if re.search(r'(Ref\.|Bon n°|Prescription|Total \(Euros\))', next_line, re.IGNORECASE):
                break

            # S’il y a un prix sous forme numérique
            if re.match(r'^\d+[\.,]\d{2}$', next_line):
                if found_price is None:
                    found_price = float(next_line.replace(',', '.'))
                    continue
                elif found_total is None:
                    found_total = float(next_line.replace(',', '.'))
                    continue

            # Ajoute les morceaux de description
            else:
                description += " " + next_line

        # 🔹 Recherche des numéros de dents (pour déduire la quantité)
        dents_match = re.findall(r'\b\d{2}\b', description)
        if dents_match:
            quantity = len(dents_match)

        # 🔹 Si pas de total trouvé, calcule-le
        if found_price and not found_total:
            found_total = found_price * quantity

        # 🔹 Vérifie que c’est bien un acte valide
        if found_total and found_total > 0 and found_price and found_price > 0:
            results.append({
                'Patient': current_patient,
                'Acte Cosmident': description.strip(),
                'Prix Cosmident': f"{found_total:.2f}"
            })
