"""Synthetic French criminal case files (fiction only).

A scenario is a list of `PieceSpec` (one procès-verbal each) plus ground-truth entries:
the nullities we injected on purpose and the decoys (irregular-looking but lawful situations).
The same building blocks produce the fixed demo case ("Affaire des Mathurins") and the random
dossiers of NullityBench-FR.

Every name, place and number here is invented. No real data.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from casebreak.synth import fr

CITY = "Valmorin"
SERVICE = f"Commissariat de police de {CITY} - Service local de police judiciaire"
COURT = f"TRIBUNAL JUDICIAIRE DE {CITY.upper()}"

FIRST = ["Théo", "Romain", "Jonas", "Inès", "Lucas", "Maëlle", "Bastien", "Clara", "Yanis", "Léa",
         "Hugo", "Sarah", "Nolan", "Camille", "Malik", "Elsa", "Adrien", "Jade", "Tristan", "Manon"]
LAST = ["VASSEUR", "LECLERC", "WEBER", "ROCHAT", "PERRIN", "MARCHAND", "BRUNET", "GAUTHIER", "FAURE",
        "LEMAIRE", "COLLET", "BARBIER", "RENARD", "PICARD", "GIRAUD", "HUBERT", "MEUNIER", "CARON"]
OPJS = [("Claire", "DUMONT", "Capitaine de police"), ("Hugo", "FERRAND", "Lieutenant de police"),
        ("Jeanne", "MARCHETTI", "Lieutenante de police"), ("Paul", "SERVAN", "Commandant de police")]
APJS = [("Sami", "OUALI", "Brigadier-chef"), ("Lina", "MOREAU", "Gardienne de la paix")]
LAWYERS = [("Élise", "RENAUD", "avocate"), ("Marc", "DELAUNAY", "avocat"), ("Nora", "BENALI", "avocate")]
STREETS = ["allée des Tilleuls", "rue des Mathurins", "impasse du Moulin", "rue Haute", "chemin des Vignes",
           "boulevard de l'Orbe", "rue du Pressoir", "place des Halles"]


@dataclass
class Person:
    first: str
    last: str
    born: str
    address: str
    language: str = "française"
    mother: str = ""

    @property
    def name(self) -> str:
        return f"{self.last} {self.first}"

    @property
    def civil(self) -> str:
        return f"{self.first} {self.last}"


@dataclass
class PieceSpec:
    type: str
    objet: str
    dt: datetime | None
    body: list[str]
    number: str = ""
    header: str = "police"  # police | court | lab
    cadre: str = ""
    person: str = ""
    scan: bool = False
    photo: dict | None = None  # {"label": ..., "exif": datetime, "subject": ...}
    gt: list[dict] = field(default_factory=list)
    key: str = ""  # stable handle used by ground truth (cascade targets)
    cote: str = ""


@dataclass
class Custody:
    person: Person
    start: datetime
    pieces: dict[str, PieceSpec] = field(default_factory=dict)


class CaseBuilder:
    def __init__(self, seed: int, base: datetime, affaire: str, pv_prefix: str):
        self.rng = random.Random(seed)
        self.base = base
        self.affaire = affaire
        self.pv_prefix = pv_prefix
        self.pieces: list[PieceSpec] = []
        self._n = 0
        self.opj = self.rng.sample(OPJS, 3)
        self.apj = self.rng.choice(APJS)
        self.lawyer = self.rng.choice(LAWYERS)
        self.used_names: set[str] = set()

    # ------------------------------------------------------------------ helpers
    def person(self, language: str = "française") -> Person:
        while True:
            first, last = self.rng.choice(FIRST), self.rng.choice(LAST)
            if last not in self.used_names:
                self.used_names.add(last)
                break
        born = f"{self.rng.randint(1,28):02d}/{self.rng.randint(1,12):02d}/{self.rng.randint(1975, 2004)}"
        addr = f"{self.rng.randint(2, 48)}, {self.rng.choice(STREETS)} à {CITY}"
        mother_first = self.rng.choice(["Martine", "Sylvie", "Nathalie", "Isabelle", "Brigitte"])
        return Person(first, last, born, addr, language, mother=f"Mme {mother_first} {last}")

    def number(self) -> str:
        self._n += 1
        return f"{self.pv_prefix}/{self._n:02d}"

    def opj_line(self, i: int = 0) -> str:
        f, l, g = self.opj[i % len(self.opj)]
        return f"Nous, {f} {l}, {g}, officier de police judiciaire en résidence à {CITY},"

    def add(self, spec: PieceSpec) -> PieceSpec:
        if not spec.number:
            spec.number = self.number()
        self.pieces.append(spec)
        return spec

    def at(self, dt: datetime) -> str:
        return fr.at_time(dt, self.rng)

    def filler_qa(self, n: int) -> list[str]:
        qs = [
            ("Où vous trouviez-vous le soir des faits ?", "J'étais chez moi, je n'ai rien à voir avec cette histoire."),
            ("Connaissez-vous la bijouterie située place des Halles ?", "Je passe devant tous les jours, comme tout le monde."),
            ("Avez-vous un véhicule ?", "Oui, une voiture grise, mais je la prête souvent."),
            ("Comment expliquez-vous la présence de bijoux à votre domicile ?", "Ce sont des cadeaux, je ne savais pas d'où ils venaient."),
            ("Avec qui étiez-vous en contact ce soir-là ?", "Je ne m'en souviens pas, j'ai beaucoup de contacts."),
            ("Avez-vous déjà été condamné ?", "Une fois, il y a longtemps, pour une affaire de stupéfiants."),
            ("Que faisiez-vous près du commerce vers vingt-deux heures ?", "Je rentrais du travail à pied."),
            ("Reconnaissez-vous la personne sur la photographie présentée ?", "Non, je ne la connais pas."),
            ("Souhaitez-vous ajouter quelque chose ?", "Non, je n'ai rien à ajouter."),
            ("Expliquez vos échanges téléphoniques de la nuit des faits.", "Je parlais avec un ami pour un déménagement."),
        ]
        out = []
        for q, a in self.rng.sample(qs, min(n, len(qs))):
            out.append(f"QUESTION : {q}")
            out.append(f"RÉPONSE : {a}")
        return out

    def boiler(self, n: int) -> list[str]:
        bank = [
            "Les diligences effectuées sont consignées au présent procès-verbal, établi en un seul exemplaire.",
            "Les images de vidéoprotection du secteur ont été requises auprès du service municipal compétent.",
            "Les constatations sont réalisées en présence des fonctionnaires désignés en tête du présent.",
            "Une copie des pièces est transmise au parquet par la voie hiérarchique.",
            "Les vérifications au fichier des véhicules n'appellent pas d'observation particulière.",
            "Le témoin précise avoir entendu un bruit de verre brisé, sans pouvoir donner d'heure exacte.",
            "Les relevés de traces papillaires sont confiés au service de l'identité judiciaire.",
            "La victime remet la liste des bijoux dérobés, annexée au présent procès-verbal.",
            "Le quartier est décrit comme calme, peu fréquenté après la fermeture des commerces.",
            "Les recherches de voisinage restent infructueuses à ce stade de l'enquête.",
            "Le préjudice déclaré par la victime est évalué à titre provisoire, sous réserve d'expertise.",
            "Les opérations techniques sont réalisées sans incident et consignées ci-après.",
        ]
        return [self.rng.choice(bank) for _ in range(n)]

    # ------------------------------------------------------------------ acts
    def interpellation(self, p: Person, dt: datetime, cadre: str, placed_at: datetime | None,
                       cite: PieceSpec | None = None) -> PieceSpec:
        f, l, g = self.apj
        body = [fr.opener(dt, self.rng),
                f"Nous, {f} {l}, {g}, agent de police judiciaire, assisté des fonctionnaires de la brigade de roulement,"]
        if cite is not None:
            body.append(f"Agissant sur la base des données du dispositif de géolocalisation (procès-verbal n° {cite.number}),")
        body += [f"Procédons à l'interpellation de {p.name}, né le {p.born}, demeurant {p.address}.",
                 "L'intéressé est appréhendé sans opposition et conduit au service."]
        if placed_at is not None:
            body.append(f"Il est placé en garde à vue {self.at(placed_at)} par l'officier de police judiciaire.")
        body += self.boiler(2)
        return self.add(PieceSpec("PV_INTERPELLATION", "INTERPELLATION", dt, body, cadre=cadre, person=p.name,
                                  key=f"interp:{p.last}"))

    def placement(self, p: Person, dt: datetime, cadre: str, interp: PieceSpec | None,
                  prosecutor_at: datetime | None, objectives: bool = True, regime: str | None = None) -> PieceSpec:
        body = [fr.opener(dt, self.rng), self.opj_line(0)]
        if interp is not None:
            body.append(f"Vu le procès-verbal d'interpellation n° {interp.number},")
        body.append(f"Décidons de placer en garde à vue {p.name}, né le {p.born}, à compter de {fr.time_digits(dt, self.rng)}.")
        if objectives:
            body.append("Aux motifs que cette mesure constitue l'unique moyen de permettre l'exécution des "
                        "investigations impliquant la présence de la personne et d'empêcher qu'elle ne se concerte "
                        "avec d'autres personnes susceptibles d'être ses coauteurs ou complices.")
        else:
            body.append("La mesure est décidée pour les nécessités de l'enquête.")
        if regime:
            body.append(f"Les faits relèvent du régime dérogatoire applicable à la {regime}.")
        if prosecutor_at is not None:
            body.append(f"Avisons {self.at(prosecutor_at)} Mme la procureure de la République de la mesure de garde à vue.")
        if p.language != "française":
            body.append(f"La personne déclare ne pas comprendre la langue française et s'exprimer en langue {p.language}.")
        else:
            body.append("La personne déclare comprendre parfaitement la langue française.")
        body.append("Dont procès-verbal.")
        return self.add(PieceSpec("PV_PLACEMENT_GAV", "PLACEMENT EN GARDE À VUE", dt, body, cadre=cadre,
                                  person=p.name, key=f"placement:{p.last}"))

    def notification(self, p: Person, dt: datetime, cadre: str, stated_start: datetime, *, lawyer: bool,
                     doctor: bool, family: bool, interpreter: str | None = None,
                     justification: str | None = None, signed: bool = True) -> PieceSpec:
        f, l, t = self.lawyer
        body = [fr.opener(dt, self.rng), self.opj_line(0)]
        who = f"Notifions à {p.name}, placé en garde à vue ce jour {fr.at_time(stated_start, self.rng)},"
        if interpreter:
            who += f" par l'intermédiaire de {interpreter}, interprète en langue {p.language},"
        elif p.language != "française":
            who += " en langue française,"
        body.append(who)
        body.append("la qualification, la date et le lieu présumés de l'infraction, la durée de la mesure, ainsi que "
                    "les droits suivants : droit de faire prévenir un proche et son employeur, droit d'être examiné "
                    "par un médecin, droit d'être assisté par un avocat, droit d'être assisté par un interprète, "
                    "droit de se taire.")
        if justification:
            body.append(f"La notification des droits a été différée en raison de {justification}.")
        body.append(f"La personne déclare souhaiter être assistée par Maître {f} {l}, {t} au barreau de {CITY}."
                    if lawyer else "La personne déclare ne pas souhaiter être assistée par un avocat.")
        body.append("La personne déclare souhaiter être examinée par un médecin." if doctor
                    else "La personne déclare ne pas souhaiter être examinée par un médecin.")
        body.append(f"La personne déclare souhaiter faire prévenir {p.mother}, sa mère." if family
                    else "La personne déclare ne pas souhaiter faire prévenir un proche.")
        body.append("Après lecture faite, la personne persiste et signe avec nous." if signed
                    else "Après lecture faite, la personne refuse de signer.")
        return self.add(PieceSpec("PV_NOTIFICATION_DROITS", "NOTIFICATION DES DROITS AU GARDÉ À VUE", dt, body,
                                  cadre=cadre, person=p.name, key=f"notif:{p.last}"))

    def avis_avocat(self, p: Person, dt: datetime, cadre: str) -> PieceSpec:
        f, l, t = self.lawyer
        body = [fr.opener(dt, self.rng), self.opj_line(1),
                f"Avisons par téléphone Maître {f} {l}, {t} au barreau de {CITY}, de la demande d'assistance formulée par {p.name}.",
                "Le message est laissé au secrétariat du cabinet, qui en accuse réception."]
        return self.add(PieceSpec("PV_AVIS_AVOCAT", "AVIS À AVOCAT", dt, body, cadre=cadre, person=p.name,
                                  key=f"avocat:{p.last}"))

    def avis_famille(self, p: Person, dt: datetime, cadre: str, scan: bool = False) -> PieceSpec:
        body = [fr.opener(dt, self.rng), self.opj_line(1),
                f"Conformément à la demande de {p.name}, avisons {p.mother}, sa mère, de la mesure de garde à vue dont il fait l'objet."]
        return self.add(PieceSpec("PV_AVIS_FAMILLE", "AVIS À FAMILLE", dt, body, cadre=cadre, person=p.name,
                                  scan=scan, key=f"famille:{p.last}"))

    def examen_medical(self, p: Person, dt: datetime, cadre: str) -> PieceSpec:
        body = [fr.opener(dt, self.rng), self.opj_line(1),
                f"Le docteur Anne LOISEL procède à l'examen médical de {p.name} dans les locaux du service.",
                "Le certificat médical conclut à la compatibilité de l'état de santé avec la mesure de garde à vue."]
        return self.add(PieceSpec("PV_EXAMEN_MEDICAL", "EXAMEN MÉDICAL", dt, body, cadre=cadre, person=p.name,
                                  key=f"medecin:{p.last}"))

    def audition(self, p: Person, start: datetime, end: datetime, cadre: str, *, mode: str,
                 lawyer_notified: datetime | None = None, interpreter: str | None = None,
                 cites: list[PieceSpec] | None = None, seal: str | None = None, witness: bool = False,
                 n_qa: int = 6) -> PieceSpec:
        f, l, t = self.lawyer
        body = [fr.opener(start, self.rng), self.opj_line(2 if witness else 0)]
        for c in cites or []:
            body.append(f"Vu le procès-verbal n° {c.number},")
        if witness:
            body.append(f"Entendons en qualité de témoin {p.name}, né le {p.born}, demeurant {p.address}.")
        else:
            body.append(f"Entendons {p.name}, actuellement en garde à vue dans nos locaux.")
        if interpreter:
            body.append(f"L'audition se déroule avec l'assistance de {interpreter}, interprète en langue {p.language}.")
        if mode == "present":
            body.append(f"L'audition se déroule en présence de Maître {f} {l}, {t}.")
        elif mode == "absent":
            when = f", avisée {fr.at_time(lawyer_notified, self.rng)}" if lawyer_notified else ""
            body.append(f"Maître {f} {l}{when}, ne s'étant pas présentée, l'audition débute hors la présence de l'avocat.")
        elif mode == "waiver":
            body.append("L'intéressé renonce expressément à l'assistance d'un avocat pour la présente audition "
                        "et porte cette mention de sa main.")
        if seal:
            body.append(f"Sont présentés à l'intéressé les éléments issus de l'exploitation du scellé n° {seal}.")
        body += self.filler_qa(n_qa)
        body.append(f"Fin de l'audition {self.at(end)}.")
        body.append("Lecture faite par lui-même, l'intéressé persiste et signe avec nous.")
        typ = "PV_AUDITION_TEMOIN" if witness else "PV_AUDITION_GAV"
        return self.add(PieceSpec(typ, "AUDITION DE TÉMOIN" if witness else "AUDITION DE PERSONNE GARDÉE À VUE",
                                  start, body, cadre=cadre, person=p.name,
                                  key=f"audition:{p.last}:{start:%d%H%M}"))

    def perquisition(self, p: Person, start: datetime | None, end: datetime, cadre: str, *, place: str,
                     presence: str, consent: str | None, items: list[tuple[str, str | None]],
                     scan: bool = False, hw_start: str | None = None, jld: bool = False) -> PieceSpec:
        """items: (description, seal or None). presence: occupant | witnesses | none."""
        if hw_start:
            body = [f"Le {fr.date_digits(end)} à {{HW:{hw_start}}},"]
        else:
            body = [fr.opener(start, self.rng)]
        body.append(self.opj_line(1))
        body.append(f"Nous transportons {place} {p.name}, sis {p.address}.")
        if jld:
            body.append("En exécution de l'autorisation écrite et motivée du juge des libertés et de la détention annexée au présent,")
        if consent == "handwritten":
            body.append(f"{p.name} donne son assentiment exprès à la perquisition par déclaration écrite de sa main : "
                        "« Je consens à ce que la perquisition et les saisies aient lieu. »")
        elif consent == "verbal":
            body.append(f"{p.name} donne verbalement son accord à la perquisition.")
        if presence == "occupant":
            body.append(f"Procédons à la perquisition en présence constante de {p.name}, occupant des lieux.")
        elif presence == "witnesses":
            body.append("En l'absence de l'occupant, procédons à la perquisition en présence de deux témoins requis, "
                        "M. Henri BLONDEL et Mme Odile FRANCE, étrangers au service.")
        else:
            body.append("Procédons à la perquisition des lieux.")
        body.append("Découvrons et saisissons :")
        for desc, seal in items:
            body.append(f"- {desc}, placé sous scellé n° {seal} ;" if seal else f"- {desc}, saisi ;")
        body.append("Les objets saisis sont inventoriés en présence des personnes susvisées.")
        body += self.boiler(2)
        body.append(f"Fin des opérations {self.at(end)}.")
        body.append("Lecture faite, les personnes présentes signent avec nous.")
        return self.add(PieceSpec("PV_PERQUISITION", "PERQUISITION ET SAISIES", start or end, body, cadre=cadre,
                                  person=p.name, scan=scan, key=f"perquisition:{p.last}"))

    def exploitation(self, seal: str, what: str, dt: datetime, cadre: str, cite: PieceSpec) -> PieceSpec:
        body = [fr.opener(dt, self.rng), self.opj_line(2),
                f"Vu le procès-verbal n° {cite.number},",
                f"Procédons à l'exploitation du scellé n° {seal} ({what}), après bris de scellé régulier.",
                "Constatons la présence de messages échangés la nuit des faits avec un correspondant non identifié.",
                "Les données extraites sont gravées sur support numérique et placées en annexe."]
        body += self.boiler(2)
        return self.add(PieceSpec("PV_EXPLOITATION", f"EXPLOITATION DU SCELLÉ {seal}", dt, body, cadre=cadre,
                                  key=f"exploitation:{seal}"))

    def expertise(self, seals: list[str], dt: datetime, ordered_by: PieceSpec | None) -> PieceSpec:
        sl = " et ".join(f"n° {s}" for s in seals)
        body = [fr.opener(dt, self.rng),
                "Nous, Docteur Marion ESTÈVE, expert près la cour d'appel, inscrite en génétique,"]
        if ordered_by is not None:
            body.append(f"Vu l'ordonnance de commission d'expert n° {ordered_by.number},")
        body += [f"Procédons à l'analyse génétique des scellés {sl}.",
                 "Un profil génétique masculin exploitable est mis en évidence sur les prélèvements.",
                 "Les résultats sont détaillés dans les tableaux annexés au présent rapport."]
        return self.add(PieceSpec("RAPPORT_EXPERTISE", "RAPPORT D'EXPERTISE GÉNÉTIQUE", dt, body, header="lab",
                                  key=f"expertise:{'-'.join(seals)}"))

    def prolongation(self, p: Person, dt: datetime, cadre: str, from_dt: datetime) -> PieceSpec:
        body = [fr.opener(dt, self.rng),
                f"Nous, procureure de la République près le tribunal judiciaire de {CITY},",
                f"Vu la garde à vue de {p.name},",
                f"Autorisons la prolongation de la garde à vue de {p.name} pour une durée de vingt-quatre heures, "
                f"à compter du {fr.date_digits(from_dt)} à {fr.time_digits(from_dt)}.",
                "La présente autorisation est écrite et motivée par les nécessités de l'enquête."]
        return self.add(PieceSpec("AUTORISATION_PROLONGATION", "AUTORISATION DE PROLONGATION DE GARDE À VUE",
                                  dt, body, header="court", cadre=cadre, person=p.name, key=f"prolongation:{p.last}"))

    def fin_gav(self, p: Person, dt: datetime, cadre: str, with_time: bool = True, scan: bool = False) -> PieceSpec:
        if with_time:
            body = [fr.opener(dt, self.rng), self.opj_line(0),
                    f"Mettons fin à la garde à vue de {p.name} {self.at(dt)}."]
        else:
            body = [f"Le {fr.date_digits(dt)},", self.opj_line(0),
                    f"Mettons fin à la mesure de garde à vue de {p.name}."]
        body += ["La personne est conduite devant le magistrat sur instruction du parquet.",
                 "Lecture faite, l'intéressé signe avec nous."]
        return self.add(PieceSpec("PV_FIN_GAV", "FIN DE GARDE À VUE", dt, body, cadre=cadre, person=p.name,
                                  scan=scan, key=f"fin:{p.last}"))

    def geoloc(self, target: Person, dt: datetime, auth_date: datetime, auth_piece: PieceSpec | None) -> PieceSpec:
        ref = f" n° {auth_piece.number}" if auth_piece else ""
        body = [fr.opener(dt, self.rng), self.opj_line(1),
                f"En exécution de l'autorisation{ref} délivrée par Mme la procureure de la République en date du {fr.date_digits(auth_date)},",
                f"Procédons à la mise en place d'un dispositif de géolocalisation sur le véhicule utilisé par {target.name}.",
                "Le dispositif est opérationnel ; les données sont recueillies sur le serveur sécurisé du service."]
        return self.add(PieceSpec("PV_GEOLOCALISATION", "MISE EN PLACE D'UN DISPOSITIF DE GÉOLOCALISATION", dt, body,
                                  cadre="preliminaire", person=target.name, key=f"geoloc:{target.last}"))

    def autorisation_geoloc(self, target: Person, dt: datetime) -> PieceSpec:
        body = [fr.opener(dt, self.rng),
                f"Nous, procureure de la République près le tribunal judiciaire de {CITY},",
                f"Autorisons la mise en place d'un dispositif de géolocalisation sur le véhicule utilisé par {target.name}.",
                "La présente autorisation est délivrée pour une durée limitée et motivée par les nécessités de l'enquête."]
        return self.add(PieceSpec("AUTORISATION_GEOLOC", "AUTORISATION DE GÉOLOCALISATION", dt, body, header="court",
                                  key=f"auth-geoloc:{target.last}"))

    def ordonnance_interception(self, target: Person, dt: datetime, judge: str) -> PieceSpec:
        body = [fr.opener(dt, self.rng), f"Nous, {judge}, juge d'instruction au tribunal judiciaire de {CITY},",
                f"Ordonnons l'interception des correspondances émises par la voie des communications électroniques sur la ligne utilisée par {target.name}.",
                "La présente ordonnance est délivrée pour une durée limitée et pourra être renouvelée."]
        return self.add(PieceSpec("ORDONNANCE_INTERCEPTION", "ORDONNANCE AUTORISANT L'INTERCEPTION DE CORRESPONDANCES",
                                  dt, body, header="court", cadre="instruction", key=f"ord-interception:{target.last}"))

    def interception(self, target: Person, dt: datetime, ordonnance: PieceSpec | None, auth_date: datetime) -> PieceSpec:
        ref = f"de l'ordonnance n° {ordonnance.number}" if ordonnance else "de l'ordonnance"
        body = [fr.opener(dt, self.rng), self.opj_line(2),
                f"En exécution {ref} du juge d'instruction en date du {fr.date_digits(auth_date)},",
                f"Procédons à la retranscription des communications interceptées sur la ligne utilisée par {target.name}.",
                "Les conversations sans rapport avec les faits ne sont pas retranscrites."]
        return self.add(PieceSpec("PV_INTERCEPTION", "RETRANSCRIPTION D'INTERCEPTIONS", dt, body, cadre="instruction",
                                  key=f"interception:{target.last}"))

    def requisitoire(self, dt: datetime, names: list[str]) -> PieceSpec:
        body = [fr.opener(dt, self.rng), f"Nous, procureure de la République près le tribunal judiciaire de {CITY},",
                f"Requérons qu'il plaise à M. ou Mme le juge d'instruction informer contre {', '.join(names)} "
                "des chefs de vol avec effraction et recel."]
        return self.add(PieceSpec("REQUISITOIRE_INTRODUCTIF", "RÉQUISITOIRE INTRODUCTIF", dt, body, header="court",
                                  cadre="instruction", key="requisitoire"))

    def mise_en_examen(self, p: Person, dt: datetime, judge: str, cites: list[PieceSpec]) -> PieceSpec:
        body = [fr.opener(dt, self.rng), f"Devant nous, {judge}, juge d'instruction au tribunal judiciaire de {CITY},",
                f"A comparu {p.name}, assisté de son conseil."]
        for c in cites:
            body.append(f"Vu le procès-verbal n° {c.number},")
        body += [f"Mettons en examen {p.name} des chefs de vol avec effraction et recel.",
                 "Avisons la personne de son droit de formuler des demandes d'actes ou des requêtes en annulation."]
        return self.add(PieceSpec("PV_MISE_EN_EXAMEN", "INTERROGATOIRE DE PREMIÈRE COMPARUTION", dt, body,
                                  header="court", cadre="instruction", person=p.name, key=f"mex:{p.last}"))

    def ordonnance_expertise(self, dt: datetime, judge: str, seals: list[str]) -> PieceSpec:
        body = [fr.opener(dt, self.rng), f"Nous, {judge}, juge d'instruction,",
                f"Commettons le Docteur Marion ESTÈVE aux fins d'analyse génétique des scellés {', '.join(seals)}."]
        return self.add(PieceSpec("ORDONNANCE_EXPERTISE", "ORDONNANCE DE COMMISSION D'EXPERT", dt, body,
                                  header="court", cadre="instruction", key="ord-expertise"))

    def arret_chambre(self, dt: datetime) -> PieceSpec:
        body = [fr.opener(dt, self.rng), f"La chambre de l'instruction de la cour d'appel, statuant sur la requête en annulation,",
                "Rejette la requête et ordonne le retour du dossier au juge d'instruction saisi."]
        return self.add(PieceSpec("ARRET_CHAMBRE_INSTRUCTION", "ARRÊT DE LA CHAMBRE DE L'INSTRUCTION", dt, body,
                                  header="court", cadre="instruction", key="arret-chambre"))

    def filler(self, typ: str, objet: str, dt: datetime, cadre: str, n: int, scan: bool = False,
               who: Person | None = None) -> PieceSpec:
        body = [fr.opener(dt, self.rng), self.opj_line(self.rng.randrange(3))]
        if who is not None and typ == "PV_AUDITION_TEMOIN":
            body.append(f"Entendons en qualité de témoin {who.name}, né le {who.born}, demeurant {who.address}.")
            body += self.filler_qa(min(n, 8))
            body.append(f"Fin de l'audition {self.at(dt + timedelta(minutes=self.rng.randint(25, 70)))}.")
        else:
            body += self.boiler(n)
        return self.add(PieceSpec(typ, objet, dt, body, cadre=cadre, scan=scan, key=f"filler:{len(self.pieces)}"))

    def annex(self, typ: str, objet: str, dt: datetime, cadre: str, rows: int, kind: str = "fadettes") -> PieceSpec:
        """Long annexes (call records, transcripts): they make the file thick, like the real ones."""
        body = [fr.opener(dt, self.rng), self.opj_line(self.rng.randrange(3)),
                "Annexons au présent les éléments communiqués en réponse à notre réquisition, reproduits ci-après."]
        t = dt - timedelta(days=3)
        relays = ["VALMORIN-NORD", "VALMORIN-GARE", "ORBE-SUD", "LES-HALLES", "ZI-EST"]
        for _ in range(rows):
            t += timedelta(minutes=self.rng.randint(3, 160), seconds=self.rng.randint(0, 59))
            if kind == "fadettes":
                body.append(f"- {t:%d/%m/%Y} {t:%H:%M:%S} | {self.rng.choice(['SORTANT', 'ENTRANT', 'SMS'])} | "
                            f"+33 6 00 {self.rng.randint(10, 99)} {self.rng.randint(10, 99)} {self.rng.randint(10, 99)} | "
                            f"durée {self.rng.randint(0, 9):02d}:{self.rng.randint(0, 59):02d} | relais {self.rng.choice(relays)}")
            else:
                body.append(f"- Séquence {self.rng.randint(100, 999)} : {self.rng.choice(['échange sans intérêt pour l’enquête', 'conversation d’ordre familial', 'appel bref, interlocuteur non identifié', 'messagerie vocale, message non retranscrit'])}.")
        return self.add(PieceSpec(typ, objet, dt, body, cadre=cadre, key=f"annex:{len(self.pieces)}"))

    def photo(self, label: str, exif: datetime, subject: str, cadre: str) -> PieceSpec:
        return self.add(PieceSpec("PHOTO", f"PHOTOGRAPHIE - {label}", exif, [], cadre=cadre,
                                  photo={"label": label, "exif": exif, "subject": subject}, key=f"photo:{label}"))


def gt(spec: PieceSpec, nullity_id: str, expected: str, injected: bool, note: str, phrase: str = "",
       affected: list[PieceSpec] | None = None, cert: str = "") -> None:
    """Attach a ground-truth entry to a piece. expected: possible_nullity | needs_reading | not_flagged."""
    spec.gt.append({"nullity_id": nullity_id, "expected": expected, "injected": injected, "note": note,
                    "phrase": phrase, "affected_keys": [a.key for a in (affected or [])], "certainty": cert})


# ============================================================================ demo scenario


def demo_case() -> CaseBuilder:
    """Affaire des Mathurins — the frozen demo dossier (seed 7)."""
    b = CaseBuilder(seed=7, base=datetime(2026, 9, 15), affaire="VOL AVEC EFFRACTION - BIJOUTERIE ARNAUD & FILS",
                    pv_prefix="2026/00873")
    b.used_names.update({"VASSEUR", "LECLERC", "WEBER", "ROCHAT", "ARNAUD"})
    vasseur = Person("Théo", "VASSEUR", "04/02/1998", f"14, allée des Tilleuls à {CITY}", mother="Mme Sylvie VASSEUR")
    leclerc = Person("Romain", "LECLERC", "21/11/1994", f"3, rue du Pressoir à {CITY}", mother="Mme Nathalie LECLERC")
    weber = Person("Jonas", "WEBER", "09/06/1989", f"27, chemin des Vignes à {CITY}", language="allemande",
                   mother="Mme Ursula WEBER")
    rochat = Person("Inès", "ROCHAT", "17/08/1999", f"8, rue Haute à {CITY}")
    arnaud = Person("Paul", "ARNAUD", "02/05/1961", f"5, place des Halles à {CITY}")
    d = lambda day, h, m=0: datetime(2026, 9, day, h, m)  # noqa: E731
    flag, prel, instr = "flagrance", "preliminaire", "instruction"
    judge = "Hélène GARNIER"

    # --- complaint and first findings
    b.filler("PV_PLAINTE", "DÉPÔT DE PLAINTE", d(15, 8, 10), flag, 7, who=None)
    b.filler("PV_AUDITION_TEMOIN", "AUDITION DE TÉMOIN", d(15, 8, 40), flag, 8, who=arnaud)
    b.filler("PV_CONSTATATIONS", "CONSTATATIONS ET TRANSPORT SUR LES LIEUX", d(15, 9, 30), flag, 12)
    b.filler("PV_VIDEOPROTECTION", "EXPLOITATION DE VIDÉOPROTECTION", d(15, 10, 5), flag, 9, scan=True)

    # --- VASSEUR: arrest, custody (injected GAV-04, GAV-08, GAV-09, GAV-02, GAV-13), search (PRQ-01, PRQ-04)
    i_v = b.interpellation(vasseur, d(15, 10, 50), flag, placed_at=d(15, 11, 5))
    p_v = b.placement(vasseur, d(15, 11, 5), flag, i_v, prosecutor_at=d(15, 11, 20))
    n_v = b.notification(vasseur, d(15, 14, 20), flag, stated_start=d(15, 10, 35), lawyer=True, doctor=True, family=True)
    a_v = b.avis_avocat(vasseur, d(15, 14, 25), flag)
    f_v = b.avis_famille(vasseur, d(15, 14, 30), flag, scan=True)
    h1_v = b.audition(vasseur, d(15, 16, 40), d(15, 17, 35), flag, mode="absent", lawyer_notified=d(15, 14, 25))
    s_v = b.perquisition(vasseur, d(15, 21, 35), d(15, 23, 10), flag, place="au domicile de", presence="occupant",
                         consent=None, items=[("un téléphone portable de marque Orphée, de couleur noire", "S1"),
                                              ("un sachet contenant douze bijoux en or", "S2"),
                                              ("un ordinateur portable de couleur grise", None)])
    ph = b.photo("SCELLÉ N° S2", d(15, 21, 20), "bijoux saisis", flag)
    x_v = b.exploitation("S1", "téléphone portable", d(16, 9, 0), flag, s_v)
    h2_v = b.audition(vasseur, d(16, 11, 0), d(16, 12, 10), flag, mode="present", cites=[x_v], seal="S1")
    e_v = b.fin_gav(vasseur, d(16, 16, 0), flag)

    gt(n_v, "GAV-04", "possible_nullity", True, "Rights notified 3h15 after custody began, with no justification.",
       phrase="Notifions", affected=[h1_v, h2_v], cert="documented")
    gt(n_v, "GAV-13", "needs_reading", True, "Custody start time: 11:05 (placement report) vs 10:35 (notification report).",
       phrase="placé en garde à vue ce jour", cert="needs_reading")
    gt(h1_v, "GAV-08", "possible_nullity", True, "Questioned without the requested lawyer, no waiver (post-2024 law).",
       phrase="hors la présence", cert="documented")
    gt(n_v, "GAV-09", "possible_nullity", True, "Medical examination requested, no examination report in the file.",
       phrase="examinée par un médecin", cert="needs_reading")
    gt(p_v, "GAV-02", "possible_nullity", True, "Custody of 28h55 with no extension authorisation.",
       phrase="Décidons de placer", affected=[h2_v, x_v], cert="documented")
    gt(s_v, "PRQ-01", "possible_nullity", True, "Home search started at 21:35.",
       phrase="Nous transportons", affected=[x_v, h2_v], cert="documented")
    gt(s_v, "PRQ-04", "possible_nullity", True, "Laptop seized without being placed under seal.",
       phrase="ordinateur portable", cert="documented")
    gt(ph, "MMC-01", "needs_reading", True, "Photo of seal S2 timestamped (EXIF) 21:20, before the search began (21:35).",
       phrase="", cert="needs_reading")

    # --- LECLERC: decoys (justified delay GAV-05, lawyer present)
    i_l = b.interpellation(leclerc, d(16, 2, 15), flag, placed_at=d(16, 2, 30))
    p_l = b.placement(leclerc, d(16, 2, 30), flag, i_l, prosecutor_at=d(16, 2, 45))
    n_l = b.notification(leclerc, d(16, 4, 40), flag, stated_start=d(16, 2, 30), lawyer=True, doctor=False, family=False,
                         justification="l'état d'ébriété manifeste de l'intéressé, constaté à son arrivée au service")
    b.avis_avocat(leclerc, d(16, 4, 45), flag)
    h_l = b.audition(leclerc, d(16, 10, 0), d(16, 11, 5), flag, mode="present")
    b.fin_gav(leclerc, d(16, 15, 30), flag)
    gt(n_l, "GAV-04", "not_flagged", False, "Decoy: late notification justified by intoxication (stated in the report).",
       phrase="différée")
    gt(h_l, "GAV-08", "not_flagged", False, "Decoy: hearing with the lawyer present.")

    # --- geolocation (GEO-01: authorization not in the file), then WEBER
    g_w = b.geoloc(weber, d(17, 14, 0), d(16, 0), None)
    gt(g_w, "GEO-01", "needs_reading", True, "Geolocation authorisation cited but missing from the file.",
       phrase="En exécution de l'autorisation", cert="needs_reading")
    b.filler("PV_REQUISITION", "RÉQUISITION À OPÉRATEUR DE TÉLÉPHONIE", d(17, 15, 30), prel, 6)
    b.filler("PV_AUDITION_TEMOIN", "AUDITION DE TÉMOIN", d(17, 17, 0), prel, 8, who=b.person())
    b.annex("PV_ANNEXE", "RELEVÉ DÉTAILLÉ DES COMMUNICATIONS (ANNEXE)", d(17, 18, 10), prel, 900)
    b.annex("PV_ANNEXE", "DONNÉES DE BORNAGE (ANNEXE)", d(17, 18, 40), prel, 640)

    # WEBER: injected GAV-10, GAV-06 (missing), GAV-12 (missing end time), PRQ-03 ; decoys GAV-08 waiver, GAV-02 extension
    i_w = b.interpellation(weber, d(18, 6, 20), prel, placed_at=d(18, 6, 35), cite=g_w)
    p_w = b.placement(weber, d(18, 6, 35), prel, i_w, prosecutor_at=None)
    n_w = b.notification(weber, d(18, 6, 50), prel, stated_start=d(18, 6, 35), lawyer=False, doctor=False, family=True)
    b.avis_famille(weber, d(18, 7, 0), prel)
    s_w = b.perquisition(weber, d(18, 7, 30), d(18, 8, 40), prel, place="au garage loué par", presence="occupant",
                         consent="verbal", items=[("un pied-de-biche et une paire de gants", "S5")])
    b.filler("PV_REQUISITION", "RÉQUISITION D'INTERPRÈTE", d(18, 9, 10), prel, 4)
    h_w = b.audition(weber, d(18, 10, 0), d(18, 11, 20), prel, mode="waiver",
                     interpreter="Mme Anna KELLER")
    b.prolongation(weber, d(19, 5, 30), prel, from_dt=d(19, 6, 35))
    e_w = b.fin_gav(weber, d(19, 13, 20), prel, with_time=False, scan=True)
    gt(n_w, "GAV-10", "possible_nullity", True, "Rights notified in French to a person who says they do not understand it, with no interpreter.",
       phrase="en langue française", affected=[h_w], cert="documented")
    gt(p_w, "GAV-06", "possible_nullity", True, "No record that the public prosecutor was informed.",
       phrase="Décidons de placer", cert="needs_reading")
    gt(e_w, "GAV-12", "possible_nullity", True, "Custody end time not recorded.",
       phrase="Mettons fin", cert="needs_reading")
    gt(s_w, "PRQ-03", "possible_nullity", True, "Preliminary-inquiry search on verbal agreement, with no handwritten consent.",
       phrase="verbalement", affected=[], cert="documented")
    gt(h_w, "GAV-08", "not_flagged", False, "Decoy: express handwritten waiver of the lawyer.")
    gt(p_w, "GAV-02", "not_flagged", False, "Decoy: 30h45 with a written extension authorisation.")

    # --- ROCHAT: decoys PRQ-01 (started 20:50, ends 22:15) and PRQ-03 (handwritten consent); handwritten time on a scan
    s_r = b.perquisition(rochat, None, d(18, 22, 15), prel, place="au domicile de", presence="occupant",
                         consent="handwritten", items=[("un sweat-shirt à capuche de couleur sombre", "S6")],
                         scan=True, hw_start="20h50")
    h_r = b.audition(rochat, d(18, 22, 30), d(18, 23, 15), prel, mode="none", witness=True)
    gt(s_r, "PRQ-01", "not_flagged", False, "Decoy: search started at 20:50 (handwritten) and continued after 21:00.")
    gt(s_r, "PRQ-03", "not_flagged", False, "Decoy: express handwritten consent.")

    # --- judicial investigation
    r = b.requisitoire(d(20, 10, 0), [vasseur.name, weber.name])
    m_v = b.mise_en_examen(vasseur, d(21, 15, 0), judge, [h2_v, x_v])
    m_w = b.mise_en_examen(weber, d(21, 17, 0), judge, [h_w])
    oe = b.ordonnance_expertise(d(22, 9, 0), judge, ["S2", "S7"])
    ex = b.expertise(["S2", "S7"], d(25, 14, 0), oe)
    gt(ex, "EXP-01", "needs_reading", True, "Analysed seal S7 is not linked to any seizure in the file.",
       phrase="S7", cert="needs_reading")
    oi = b.ordonnance_interception(weber, d(28, 10, 0), judge)
    it = b.interception(weber, d(29, 18, 0), oi, d(28, 10, 0))
    gt(it, "INT-01", "not_flagged", False, "Decoy: interception with the order present in the file.")
    b.filler("PV_AUDITION_TEMOIN", "AUDITION DE TÉMOIN", d(29, 9, 30), instr, 8, who=b.person())
    b.annex("PV_ANNEXE", "SYNTHÈSE DES INTERCEPTIONS (ANNEXE)", d(30, 9, 0), instr, 700, kind="ecoutes")
    for k in range(6):
        b.filler("PV_AUDITION_TEMOIN", "AUDITION DE TÉMOIN", d(29, 10 + k, 15), instr, 8, who=b.person(),
                 scan=k % 3 == 0)
    b.filler("PV_CONSTATATIONS", "COMPTE RENDU D'ENQUÊTE", d(30, 11, 0), instr, 14)

    # cascade ground truth for the search: phone S1 → exploitation → hearing 2 → mise en examen
    for g in s_v.gt:
        if g["nullity_id"] == "PRQ-01":
            g["affected_keys"] = [x_v.key, h2_v.key, m_v.key, ex.key]
    for g in n_v.gt:
        if g["nullity_id"] == "GAV-04":
            g["affected_keys"] = [h1_v.key, h2_v.key, m_v.key]
    del r, m_w, e_v, f_v, a_v, ph
    return b


# ============================================================================ random scenarios (NullityBench-FR)

INJECTABLE = ["GAV-02", "GAV-04", "GAV-06", "GAV-08", "GAV-09", "GAV-10", "GAV-11", "GAV-12", "GAV-13",
              "PRQ-01", "PRQ-02", "PRQ-03", "PRQ-04", "EXP-01", "GEO-01"]
DECOYS = ["GAV-04", "GAV-08", "GAV-02", "PRQ-01", "PRQ-03"]


def random_case(seed: int) -> CaseBuilder:
    """A random dossier: 1–3 suspects, random injections and decoys, random dates (2022–2026)."""
    rng = random.Random(seed * 7919 + 13)
    year = rng.choice([2022, 2023, 2024, 2025, 2026])
    month = rng.randint(1, 11)
    base = datetime(year, month, rng.randint(2, 20))
    b = CaseBuilder(seed=seed, base=base, affaire=rng.choice(["VOL AVEC EFFRACTION", "RECEL EN BANDE",
                                                              "VOL AGGRAVÉ", "ESCROQUERIE"]),
                    pv_prefix=f"{year}/{rng.randint(100, 999):05d}")
    inject = set(rng.sample(INJECTABLE, rng.randint(3, 7)))
    decoys = set(rng.sample(DECOYS, rng.randint(1, 3))) - inject
    flag = "flagrance"
    t0 = base.replace(hour=rng.randint(7, 12), minute=rng.choice([0, 5, 10, 20, 35, 50]))
    b.filler("PV_PLAINTE", "DÉPÔT DE PLAINTE", t0 - timedelta(hours=2), flag, rng.randint(5, 10))
    b.filler("PV_CONSTATATIONS", "CONSTATATIONS", t0 - timedelta(hours=1), flag, rng.randint(6, 14),
             scan=rng.random() < 0.3)

    p = b.person(language="anglaise" if "GAV-10" in inject else "française")
    lang_interp = None
    if p.language != "française" and "GAV-10" not in inject:
        lang_interp = "M. Ian HOLT"
    interp = b.interpellation(p, t0, flag, placed_at=t0 + timedelta(minutes=15))
    start = t0 + timedelta(minutes=15)
    stated = start - timedelta(minutes=30) if "GAV-13" in inject else start
    pl = b.placement(p, start, flag, interp, prosecutor_at=None if "GAV-06" in inject else start + timedelta(minutes=10))
    if "GAV-06" in inject:
        gt(pl, "GAV-06", "possible_nullity", True, "Prosecutor notice missing", phrase="Décidons de placer")
    delay = timedelta(minutes=rng.choice([185, 200, 240])) if "GAV-04" in inject else (
        timedelta(minutes=rng.choice([110, 130])) if "GAV-04" in decoys else timedelta(minutes=rng.choice([5, 10, 15])))
    just = "l'état d'ébriété manifeste de l'intéressé, constaté à son arrivée au service" if "GAV-04" in decoys else None
    lawyer_req = "GAV-08" in inject or "GAV-08" in decoys or rng.random() < 0.5
    doctor_req = "GAV-09" in inject or rng.random() < 0.3
    family_req = "GAV-11" in inject or rng.random() < 0.5
    nt = b.notification(p, start + delay, flag, stated_start=stated, lawyer=lawyer_req, doctor=doctor_req,
                        family=family_req, interpreter=lang_interp, justification=just)
    if family_req and "GAV-11" not in inject:
        b.avis_famille(p, start + delay + timedelta(minutes=20), flag, scan=rng.random() < 0.3)
    if "GAV-11" in inject:
        gt(nt, "GAV-11", "possible_nullity", True, "Relative to inform not informed", phrase="faire prévenir")
    if "GAV-04" in inject:
        gt(nt, "GAV-04", "possible_nullity", True, "Late notification", phrase="Notifions")
    if "GAV-04" in decoys:
        gt(nt, "GAV-04", "not_flagged", False, "Justified delay", phrase="différée")
    if "GAV-13" in inject:
        gt(nt, "GAV-13", "needs_reading", True, "Conflicting custody start time", phrase="placé en garde à vue")
    if "GAV-10" in inject:
        gt(nt, "GAV-10", "possible_nullity", True, "No interpreter", phrase="en langue française")
    if doctor_req and "GAV-09" not in inject:
        b.examen_medical(p, start + delay + timedelta(minutes=50), flag)
    if "GAV-09" in inject:
        gt(nt, "GAV-09", "possible_nullity", True, "Doctor requested, not seen", phrase="médecin")
    notified = start + delay + timedelta(minutes=5)
    if lawyer_req:
        b.avis_avocat(p, notified, flag)
    # hearing: inject = absent lawyer 2h15 after notice (post-2024 rule); decoy = waiver
    hstart = notified + timedelta(minutes=135)
    if "GAV-08" in inject:
        mode = "absent"
    elif "GAV-08" in decoys:
        mode = "waiver"
    else:
        mode = "present" if lawyer_req else "none"
    h = b.audition(p, hstart, hstart + timedelta(minutes=rng.randint(40, 90)), flag, mode=mode,
                   lawyer_notified=notified if mode == "absent" else None, interpreter=lang_interp)
    if "GAV-08" in inject:
        reform = datetime(2024, 7, 1)
        exp = "possible_nullity" if hstart >= reform else "not_flagged"
        gt(h, "GAV-08", exp, exp == "possible_nullity", "Hearing without lawyer (rule depends on date)", phrase="hors la présence")
    if "GAV-08" in decoys:
        gt(h, "GAV-08", "not_flagged", False, "Express waiver")

    # search
    is_night = "PRQ-01" in inject
    s_start = (start.replace(hour=21, minute=rng.choice([20, 35, 50])) if is_night else
               start.replace(hour=20, minute=50) if "PRQ-01" in decoys else start + timedelta(hours=3))
    s_end = s_start + timedelta(minutes=rng.randint(50, 100))
    prelim_consent = "PRQ-03" in inject or "PRQ-03" in decoys
    items = [("un téléphone portable", "S1"), ("une somme en numéraire", "S2")]
    if "PRQ-04" in inject:
        items.append(("une tablette numérique", None))
    sp = b.perquisition(p, s_start, s_end, "preliminaire" if prelim_consent else flag, place="au domicile de",
                        presence="none" if "PRQ-02" in inject else "occupant",
                        consent=("verbal" if "PRQ-03" in inject else "handwritten") if prelim_consent else None,
                        items=items)
    if "PRQ-01" in inject:
        gt(sp, "PRQ-01", "possible_nullity", True, "Search after 21:00", phrase="Nous transportons")
    if "PRQ-01" in decoys:
        gt(sp, "PRQ-01", "not_flagged", False, "Started 20:50")
    if "PRQ-02" in inject:
        gt(sp, "PRQ-02", "possible_nullity", True, "Neither occupant nor witnesses", phrase="Procédons à la perquisition")
    if "PRQ-03" in inject:
        gt(sp, "PRQ-03", "possible_nullity", True, "Verbal agreement", phrase="verbalement")
    if "PRQ-03" in decoys:
        gt(sp, "PRQ-03", "not_flagged", False, "Handwritten consent")
    if "PRQ-04" in inject:
        gt(sp, "PRQ-04", "possible_nullity", True, "Item not placed under seal", phrase="tablette")
    x = b.exploitation("S1", "téléphone portable", s_end + timedelta(hours=10), flag, sp)

    # custody length
    if "GAV-02" in inject:
        end = start + timedelta(hours=rng.randint(26, 30), minutes=rng.choice([0, 15, 40]))
    elif "GAV-02" in decoys:
        end = start + timedelta(hours=rng.randint(27, 34))
        b.prolongation(p, start + timedelta(hours=22), flag, from_dt=start + timedelta(hours=24))
    else:
        end = start + timedelta(hours=rng.randint(8, 20))
    end = max(end, s_end + timedelta(minutes=30), hstart + timedelta(hours=2))
    if "GAV-02" not in inject and "GAV-02" not in decoys and end - start > timedelta(hours=24):
        b.prolongation(p, start + timedelta(hours=22), flag, from_dt=start + timedelta(hours=24))
    fin = b.fin_gav(p, end, flag, with_time="GAV-12" not in inject, scan=rng.random() < 0.25)
    if "GAV-02" in inject:
        # without an end time (GAV-12) the duration cannot be computed: the honest answer is « à lire »
        exp = "needs_reading" if "GAV-12" in inject else "possible_nullity"
        gt(pl, "GAV-02", exp, True, "Over 24h without extension", phrase="Décidons de placer")
    if "GAV-02" in decoys:
        gt(pl, "GAV-02", "not_flagged", False, "Extension authorised")
    if "GAV-12" in inject:
        gt(fin, "GAV-12", "possible_nullity", True, "End time missing", phrase="Mettons fin")

    b.annex("PV_ANNEXE", "RELEVÉ DÉTAILLÉ DES COMMUNICATIONS (ANNEXE)", end + timedelta(hours=5), flag,
            rng.randint(60, 240))
    for _ in range(rng.randint(2, 6)):
        b.filler("PV_AUDITION_TEMOIN", "AUDITION DE TÉMOIN", end + timedelta(hours=rng.randint(1, 60)), flag,
                 rng.randint(4, 8), who=b.person(), scan=rng.random() < 0.2)
    if "GEO-01" in inject:
        g = b.geoloc(p, end + timedelta(days=1), end, None)
        gt(g, "GEO-01", "needs_reading", True, "Authorisation missing", phrase="En exécution")
    judge = "Hélène GARNIER"
    b.mise_en_examen(p, end + timedelta(days=2), judge, [h, x])
    if "EXP-01" in inject:
        oe = b.ordonnance_expertise(end + timedelta(days=3), judge, ["S2", "S9"])
        ex = b.expertise(["S2", "S9"], end + timedelta(days=6), oe)
        gt(ex, "EXP-01", "needs_reading", True, "Orphan seal S9", phrase="S9")
    b.pieces.sort(key=lambda s: s.dt or datetime.max)
    return b
