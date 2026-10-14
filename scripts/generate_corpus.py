"""Generates the ~60-document Sakkan corpus into data/docs/ (deterministic, no randomness).
Run:  python scripts/generate_corpus.py
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "docs"
OUT.mkdir(parents=True, exist_ok=True)

PPSM = {  # EGP per sqm of built-up area, by district and property type
    "New Cairo": {"apartment": 32000, "townhouse": 46000, "villa": 55000},
    "Sheikh Zayed": {"apartment": 30000, "townhouse": 42000, "villa": 50000},
    "6th of October": {"apartment": 24000, "townhouse": 30000, "villa": 36000},
    "Maadi": {"apartment": 45000, "townhouse": 60000, "villa": 80000},
    "North Coast": {"apartment": 38000, "townhouse": 50000, "villa": 60000},
}
FINISH_FACTOR = {"fully finished": 1.0, "semi-finished": 0.9, "core & shell": 0.8}
TRAILER = {
    "New Cairo": "The compound has quick access to the Ring Road and the American University area.",
    "Sheikh Zayed": "Residents enjoy easy access to the Cairo-Alexandria Desert Road and Zayed's malls.",
    "6th of October": "The location offers good value for families and quick access to the Wahat Road.",
    "Maadi": "The area is known for its tree-lined streets, embassies, and an established expat community.",
    "North Coast": "The project sits close to the beach and is popular for summer use and rental income.",
}
# (district, compound, type, beds, baths, sqm, finishing, feature)
SPECS = [
 ("New Cairo","Narges Gardens","apartment",3,2,140,"fully finished","a 10-minute walk to Nile International School and a shared garden"),
 ("New Cairo","Lotus Heights","apartment",3,2,150,"fully finished","a bright corner layout with a balcony facing the central park"),
 ("New Cairo","Mountain Park Residence","apartment",3,2,145,"fully finished","a 12-minute drive to Horizon American School and the 90th Street cafes"),
 ("New Cairo","Garden Hills","apartment",3,3,165,"fully finished","a spacious reception area and access to a private roof terrace"),
 ("New Cairo","Zahra Compound","apartment",2,2,110,"fully finished","a quiet courtyard setting that suits a young couple"),
 ("New Cairo","Lotus Heights","apartment",4,3,190,"fully finished","a large family layout with a separate maid's room"),
 ("New Cairo","Narges Gardens","apartment",3,2,155,"semi-finished","a ground-floor layout with a private garden"),
 ("New Cairo","Mountain Park Residence","villa",4,4,320,"fully finished","a standalone design with a swimming pool and a two-car garage"),
 ("New Cairo","Garden Hills","townhouse",3,3,230,"semi-finished","a corner plot with a landscaped front yard"),
 ("New Cairo","Zahra Compound","villa",5,5,420,"fully finished","a wide-street plot and a rooftop lounge"),
 ("Sheikh Zayed","Dunes Residence","apartment",3,2,150,"fully finished","a short walk to Zayed Plaza Mall"),
 ("Sheikh Zayed","Palm Court","apartment",2,2,105,"fully finished","a clubhouse and a heated pool shared by residents"),
 ("Sheikh Zayed","Orchard Park","apartment",3,2,170,"fully finished","a high floor with open views over the central lake"),
 ("Sheikh Zayed","Green Belt Villas","townhouse",4,3,250,"semi-finished","a private garden and a spacious family room"),
 ("Sheikh Zayed","Green Belt Villas","villa",4,4,350,"fully finished","a landscaped garden, a pool, and a separate guest suite"),
 ("Sheikh Zayed","Palm Court","villa",5,5,450,"fully finished","a double-height reception and a home cinema room"),
 ("Sheikh Zayed","Dunes Residence","apartment",3,2,160,"semi-finished","a quiet street and a garden-facing balcony"),
 ("Sheikh Zayed","Orchard Park","villa",4,3,300,"semi-finished","a corner plot close to the compound's sports club"),
 ("6th of October","Hadayek Residence","apartment",3,2,140,"fully finished","a ground-level garden and underground parking"),
 ("6th of October","Pyramids Heights","apartment",2,1,100,"fully finished","a compact layout with a low service fee"),
 ("6th of October","Sphinx Gardens","apartment",3,2,155,"semi-finished","a bright layout near the compound's playground area"),
 ("6th of October","Oasis Park","townhouse",3,3,220,"fully finished","a private entrance and a small garden"),
 ("6th of October","Hadayek Residence","villa",4,4,300,"fully finished","a swimming pool and a landscaped garden"),
 ("6th of October","Pyramids Heights","apartment",4,3,180,"fully finished","a family layout with a large balcony"),
 ("6th of October","Sphinx Gardens","apartment",3,2,130,"semi-finished","a budget-friendly layout close to the compound gate"),
 ("6th of October","Oasis Park","villa",5,4,380,"semi-finished","a large plot with room for a pool"),
 ("Maadi","Degla Residence","apartment",3,2,170,"fully finished","a renovated kitchen and a quiet tree-lined street"),
 ("Maadi","Sarayat Tower","apartment",2,2,120,"fully finished","a Nile-side location with 24-hour security"),
 ("Maadi","Road 9 Building","apartment",3,2,200,"fully finished","high ceilings and a large entrance reception"),
 ("Maadi","Zahraa Gardens","apartment",4,3,230,"fully finished","a spacious layout close to international schools"),
 ("Maadi","Degla Residence","villa",5,5,400,"fully finished","a private garden and a separate staff entrance"),
 ("Maadi","Road 9 Building","apartment",3,2,150,"semi-finished","a prime street location, steps from cafes"),
 ("Maadi","Sarayat Tower","apartment",2,1,95,"fully finished","a compact layout that suits a single professional"),
 ("North Coast","Blue Marina","apartment",2,2,100,"fully finished","a sea view and direct access to the marina"),
 ("North Coast","Sandy Bay","apartment",3,2,130,"fully finished","a large terrace and a short walk to the beach"),
 ("North Coast","Coral Heights","villa",4,4,300,"fully finished","a private pool and a rooftop terrace"),
 ("North Coast","Palm Shore","townhouse",3,3,200,"semi-finished","a garden and two parking spaces"),
 ("North Coast","Blue Marina","apartment",1,1,70,"fully finished","a studio-style layout that works well for rental"),
 ("North Coast","Sandy Bay","apartment",3,2,150,"fully finished","a first-row lagoon view"),
 ("North Coast","Coral Heights","villa",5,5,380,"fully finished","a beachfront location and a large entertaining terrace"),
]

def rnd50k(x): return int(round(x / 50000.0)) * 50000

for i, (dist, comp, typ, beds, baths, sqm, fin, feat) in enumerate(SPECS, 1):
    price = rnd50k(PPSM[dist][typ] * sqm * FINISH_FACTOR[fin])
    desc = (f"A {fin} {beds}-bedroom {typ} in {comp}, {dist}, with {sqm} sqm of built-up area. "
            f"The unit offers {feat}. {TRAILER[dist]}")
    (OUT / f"LST-{i:03d}.txt").write_text(
        f"ID: LST-{i:03d}\nDocType: listing\nTitle: {typ.title()} in {comp}, {dist}\nDistrict: {dist}\n"
        f"Compound: {comp}\nPropertyType: {typ}\nBedrooms: {beds}\nBathrooms: {baths}\nSizeSqm: {sqm}\n"
        f"PriceEGP: {price:,}\nFinishing: {fin}\nDescription: {desc}\n", encoding="utf-8")

CLIENTS = [
 ("Mr. Hassan Ibrahim","الأستاذ حسن إبراهيم","4,000,000 - 5,000,000","New Cairo",5,"International school within 15 minutes of home (two children, ages 7 and 10)","3 months","Arabic","Prefers apartments of 3 bedrooms in a gated compound."),
 ("Mrs. Nadia Magdy","السيدة نادية مجدي","15,000,000 - 20,000,000","Sheikh Zayed",4,"Not a priority","2 months","both","Looking for a standalone villa with a garden and a pool."),
 ("Eng. Omar Farouk","المهندس عمر فاروق","2,500,000 - 3,500,000","6th of October",3,"Nursery nearby","6 months","English","First-time buyer, interested in a mortgage."),
 ("Dr. Salma Adel","الدكتورة سلمى عادل","6,000,000 - 9,000,000","Maadi",2,"Not needed","4 months","both","Wants a quiet street and walking distance to cafes."),
 ("Mr. Karim Nasser","الأستاذ كريم ناصر","5,000,000 - 8,000,000","North Coast",4,"Not needed","1 month","both","Wants a summer home with a sea view and rental potential."),
 ("Mrs. Heba Fawzy","السيدة هبة فوزي","4,500,000 - 5,500,000","Sheikh Zayed",4,"Private school within 20 minutes","3 months","Arabic","Needs 3 bedrooms and a ground floor or elevator."),
 ("Mr. Tarek Zaki","الأستاذ طارق زكي","9,000,000 - 12,000,000","New Cairo",6,"International school required","5 months","English","Looking for a townhouse with at least 3 bedrooms."),
 ("Ms. Laila Mostafa","الآنسة ليلى مصطفى","3,500,000 - 5,000,000","Maadi",1,"Not needed","2 months","English","Single professional, wants a compact apartment close to work."),
]
for i, (n, ar, b, d, fam, sch, tl, lang, note) in enumerate(CLIENTS, 1):
    (OUT / f"CLT-{i:03d}.txt").write_text(
        f"ID: CLT-{i:03d}\nDocType: client_brief\nName: {n}\nArabicName: {ar}\nBudgetEGP: {b}\n"
        f"PreferredDistricts: {d}\nFamilySize: {fam}\nSchoolRequirement: {sch}\nTimeline: {tl}\n"
        f"Language: {lang}\n\nNotes: {note}\n", encoding="utf-8")

AREAS = [
 ("New Cairo","Fifth Settlement and surrounding compounds","35-50 minutes to Downtown outside rush hour, 25 minutes to Cairo Airport","Several international schools including Nile International School and Horizon American School","Large malls and the 90th Street cafe strip","about 33,000 EGP per sqm for apartments"),
 ("Sheikh Zayed","Zayed City and the Beverly Hills area","40-60 minutes to Downtown, direct access to the Desert Road","Established private and international schools within 15 minutes","Zayed Plaza Mall and several open-air shopping streets","about 31,000 EGP per sqm for apartments"),
 ("6th of October","October Gardens and the Wahat Road compounds","45-70 minutes to Downtown depending on the Mehwar road traffic","Good private schools; fewer international options","Several family malls and Hosary Square","about 24,000 EGP per sqm for apartments"),
 ("Maadi","Degla, Sarayat and the Road 9 area","20-35 minutes to Downtown by car or metro","Strong international school cluster and many nurseries","Maadi City Center and boutique shops on Road 9","about 45,000 EGP per sqm for apartments"),
 ("North Coast","Sidi Abdel Rahman to Ras El Hekma strip","3 to 4 hours drive from Cairo","Seasonal; no permanent international schools","Beach clubs, marina restaurants and seasonal malls","about 38,000 EGP per sqm for apartments"),
]
for i, (d, sub, commute, schools, malls, avg) in enumerate(AREAS, 1):
    (OUT / f"AREA-{i:03d}.txt").write_text(
        f"ID: AREA-{i:03d}\nDocType: neighbourhood_guide\nDistrict: {d}\n\n"
        f"Neighbourhood guide for {d} ({sub}).\nCommute: {commute}.\nSchools: {schools}.\n"
        f"Malls and lifestyle: {malls}.\nAverage price: {avg}.\n", encoding="utf-8")

BANKS = [("Delta National Bank",18.0,20,20,"Fixed rate for the full tenure. Salary transfer required."),
         ("Pyramid Housing Bank",17.5,15,30,"Lower rate but a higher minimum down payment. No early settlement fee after year 3."),
         ("Cairo Capital Bank",19.0,25,25,"Longest tenure available. Variable rate reviewed every 12 months.")]
for i, (b, r, t, dp, note) in enumerate(BANKS, 1):
    (OUT / f"MORT-{i:03d}.txt").write_text(
        f"ID: MORT-{i:03d}\nDocType: mortgage_sheet\nBank: {b}\nAnnualRatePct: {r}\nMaxTenureYears: {t}\n"
        f"MinDownPaymentPct: {dp}\n\nRate sheet for {b} (fictional). {note} "
        f"Maximum tenure {t} years, minimum down payment {dp} percent, indicative rate {r} percent per year.\n", encoding="utf-8")

SOPS = [
 ("Viewings","Every viewing must be booked through the viewing scheduler and confirmed in writing to the client. A broker must accompany the client at all times. Viewings are offered in 60-minute slots between 10:00 and 18:00. Cancellations need 24 hours notice."),
 ("Offers","Offers are never sent to a client without the senior broker's approval. Every offer must quote the listing ID and the current listed price. No discount may be promised in writing. Negotiation requests must be escalated to a senior broker."),
 ("Disclosures","Brokers must disclose the finishing status, any pending service fees, and any known legal or ownership issues before an offer is made. Mortgage figures shared with clients are indicative only and must be labelled as such."),
 ("Client communications","All client-facing messages (WhatsApp, email, viewing offers) require human review before sending. Use the client's preferred language, a respectful tone, and the proper honorific. Never share one client's data with another. Never invent listings, prices or availability."),
]
for i, (t, body) in enumerate(SOPS, 1):
    (OUT / f"SOP-{i:03d}.txt").write_text(
        f"ID: SOP-{i:03d}\nDocType: sop\nTitle: SOP - {t}\n\n{body}\n", encoding="utf-8")

print("files:", len(list(OUT.glob("*.txt"))))
