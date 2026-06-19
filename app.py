import os
import json
import re
import html

import requests
from flask import (
    Flask, render_template, request, jsonify
)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

EXCAVATIONS = [
    {
        "id": "pompeii",
        "title": "Pompeii",
        "lat": 40.7497,
        "lng": 14.4856,
        "description": "Roman city buried by Vesuvius in 79 CE. Large-scale excavations begun in 1748 under King Charles III of Bourbon.",
        "period": "Roman (79 CE)",
        "startYear": 1748,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["city", "roman", "volcanic"],
        "era": "ancient",
    },
    {
        "id": "herculaneum",
        "title": "Herculaneum",
        "lat": 40.8058,
        "lng": 14.3472,
        "description": "Wealthier sister city of Pompeii, preserved by pyroclastic flow. Excavations began in 1738 with tunneling; modern excavations ongoing.",
        "period": "Roman (79 CE)",
        "startYear": 1738,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["city", "roman", "volcanic"],
        "era": "ancient",
    },
    {
        "id": "ostia-antica",
        "title": "Ostia Antica",
        "lat": 41.7527,
        "lng": 12.2914,
        "description": "Port of ancient Rome. Systematic excavations began in the 19th century; approximately 2/3 of the city uncovered.",
        "period": "Roman (4th c. BCE - 4th c. CE)",
        "startYear": 1855,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["port", "city", "roman"],
        "era": "ancient",
    },
    {
        "id": "acropolis",
        "title": "Athens Acropolis",
        "lat": 37.9714,
        "lng": 23.7257,
        "description": "Sacred citadel of Athens. Major excavations by the Greek Archaeological Society from 1834 onward; ongoing restoration and conservation.",
        "period": "Mycenaean to Classical (1600 BCE - 5th c. CE)",
        "startYear": 1834,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["acropolis", "temple", "greek"],
        "era": "ancient",
    },
    {
        "id": "knossos",
        "title": "Knossos",
        "lat": 35.2980,
        "lng": 25.1632,
        "description": "Minoan palace complex on Crete. First excavated by Minos Kalokairinos in 1878, then famously by Arthur Evans from 1900.",
        "period": "Minoan (1900-1370 BCE)",
        "startYear": 1878,
        "endYear": 1931,
        "ongoing": False,
        "featureTypes": ["palace", "minoan", "bronze age"],
        "era": "ancient",
    },
    {
        "id": "troy",
        "title": "Troy",
        "lat": 39.9575,
        "lng": 26.2383,
        "description": "Legendary city of the Trojan War. Excavated by Heinrich Schliemann (1870s), later by Dörpfeld, Blegen, and Korfmann.",
        "period": "Bronze Age (3000-1200 BCE)",
        "startYear": 1870,
        "endYear": 2012,
        "ongoing": False,
        "featureTypes": ["city", "bronze age", "fortress"],
        "era": "ancient",
    },
    {
        "id": "delphi",
        "title": "Delphi",
        "lat": 38.4824,
        "lng": 22.5013,
        "description": "Sanctuary of Apollo and home of the Oracle. Excavated by the French School at Athens from 1892.",
        "period": "Archaic to Roman (8th c. BCE - 4th c. CE)",
        "startYear": 1892,
        "endYear": 1903,
        "ongoing": False,
        "featureTypes": ["sanctuary", "oracle", "temple", "greek"],
        "era": "ancient",
    },
    {
        "id": "olympia",
        "title": "Olympia",
        "lat": 37.6387,
        "lng": 21.6283,
        "description": "Sanctuary of Zeus and birthplace of the Olympic Games. Excavated by German archaeologists from 1875.",
        "period": "Archaic to Roman (8th c. BCE - 4th c. CE)",
        "startYear": 1875,
        "endYear": 1881,
        "ongoing": False,
        "featureTypes": ["sanctuary", "sports", "temple", "greek"],
        "era": "ancient",
    },
    {
        "id": "ephesus",
        "title": "Ephesus",
        "lat": 37.9392,
        "lng": 27.3414,
        "description": "Major Ionian Greek city and Roman provincial capital. Excavations by Austrian Archaeological Institute since 1895.",
        "period": "Greek to Roman (10th c. BCE - 7th c. CE)",
        "startYear": 1895,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["city", "temple", "roman", "greek"],
        "era": "ancient",
    },
    {
        "id": "paestum",
        "title": "Paestum",
        "lat": 40.4196,
        "lng": 15.0055,
        "description": "Magna Graecia city with three stunning Greek temples. Excavations from the 18th century onward.",
        "period": "Greek to Roman (6th - 3rd c. BCE)",
        "startYear": 1746,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["city", "temple", "greek"],
        "era": "ancient",
    },
    {
        "id": "carthage",
        "title": "Carthage",
        "lat": 36.8529,
        "lng": 10.3230,
        "description": "Phoenician and Roman city in North Africa. Excavations by UNESCO from 1972 as part of the international salvage campaign.",
        "period": "Phoenician to Roman (8th c. BCE - 7th c. CE)",
        "startYear": 1830,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["city", "port", "phoenician", "roman"],
        "era": "ancient",
    },
    {
        "id": "palmyra",
        "title": "Palmyra",
        "lat": 34.5505,
        "lng": 38.2714,
        "description": "Oasis city and caravan hub in Syria. Excavated by various missions; severely damaged in 2015-2017 conflict.",
        "period": "Roman to Byzantine (1st - 7th c. CE)",
        "startYear": 1900,
        "endYear": None,
        "ongoing": False,
        "featureTypes": ["city", "caravan", "roman"],
        "era": "ancient",
    },
    {
        "id": "leptis-magna",
        "title": "Leptis Magna",
        "lat": 32.6330,
        "lng": 14.2910,
        "description": "Best-preserved Roman city in Africa, birthplace of Emperor Septimius Severus. Excavations from 1912.",
        "period": "Roman (1st - 4th c. CE)",
        "startYear": 1912,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["city", "roman", "port"],
        "era": "ancient",
    },
    {
        "id": "mycenae",
        "title": "Mycenae",
        "lat": 37.7310,
        "lng": 22.7564,
        "description": "Citadel of the Mycenaean civilization, home of Agamemnon. Excavated by Schliemann (1876) and subsequent Greek missions.",
        "period": "Mycenaean (1600-1100 BCE)",
        "startYear": 1841,
        "endYear": 1969,
        "ongoing": False,
        "featureTypes": ["citadel", "bronze age", "fortress"],
        "era": "ancient",
    },
    {
        "id": "hadrians-wall",
        "title": "Hadrian's Wall",
        "lat": 55.0069,
        "lng": -2.3150,
        "description": "Roman defensive wall across Britain. Excavations ongoing since the 19th century; UNESCO World Heritage Site.",
        "period": "Roman (122-410 CE)",
        "startYear": 1848,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["wall", "fort", "roman"],
        "era": "ancient",
    },
    {
        "id": "pompei-new",
        "title": "Regio V (New Pompeii Excavations)",
        "lat": 40.7515,
        "lng": 14.4890,
        "description": "The Great Pompeii Project — large-scale excavations of previously unexcavated Regio V area, begun in 2018 revealing dramatic new finds.",
        "period": "Roman (79 CE)",
        "startYear": 2018,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["city", "roman", "volcanic", "new"],
        "era": "modern",
    },
    {
        "id": "santorini-akrotiri",
        "title": "Akrotiri (Thera)",
        "lat": 36.3525,
        "lng": 25.3975,
        "description": "Minoan Bronze Age settlement buried by the Theran eruption. Excavations by Spyridon Marinatos from 1967.",
        "period": "Minoan (17th c. BCE)",
        "startYear": 1967,
        "endYear": 1974,
        "ongoing": False,
        "featureTypes": ["city", "minoan", "volcanic", "bronze age"],
        "era": "ancient",
    },
    {
        "id": "gobekli-tepe",
        "title": "Göbekli Tepe (Neolithic context)",
        "lat": 37.2231,
        "lng": 38.9225,
        "description": "Neolithic temple complex predating Greco-Roman era but contextually significant. Excavated by Klaus Schmidt from 1995.",
        "period": "Neolithic (9600-8000 BCE)",
        "startYear": 1995,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["temple", "neolithic", "megalithic"],
        "era": "prehistoric",
    },
    {
        "id": "corinth",
        "title": "Corinth",
        "lat": 37.9056,
        "lng": 22.8797,
        "description": "Major Greek and Roman city. Excavated by the American School of Classical Studies from 1896.",
        "period": "Greek to Roman (8th c. BCE - 6th c. CE)",
        "startYear": 1896,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["city", "temple", "greek", "roman"],
        "era": "ancient",
    },
    {
        "id": "vindolanda",
        "title": "Vindolanda",
        "lat": 54.9913,
        "lng": -2.3591,
        "description": "Roman auxiliary fort in Britain, famous for the Vindolanda writing tablets. Excavated annually since 1970.",
        "period": "Roman (85-410 CE)",
        "startYear": 1970,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["fort", "roman", "military"],
        "era": "ancient",
    },
    {
        "id": "stobi",
        "title": "Stobi",
        "lat": 41.5512,
        "lng": 21.9731,
        "description": "Major city in Macedonia (modern North Macedonia). Excavated by Yugoslav and later Macedonian and US teams from 1924.",
        "period": "Hellenistic to Roman (3rd c. BCE - 6th c. CE)",
        "startYear": 1924,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["city", "roman", "greek"],
        "era": "ancient",
    },
    {
        "id": "nimes",
        "title": "Nemausus (Nîmes)",
        "lat": 43.8366,
        "lng": 4.3598,
        "description": "Roman city with the best-preserved amphitheater and Maison Carrée temple. Excavations and restoration ongoing.",
        "period": "Roman (1st c. BCE - 4th c. CE)",
        "startYear": 1820,
        "endYear": None,
        "ongoing": True,
        "featureTypes": ["city", "temple", "amphitheater", "roman"],
        "era": "ancient",
    },
]

ERA_ORDER = ["prehistoric", "ancient", "medieval", "modern"]
ERA_LABELS = {
    "prehistoric": "Prehistoric",
    "ancient": "Ancient",
    "medieval": "Medieval",
    "modern": "Modern",
}

YEAR_MIN = min(e["startYear"] for e in EXCAVATIONS) if EXCAVATIONS else 1700
YEAR_MAX = max((e["endYear"] or 2026) for e in EXCAVATIONS)

# ---------------------------------------------------------------------------
# CLASSICAL TEXT RECOGNITION
# ---------------------------------------------------------------------------
PHRASE_LIBRARY = [
    {
        "text": "arma virumque cano",
        "work": "Aeneid",
        "author": "Virgil",
        "book": 1,
        "line": 1,
        "description": "Opening of Virgil's epic; 'I sing of arms and the man'.",
        "translations": {
            "Dryden (1697)": "Arms, and the man I sing...",
            "Fagles (2006)": "I sing of warfare and a man at war...",
            "Fairclough (1916)": "I sing of arms and the man, who first from the coasts of Troy...",
        },
    },
    {
        "text": "ἄνδρα μοι ἔννεπε μοῦσα πολύτροπον",
        "work": "Odyssey",
        "author": "Homer",
        "book": 1,
        "line": 1,
        "description": "Opening of Homer's Odyssey; 'Tell me, Muse, of the man of many ways'.",
        "translations": {
            "Murray (1919)": "Tell me, O Muse, of the man of many devices...",
            "Fagles (1996)": "Sing to me of the man, Muse, the man of twists and turns...",
            "Lattimore (1965)": "Tell me, Muse, of the man of many ways...",
        },
    },
    {
        "text": "gallia est omnis divisa in partes tres",
        "work": "Commentarii de Bello Gallico",
        "author": "Julius Caesar",
        "book": 1,
        "section": 1,
        "line": 1,
        "description": "Opening of Caesar's Gallic Wars; 'All Gaul is divided into three parts'.",
        "translations": {
            "McDevitte & Bohn (1869)": "All Gaul is divided into three parts...",
            "Edwards (1917)": "The whole of Gaul is divided into three parts...",
            "Hammond (1996)": "Gaul as a whole is divided into three parts...",
        },
    },
    {
        "text": "ἡ μὲν γνώμη τῶν ἀνθρώπων πρὶν ἢ παθεῖν",
        "work": "Histories",
        "author": "Herodotus",
        "book": 1,
        "section": 5,
        "description": "Reflection on human fortune from Herodotus' Histories.",
        "translations": {
            "Godley (1920)": "Human prosperity never continues in one stay...",
            "Rawlinson (1858)": "Thus it is that men's fortunes never remain fixed...",
            "Waterfield (1998)": "Human happiness never remains long in the same place...",
        },
    },
]

def normalize_text(txt):
    txt = html.unescape(txt)
    txt = re.sub(r"[^a-zA-Zα-ωΑ-Ωάέήίόύώϊϋᾶῆῖῦῶἀἁἂἃἄἅἆἐἑἒἓἔἕἠἡἢἣἤἥἦἧἰἱἲἳἴἵἶἷὀὁὂὃὄὅὐὑὒὓὔὕὖὗὠὡὢὣὤὥὦὧὰὲὴὶὸὺὼάέήίόύώᾳᾴᾷῃῄῇῳῴῷ]", " ", txt)
    return re.sub(r"\s+", " ", txt).strip().lower()

def find_text_match(input_text):
    normalized = normalize_text(input_text)
    best = None
    best_score = 0
    for entry in PHRASE_LIBRARY:
        phrase_norm = normalize_text(entry["text"])
        if phrase_norm in normalized:
            score = len(phrase_norm) / len(normalized) if normalized else 0
            if score > best_score:
                best_score = score
                best = entry
    return best

# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/excavations")
def api_excavations():
    era = request.args.get("era", "")
    status = request.args.get("status", "")
    results = list(EXCAVATIONS)
    if era and era in ERA_ORDER:
        results = [e for e in results if e.get("era") == era]
    if status == "ongoing":
        results = [e for e in results if e.get("ongoing")]
    elif status == "completed":
        results = [e for e in results if not e.get("ongoing")]
    return jsonify({
        "sites": results,
        "yearMin": YEAR_MIN,
        "yearMax": YEAR_MAX,
    })

@app.route("/api/identify", methods=["POST"])
def api_identify():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400
    match = find_text_match(text)
    if not match:
        return jsonify({"matched": False, "message": "No classical text match found."})
    return jsonify({"matched": True, **match})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
