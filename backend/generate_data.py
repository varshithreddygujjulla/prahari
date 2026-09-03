"""
generate_data.py — Creates all synthetic datasets for the SIH demo.
Run once:  python backend/generate_data.py
Outputs go to ./data/

THE HIDDEN STORY (what the graph will reveal in the demo):
  - KINGPIN: Vikram "VR" Rathore (never appears in any FIR directly!)
  - GANG A (Delhi drugs): led by Ramesh Yadav — 6 street dealers under him
  - GANG B (Mumbai smuggling): led by Salim Qureshi — 5 members
  - HIDDEN LINK 1: Ramesh & Salim shared a cell block in Tihar (2022)
  - HIDDEN LINK 2: burner number 9990001111 talks to BOTH gang leaders
    and to Vikram Rathore — he is the broker
  - MONEY TRAIL: street dealers -> Ramesh -> shell acct "OM TRADERS"
    -> Vikram Rathore's account
  - ANOMALY: call spike between the gangs 48h before the Mundra seizure
"""
import csv, os, random, json
from datetime import datetime, timedelta

random.seed(26189)  # problem statement ID -> reproducible data
BASE = os.path.join(os.path.dirname(__file__), "..", "data")
FIRS = os.path.join(BASE, "firs")
os.makedirs(FIRS, exist_ok=True)

# ---------------------------------------------------------------- people
KINGPIN = {"name": "Vikram Rathore", "phone": "9811000001", "acct": "ACC9001"}
BROKER_BURNER = "9990001111"   # the mystery number

GANG_A = {  # Delhi drug network
    "leader": {"name": "Ramesh Yadav", "phone": "9811000002", "acct": "ACC9002"},
    "members": [
        {"name": "Sunil Kumar",   "phone": "9811000003", "acct": "ACC9003"},
        {"name": "Deepak Singh",  "phone": "9811000004", "acct": "ACC9004"},
        {"name": "Ajay Verma",    "phone": "9811000005", "acct": "ACC9005"},
        {"name": "Mohit Sharma",  "phone": "9811000006", "acct": "ACC9006"},
        {"name": "Rakesh Gupta",  "phone": "9811000007", "acct": "ACC9007"},
        {"name": "Pawan Mishra",  "phone": "9811000008", "acct": "ACC9008"},
    ],
}
GANG_B = {  # Mumbai smuggling network
    "leader": {"name": "Salim Qureshi", "phone": "9822000001", "acct": "ACC8001"},
    "members": [
        {"name": "Irfan Shaikh",  "phone": "9822000002", "acct": "ACC8002"},
        {"name": "Anwar Khan",    "phone": "9822000003", "acct": "ACC8003"},
        {"name": "Javed Ansari",  "phone": "9822000004", "acct": "ACC8004"},
        {"name": "Faisal Sayyed", "phone": "9822000005", "acct": "ACC8005"},
    ],
}
SHELL = {"name": "OM TRADERS PVT LTD", "acct": "ACC7777"}

# innocent noise population (makes the graph realistic)
NOISE = [{"name": n, "phone": f"98{random.randint(10000000,99999999)}",
          "acct": f"ACC{1000+i}"} for i, n in enumerate([
    "Amit Patel", "Suresh Nair", "Kiran Rao", "Vijay Iyer", "Nitin Joshi",
    "Sanjay Das", "Manoj Pillai", "Arun Reddy", "Dinesh Menon", "Rohit Bose",
    "Prakash Sen", "Gopal Roy", "Harish Shetty", "Naveen Kaul", "Tarun Bakshi",
])]

ALL_KNOWN = [KINGPIN, GANG_A["leader"], *GANG_A["members"],
             GANG_B["leader"], *GANG_B["members"], *NOISE]

# ---------------------------------------------------------------- 1. FIRs
FIR_TEMPLATES = [
    ("Delhi", "NDPS Act 8/20", "Accused {a} was apprehended near {loc} in possession "
     "of 250g contraband. During interrogation accused named associate {b}. "
     "Mobile number {ph} recovered from accused."),
    ("Mumbai", "Customs Act 135", "Container inspection at {loc} revealed undeclared "
     "goods. Accused {a} listed as consignee. Co-accused {b} absconding. "
     "Contact number {ph} found on shipping documents."),
    ("Delhi", "IPC 420", "Complainant reported fraud by {a} operating near {loc}. "
     "Investigation links accused to {b}. Number {ph} used for transactions."),
]
LOCS_DELHI = ["Seelampur", "Jahangirpuri", "Okhla Mandi", "Karol Bagh", "Azadpur"]
LOCS_MUM = ["Mundra Port", "JNPT Nhava Sheva", "Dongri", "Kurla", "Bhiwandi"]

def write_fir(idx, city, section, text, date):
    with open(os.path.join(FIRS, f"FIR_{idx:03d}.txt"), "w") as f:
        f.write(f"FIRST INFORMATION REPORT\nFIR No: {idx:03d}/2026\n"
                f"Police Station: {city}\nDate: {date}\nSections: {section}\n"
                f"NARRATIVE:\n{text}\n")

fir_idx = 1
start = datetime(2026, 1, 5)
# Gang A FIRs — members name each other, leader named twice, kingpin NEVER named
pairs_a = [(GANG_A["members"][i], GANG_A["members"][(i+1) % 6]) for i in range(6)]
pairs_a += [(GANG_A["members"][0], GANG_A["leader"]), (GANG_A["members"][3], GANG_A["leader"])]
for a, b in pairs_a:
    city, sec, tpl = FIR_TEMPLATES[0]
    write_fir(fir_idx, city, sec, tpl.format(a=a["name"], b=b["name"],
              loc=random.choice(LOCS_DELHI), ph=a["phone"]),
              (start + timedelta(days=fir_idx*3)).strftime("%d-%m-%Y"))
    fir_idx += 1
# Gang B FIRs
pairs_b = [(GANG_B["members"][i], GANG_B["members"][(i+1) % 4]) for i in range(4)]
pairs_b += [(GANG_B["members"][1], GANG_B["leader"])]
for a, b in pairs_b:
    city, sec, tpl = FIR_TEMPLATES[1]
    write_fir(fir_idx, city, sec, tpl.format(a=a["name"], b=b["name"],
              loc=random.choice(LOCS_MUM), ph=a["phone"]),
              (start + timedelta(days=fir_idx*3)).strftime("%d-%m-%Y"))
    fir_idx += 1
# noise FIRs (unconnected)
for i in range(8):
    a, b = random.sample(NOISE, 2)
    city, sec, tpl = FIR_TEMPLATES[2]
    write_fir(fir_idx, city, sec, tpl.format(a=a["name"], b=b["name"],
              loc=random.choice(LOCS_DELHI+LOCS_MUM), ph=a["phone"]),
              (start + timedelta(days=fir_idx*3)).strftime("%d-%m-%Y"))
    fir_idx += 1

# ---------------------------------------------------------------- 2. CDR
cdr_rows = []
def calls(p1, p2, n, day0, spike=False):
    for i in range(n):
        t = datetime(2026, 3, day0) + timedelta(hours=random.randint(0, 200 if not spike else 40))
        cdr_rows.append([p1, p2, t.strftime("%Y-%m-%d %H:%M"),
                         random.randint(20, 600), f"TWR{random.randint(100,999)}"])

# intra-gang chatter
for m in GANG_A["members"]:
    calls(m["phone"], GANG_A["leader"]["phone"], random.randint(4, 8), 1)
for m in GANG_B["members"]:
    calls(m["phone"], GANG_B["leader"]["phone"], random.randint(4, 8), 1)
# THE BROKER: burner talks to both leaders AND the kingpin
calls(BROKER_BURNER, GANG_A["leader"]["phone"], 6, 5)
calls(BROKER_BURNER, GANG_B["leader"]["phone"], 6, 5)
calls(BROKER_BURNER, KINGPIN["phone"], 9, 5)
# ANOMALY: spike 48h before 20-Mar Mundra seizure
calls(GANG_A["leader"]["phone"], BROKER_BURNER, 11, 18, spike=True)
calls(BROKER_BURNER, GANG_B["leader"]["phone"], 13, 18, spike=True)
# noise calls — sparse ring so noise people don't form a dense fake gang
for i in range(len(NOISE)):
    a, b = NOISE[i], NOISE[(i + 1) % len(NOISE)]
    calls(a["phone"], b["phone"], 1, random.randint(1, 25))

with open(os.path.join(BASE, "cdr.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["caller", "receiver", "timestamp", "duration_sec", "tower_id"])
    w.writerows(sorted(cdr_rows, key=lambda r: r[2]))

# ---------------------------------------------------------------- 3. Bank
bank = []
def pay(src, dst, amt, d):
    bank.append([src, dst, amt, f"2026-03-{d:02d}"])
# dealers -> Ramesh
for m in GANG_A["members"]:
    pay(m["acct"], GANG_A["leader"]["acct"], random.randrange(40000, 90000, 5000),
        random.randint(2, 15))
# Ramesh -> shell -> KINGPIN  (the money trail)
pay(GANG_A["leader"]["acct"], SHELL["acct"], 350000, 16)
pay(GANG_A["leader"]["acct"], SHELL["acct"], 425000, 17)
pay(SHELL["acct"], KINGPIN["acct"], 700000, 18)
# Salim also pays the shell
pay(GANG_B["leader"]["acct"], SHELL["acct"], 510000, 17)
# noise
for _ in range(25):
    a, b = random.sample(NOISE, 2)
    pay(a["acct"], b["acct"], random.randrange(1000, 20000, 500), random.randint(1, 28))

with open(os.path.join(BASE, "bank.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["from_account", "to_account", "amount_inr", "date"])
    w.writerows(bank)

# ---------------------------------------------------------------- 4. Prison
with open(os.path.join(BASE, "prison.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["prisoner_name", "jail", "cell_block", "from_date", "to_date"])
    w.writerow(["Ramesh Yadav", "Tihar Jail", "Block-4", "2022-02-10", "2022-11-30"])
    w.writerow(["Salim Qureshi", "Tihar Jail", "Block-4", "2022-05-01", "2023-01-15"])  # OVERLAP!
    w.writerow(["Sunil Kumar", "Tihar Jail", "Block-2", "2023-03-01", "2023-06-01"])
    for n in random.sample(NOISE, 5):
        w.writerow([n["name"], random.choice(["Tihar Jail", "Arthur Road", "Yerwada"]),
                    f"Block-{random.randint(1,6)}", "2021-01-01", "2021-06-01"])

# ---------------------------------------------------------------- 5. Travel
with open(os.path.join(BASE, "travel.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["passenger_name", "from_city", "to_city", "date", "flight"])
    w.writerow(["Vikram Rathore", "Delhi", "Dubai", "2026-03-19", "EK511"])  # flees after payout
    w.writerow(["Salim Qureshi", "Mumbai", "Delhi", "2026-03-14", "6E204"])
    for n in random.sample(NOISE, 6):
        w.writerow([n["name"], random.choice(["Delhi","Mumbai","Chennai"]),
                    random.choice(["Goa","Kolkata","Pune"]),
                    f"2026-03-{random.randint(1,28):02d}", f"AI{random.randint(100,999)}"])

# ---------------------------------------------------------------- 6. Vehicles
with open(os.path.join(BASE, "vehicles.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["vehicle_number", "owner_name", "vehicle_type"])
    w.writerow(["DL01AB4455", "Ramesh Yadav", "Tata Ace (cargo)"])
    w.writerow(["MH02XY9911", "Salim Qureshi", "Eicher truck"])
    w.writerow(["DL08VR0001", "Vikram Rathore", "Toyota Fortuner"])
    for n in random.sample(NOISE, 6):
        w.writerow([f"{random.choice(['DL','MH','KA'])}{random.randint(10,99)}"
                    f"ZZ{random.randint(1000,9999)}", n["name"], "Hatchback"])

# ---------------------------------------------------------------- 7. phone directory (aids entity resolution)
with open(os.path.join(BASE, "phone_directory.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["phone", "registered_name"])
    for p in ALL_KNOWN:
        w.writerow([p["phone"], p["name"]])
    # burner is UNREGISTERED — deliberately absent

with open(os.path.join(BASE, "accounts.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["account", "holder_name"])
    for p in ALL_KNOWN:
        w.writerow([p["acct"], p["name"]])
    w.writerow([SHELL["acct"], SHELL["name"]])

print(f"Done. {fir_idx-1} FIRs, {len(cdr_rows)} calls, {len(bank)} transactions written to /data")
