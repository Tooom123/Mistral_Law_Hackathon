"""Typed questions asked to the judge. Facts only: "is it stated?", never "is it lawful?"."""

QUESTIONS = {
    "objective_stated": {
        "type": "boolean",
        "text": "Do the grounds for custody state at least one concrete objective (not just a generic phrase)?",
    },
    "delay_justified": {
        "type": "enum",
        "options": ["circumstance_stated", "none", "not_documented"],
        "text": "Does the report state a circumstance explaining the late notification of rights?",
    },
}

PROSECUTION = {
    "delay_justified_claim": "The delay was justified by an insurmountable circumstance.",
    "no_prejudice": "The irregularity did not harm the person's interests (no nullity without prejudice, art. 171 and 802 CPP).",
    "extension": "An extension authorisation exists outside the numbered file.",
    "special_regime": "A special regime authorised the measure.",
    "waiver": "The person waived the right to a lawyer.",
    "prosecutor_authorisation": "The prosecutor authorised immediate questioning (exceptional circumstances).",
    "notice_elsewhere": "The notice appears in another document (register, logbook).",
    "document_outside_file": "The document exists but was not added to the file disclosed.",
    "renotification": "Rights were notified again with the interpreter present.",
    "entry_elsewhere": "The entry appears in another document of the proceedings.",
    "consent": "The occupant consented to the search.",
    "jld_authorisation": "An authorisation from the liberty and custody judge exists.",
    "signature": "Presence follows from the signatures on the report.",
    "later_seal": "The item was placed under seal in a later act.",
    "clerical_error": "The discrepancy is a harmless clerical error.",
    "camera_clock": "The camera clock was set wrong.",
    "sufficient_grounds": "The grounds are sufficient in light of the legal objectives.",
}
