import os
import json
import re
import html
import urllib.parse

import requests
from flask import (
    Flask, render_template, request, jsonify, session
)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

# ---------------------------------------------------------------------------
# PLEIADES / EXCAVATION DATA
# ---------------------------------------------------------------------------
PLEIADES_API = "https://pleiades.stoa.org/places/search"

def fetch_excavations(query="excavation", limit=200):
    params = {
        "q": query,
        "type": "site",
        "maxResults": limit,
        "format": "json",
    }
    try:
        r = requests.get(PLEIADES_API, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    features = []
    for place in data.get("features", []):
        props = place.get("properties", {})
        geom = place.get("geometry", {})
        coords = geom.get("coordinates") if geom and geom.get("type") == "Point" else None
        if not coords:
            continue
        features.append({
            "id": props.get("pid", ""),
            "title": props.get("title", "Unknown Site"),
            "description": props.get("description", ""),
            "lat": coords[1],
            "lng": coords[0],
            "uri": f"https://pleiades.stoa.org/places/{props.get('pid', '')}",
            "featureTypes": props.get("featureTypes", []),
        })
    return features

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
    q = request.args.get("q", "excavation")
    data = fetch_excavations(q)
    return jsonify(data)

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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
