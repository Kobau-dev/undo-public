"""Paris East sector portfolio (fictional data)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

COMPANY = "Delmas Laboratories"
APP_NAME = "Sillage CRM"
USER_NAME = "Camille Fournier"
USER_LOGIN = "camille.fournier@labo-delmas.fr"
USER_ROLE = "Medical rep · Paris East sector"


@dataclass(frozen=True)
class Product:
    name: str
    detail: str


PRODUCTS = [
    Product("Tensiora 5/10 mg", "high blood pressure"),
    Product("Glycalm XR 1000 mg", "type 2 diabetes"),
    Product("Lipeva 20 mg", "dyslipidemia"),
    Product("Cardiolis 75 mg", "cardiovascular prevention"),
    Product("Respilib 92/22 µg", "COPD"),
]

VISIT_TYPES = ["In person", "Video call", "Phone", "Staff / department meeting"]
OBJECTIVES = [
    "Product presentation",
    "Prescription follow-up",
    "Clinical study feedback",
    "New indication launch",
    "Invitation to a scientific evening",
    "Hospital formulary listing",
]
DURATIONS = ["10 min", "15 min", "20 min", "30 min", "45 min", "1 h", "1 h 30"]


@dataclass
class Account:
    id: int
    name: str
    kind: str
    address: str
    city: str
    phone: str
    segment: str
    potential: str
    owner: str = USER_NAME


@dataclass
class Visit:
    days_ago: int
    kind: str
    objective: str
    products: list[str]
    summary: str
    author: str = USER_NAME

    @property
    def day(self) -> date:
        return date.today() - timedelta(days=self.days_ago)


@dataclass
class Contact:
    id: int
    civility: str
    first: str
    last: str
    specialty: str
    account_id: int
    phone: str
    email: str
    rpps: str
    segment: str
    availability: str
    visits: list[Visit] = field(default_factory=list)
    next_visit_in: int | None = None

    @property
    def name(self) -> str:
        return f"{self.civility} {self.first} {self.last}"

    @property
    def initials(self) -> str:
        return (self.first[:1] + self.last[:1]).upper()

    @property
    def last_visit(self) -> date | None:
        return max((v.day for v in self.visits), default=None)


@dataclass
class Opportunity:
    title: str
    account_id: int
    stage: str
    amount: int
    close_in_days: int
    probability: int


ACCOUNTS = [
    Account(1, "Les Lilas Medical Practice", "Group practice", "12 rue de Paris", "93260 Les Lilas", "01 43 62 18 40", "A", "High"),
    Account(2, "Belleville Health Center", "Health center", "48 rue de Belleville", "75020 Paris", "01 46 36 72 15", "A", "High"),
    Account(3, "Nation Cardiology Practice", "Specialist practice", "5 place de la Nation", "75012 Paris", "01 43 43 29 08", "A", "Very high"),
    Account(4, "Coteaux Clinic", "Acute care clinic", "21 boulevard de Strasbourg", "94130 Nogent-sur-Marne", "01 48 71 50 00", "A", "Very high"),
    Account(5, "Vincennes-Est Health Practice", "Multi-professional practice", "3 avenue de la République", "94300 Vincennes", "01 43 28 11 67", "B", "Medium"),
    Account(6, "Mairie Pharmacy", "Pharmacy", "1 place Jean-Jaurès", "93100 Montreuil", "01 48 58 20 33", "B", "Medium"),
    Account(7, "Marne-Rives Private Hospital", "Private hospital", "77 quai de la Marne", "94340 Joinville-le-Pont", "01 45 11 80 00", "A", "Very high"),
    Account(8, "Gambetta Pharmacy", "Pharmacy", "14 avenue Gambetta", "75020 Paris", "01 43 66 41 92", "C", "Low"),
    Account(9, "Dr Benali's Practice", "Solo practice", "62 rue Sadi-Carnot", "93170 Bagnolet", "01 43 60 07 51", "B", "Medium"),
    Account(10, "République Medical Center", "Medical center", "9 rue du Faubourg-du-Temple", "75011 Paris", "01 48 05 66 20", "B", "High"),
    Account(11, "Daumesnil Endocrinology Practice", "Specialist practice", "180 avenue Daumesnil", "75012 Paris", "01 43 07 92 64", "A", "High"),
    Account(12, "Marché Pharmacy", "Pharmacy", "27 avenue du Général-de-Gaulle", "94160 Saint-Mandé", "01 43 28 54 19", "C", "Low"),
]

CONTACTS = [
    Contact(1, "Dr", "Hélène", "Marchand", "General practitioner", 1, "01 43 62 18 41", "h.marchand@cabinet-leslilas.fr", "10003427815", "Target A",
            "Sees reps on Tuesdays and Thursdays, 12:30–2 pm, by appointment", [
                Visit(23, "In person", "Prescription follow-up", ["Tensiora 5/10 mg"],
                      "Happy with tolerance in hypertensive patients over 65. Would like adherence data."),
                Visit(61, "In person", "Product presentation", ["Glycalm XR 1000 mg", "Lipeva 20 mg"],
                      "Interested in the extended-release form to limit digestive issues. Asked for the dosing sheet."),
                Visit(118, "Phone", "Invitation to a scientific evening", [],
                      "Invited to the hypertension evening on 14/06, confirmed attendance."),
            ], 2),
    Contact(2, "Dr", "Karim", "Benali", "General practitioner", 9, "01 43 60 07 51", "dr.benali@medecin-bagnolet.fr", "10101876342", "Target B",
            "Prefers visits late in the day, after 6 pm", [
                Visit(40, "In person", "Product presentation", ["Cardiolis 75 mg"], "Short on time, took the documentation. See again in January."),
            ], 9),
    Contact(3, "Dr", "Sophie", "Lemaire-Vidal", "Cardiologist", 3, "01 43 43 29 09", "s.lemaire-vidal@cardio-nation.fr", "10002981137", "Target A",
            "Practice meeting on Friday mornings, 8:30", [
                Visit(15, "Staff / department meeting", "Clinical study feedback", ["Tensiora 5/10 mg", "Cardiolis 75 mg"],
                      "Presented the 3-year results to 4 cardiologists. Questions about patients with kidney failure."),
                Visit(74, "Video call", "Prescription follow-up", ["Lipeva 20 mg"], "Nothing to report, prescriptions stable."),
            ], 5),
    Contact(4, "Dr", "Antoine", "Rousseau", "Endocrinologist", 11, "01 43 07 92 65", "a.rousseau@endoc-daumesnil.fr", "10003310964", "Target A",
            "By appointment only, through the front desk", [
                Visit(30, "In person", "New indication launch", ["Glycalm XR 1000 mg"],
                      "Keen on data in combination with SGLT2 inhibitors. Send the publication."),
            ], 12),
    Contact(5, "Ms", "Claire", "Dubreuil", "Head pharmacist", 6, "01 48 58 20 33", "pharmacie.mairie.montreuil@orange.fr", "10000774512", "Target B",
            "Drop-in possible Monday to Friday, 2–4 pm", [
                Visit(12, "In person", "Prescription follow-up", ["Tensiora 5/10 mg", "Glycalm XR 1000 mg"], "Stock fine. Reported two wholesaler shortages in October."),
            ], None),
    Contact(6, "Dr", "Julien", "Perrin", "Head of cardiology", 7, "01 45 11 80 42", "j.perrin@hp-marnerives.fr", "10002456890", "Target A",
            "Department meeting on Wednesdays at 1 pm", [
                Visit(9, "Staff / department meeting", "Hospital formulary listing", ["Cardiolis 75 mg"],
                      "Formulary file presented to the December committee. Waiting for the economic file."),
                Visit(52, "In person", "Product presentation", ["Tensiora 5/10 mg"], "First appointment, warm welcome."),
            ], 4),
    Contact(7, "Dr", "Nadia", "Haddad", "General practitioner", 5, "01 43 28 11 68", "n.haddad@msp-vincennes.fr", "10101233478", "Target A",
            "Sees reps on Monday afternoons", [
                Visit(19, "Video call", "Product presentation", ["Respilib 92/22 µg"], "Interested for COPD patients who smoke. Asked for a demonstration device."),
            ], 7),
    Contact(8, "Dr", "Pierre-Yves", "Le Goff", "General practitioner", 2, "01 46 36 72 18", "py.legoff@cds-belleville.fr", "10003896521", "Target B",
            "No visits during school holidays", [
                Visit(66, "In person", "Prescription follow-up", ["Lipeva 20 mg"], "Regular prescriber. Would like 90-day packs."),
            ], None),
    Contact(9, "M.", "Thomas", "Nguyen", "Deputy pharmacist", 8, "01 43 66 41 92", "contact@pharmacie-gambetta.fr", "10000912846", "Target C",
            "Mornings before 11 am", [], None),
    Contact(10, "Dr", "Isabelle", "Moreau", "Diabetologist", 4, "01 48 71 50 37", "i.moreau@clinique-coteaux.fr", "10002768413", "Target A",
            "Consultations in the morning, available from 1 pm", [
                Visit(27, "In person", "Clinical study feedback", ["Glycalm XR 1000 mg"],
                      "Discussed the digestive tolerance study. Wants a session for the patient education nurses."),
            ], 3),
    Contact(11, "Dr", "François", "Garnier", "Cardiologist", 4, "01 48 71 50 22", "f.garnier@clinique-coteaux.fr", "10002113895", "Target B",
            "By appointment only", [
                Visit(88, "In person", "Product presentation", ["Cardiolis 75 mg"], "Reserved, waiting for the ESC guidelines."),
            ], None),
    Contact(12, "Dr", "Amélie", "Chevalier", "General practitioner", 10, "01 48 05 66 24", "a.chevalier@cm-republique.fr", "10101654329", "Target B",
            "Tuesday morning", [
                Visit(35, "Phone", "Prescription follow-up", ["Tensiora 5/10 mg"], "Quick call, no particular questions."),
            ], 15),
    Contact(13, "Dr", "Mehdi", "Ouali", "General practitioner", 1, "01 43 62 18 43", "m.ouali@cabinet-leslilas.fr", "10003587260", "Target B",
            "Thursday afternoon", [
                Visit(44, "In person", "Product presentation", ["Respilib 92/22 µg"], "Asked for demonstration samples of the device."),
            ], None),
    Contact(14, "Ms", "Laure", "Besson", "Nurse manager", 7, "01 45 11 80 15", "l.besson@hp-marnerives.fr", "", "Target B",
            "Reachable by email", [], None),
]

OPPORTUNITIES = [
    Opportunity("Cardiolis formulary listing", 7, "Formulary committee file", 86000, 38, 60),
    Opportunity("Diabetes patient education training", 4, "Proposal sent", 12500, 21, 50),
    Opportunity("Tensiora listing — Coteaux Clinic", 4, "Qualification", 54000, 75, 30),
    Opportunity("Hypertension scientific evening — Paris 12th", 3, "Approved", 8200, 12, 90),
    Opportunity("COPD screening partnership", 5, "Negotiation", 15800, 30, 70),
    Opportunity("Direct pharmacy order — cardio range", 6, "Proposal sent", 4300, 9, 60),
    Opportunity("Multidisciplinary diabetes meeting", 2, "Qualification", 3600, 45, 20),
]

TODAY_AGENDA = [
    ("09:00", 6, "Hospital formulary listing"),
    ("11:30", 3, "Clinical study feedback"),
    ("13:00", 1, "Prescription follow-up"),
    ("15:30", 5, "Prescription follow-up"),
    ("17:00", 10, "Product presentation"),
]


def account(account_id: int) -> Account:
    return next(a for a in ACCOUNTS if a.id == account_id)


def contacts_of(account_id: int) -> list[Contact]:
    return [c for c in CONTACTS if c.account_id == account_id]


def find_contact(query: str) -> Contact | None:
    q = query.strip().lower()
    if not q:
        return None
    if q.isdigit():
        return next((c for c in CONTACTS if c.id == int(q)), None)
    return next((c for c in CONTACTS if q in c.name.lower()), None)


def euros(n: int) -> str:
    return f"{n:,}".replace(",", "\u202f") + " €"


def fr_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")
