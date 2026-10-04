"""Case files for the conflict-of-interest audit.

`mckinsey` — consulting firms and the State, 2018–2022. A synthetic reconstruction built around the public
chronology of the French Senate inquiry into consulting firms (framework agreement, COVID-19 vaccination campaign,
inquiry committee, hearings under oath, report of March 2022). Individuals, figures, companies other than the
firm, and every relationship between them are fictional; each page carries that notice in the viewer. No original
document is reproduced. The file never states a conflict: the engine has to find it by cross-referencing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SYNTHETIC = "Synthetic reconstruction · individuals, companies other than the firm, figures and relationships are fictional"
PUBLIC = "Public chronology · summary written for the demo, not a verbatim extract"

# Timeline lanes, top to bottom.
LANES = [
    {"id": "procurement", "label": "Procurement"},
    {"id": "private", "label": "Private clients"},
    {"id": "declarations", "label": "Declarations"},
    {"id": "decisions", "label": "Decisions"},
    {"id": "scrutiny", "label": "Scrutiny"},
]


@dataclass
class Doc:
    id: str
    date: str            # ISO date
    lane: str
    kind: str
    title: str
    issuer: str
    pages: list[str]
    provenance: str = "synthetic"   # synthetic | public_record
    precision: str = "day"          # day | month
    tags: list[str] = field(default_factory=list)
    short: str = ""                 # label on the timeline tile

    @property
    def notice(self) -> str:
        return SYNTHETIC if self.provenance == "synthetic" else PUBLIC


@dataclass
class CaseFile:
    id: str
    title: str
    subtitle: str
    jurisdiction: str
    docs: list[Doc]
    context: list[dict] = field(default_factory=list)   # public anchor events without a document


def _p(text: str) -> str:
    """Dedent a page and drop the first/last blank lines."""
    lines = text.strip("\n").splitlines()
    pad = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
    return "\n".join(l[pad:] for l in lines)


def mckinsey() -> CaseFile:
    D = Doc
    docs = [
        D("D01", "2018-05-15", "procurement", "framework_agreement",
          "Framework agreement DITP-2018-AC01 — strategy & transformation consulting", "DITP", [
              _p("""
                FRAMEWORK AGREEMENT DITP-2018-AC01
                Interministerial Directorate for Public Transformation (DITP)
                Lot 1 — Strategy and transformation consulting

                Holder: McKinsey & Company Inc. France, Paris office
                Duration: four years from notification
                Date of notification: 15/05/2018

                Article 1 — Object
                The holder supports ministries in the design and execution of transformation programmes.

                Article 3 — Orders
                Orders are placed by purchase orders signed by the competent authority of the ordering ministry.
                Each purchase order specifies the object, the period, the price and the team assigned.
              """),
              _p("""
                Article 7 — Ethics and conflicts of interest
                7.1 The holder acts with independence and impartiality towards the administration.
                7.2 The holder shall inform the buyer without delay of any situation of conflict of interest, actual or potential, affecting the firm or a member of the team.
                7.3 Before the start of any order, each consultant assigned shall file a declaration of interests with the ordering administration.
                7.4 A consultant who, during the twelve months preceding the order, worked for a company whose interests may be affected by the order shall not be assigned without the buyer's written consent.

                Article 9 — Confidentiality
                Information received in the course of an order shall not be used for the benefit of any other client.
              """),
          ], tags=["contract"]),

        D("D02", "2020-03-16", "declarations", "official_declaration",
          "Declaration of interests — Mathilde Rousseau, on appointment", "Ministry of Solidarity and Health", [
              _p("""
                DECLARATION OF INTERESTS
                On appointment as Deputy Director, Vaccine and Health Products Policy
                Ministry of Solidarity and Health — Directorate General for Health

                Declarant: Mathilde Rousseau
                Date: 16/03/2020

                Section 1 — Professional activities during the last five years
                Previous activity: McKinsey & Company, Paris — Engagement manager — 09/2014 to 09/2019
                Previous activity: Ministry of Solidarity and Health — Project director, vaccine policy — 10/2019 to 02/2020

                Section 2 — Consulting activities: none
                Section 3 — Holdings in companies: none
                Section 5 — Interests of a close relative: none

                I certify that this declaration is accurate and complete.
              """),
          ], tags=["declaration"]),

        D("D03", "2020-11-09", "private", "engagement_letter",
          "Engagement letter VX-2020-31 — Vaxellis SA", "McKinsey & Company, Paris office", [
              _p("""
                ENGAGEMENT LETTER
                Engagement: VX-2020-31 · Client: Vaxellis SA · Sector: health — vaccines
                Firm: McKinsey & Company, Paris office
                Date: 09/11/2020

                Object: European supply and allocation strategy for the Vaxellis COVID-19 vaccine, including the
                preparation of discussions with national health authorities on delivery schedules.
                Period: 09/11/2020 to 31/03/2021

                Team:
                Julien Marchetti — Partner, engagement lead — 20 % — 09/11/2020 to 31/03/2021
                Clara Vasseur — Senior associate — 50 % — 09/11/2020 to 31/03/2021
                Benoît Lacroix — Consultant — 100 % — 09/11/2020 to 31/03/2021

                Fees: fixed fee, see annex. Confidential.
              """),
          ], tags=["private client"]),

        D("D04", "2020-12-04", "procurement", "specifications",
          "Specifications DGS-2020-VAC-04 — logistics strategy of the vaccination campaign", "Directorate General for Health", [
              _p("""
                SPECIFICATIONS
                Support for the logistics strategy of the COVID-19 vaccination campaign
                Ordering administration: Ministry of Solidarity and Health — Directorate General for Health
                Reference: DGS-2020-VAC-04
                Framework: DITP-2018-AC01, Lot 1
                Date: 04/12/2020

                Scope:
                — allocation of doses between suppliers and delivery schedules by region;
                — selection criteria and scenario analysis for the cold-chain logistics provider;
                — steering dashboard of the campaign.

                Stakeholders affected by the deliverables: Vaxellis SA; Nordvac AG; LogiFroid SAS; TransMed Logistique.
              """),
          ], tags=["contract"]),

        D("D05", "2020-12-14", "declarations", "consultant_declaration",
          "Declaration of interests — Clara Vasseur", "McKinsey & Company, Paris office", [
              _p("""
                DECLARATION OF INTERESTS
                Consultant assigned to order DGS-2020-VAC-04

                Declarant: Clara Vasseur
                Firm: McKinsey & Company, Paris office
                Date: 14/12/2020

                Q1. Over the last twelve months, have you worked for a company whose interests may be affected by the order? [ ] Yes [X] No
                Q2. Do you currently hold an engagement for a company in the health sector? [ ] Yes [X] No
                Q3. Interests of a close relative: none

                I certify that this declaration is accurate and complete.
              """),
          ], tags=["declaration"]),

        D("D06", "2020-12-14", "declarations", "consultant_declaration",
          "Declaration of interests — Thomas Le Gall", "McKinsey & Company, Paris office", [
              _p("""
                DECLARATION OF INTERESTS
                Consultant assigned to order DGS-2020-VAC-04

                Declarant: Thomas Le Gall
                Firm: McKinsey & Company, Paris office
                Date: 14/12/2020

                Q1. Over the last twelve months, have you worked for a company whose interests may be affected by the order? [ ] Yes [X] No
                Q2. Do you currently hold an engagement for a company in the health sector? [ ] Yes [X] No
                Q3. Interests of a close relative: spouse employed by Froidis Group as regional director

                I certify that this declaration is accurate and complete.
              """),
          ], tags=["declaration"]),

        D("D07", "2020-12-15", "declarations", "consultant_declaration",
          "Declaration of interests — Inès Haddad", "McKinsey & Company, Paris office", [
              _p("""
                DECLARATION OF INTERESTS
                Consultant assigned to order DGS-2020-VAC-04

                Declarant: Inès Haddad
                Firm: McKinsey & Company, Paris office
                Date: 15/12/2020

                Q1. Over the last twelve months, have you worked for a company whose interests may be affected by the order? [ ] Yes [X] No
                Q2. Do you currently hold an engagement for a company in the health sector? [ ] Yes [X] No
                Q3. Interests of a close relative: none

                Previous activity: Medilab SA — Analyst — 01/2013 to 06/2015

                I certify that this declaration is accurate and complete.
              """),
          ], tags=["declaration"]),

        D("D08", "2020-12-22", "procurement", "purchase_order",
          "Purchase order BC-2020-117", "Ministry of Solidarity and Health", [
              _p("""
                PURCHASE ORDER BC-2020-117
                Under framework agreement DITP-2018-AC01, Lot 1

                Holder: McKinsey & Company Inc. France
                Object: Support for the logistics strategy of the COVID-19 vaccination campaign (specifications DGS-2020-VAC-04)
                Period: 04/01/2021 to 30/06/2021
                Amount: EUR 3,960,000 excl. VAT

                Signed for the Minister, by delegation: Mathilde Rousseau, Deputy Director, Vaccine and Health Products Policy
                Date: 22/12/2020
              """),
          ], tags=["contract"]),

        D("D09", "2020-12-23", "procurement", "staffing_plan",
          "Annex 1 to BC-2020-117 — team assigned", "McKinsey & Company, Paris office", [
              _p("""
                ANNEX 1 TO PURCHASE ORDER BC-2020-117 — TEAM
                Engagement: BC-2020-117 · Client: Ministry of Solidarity and Health · Sector: public — health
                Date: 23/12/2020

                Raphaël Dumont — Senior partner — 10 % — 04/01/2021 to 30/06/2021
                Julien Marchetti — Partner, engagement lead — 30 % — 04/01/2021 to 30/06/2021
                Thomas Le Gall — Engagement manager — 100 % — 04/01/2021 to 30/06/2021
                Clara Vasseur — Senior associate — 50 % — 04/01/2021 to 30/06/2021
                Inès Haddad — Consultant — 100 % — 04/01/2021 to 30/06/2021
                Hugo Ferreira — Consultant — 100 % — 04/01/2021 to 30/06/2021
                Léa Martin — Business analyst — 100 % — 04/01/2021 to 30/06/2021
                Nadia Benali — Business analyst — 100 % — 04/01/2021 to 30/06/2021
                Paul Girard — Supply-chain specialist — 50 % — 04/01/2021 to 30/06/2021
              """),
          ], tags=["staffing"]),

        D("D10", "2021-01-19", "decisions", "deliverable",
          "Deliverable L2 — dose allocation scenarios", "McKinsey & Company, Paris office", [
              _p("""
                DELIVERABLE L2 — DOSE ALLOCATION SCENARIOS, Q1–Q2 2021
                Order BC-2020-117
                Prepared by: Clara Vasseur, Thomas Le Gall
                Reviewed by: Julien Marchetti
                Date: 19/01/2021

                Scenario A — pro rata of the volumes contracted at EU level.
                Scenario B (recommended) — front-load deliveries from Vaxellis SA in February–March 2021 and secure an additional regional allocation, on the basis of the delivery schedule presented by the manufacturer.
                Scenario C — prioritise the supplier with the shortest cold-chain constraints.

                Recommendation: Scenario B.
              """),
          ], tags=["deliverable"]),

        D("D11", "2021-01-26", "decisions", "decision_memo",
          "Decision memo — allocation scenario and cold-chain provider", "Directorate General for Health", [
              _p("""
                MEMO — DECISION OF THE DIRECTOR GENERAL FOR HEALTH
                Order BC-2020-117
                Date: 26/01/2021

                Allocation scenario retained: Scenario B of deliverable L2.
                Selected provider: LogiFroid SAS, on the basis of deliverable L3 prepared by Thomas Le Gall and Paul Girard.

                Prepared for signature by: Mathilde Rousseau, Deputy Director, Vaccine and Health Products Policy
              """),
          ], tags=["decision"]),

        D("D12", "2021-02-01", "private", "registry_extract",
          "Company registry extract — LogiFroid SAS", "Trade and companies register", [
              _p("""
                COMPANY REGISTRY EXTRACT
                Company: LogiFroid SAS
                Activity: temperature-controlled logistics
                Date: 01/02/2021

                Sole shareholder: Froidis Group (100 %)
                Chair: Froidis Group, represented by its chief executive
              """),
          ], tags=["ownership"]),

        D("D13", "2021-03-05", "private", "time_report",
          "Firm time report — February 2021", "McKinsey & Company, Paris office", [
              _p("""
                TIME REPORT — FEBRUARY 2021
                Paris office · staffing and time recording
                Date: 05/03/2021

                Engagement VX-2020-31 (Vaxellis SA)
                Clara Vasseur — 9 days — 01/02/2021 to 26/02/2021
                Julien Marchetti — 3 days — 01/02/2021 to 26/02/2021

                Engagement BC-2020-117 (Ministry of Solidarity and Health)
                Clara Vasseur — 10 days — 01/02/2021 to 26/02/2021
                Julien Marchetti — 6 days — 01/02/2021 to 26/02/2021
                Thomas Le Gall — 19 days — 01/02/2021 to 26/02/2021
              """),
          ], tags=["time report"]),

        D("D14", "2021-11-01", "scrutiny", "inquiry",
          "Senate inquiry committee on the influence of consulting firms", "French Senate", [
              _p("""
                SENATE INQUIRY COMMITTEE
                Influence of private consulting firms on public policy
                Date: 11/2021

                The Senate sets up an inquiry committee on the growing role of consulting firms in public policy.
                Its remit covers the cost of contracts, how they were awarded, the actual role of consultants in
                decisions, ethical rules and declarations of interests.
              """),
          ], provenance="public_record", precision="month", tags=["public record"]),

        D("D15", "2022-01-18", "scrutiny", "hearing",
          "Hearing under oath — Raphaël Dumont", "Senate inquiry committee", [
              _p("""
                SENATE INQUIRY COMMITTEE ON THE INFLUENCE OF CONSULTING FIRMS
                Hearing under oath
                Date: 18/01/2022
                Witness: Raphaël Dumont, Senior partner, McKinsey & Company Paris (sworn)

                The Rapporteur: Did every consultant assigned to the vaccination mission file a declaration of interests?
                Mr Raphaël Dumont: Yes. Every consultant assigned to the vaccination mission filed a declaration of interests before the start of the order.
                The Rapporteur: Did any of them work at the same time for a vaccine manufacturer?
                Mr Raphaël Dumont: No member of the team worked for a vaccine manufacturer during the mission.
              """),
          ], tags=["hearing", "under oath"]),

        D("D16", "2022-02-07", "scrutiny", "administration_answer",
          "Ministry answer to the committee questionnaire", "Directorate General for Health", [
              _p("""
                ANSWER TO THE QUESTIONNAIRE OF THE INQUIRY COMMITTEE
                Directorate General for Health
                Date: 07/02/2022

                Question 12 — Declarations of interests for order BC-2020-117.
                The Directorate holds 3 declarations of interests for order BC-2020-117: Clara Vasseur, Thomas Le Gall, Inès Haddad.
                No written consent under article 7.4 of the framework agreement was requested or issued for this order.
                No recusal record exists for the signatory of purchase order BC-2020-117.
              """),
          ], tags=["answer"]),

        D("D17", "2022-03-17", "scrutiny", "report",
          "Senate inquiry report", "French Senate", [
              _p("""
                REPORT OF THE INQUIRY COMMITTEE
                Date: 17/03/2022

                The committee reports that it obtained a very limited number of declarations of interests compared
                with the number of consultants involved in some missions, and questions whether the administration
                had the information needed to identify potential conflicts of interest.
              """),
          ], provenance="public_record", tags=["public record"]),
    ]
    short = {
        "D01": "Framework agreement",
        "D02": "Rousseau declaration",
        "D03": "Vaxellis engagement",
        "D04": "Specifications",
        "D05": "Vasseur declaration",
        "D06": "Le Gall declaration",
        "D07": "Haddad declaration",
        "D08": "Purchase order",
        "D09": "Team annex",
        "D10": "Allocation scenarios",
        "D11": "Decision memo",
        "D12": "LogiFroid registry",
        "D13": "Time report",
        "D14": "Senate inquiry",
        "D15": "Hearing under oath",
        "D16": "Ministry answer",
        "D17": "Senate report",
    }
    for doc in docs:
        doc.short = short[doc.id]
    context = [
        {"date": "2020-12-27", "label": "Vaccination campaign starts in France"},
    ]
    return CaseFile(
        id="mckinsey",
        title="Consulting firms & the State — McKinsey",
        subtitle="Vaccination logistics mission, 2018–2022 · synthetic reconstruction",
        jurisdiction="FR",
        docs=docs,
        context=context,
    )


CASES = {"mckinsey": mckinsey}
DEFAULT_CASE = "mckinsey"
