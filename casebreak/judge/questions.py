"""Typed questions asked to the judge. Facts only: « is it stated? », never « is it lawful? »."""

QUESTIONS = {
    "objective_stated": {
        "type": "boolean",
        "fr": "La motivation du placement énonce-t-elle au moins un objectif concret (et pas seulement une formule générale) ?",
    },
    "delay_justified": {
        "type": "enum",
        "options": ["circonstance_relevee", "aucune", "non_documentee"],
        "fr": "Le procès-verbal fait-il état d'une circonstance expliquant le retard de notification des droits ?",
    },
}

PROSECUTION = {
    "justification_retard": "Le retard serait justifié par une circonstance insurmontable.",
    "grief": "L'irrégularité n'aurait pas porté atteinte aux intérêts de la personne (pas de nullité sans grief, art. 171 et 802 CPP).",
    "prolongation": "Une autorisation de prolongation existerait hors cote.",
    "regime_derogatoire": "Un régime dérogatoire autoriserait la mesure.",
    "renonciation": "La personne aurait renoncé à l'assistance de l'avocat.",
    "autorisation_procureur": "Le procureur aurait autorisé l'audition immédiate (circonstances exceptionnelles).",
    "avis_ailleurs": "L'avis figurerait dans une autre pièce (registre, main courante).",
    "piece_hors_dossier": "La pièce existerait mais n'aurait pas été versée au dossier communiqué.",
    "renotification": "Les droits auraient été renotifiés en présence de l'interprète.",
    "mention_ailleurs": "La mention figurerait dans une autre pièce de la procédure.",
    "assentiment": "L'occupant aurait consenti à la perquisition.",
    "autorisation_jld": "Une autorisation du juge des libertés et de la détention existerait.",
    "signature": "La présence résulterait des signatures apposées au PV.",
    "scelle_ulterieur": "L'objet aurait été placé sous scellé dans un acte ultérieur.",
    "erreur_materielle": "L'écart résulterait d'une erreur matérielle sans incidence.",
    "horloge_appareil": "L'horloge de l'appareil photo serait mal réglée.",
    "motivation_suffisante": "La motivation serait suffisante au regard des objectifs légaux.",
}
