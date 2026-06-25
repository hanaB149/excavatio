import os
import json
import re
import html
import logging
import threading
import base64
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from functools import wraps
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import requests
from flask import (
    Flask, render_template, request, jsonify, redirect, url_for, session
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# ---------------------------------------------------------------------------
# USER STORE — backed by build.io config vars (persists across restarts)
# Points/achievements stored in Flask session cookie (also persists)
# ---------------------------------------------------------------------------

_users_cache = None
_persist_lock = threading.Lock()


def _load_users():
    global _users_cache
    if _users_cache is not None:
        return _users_cache
    raw = os.environ.get("USER_STORE", "")
    if raw:
        try:
            _users_cache = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            _users_cache = []
    else:
        _users_cache = []
    # clean up truncated avatars from old bug
    for u in _users_cache:
        av = u.get("avatar", "")
        if av and not av.startswith("/static/") and not av.startswith("http") and not av.startswith("<img") and len(av) < 30:
            u["avatar"] = ""
    return _users_cache


def _persist_users():
    token = os.environ.get("BLD_API_TOKEN", "")
    app_name = os.environ.get("BLD_APP_NAME", "excavatio")
    if not token:
        logger.warning("BLD_API_TOKEN not set — user data will not persist")
        return False
    try:
        sess = requests.Session()
        sess.trust_env = False
        resp = sess.patch(
            f"https://app.build.io/api/v1/apps/{app_name}/config-vars",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={"USER_STORE": json.dumps(_users_cache)},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to persist users to config var: {e}")
        return False


def find_user_by_username(username):
    for u in _load_users():
        if u.get("username") == username:
            return u
    return None


def _clean_avatar(av):
    """Return a clean avatar value or a random default Greek emoji."""
    if not av:
        import random
        return random.choice(["\u26EA", "\U0001F3FA"])
    # already a clean image path
    if av.startswith("/static/") or av.startswith("http"):
        return av[:200]
    # already an img tag (old saved format)
    if av.startswith("<img"):
        m = re.search(r'src="([^"]+)"', av)
        if m:
            return m.group(1)
    # short string that's not an emoji entity — probably trash
    if len(av) < 30 and not av.startswith("&#x"):
        import random
        return random.choice(["\u26EA", "\U0001F3FA"])
    return av[:200]


def find_user_by_email(email):
    for u in _load_users():
        if u.get("email") == email:
            return u
    return None


def create_user(username, email, password):
    users = _load_users()
    import random
    default_avatars = ["\u26EA", "\U0001F3FA"]
    user = {
        "id": len(users) + 1,
        "username": username,
        "email": email,
        "password_hash": generate_password_hash(password),
        "created_at": datetime.now().isoformat(),
        "total_points": 0,
        "action_counts": {},
        "bio": "",
        "interests": "",
        "avatar": random.choice(default_avatars),
        "saved_items": [],
        "game_levels": {},
        "followers": [],
        "following": [],
    }
    users.append(user)
    with _persist_lock:
        _persist_users()
    return user


def save_user_progress(user_id):
    """Persist the current session's points/counts back to the user store."""
    users = _load_users()
    for u in users:
        if u.get("id") == user_id:
            u["total_points"] = session.get("total_points", 0)
            u["action_counts"] = session.get("action_counts", {})
            u["bio"] = session.get("bio", "")
            u["interests"] = session.get("interests", "")
            u["avatar"] = session.get("avatar", "")
            u["saved_items"] = session.get("saved_items", [])
            u["game_levels"] = session.get("game_levels", {})
            u["followers"] = session.get("followers", [])
            u["following"] = session.get("following", [])
            break
    with _persist_lock:
        _persist_users()


POINTS = {
    "view_site": 2,
    "trace_journey": 5,
    "identify_text": 10,
    "view_event": 5,
    "ai_search": 3,
}

ACHIEVEMENTS = [
    {"id": "cartographer", "name": "Cartographer", "icon": "map", "action": "view_site",
     "tiers": [
         {"threshold": 10, "label": "Cartographer I", "desc": "View 10 excavation sites"},
         {"threshold": 25, "label": "Cartographer II", "desc": "View 25 excavation sites"},
         {"threshold": 50, "label": "Cartographer III", "desc": "View 50 excavation sites"},
         {"threshold": 100, "label": "Master Cartographer", "desc": "View 100 excavation sites"},
     ]},
    {"id": "wayfarer", "name": "Wayfarer", "icon": "route", "action": "trace_journey",
     "tiers": [
         {"threshold": 5, "label": "Wayfarer I", "desc": "Trace 5 ancient journeys"},
         {"threshold": 10, "label": "Wayfarer II", "desc": "Trace 10 ancient journeys"},
         {"threshold": 20, "label": "Wayfarer III", "desc": "Trace 20 ancient journeys"},
         {"threshold": 50, "label": "Master Wayfarer", "desc": "Trace 50 ancient journeys"},
     ]},
    {"id": "philologist", "name": "Philologist", "icon": "scroll", "action": "identify_text",
     "tiers": [
         {"threshold": 3, "label": "Philologist I", "desc": "Identify 3 classical texts"},
         {"threshold": 10, "label": "Philologist II", "desc": "Identify 10 classical texts"},
         {"threshold": 25, "label": "Philologist III", "desc": "Identify 25 classical texts"},
         {"threshold": 50, "label": "Master Philologist", "desc": "Identify 50 classical texts"},
     ]},
    {"id": "historian", "name": "Historian", "icon": "book", "action": "view_event",
     "tiers": [
         {"threshold": 5, "label": "Historian I", "desc": "Explore 5 source connections"},
         {"threshold": 15, "label": "Historian II", "desc": "Explore 15 source connections"},
         {"threshold": 30, "label": "Historian III", "desc": "Explore 30 source connections"},
         {"threshold": 60, "label": "Master Historian", "desc": "Explore 60 source connections"},
     ]},
    {"id": "polymath", "name": "Polymath", "icon": "laurel", "action": None,
     "tiers": [
         {"threshold": 100, "label": "Polymath I", "desc": "Earn 100 total drachmae"},
         {"threshold": 250, "label": "Polymath II", "desc": "Earn 250 total drachmae"},
         {"threshold": 500, "label": "Polymath III", "desc": "Earn 500 total drachmae"},
         {"threshold": 1000, "label": "Master Polymath", "desc": "Earn 1000 total drachmae"},
     ]},
    {"id": "gamer", "name": "Gladiator", "icon": "laurel", "action": "quiz_correct",
     "tiers": [
         {"threshold": 5, "label": "Gladiator I", "desc": "Win 5 game rounds"},
         {"threshold": 15, "label": "Gladiator II", "desc": "Win 15 game rounds"},
         {"threshold": 30, "label": "Gladiator III", "desc": "Win 30 game rounds"},
         {"threshold": 60, "label": "Master Gladiator", "desc": "Win 60 game rounds"},
     ]},
]


def award_points(action, detail=""):
    pts = POINTS.get(action, 0)
    if pts == 0:
        return None
    total = max(0, session.get("total_points", 0) + pts)
    counts = session.get("action_counts", {})
    counts[action] = counts.get(action, 0) + 1
    session["total_points"] = total
    session["action_counts"] = counts
    session.modified = True
    return {"action": action, "points": pts, "detail": detail}


def adjust_points(delta, detail=""):
    """Award or deduct arbitrary points (for quiz games)."""
    total = max(0, session.get("total_points", 0) + delta)
    counts = session.get("action_counts", {})
    if delta > 0:
        counts["quiz_correct"] = counts.get("quiz_correct", 0) + 1
    elif delta < 0:
        counts["quiz_wrong"] = counts.get("quiz_wrong", 0) + 1
    session["total_points"] = total
    session["action_counts"] = counts
    session.modified = True
    return {"points": delta, "total": total}


def _compute_unlocked(total, counts):
    """Return (unlocked_ids, tier_info) where tier_info has per-achievement current tier + progress."""
    unlocked = []
    tiers_out = []
    for a in ACHIEVEMENTS:
        if a["action"] is None:
            current = total
        else:
            current = counts.get(a["action"], 0)
        highest = -1
        for ti, tier in enumerate(a["tiers"]):
            if current >= tier["threshold"]:
                highest = ti
                unlocked.append(a["id"] + "_" + str(ti))
        if highest >= 0:
            next_tier = a["tiers"][highest + 1] if highest + 1 < len(a["tiers"]) else None
        else:
            next_tier = a["tiers"][0]
        tiers_out.append({
            "id": a["id"],
            "icon": a["icon"],
            "current": current,
            "current_tier": highest >= 0 and a["tiers"][highest]["label"] or None,
            "current_tier_idx": highest,
            "next_tier": next_tier,
            "maxed": highest == len(a["tiers"]) - 1,
            "tiers": a["tiers"],
        })
    return unlocked, tiers_out


def get_user_stats():
    total = session.get("total_points", 0)
    counts = session.get("action_counts", {})
    unlocked, tiers = _compute_unlocked(total, counts)
    return {
        "total_points": total,
        "action_counts": counts,
        "achievements_unlocked": unlocked,
        "achievements": ACHIEVEMENTS,
        "tiers": tiers,
    }

EXCAVATIONS = [
    {"id": "pompeii", "title": "Pompeii", "lat": 40.7497, "lng": 14.4856, "description": "Roman city buried by Vesuvius in 79 CE. Excavations since 1748.", "period": "Roman (79 CE)", "startYear": 1748, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman", "volcanic"], "era": "ancient"},
    {"id": "herculaneum", "title": "Herculaneum", "lat": 40.8058, "lng": 14.3472, "description": "Wealthier Pompeii sister, preserved by pyroclastic flow. Excavations since 1738.", "period": "Roman (79 CE)", "startYear": 1738, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman", "volcanic"], "era": "ancient"},
    {"id": "ostia-antica", "title": "Ostia Antica", "lat": 41.7527, "lng": 12.2914, "description": "Port of ancient Rome. Systematic excavations since the 19th century.", "period": "Roman (4th c. BCE - 4th c. CE)", "startYear": 1855, "endYear": None, "ongoing": True, "featureTypes": ["port", "city", "roman"], "era": "ancient"},
    {"id": "acropolis", "title": "Athens Acropolis", "lat": 37.9714, "lng": 23.7257, "description": "Sacred citadel of Athens. Excavations by Greek Archaeological Society from 1834.", "period": "Mycenaean to Classical", "startYear": 1834, "endYear": None, "ongoing": True, "featureTypes": ["acropolis", "temple", "greek"], "era": "ancient"},
    {"id": "knossos", "title": "Knossos", "lat": 35.2980, "lng": 25.1632, "description": "Minoan palace. Excavated by Kalokairinos (1878) and Arthur Evans (1900-1931).", "period": "Minoan (1900-1370 BCE)", "startYear": 1878, "endYear": 1931, "ongoing": False, "featureTypes": ["palace", "minoan", "bronze age"], "era": "ancient"},
    {"id": "troy", "title": "Troy", "lat": 39.9575, "lng": 26.2383, "description": "Legendary city of the Trojan War. Schliemann (1870s), Dörpfeld, Blegen, Korfmann.", "period": "Bronze Age (3000-1200 BCE)", "startYear": 1870, "endYear": 2012, "ongoing": False, "featureTypes": ["city", "bronze age", "fortress"], "era": "ancient"},
    {"id": "delphi", "title": "Delphi", "lat": 38.4824, "lng": 22.5013, "description": "Sanctuary of Apollo and the Oracle. Excavated by French School at Athens from 1892.", "period": "Archaic to Roman", "startYear": 1892, "endYear": 1903, "ongoing": False, "featureTypes": ["sanctuary", "oracle", "temple", "greek"], "era": "ancient"},
    {"id": "olympia", "title": "Olympia", "lat": 37.6387, "lng": 21.6283, "description": "Sanctuary of Zeus, birthplace of the Olympic Games. German excavations from 1875.", "period": "Archaic to Roman", "startYear": 1875, "endYear": 1881, "ongoing": False, "featureTypes": ["sanctuary", "sports", "temple", "greek"], "era": "ancient"},
    {"id": "ephesus", "title": "Ephesus", "lat": 37.9392, "lng": 27.3414, "description": "Ionian Greek city, Roman provincial capital. Austrian excavations since 1895.", "period": "Greek to Roman", "startYear": 1895, "endYear": None, "ongoing": True, "featureTypes": ["city", "temple", "roman", "greek"], "era": "ancient"},
    {"id": "paestum", "title": "Paestum", "lat": 40.4196, "lng": 15.0055, "description": "Magna Graecia city with three Greek temples. Excavations from 1746.", "period": "Greek to Roman", "startYear": 1746, "endYear": None, "ongoing": True, "featureTypes": ["city", "temple", "greek"], "era": "ancient"},
    {"id": "carthage", "title": "Carthage", "lat": 36.8529, "lng": 10.3230, "description": "Phoenician and Roman city. UNESCO salvage campaign from 1972.", "period": "Phoenician to Roman", "startYear": 1830, "endYear": None, "ongoing": True, "featureTypes": ["city", "port", "phoenician", "roman"], "era": "ancient"},
    {"id": "palmyra", "title": "Palmyra", "lat": 34.5505, "lng": 38.2714, "description": "Oasis caravan hub. Damaged in 2015-2017 conflict.", "period": "Roman to Byzantine", "startYear": 1900, "endYear": None, "ongoing": False, "featureTypes": ["city", "caravan", "roman"], "era": "ancient"},
    {"id": "leptis-magna", "title": "Leptis Magna", "lat": 32.6330, "lng": 14.2910, "description": "Best-preserved Roman city in Africa, birthplace of Septimius Severus.", "period": "Roman (1st-4th c. CE)", "startYear": 1912, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman", "port"], "era": "ancient"},
    {"id": "mycenae", "title": "Mycenae", "lat": 37.7310, "lng": 22.7564, "description": "Citadel of Agamemnon. Schliemann (1876) and subsequent Greek missions.", "period": "Mycenaean (1600-1100 BCE)", "startYear": 1841, "endYear": 1969, "ongoing": False, "featureTypes": ["citadel", "bronze age", "fortress"], "era": "ancient"},
    {"id": "hadrians-wall", "title": "Hadrian's Wall", "lat": 55.0069, "lng": -2.3150, "description": "Roman defensive wall across Britain. Excavations since the 19th century.", "period": "Roman (122-410 CE)", "startYear": 1848, "endYear": None, "ongoing": True, "featureTypes": ["wall", "fort", "roman"], "era": "ancient"},
    {"id": "akrotiri", "title": "Akrotiri (Thera)", "lat": 36.3525, "lng": 25.3975, "description": "Minoan settlement buried by the Theran eruption. Marinatos (1967-1974).", "period": "Minoan (17th c. BCE)", "startYear": 1967, "endYear": 1974, "ongoing": False, "featureTypes": ["city", "minoan", "volcanic"], "era": "ancient"},
    {"id": "gobekli-tepe", "title": "Göbekli Tepe", "lat": 37.2231, "lng": 38.9225, "description": "Neolithic temple complex. Klaus Schmidt from 1995.", "period": "Neolithic (9600-8000 BCE)", "startYear": 1995, "endYear": None, "ongoing": True, "featureTypes": ["temple", "neolithic", "megalithic"], "era": "prehistoric"},
    {"id": "corinth", "title": "Corinth", "lat": 37.9056, "lng": 22.8797, "description": "Major Greek and Roman city. American School from 1896.", "period": "Greek to Roman", "startYear": 1896, "endYear": None, "ongoing": True, "featureTypes": ["city", "temple", "greek", "roman"], "era": "ancient"},
    {"id": "vindolanda", "title": "Vindolanda", "lat": 54.9913, "lng": -2.3591, "description": "Roman fort famous for writing tablets. Excavated annually since 1970.", "period": "Roman (85-410 CE)", "startYear": 1970, "endYear": None, "ongoing": True, "featureTypes": ["fort", "roman", "military"], "era": "ancient"},
    {"id": "stobi", "title": "Stobi", "lat": 41.5512, "lng": 21.9731, "description": "Major Macedonian city. Yugoslav/US teams from 1924.", "period": "Hellenistic to Roman", "startYear": 1924, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman", "greek"], "era": "ancient"},
    {"id": "nimes", "title": "Nemausus (Nîmes)", "lat": 43.8366, "lng": 4.3598, "description": "Roman city with Maison Carrée and amphitheater.", "period": "Roman (1st c. BCE - 4th c. CE)", "startYear": 1820, "endYear": None, "ongoing": True, "featureTypes": ["city", "temple", "amphitheater", "roman"], "era": "ancient"},
    {"id": "jerash", "title": "Jerash (Gerasa)", "lat": 32.2722, "lng": 35.8914, "description": "One of the best-preserved Roman cities in the East. Excavations from 1925.", "period": "Roman to Byzantine", "startYear": 1925, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman", "temple"], "era": "ancient"},
    {"id": "paphos", "title": "Paphos", "lat": 34.7577, "lng": 32.4095, "description": "Cypriot city with magnificent Roman mosaics. UNESCO site.", "period": "Greek to Roman", "startYear": 1960, "endYear": None, "ongoing": True, "featureTypes": ["city", "temple", "greek", "roman"], "era": "ancient"},
    {"id": "salamis-cyprus", "title": "Salamis (Cyprus)", "lat": 35.1833, "lng": 33.9000, "description": "Major city-kingdom of Cyprus. French excavations since 1952.", "period": "Greek to Roman", "startYear": 1952, "endYear": 1998, "ongoing": False, "featureTypes": ["city", "greek", "roman"], "era": "ancient"},
    {"id": "numantia", "title": "Numantia", "lat": 41.8125, "lng": -2.4472, "description": "Celtiberian stronghold that resisted Rome. Excavated from 1905.", "period": "Iron Age (2nd-1st c. BCE)", "startYear": 1905, "endYear": 1923, "ongoing": False, "featureTypes": ["city", "fortress", "celtic"], "era": "ancient"},
    {"id": "megalithic-malta", "title": "Megalithic Temples of Malta", "lat": 35.8680, "lng": 14.5133, "description": "Oldest freestanding stone structures in the world. Excavated from 1900.", "period": "Neolithic (3600-2500 BCE)", "startYear": 1900, "endYear": None, "ongoing": True, "featureTypes": ["temple", "neolithic", "megalithic"], "era": "prehistoric"},
    {"id": "atlantis-hab", "title": "Tartessos / Huelva", "lat": 37.2667, "lng": -6.9500, "description": "Tartessian civilization — possible Atlantis inspiration. Excavations ongoing.", "period": "Bronze Age (1000-500 BCE)", "startYear": 1923, "endYear": None, "ongoing": True, "featureTypes": ["city", "bronze age", "port"], "era": "ancient"},
    {"id": "elche", "title": "La Alcudia (Elche)", "lat": 38.2672, "lng": -0.6981, "description": "Iberian and Roman city, home of the Lady of Elche. Excavations from 1905.", "period": "Iberian to Roman", "startYear": 1905, "endYear": None, "ongoing": True, "featureTypes": ["city", "iberian", "roman"], "era": "ancient"},
    {"id": "teotihuacan", "title": "Teotihuacan", "lat": 19.6925, "lng": -98.8438, "description": "Mesoamerican pyramid city. Excavations since 1905.", "period": "Classic (200-650 CE)", "startYear": 1905, "endYear": None, "ongoing": True, "featureTypes": ["city", "pyramid", "temple"], "era": "ancient"},
    {"id": "nazca", "title": "Nazca Lines", "lat": -14.8308, "lng": -75.1075, "description": "Giant geoglyphs in the Peruvian desert. Studied from 1927.", "period": "Nazca (200 BCE-600 CE)", "startYear": 1927, "endYear": None, "ongoing": True, "featureTypes": ["geoglyph", "ritual"], "era": "ancient"},
    {"id": "persepolis-iran", "title": "Persepolis", "lat": 29.9344, "lng": 52.8915, "description": "Ceremonial capital of the Achaemenid Empire. Excavated by Herzfeld (1931) and Schmidt.", "period": "Persian (518-330 BCE)", "startYear": 1931, "endYear": 1939, "ongoing": False, "featureTypes": ["palace", "temple", "persian"], "era": "ancient"},
    {"id": "pasargadae", "title": "Pasargadae", "lat": 30.2030, "lng": 53.1794, "description": "First Persian capital, tomb of Cyrus the Great. Excavations from 1928.", "period": "Persian (6th c. BCE)", "startYear": 1928, "endYear": None, "ongoing": True, "featureTypes": ["city", "tomb", "persian"], "era": "ancient"},
    {"id": "susa-iran", "title": "Susa", "lat": 32.1892, "lng": 48.2561, "description": "Elamite and Persian capital. French excavations from 1885.", "period": "Elamite to Persian", "startYear": 1885, "endYear": 1979, "ongoing": False, "featureTypes": ["city", "palace", "persian"], "era": "ancient"},
    {"id": "bablyon", "title": "Babylon", "lat": 32.5364, "lng": 44.4209, "description": "Legendary city of Nebuchadnezzar and the Hanging Gardens. German excavations 1899-1917.", "period": "Babylonian (18th-6th c. BCE)", "startYear": 1899, "endYear": 1917, "ongoing": False, "featureTypes": ["city", "temple", "ziggurat"], "era": "ancient"},
    {"id": "uruk", "title": "Uruk (Warka)", "lat": 31.3242, "lng": 45.6375, "description": "The world's first city. German excavations from 1912.", "period": "Sumerian (4000-3100 BCE)", "startYear": 1912, "endYear": None, "ongoing": True, "featureTypes": ["city", "temple", "sumerian"], "era": "ancient"},
    {"id": "niniveh", "title": "Nineveh", "lat": 36.3667, "lng": 43.1667, "description": "Capital of the Assyrian Empire. Excavated by Layard (1845) and subsequent missions.", "period": "Assyrian (7th c. BCE)", "startYear": 1845, "endYear": None, "ongoing": True, "featureTypes": ["city", "palace", "assyrian"], "era": "ancient"},
    {"id": "hittite-hattusa", "title": "Hattusa", "lat": 40.0167, "lng": 34.5333, "description": "Capital of the Hittite Empire. German excavations from 1907.", "period": "Hittite (17th-12th c. BCE)", "startYear": 1907, "endYear": None, "ongoing": True, "featureTypes": ["city", "temple", "fortress"], "era": "ancient"},
    {"id": "catalhoyuk", "title": "Çatalhöyük", "lat": 37.6675, "lng": 32.8275, "description": "9,000-year-old Neolithic city. Excavated by Mellaart (1958) and Hodder (1993-2018).", "period": "Neolithic (7500-5700 BCE)", "startYear": 1958, "endYear": 2018, "ongoing": False, "featureTypes": ["city", "neolithic"], "era": "prehistoric"},
    {"id": "mohenjo-daro", "title": "Mohenjo-Daro", "lat": 27.3258, "lng": 68.1389, "description": "Great city of the Indus Valley Civilization. Excavated from 1920.", "period": "Indus Valley (2600-1900 BCE)", "startYear": 1920, "endYear": 1965, "ongoing": False, "featureTypes": ["city", "bronze age"], "era": "ancient"},
    {"id": "harappa", "title": "Harappa", "lat": 30.6278, "lng": 72.8672, "description": "Type site of the Indus Valley Civilization. Excavated from 1920.", "period": "Indus Valley (2600-1900 BCE)", "startYear": 1920, "endYear": None, "ongoing": True, "featureTypes": ["city", "bronze age"], "era": "ancient"},
    {"id": "taxila", "title": "Taxila", "lat": 33.7458, "lng": 72.7875, "description": "Ancient Gandharan centre of learning. Excavated by Marshall (1913-1934).", "period": "Gandharan to Kushan", "startYear": 1913, "endYear": 1934, "ongoing": False, "featureTypes": ["city", "temple", "greek", "buddhist"], "era": "ancient"},
    {"id": "ai-khanoum", "title": "Ai Khanoum", "lat": 37.1667, "lng": 69.4167, "description": "Hellenistic city in Afghanistan. French excavations 1964-1978.", "period": "Hellenistic (4th-2nd c. BCE)", "startYear": 1964, "endYear": 1978, "ongoing": False, "featureTypes": ["city", "greek", "temple"], "era": "ancient"},
    {"id": "begram", "title": "Begram", "lat": 34.9667, "lng": 69.3000, "description": "Kushan city with famous treasure. Excavated by Hackin (1936-1946).", "period": "Kushan (1st-2nd c. CE)", "startYear": 1936, "endYear": 1946, "ongoing": False, "featureTypes": ["city", "fortress", "trade"], "era": "ancient"},
    {"id": "petra", "title": "Petra", "lat": 30.3285, "lng": 35.4443, "description": "Nabataean rock-cut city. Excavated from 1929, ongoing.", "period": "Nabataean to Roman (3rd c. BCE-2nd c. CE)", "startYear": 1929, "endYear": None, "ongoing": True, "featureTypes": ["city", "temple", "tomb"], "era": "ancient"},
    {"id": "jericho", "title": "Tell es-Sultan (Jericho)", "lat": 31.8708, "lng": 35.4445, "description": "Oldest continuously inhabited city. Excavated from 1907.", "period": "Neolithic to Roman", "startYear": 1907, "endYear": None, "ongoing": True, "featureTypes": ["city", "tower", "neolithic"], "era": "prehistoric"},
    {"id": "megiddo", "title": "Megiddo (Armageddon)", "lat": 32.5847, "lng": 35.1831, "description": "Biblical city and strategic crossroads. Oriental Institute (1925-1939).", "period": "Bronze Age to Iron Age", "startYear": 1903, "endYear": 1971, "ongoing": False, "featureTypes": ["city", "fortress", "temple"], "era": "ancient"},
    {"id": "masada", "title": "Masada", "lat": 31.3157, "lng": 35.3539, "description": "Herodian fortress and site of the Jewish revolt. Yadin excavations 1963-1965.", "period": "Roman (1st c. BCE-1st c. CE)", "startYear": 1963, "endYear": 1965, "ongoing": False, "featureTypes": ["fortress", "palace", "roman"], "era": "ancient"},
    {"id": "caesarea", "title": "Caesarea Maritima", "lat": 32.5000, "lng": 34.8917, "description": "Herod's great port city. Excavations from 1946, ongoing.", "period": "Roman to Byzantine", "startYear": 1946, "endYear": None, "ongoing": True, "featureTypes": ["city", "port", "roman"], "era": "ancient"},
    {"id": "beth-shean", "title": "Beit She'an (Scythopolis)", "lat": 32.4990, "lng": 35.4995, "description": "Decapolis city with Roman theatre. Excavations from 1920.", "period": "Roman to Byzantine", "startYear": 1920, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman", "temple", "theatre"], "era": "ancient"},
    {"id": "apamea", "title": "Apamea", "lat": 35.4167, "lng": 36.4000, "description": "Hellenistic and Roman city with the longest colonnaded street. Belgian excavations.", "period": "Hellenistic to Roman", "startYear": 1930, "endYear": 1990, "ongoing": False, "featureTypes": ["city", "roman", "greek"], "era": "ancient"},
    {"id": "dougga", "title": "Dougga", "lat": 36.4200, "lng": 9.2200, "description": "Best-preserved Roman city in North Africa. Excavations from 1890.", "period": "Roman to Byzantine", "startYear": 1890, "endYear": None, "ongoing": True, "featureTypes": ["city", "temple", "roman"], "era": "ancient"},
    {"id": "volubilis", "title": "Volubilis", "lat": 34.0744, "lng": -5.5542, "description": "Roman city in Morocco. Excavations from 1915.", "period": "Roman (1st-3rd c. CE)", "startYear": 1915, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman"], "era": "ancient"},
    {"id": "loninum", "title": "Londinium", "lat": 51.5125, "lng": -0.0900, "description": "Roman London — amphitheatre, forum, basilica discovered under the City.", "period": "Roman (43-410 CE)", "startYear": 1848, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman", "port"], "era": "ancient"},
    {"id": "conimbriga", "title": "Conimbriga", "lat": 40.0983, "lng": -8.4911, "description": "Best-preserved Roman site in Portugal. Excavations from 1895.", "period": "Roman (1st-4th c. CE)", "startYear": 1895, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman", "temple"], "era": "ancient"},
    {"id": "tarraco", "title": "Tarraco (Tarragona)", "lat": 41.1167, "lng": 1.2500, "description": "Roman provincial capital in Spain. Amphitheatre, circus, forum.", "period": "Roman (2nd c. BCE-5th c. CE)", "startYear": 1800, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman", "amphitheatre"], "era": "ancient"},
    {"id": "merida", "title": "Emerita Augusta (Mérida)", "lat": 38.9167, "lng": -6.3333, "description": "Roman city with the best-preserved theatre and aqueduct in Spain.", "period": "Roman (1st c. BCE-4th c. CE)", "startYear": 1910, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman", "theatre", "temple"], "era": "ancient"},
    {"id": "itinera", "title": "Itálica", "lat": 37.4400, "lng": -6.0400, "description": "Birthplace of Trajan and Hadrian. Massive amphitheatre (third largest in Rome).", "period": "Roman (2nd c. BCE-3rd c. CE)", "startYear": 1788, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman", "amphitheatre"], "era": "ancient"},
    {"id": "carnuntum", "title": "Carnuntum", "lat": 48.1167, "lng": 16.8500, "description": "Major Roman legionary fort and city on the Danube. Excavated from 1870.", "period": "Roman (1st-4th c. CE)", "startYear": 1870, "endYear": None, "ongoing": True, "featureTypes": ["city", "fort", "roman", "military"], "era": "ancient"},
    {"id": "augusta-raur", "title": "Augusta Raurica", "lat": 47.5333, "lng": 7.7167, "description": "Best-preserved Roman city in Switzerland. Excavations from 1800.", "period": "Roman (1st-4th c. CE)", "startYear": 1800, "endYear": None, "ongoing": True, "featureTypes": ["city", "roman", "theatre"], "era": "ancient"},
    {"id": "trimontium", "title": "Trimontium (Newstead)", "lat": 55.6000, "lng": -2.6833, "description": "Roman fort complex in Scotland. Excavated by Curle (1905-1910).", "period": "Roman (1st-2nd c. CE)", "startYear": 1905, "endYear": 1910, "ongoing": False, "featureTypes": ["fort", "roman", "military"], "era": "ancient"},
    {"id": "varus-kalk", "title": "Kalkriese (Varus Battle)", "lat": 52.3667, "lng": 8.0667, "description": "Site of the Teutoburg Forest disaster (9 CE). Discovered 1987, ongoing excavations.", "period": "Roman (9 CE)", "startYear": 1987, "endYear": None, "ongoing": True, "featureTypes": ["battlefield", "roman", "military"], "era": "ancient"},
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
# JOURNEY ROUTES
# ---------------------------------------------------------------------------
JOURNEYS = {
    "odysseus": {
        "id": "odysseus",
        "name": "Odysseus",
        "title": "The Odyssey",
        "description": "Odysseus' ten-year journey home from the Trojan War to Ithaca, as told by Homer in the Odyssey (8th c. BCE). His route traverses the Aegean, Ionian and Tyrrhenian seas, with encounters at Ismarus, the land of the Lotus-Eaters, the Cyclops' cave, Aeolus' island, Circe's Aeaea, the Sirens, Scylla and Charybdis, Thrinacia, Calypso's Ogygia, and Scheria before finally reaching Ithaca.",
        "color": "#e57373",
        "factFile": {
            "source": "Homer, Odyssey (c. 750-700 BCE)",
            "period": "Late Bronze Age / Greek Dark Age (trad. 12th c. BCE)",
            "distance": "Approx. 2,500 nautical miles",
            "duration": "10 years",
            "keyThemes": "Xenia (guest-friendship), hubris, cunning vs strength, nostos (homecoming), divine interference",
            "notableTexts": "Odyssey Books 9-12 (Apologoi — Odysseus' own account of his wanderings)",
            "legacy": "The term 'odyssey' has entered the lexicon as any epic journey. Odysseus' route has been debated for millennia — ancient scholars like Eratosthenes considered it purely fantastical, while modern theorists attempt to map it to real locations in Sicily, Italy, Malta, and the Ionian islands.",
            "keyScholars": "Victor Bérard (Les Navigations d'Ulysse, 1927-29), Armin Wolf, Tim Severin (reconstructed voyage 1985)",
        },
        "stops": [
            {"lat": 39.9575, "lng": 26.2383, "name": "Troy", "desc": "Departure after the 10-year Trojan War. The wooden horse stratagem succeeded and the city fell."},
            {"lat": 40.75, "lng": 25.95, "name": "Ismarus (Cicones)", "desc": "First stop — Odysseus raided the city of the Cicones but lingered too long, losing 72 men in a counterattack."},
            {"lat": 36.4, "lng": 22.5, "name": "Land of the Lotus-Eaters", "desc": "Crew ate the lotus fruit (possibly jujube or poppy) and lost all desire to return home. Odysseus dragged them back to the ships by force."},
            {"lat": 37.8, "lng": 12.4, "name": "Cyclops' Cave (Sicily)", "desc": "Odysseus and 12 men were trapped by Polyphemus, who ate 6 of them. Odysseus got him drunk, told him his name was 'Nobody', and blinded him with a red-hot stake. Escaped clinging to sheep bellies."},
            {"lat": 40.8, "lng": 13.4, "name": "Aeolus' Island (Aeolia)", "desc": "Aeolus, keeper of the winds, gave Odysseus a bag containing all adverse winds. His crew opened it within sight of Ithaca, blowing them back across the sea."},
            {"lat": 41.4, "lng": 9.7, "name": "Laestrygonians (Corsica)", "desc": "Giant cannibals at Telepylos destroyed 11 of 12 ships by hurling boulders. Only Odysseus' own ship escaped — the most catastrophic loss of the voyage."},
            {"lat": 40.3, "lng": 12.0, "name": "Circe's Island (Aeaea / Monte Circeo)", "desc": "Circe turned half the crew into pigs. With Hermes' help (moly herb), Odysseus resisted and compelled her to restore them. Stayed one year; Circe advised him to consult Tiresias in the Underworld."},
            {"lat": 39.4, "lng": 22.0, "name": "Underworld (Nekyia)", "desc": "Sailed to the edge of the world and offered blood sacrifice. Spoke with Tiresias, his mother Anticleia, Agamemnon, Achilles, Ajax, and saw the punishments of Tityus, Tantalus, and Sisyphus."},
            {"lat": 38.0, "lng": 24.0, "name": "Sirens (Anthemoessa)", "desc": "Circe's warning: the Sirens' song lured sailors to their death. Odysseus filled his crew's ears with wax and had himself lashed to the mast, longing to hear the song."},
            {"lat": 38.2, "lng": 23.5, "name": "Scylla & Charybdis (Strait of Messina)", "desc": "The six-headed monster Scylla snatched and devoured six men — one for each mouth. Charybdis sucked the sea into a whirlpool three times daily. Odysseus chose to lose six rather than risk the whole ship."},
            {"lat": 36.6, "lng": 21.0, "name": "Thrinacia (Sun God's Cattle)", "desc": "Sheep and cattle of Helios. Odysseus warned the crew not to touch them. Starving during a month-long storm, Eurylochus persuaded the men to slaughter the cattle. Once at sea, Zeus destroyed the ship with a thunderbolt. Only Odysseus survived, clinging to the wreckage."},
            {"lat": 36.0, "lng": 14.3, "name": "Calypso's Ogygia (Malta / Gozo)", "desc": "Washed ashore on Calypso's island. The nymph kept him as her lover for seven years, promising immortality. Odysseus refused, spending his days weeping on the shore. Hermes finally compelled her release."},
            {"lat": 39.6, "lng": 19.9, "name": "Scheria (Corfu — Phaeacia)", "desc": "Shipwrecked again, Odysseus was found by Nausicaa. King Alcinous hosted him and heard the full tale of his wanderings. The Phaeacians gave him a ship and treasure."},
            {"lat": 38.38, "lng": 20.65, "name": "Ithaca (home)", "desc": "Arrived at last. In disguise by Athena, he found his palace overrun by 108 suitors vying for Penelope's hand. With Telemachus and two loyal servants, he slew all the suitors and was reunited with Penelope."},
        ],
    },
    "alexander": {
        "id": "alexander",
        "name": "Alexander the Great",
        "title": "Conquests of Alexander the Great",
        "description": "Alexander III of Macedon (356-323 BCE) created one of the largest empires of the ancient world in just 13 years, covering over 22,000 miles. From Greece to Egypt, Persia to India, he never lost a single battle. His conquests ushered in the Hellenistic Age, spreading Greek culture across three continents.",
        "color": "#ba68c8",
        "factFile": {
            "source": "Arrian, Anabasis of Alexander (2nd c. CE); Plutarch, Life of Alexander; Diodorus Siculus, Library of History",
            "period": "336-323 BCE (13-year reign)",
            "distance": "Approx. 22,000 miles (35,000 km)",
            "duration": "13 years (336-323 BCE)",
            "keyThemes": "Hellenization, divine kingship, fusion of cultures, relentless ambition, logistics of ancient warfare",
            "notableTexts": "Arrian's Anabasis (the most reliable source), Plutarch's Life of Alexander, Quintus Curtius Rufus' History of Alexander",
            "legacy": "Founded over 70 cities, most named Alexandria. His empire fragmented after his death but the Hellenistic kingdoms (Ptolemaic Egypt, Seleucid Persia, Antigonid Macedon) lasted for centuries. The Silk Road, library of Alexandria, and koine Greek all trace back to his conquests.",
            "keyScholars": "Sir William Tarn, Robin Lane Fox, Peter Green, Ian Worthington, A.B. Bosworth",
        },
        "stops": [
            {"lat": 40.76, "lng": 22.52, "name": "Pella (Macedonia)", "desc": "Birthplace (356 BCE). Tutored by Aristotle from age 13. At 16, regent of Macedon; at 18, led the cavalry at Chaeronea."},
            {"lat": 37.97, "lng": 23.72, "name": "Corinth / League of Corinth", "desc": "After sacking Thebes (335 BCE), Alexander was appointed Hegemon (supreme commander) of the Greek league for the invasion of Persia."},
            {"lat": 40.2, "lng": 26.4, "name": "Hellespont Crossing", "desc": "Spring 334 BCE. Crossed the Hellespont (Dardanelles) with 32,000 infantry, 5,100 cavalry, and a fleet of 160 ships. Threw a spear into Asian soil, claiming Asia as 'spear-won' territory."},
            {"lat": 40.0, "lng": 27.3, "name": "Granicus River", "desc": "May 334 BCE. First major battle against Persian satraps. Alexander nearly killed, personally led the charge across the river. Over 1,000 Persian cavalry killed."},
            {"lat": 37.9, "lng": 29.1, "name": "Miletus & Halicarnassus", "desc": "Captured the Persian naval bases. At Halicarnassus, a brutal house-to-house siege. Ada, the deposed queen, adopted Alexander as her son, so he restored her to power."},
            {"lat": 36.9, "lng": 30.7, "name": "Gordium", "desc": "Cut the Gordian Knot — an intricate knot tied by King Midas. Prophecy said whoever untied it would rule Asia. Alexander sliced through it with his sword."},
            {"lat": 36.8, "lng": 34.6, "name": "Issus (Turkish/Syrian border)", "desc": "November 333 BCE. Fought Darius III in a narrow plain between mountains and sea. Alexander led the Companion Cavalry in a wedge charge. Darius fled, leaving his family behind."},
            {"lat": 33.9, "lng": 35.5, "name": "Tyre", "desc": "Siege of Tyre (Jan-Jul 332 BCE). The most famous siege of antiquity. Built a 1km causeway from the mainland. After 7 months, Tyre fell; 8,000 Tyrians died, 30,000 sold into slavery."},
            {"lat": 31.2, "lng": 29.9, "name": "Alexandria (Egypt)", "desc": "Founded 331 BCE at the mouth of the Nile. The city became the greatest metropolis of the Hellenistic world, home to the Pharos lighthouse and the Great Library."},
            {"lat": 36.6, "lng": 36.2, "name": "Gaugamela (Arbela)", "desc": "October 331 BCE. Decisive battle with 47,000 Macedonians vs 100,000+ Persians. Alexander feinted right, broke through the Persian center, and aimed directly at Darius, who fled again. End of the Achaemenid Empire."},
            {"lat": 32.6, "lng": 51.7, "name": "Persepolis", "desc": "Winter 330 BCE. Persepolis, the ceremonial capital of Persia, was looted and burned. Alexander later regretted it. The palace of Xerxes was destroyed."},
            {"lat": 34.3, "lng": 62.2, "name": "Herat / Aria (Artacoana)", "desc": "Pursued the usurper Bessus through modern Afghanistan. Founded Alexandria in Aria (Herat). Crushed the rebellion of Satibarzanes."},
            {"lat": 37.0, "lng": 66.5, "name": "Bactria (Balkh) & Sogdiana", "desc": "Campaign in Central Asia, 329-327 BCE. Married Roxana, daughter of the Bactrian noble Oxyartes. Fought a brutal guerrilla war against Spitamenes."},
            {"lat": 40.3, "lng": 69.6, "name": "Alexandria Eschate (Tajikistan)", "desc": "Founded 'The Furthest Alexandria' on the Jaxartes River (Syr Darya), the northernmost outpost of the empire, on the edge of the Scythian steppe."},
            {"lat": 34.0, "lng": 70.4, "name": "Khyber Pass to India", "desc": "327 BCE. Crossed the Hindu Kush and descended through the Khyber Pass into the Indian subcontinent — the first European to do so."},
            {"lat": 32.8, "lng": 73.6, "name": "Hydaspes River (Jhelum)", "desc": "May 326 BCE. Fought King Porus of the Pauravas. The only battle where Alexander faced war elephants. After victory, he appointed Porus as his satrap — a magnanimous gesture."},
            {"lat": 31.0, "lng": 73.0, "name": "Hypanis River (Beas)", "desc": "Alexander's army mutinied at the Beas River, refusing to march further east. After 8 years and 22,000 miles, the exhausted army forced him to turn back. He wept — there were no more worlds to conquer."},
            {"lat": 26.0, "lng": 68.0, "name": "Gedrosian Desert (Makran)", "desc": "The most disastrous leg of the campaign. Marching across 600 miles of waterless desert in July. Thousands of soldiers, women, and camp followers died of thirst, heatstroke, and snakebite. Ptolemy hunted ahead for water sources."},
            {"lat": 31.6, "lng": 48.7, "name": "Susa", "desc": "324 BCE. Mass wedding of 80 Macedonian officers to Persian noblewomen. Alexander married Darius' daughter Stateira and Artaxerxes' daughter Parysatis. Backdated debts of his soldiers."},
            {"lat": 33.5, "lng": 44.4, "name": "Babylon", "desc": "June 323 BCE. Died at age 32 in the palace of Nebuchadnezzar II. Cause disputed — poisoning, malaria, typhoid, or alcohol-induced pancreatitis. His body was preserved in honey and taken to Alexandria."},
        ],
    },
    "aeneas": {
        "id": "aeneas",
        "name": "Aeneas",
        "title": "Aeneas' Journey (Aeneid)",
        "description": "Aeneas' journey from burning Troy to the shores of Italy, as recounted by Virgil in the Aeneid (19 BCE). Commissioned by Augustus as Rome's foundation epic, the Aeneid models Aeneas' voyage on Homer's Odyssey (Books 1-6) and his wars on the Iliad (Books 7-12). Aeneas embodies pietas — duty to gods, family, and fate.",
        "color": "#ffb74d",
        "factFile": {
            "source": "Virgil, Aeneid (19 BCE)",
            "period": "Late Bronze Age (trad. 1184 BCE fall of Troy) — written in the Augustan Age (1st c. BCE)",
            "distance": "Approx. 1,500 nautical miles",
            "duration": "7 years of wandering (trad. 1184-1177 BCE)",
            "keyThemes": "Pietas (duty), fatum (fate), sacrifice for destiny, the cost of empire, romanitas (Roman identity)",
            "notableTexts": "Aeneid Books 1-6 (the wanderings), Book 6 (Underworld — the pageant of future Rome), Book 8 (the Shield of Aeneas), Book 12 (death of Turnus)",
            "legacy": "The Aeneid is the national epic of Rome. It provided the Julian family (Augustus) with divine ancestry through Aeneas' son Iulus/Ascanius. Virgil died before finishing it, ordering it burned; Augustus saved it.",
            "keyScholars": "R.G.M. Nisbet, R.O.A.M. Lyne, Elaine Fantham, Nicholas Horsfall",
        },
        "stops": [
            {"lat": 39.96, "lng": 26.24, "name": "Troy", "desc": "As Troy burned, Aeneas carried his father Anchises on his back, leading his son Ascanius and his household gods (Penates). His wife Creusa was lost in the chaos — her ghost told him to seek Hesperia (Italy)."},
            {"lat": 39.7, "lng": 26.5, "name": "Mount Ida", "desc": "Gathered 20 ships of Trojan survivors in the foothills of Mount Ida while the Greeks plundered the city."},
            {"lat": 40.7, "lng": 24.2, "name": "Thrace (Aenus)", "desc": "First attempt to found a city. When Aeneas uprooted a myrtle bush, the ground bled — it was Polydorus, Priam's son, murdered for his gold. The ghost warned Aeneas to flee this cursed land."},
            {"lat": 37.46, "lng": 25.36, "name": "Delos", "desc": "Consulted the oracle of Apollo. The god's cryptic response: 'Seek your ancient mother' — Anchises misinterpreted this as Crete, their ancestral homeland."},
            {"lat": 35.34, "lng": 25.13, "name": "Crete", "desc": "Attempted to settle at Pergamea. Struck by plague and drought. The household gods appeared to Aeneas in a dream, revealing the true destination was Italy — the homeland of Dardanus, the Trojan founder."},
            {"lat": 36.6, "lng": 25.9, "name": "Strophades Islands", "desc": "Set upon by the Harpies — half-bird, half-woman monsters. Celaeno, their leader, prophesied: 'You will not found your city until hunger forces you to eat your tables'."},
            {"lat": 38.8, "lng": 20.7, "name": "Actium / Leucas", "desc": "Celebrated games at Actium (anachronistically foreshadowing Augustus' victory in 31 BCE). Anchises died here."},
            {"lat": 37.8, "lng": 12.4, "name": "Sicily (Drepanum — Trapani)", "desc": "Anchises died and was buried on Mount Eryx. While Aeneas celebrated funeral games, Juno sent Iris to convince the Trojan women to burn the ships. Four ships were destroyed. Aeneas founded Segesta for the elderly and willing."},
            {"lat": 36.9, "lng": 15.6, "name": "Scylla & Charybdis", "desc": "Passed the Strait of Messina between the six-headed monster Scylla and the whirlpool Charybdis — following Circe's warning."},
            {"lat": 37.6, "lng": 12.9, "name": "Cyclops Coast (Sicily)", "desc": "Rescued Achaemenides, a Greek sailor left behind by Odysseus (a clever cross-reference to Homer). The Cyclopes hurled boulders at the fleeing ships."},
            {"lat": 40.85, "lng": 14.06, "name": "Cumae (Bay of Naples)", "desc": "Consulted the Cumaean Sibyl, who led him into the Underworld. Aeneas saw the ghosts of Dido (who turned away from him), Anchises, and the future heroes of Rome — Romulus, Caesar, Augustus. Book 6 is the climax of the first half of the epic."},
            {"lat": 41.7, "lng": 12.3, "name": "Latium (Tiber River)", "desc": "Arrived at the mouth of the Tiber. The Trojans ate their meal on flatbread — and then ate the bread itself. Fulfilled the prophecy of 'eating your tables.'"},
            {"lat": 41.8, "lng": 12.2, "name": "Laurentum / Lavinium", "desc": "Made alliance with King Latinus, who offered his daughter Lavinia in marriage. This sparked war with Turnus of the Rutuli. Aeneas defeated Turnus in single combat but, seeing Turnus wearing Pallas' belt, killed him in fury — the final lines of the Aeneid."},
        ],
    },
    "xenophon": {
        "id": "xenophon",
        "name": "Xenophon's Ten Thousand",
        "title": "The Anabasis — March of the Ten Thousand",
        "description": "The Anabasis recounts the journey of 10,000 Greek mercenaries hired by Cyrus the Younger to claim the Persian throne from his brother Artaxerxes II. After the battle at Cunaxa where Cyrus died, the Greeks — stranded 1,500 miles from home — elected Xenophon as one of their leaders and fought their way north through hostile tribes and snowbound mountains to the Black Sea (401-399 BCE).",
        "color": "#81c784",
        "factFile": {
            "source": "Xenophon, Anabasis (c. 370 BCE)",
            "period": "401-399 BCE",
            "distance": "Approx. 2,000 miles (3,200 km)",
            "duration": "2 years (401-399 BCE)",
            "keyThemes": "Leadership under crisis, the vulnerability of mercenaries, the resilience of the Greek hoplite, the 'Thalatta' moment, xenia (guest-friendship and its violation)",
            "notableTexts": "Xenophon's Anabasis ('The March Up-Country'), Books 1-7. Book 4 (the mountain crossing) and Book 5 (the sea) are the most famous. The Anabasis was one of the most widely read classical texts in the West, influencing military thinking into the 20th century.",
            "legacy": "The Anabasis is the first surviving work of military history written by a commander who was there. The cry 'Thalatta! Thalatta!' (The Sea! The Sea!) became proverbial for reaching a hard-won goal. The Ten Thousand demonstrated the superiority of Greek hoplite tactics over Persian infantry.",
            "keyScholars": "J.B. Bury, C.B. Welles, Olivier Masson, N.G.L. Hammond, Robin Waterfield",
        },
        "stops": [
            {"lat": 38.49, "lng": 28.03, "name": "Sardis (Manisa)", "desc": "Spring 401 BCE. Departure point. Cyrus mustered an army of about 12,500 mercenaries under the pretense of a campaign against the Pisidians. His true goal: seize the Persian throne."},
            {"lat": 37.87, "lng": 32.48, "name": "Iconium (Konya)", "desc": "Marched across the Anatolian plateau. Here the Greek generals began to suspect Cyrus' true intentions."},
            {"lat": 36.92, "lng": 34.90, "name": "Tarsus", "desc": "The Greeks refused to march further — they had not signed up to fight the Great King. Clearchus, their Spartan commander, forced Cyrus to pay a bonus and reveal the true objective. They were persuaded by promises of more gold."},
            {"lat": 36.85, "lng": 38.00, "name": "Thapsacus (Euphrates)", "desc": "Crossed the Euphrates River. The river was at its lowest. This was the point of no return — once east of the Euphrates, they were cut off from the Greek world."},
            {"lat": 35.5, "lng": 39.5, "name": "Arabian Desert march", "desc": "Marched south through the desert along the left bank of the Euphrates. Days of limited water and scorching heat. The army marched by night."},
            {"lat": 33.26, "lng": 44.10, "name": "Cunaxa (Baghdad)", "desc": "September 3, 401 BCE. Cyrus' 10,400 Greek hoplites routed the Persian left wing without a single casualty. But Cyrus, in a rash charge against Artaxerxes, was killed. The victory was hollow — the Greeks were stranded."},
            {"lat": 33.8, "lng": 44.3, "name": "Sittace / Opis", "desc": "After Cyrus' death, the Greeks refused Persian demands to surrender. They began the retreat northward, harassed by Persian forces under Tissaphernes."},
            {"lat": 36.2, "lng": 43.5, "name": "Larisa & Mespila (Nineveh)", "desc": "Passed the ruins of the great Assyrian cities, destroyed a century earlier. The Greeks marveled at the massive walls of what had been the capital of the world."},
            {"lat": 37.0, "lng": 43.5, "name": "Karduchian Mountains (Kurdistan)", "desc": "The most harrowing phase. The Carduchians (Kurds) fiercely defended their mountain passes, rolling boulders down on the Greeks. Seven days of constant fighting, heavy snow, and loss of baggage animals. Xenophon organized night attacks and feints."},
            {"lat": 39.5, "lng": 42.0, "name": "Armenian Highlands", "desc": "Crossed the snowbound mountains of Armenia in winter. Soldiers froze to death, went snow-blind, or fell into hidden ravines. The guides led them astray. Xenophon urged them onward with words of encouragement."},
            {"lat": 40.2, "lng": 40.5, "name": "Teleboas River (Kara Su)", "desc": "Fought the Chalybes, the most formidable warriors they encountered — equipped with distinctive long spears and linen corslets. Also fought the Taochi, who defended their fortresses desperately."},
            {"lat": 40.4, "lng": 40.8, "name": "Mount Theches (Tekieh)", "desc": "THE MOMENT. The rear guard under Xenophon heard a shout from the vanguard — 'Thalatta! Thalatta!' (The Sea! The Sea!). The cry spread through the army. They embraced, weeping, building a cairn of stones. The Black Sea lay below them. They had made it."},
            {"lat": 41.0, "lng": 39.7, "name": "Trapezus (Trabzon)", "desc": "Reached this Greek colony on the Black Sea. They were feasted by the Trapezuntians. Held athletic games and sacrifices to Zeus the Savior. But the journey was not yet over."},
            {"lat": 41.5, "lng": 35.5, "name": "Sinope (Sinop)", "desc": "Marched west along the Black Sea coast. Here Xenophon first considered founding a city, but the soldiers rejected the idea — they wanted to go home."},
            {"lat": 42.0, "lng": 34.0, "name": "Heraclea Pontica", "desc": "Discipline broke down and the army split into three factions. They reunited and marched on, ravaging the territory of the Mariandyni for supplies."},
            {"lat": 41.0, "lng": 28.98, "name": "Byzantium (Istanbul)", "desc": "Spring 399 BCE. Finally reached Byzantium. They had survived. From here, the remnants of the Ten Thousand were absorbed into Spartan service. The Anabasis was over. The Persian Empire's internal weakness was now exposed to all Greece — a lesson Alexander would not forget."},
        ],
    },
    "hannibal": {
        "id": "hannibal",
        "name": "Hannibal",
        "title": "Hannibal's Invasion of Italy (Second Punic War)",
        "description": "Hannibal Barca's legendary crossing of the Alps with war elephants in 218 BCE, followed by 15 years of campaigning in Italy. He won stunning victories at Trebia, Trasimene, and Cannae but never captured Rome. His journey from Carthage to Italy and back remains one of the most audacious military campaigns in history.",
        "color": "#ff8a65",
        "factFile": {
            "source": "Polybius, Histories (2nd c. BCE); Livy, History of Rome (1st c. BCE)",
            "period": "218-202 BCE (Second Punic War)",
            "distance": "Approx. 2,000 miles",
            "duration": "17 years (218-202 BCE, including Italian campaign)",
            "keyThemes": "Strategic genius, asymmetric warfare, logistical miracle (elephants), failure to press advantage",
            "notableTexts": "Polybius Book 3 (the most reliable), Livy Books 21-30, Cornelius Nepos' Life of Hannibal",
            "legacy": "Hannibal is considered one of the greatest military tacticians in history. His manoeuvre at Cannae (double envelopment) is still studied at military academies. The phrase 'Hannibal ante portas' (Hannibal at the gates) became a Roman watchword for existential threat.",
            "keyScholars": "Theodor Mommsen, J.F. Lazenby, Dexter Hoyos, Adrian Goldsworthy",
        },
        "stops": [
            {"lat": 36.85, "lng": 10.32, "name": "Carthage (Tunis)", "desc": "Hannibal, aged 25, took command after his father Hamilcar's death. Sworn eternal enmity to Rome."},
            {"lat": 38.0, "lng": -1.0, "name": "Nova Carthago (Cartagena)", "desc": "Hannibal's base in Spain. Assembled 90,000 infantry, 12,000 cavalry, and 37 war elephants."},
            {"lat": 41.5, "lng": 2.0, "name": "Crossing the Ebro River", "desc": "Crossed the Ebro — the treaty line with Rome. This act began the Second Punic War."},
            {"lat": 43.5, "lng": 4.0, "name": "Rhone River Crossing", "desc": "Defeated the Volcae tribe. Built oversized rafts to transport elephants. Roman scouts arrived too late."},
            {"lat": 44.5, "lng": 5.0, "name": "The Alps Crossing", "desc": "The legendary mountain crossing with 26,000 men and 21 elephants. 15 days in the mountains. Hostile tribes, falling rocks, narrow passes. Lost half his army to cold and ambushes."},
            {"lat": 45.0, "lng": 7.5, "name": "Descent into Italy (Po Valley)", "desc": "Descended into the Po Valley — the survivor army looked like ghosts. But the Gauls flocked to his banner."},
            {"lat": 45.0, "lng": 9.5, "name": "Ticinus River", "desc": "First cavalry skirmish in Italy. Hannibal's Numidian light cavalry routed the Romans. Scipio (the elder) was wounded."},
            {"lat": 45.0, "lng": 9.7, "name": "Trebia River", "desc": "December 218 BCE. Hannibal lured the Romans across the freezing river, then ambushed them. 20,000 Romans killed or drowned. Elephants terrified the Roman cavalry."},
            {"lat": 43.5, "lng": 12.0, "name": "Lake Trasimene", "desc": "June 217 BCE. The greatest ambush in ancient history. Hannibal hid his army in fog along the lake shore. 15,000 Romans killed; Flaminius died. An earthquake accompanied the battle."},
            {"lat": 41.5, "lng": 15.5, "name": "Gerunium / Cannae", "desc": "August 2, 216 BCE. The perfect battle. 50,000 Romans encircled and annihilated in a double envelopment. 80 Roman senators died. The 'Cannae model' of battle is still taught. Hannibal did not march on Rome."},
            {"lat": 41.3, "lng": 14.5, "name": "Capua", "desc": "Hannibal's winter quarters. The luxury of Capua was said to have softened his army (Livy's moralistic view). Capua defected from Rome."},
            {"lat": 40.5, "lng": 17.0, "name": "Tarentum (Taranto)", "desc": "Captured the Greek city of Tarentum. The citadel held out, leaving the port unusable. Gradually, Rome recovered control."},
            {"lat": 41.5, "lng": 12.4, "name": "Porta Collina (Rome)", "desc": "Hannibal marched within 3 miles of Rome in 211 BCE. He rode to the Colline Gate and hurled a spear over the wall. But he could not besiege the city."},
            {"lat": 38.5, "lng": 16.0, "name": "Locri / Rhegium", "desc": "Scipio (the younger) captured Nova Carthago in Spain. Hannibal's brother Hasdrubal was killed at the Metaurus. The tide had turned."},
            {"lat": 38.0, "lng": 14.5, "name": "Crotona (last stand in Italy)", "desc": "By 204 BCE, Hannibal was cornered in Bruttium (toe of Italy). His brother Mago's invasion of Liguria had failed."},
            {"lat": 37.0, "lng": 7.5, "name": "Zama", "desc": "202 BCE. Final battle near Carthage. Hannibal fought Scipio Africanus. For the first time, Hannibal was defeated in a pitched battle — Scipio's cavalry feint and envelopment mirrored Hannibal's own tactics at Cannae."},
            {"lat": 33.0, "lng": 36.0, "name": "Exile: Tyre & Antiochus", "desc": "Hannibal fled Carthage and became an advisor to Antiochus III of Syria. His plans to invade Italy were ignored."},
            {"lat": 40.0, "lng": 29.0, "name": "Exile: Libyssa (Bithynia)", "desc": "Hannibal fled to Prusias of Bithynia. Surrounded by Roman agents, he poisoned himself at age 64, saying: 'Let us relieve the Romans of their fear.'"},
        ],
    },
    "jason": {
        "id": "jason",
        "name": "Jason & the Argonauts",
        "title": "The Voyage of the Argo",
        "description": "Jason's quest to retrieve the Golden Fleece from Colchis, accompanied by 50 of Greece's greatest heroes — including Hercules, Orpheus, and Castor and Pollux. The earliest Greek epic tradition (pre-Homeric, c. 1300 BCE), told in detail by Apollonius of Rhodes in the Argonautica (3rd c. BCE).",
        "color": "#4fc3f7",
        "factFile": {
            "source": "Apollonius of Rhodes, Argonautica (3rd c. BCE); Pindar, Pythian Odes; various lost epics",
            "period": "Late Bronze Age / Mycenaean (trad. 13th c. BCE) — written down in the Hellenistic period",
            "distance": "Approx. 2,000 nautical miles (round trip)",
            "duration": "Unknown — traditionally several months to years",
            "keyThemes": "Heroism and comradeship, the first voyage, encountering the unknown, betrayal (Medea's murder of her brother), the power of love and magic",
            "notableTexts": "Apollonius' Argonautica (the fullest surviving account), Pindar's Pythian 4, the lost Argonautica of Varro Atacinus",
            "legacy": "The Argo was the first ship ever built according to myth. The Argonautica influenced Virgil's Aeneid (Dido and Aeneas' love story borrows from Jason and Medea). The Golden Fleece may have represented the technique of gold-washing with sheepskins in Georgia.",
            "keyScholars": "Richard Hunter, R.L. Fowler, M.M. Gill, Timothy Gantz",
        },
        "stops": [
            {"lat": 39.35, "lng": 22.95, "name": "Iolcus (Volos, Greece)", "desc": "Jason demands the throne from Pelias, who sends him to fetch the Golden Fleece from Colchis. The Argo is built by Argus with Athena's help."},
            {"lat": 40.5, "lng": 23.0, "name": "Mount Pelion", "desc": "The centaur Chiron bids farewell to his pupil Jason. The heroes gather from all over Greece: Heracles, Orpheus, Castor and Pollux, Peleus (father of Achilles), and many more."},
            {"lat": 40.0, "lng": 25.5, "name": "Lemnos", "desc": "An island of women who had killed their husbands. Queen Hypsipyle seduced Jason. The Argonauts stayed for a year; Heracles urged them to leave."},
            {"lat": 39.5, "lng": 27.0, "name": "Mysia (Hylas)", "desc": "Heracles' beloved squire Hylas was abducted by a nymph. Heracles left the Argo to search for him — permanently. This story is one of the most poignant in the epic."},
            {"lat": 40.5, "lng": 28.0, "name": "Bithynia (Amycus)", "desc": "King Amycus challenged the Argonauts to a boxing match. Polydeuces (Pollux) defeated and killed him. The Bebrycians were terrorised no more."},
            {"lat": 41.0, "lng": 29.0, "name": "Salmydessus (Phineus)", "desc": "The blind prophet Phineus was tormented by the Harpies — half-woman, half-bird creatures who stole his food. The Boreads (winged sons of Boreas) chased the Harpies away, and Phineus told the Argonauts how to pass the Clashing Rocks."},
            {"lat": 41.1, "lng": 30.0, "name": "The Symplegades (Clashing Rocks)", "desc": "The greatest danger: two rocks that crashed together crushing any ship passing through. Jason released a dove between them; it lost only its tail feathers. The Argo shot through at the rebound, losing only the stern ornament. The rocks never moved again."},
            {"lat": 42.0, "lng": 35.0, "name": "Themiscyra (Amazon Country)", "desc": "Passed the land of the Amazons. Unlike Heracles' labour, the Argonauts avoided fighting them."},
            {"lat": 43.0, "lng": 38.0, "name": "Ares Island (Dia)", "desc": "Birds with bronze feathers rained down deadly darts. The Argonauts used the hero Cyzicus' strategy — shouting and banging shields to scare them off."},
            {"lat": 41.5, "lng": 41.0, "name": "Colehi (Aia)", "desc": "Arrived at Aea, capital of Colchis. King Aeëtes set three impossible tasks: ploughing with fire-breathing oxen, sowing dragon's teeth, and defeating the sleepless dragon."},
            {"lat": 41.5, "lng": 41.5, "name": "The Golden Fleece (Colchis)", "desc": "Aeëtes' daughter Medea, a sorceress, fell in love with Jason. She gave him a fireproof ointment and instructed him to throw a stone at the sown warriors — they fought and killed each other. Medea then lulled the dragon to sleep with a potion, and Jason took the Fleece."},
            {"lat": 42.5, "lng": 31.5, "name": "Flight: The Danube Route", "desc": "Medea fled Colchis with the Argonauts, taking her brother Apsyrtus. She killed and dismembered him, scattering the pieces — Aeëtes stopped to collect them, allowing the Argo to escape (the most chilling episode)."},
            {"lat": 44.5, "lng": 14.0, "name": "Circe's Island (Aeaea)", "desc": "Jason and Medea were purified by Circe (Medea's aunt) for the murder of Apsyrtus. Circe recognized Medea as a sorceress."},
            {"lat": 45.0, "lng": 13.5, "name": "The Sirens", "desc": "Orpheus sang a counter-melody so beautiful that the Argonauts forgot the Sirens. Only Boutes jumped overboard, but Aphrodite saved him."},
            {"lat": 44.4, "lng": 12.0, "name": "Scylla & Charybdis", "desc": "Thetis and the Nereids helped the Argonauts navigate the deadly strait, passing safely where Odysseus would later lose six men."},
            {"lat": 37.0, "lng": 13.0, "name": "Phaeacia (Corfu)", "desc": "Colchian pursuers caught up. King Alcinous decided Medea would stay if she was still a virgin — so Jason and Medea married that night in the Cave of Macris."},
            {"lat": 35.0, "lng": 25.0, "name": "Crete (Talos)", "desc": "The bronze giant Talos threw boulders at the Argo and heated himself red-hot to crush the ship. Medea cast a spell making him scrape his ankle on a rock — his single vein drained the ichor and he died."},
            {"lat": 36.5, "lng": 24.5, "name": "Anaphe Island", "desc": "A terrible storm drove the Argo off course. The Argonauts prayed to Apollo, who shot an arrow of light revealing a small island where they sheltered."},
            {"lat": 37.0, "lng": 23.5, "name": "Aegina", "desc": "Near the end of their journey. They stopped at Aegina, just off the coast of Attica, to refit and resupply."},
            {"lat": 39.35, "lng": 22.95, "name": "Return to Iolcus", "desc": "After many months and thousands of miles, the Argo returned to Iolcus. Jason dedicated the Argo to Poseidon on the Isthmus of Corinth. He gave the Golden Fleece to Pelias, but Medea later tricked Pelias' daughters into killing him. The Argo was immortalised as a constellation."},
        ],
    },
    "caesar": {
        "id": "caesar",
        "name": "Julius Caesar",
        "title": "Caesar's Gallic & Civil Wars",
        "description": "Gaius Julius Caesar (100-44 BCE) recorded his own campaigns in the Commentarii de Bello Gallico and De Bello Civili. In eight years he conquered Gaul, twice invaded Britain, and bridged the Rhine — then, in 49 BCE, crossed the Rubicon into Italy and ignited civil war against Pompey. Caesar is the only ancient general to write his own campaign memoirs, making this among the best-documented military careers of antiquity.",
        "color": "#d4ac0d",
        "factFile": {
            "source": "Caesar, Commentarii de Bello Gallico (7 books, 52-51 BCE) & Commentarii de Bello Civili (3 books, 47 BCE); Aulus Hirtius' continuation (Book 8); Plutarch, Life of Caesar; Appian, Civil Wars; Suetonius, Divus Julius",
            "period": "58-45 BCE (13 years of near-continuous campaigning)",
            "distance": "Approx. 15,000+ miles (cumulative marches across Gaul, Britain, Spain, Greece, Egypt, and Africa)",
            "duration": "13 years (58-45 BCE)",
            "keyThemes": "Imperial ambition, the general as author, clementia (Caesar's clemency), logistics and engineering (bridges, siege-works), the collapse of the Roman Republic",
            "notableTexts": "De Bello Gallico (written in the third person — 'Caesar' never 'I'), De Bello Civili (unfinished), Cicero's praise of Caesar's 'naked, upright' prose style",
            "legacy": "Caesar's conquest of Gaul brought Roman civilization to western Europe and fixed the Rhine as a frontier for four centuries. His crossing of the Rubicon (49 BCE) gave every language the phrase for an irrevocable decision. The Julian calendar, the month of July, and the imperial title 'Caesar' (German Kaiser, Russian Czar) all bear his name. His Commentarii became the standard Latin school text for two millennia.",
            "keyScholars": "T. Rice Holmes, Ronald Syme, Christian Meier, Adrian Goldsworthy, Mary Beard, Luciano Canfora",
        },
        "stops": [
            {"lat": 41.90, "lng": 12.49, "name": "Rome", "desc": "58 BCE. Caesar, consul for the year, departs for his provinces of Cisalpine Gaul, Transalpine Gaul, and Illyricum. He would not see Rome again for nine years."},
            {"lat": 46.20, "lng": 6.14, "name": "Geneva", "desc": "April 58 BCE. The Helvetii, fleeing Germanic pressure, planned to cross Roman territory. Caesar demolished the bridge over the Rhône and forced them to turn back. He raised two new legions in a fortnight."},
            {"lat": 46.86, "lng": 4.04, "name": "Bibracte", "desc": "58 BCE. Caesar defeated the migrating Helvetii near the Aeduan oppidum of Bibracte (Mont Beuvray). Of 368,000 said to have set out, only 110,000 returned home — ordered to rebuild the Swiss plateau."},
            {"lat": 47.6, "lng": 7.3, "name": "Battle against Ariovistus", "desc": "58 BCE. The Suebian king Ariovistus had settled in Alsace with 120,000 Germans. Caesar defeated him near the Vosges (Mulhouse/Belfort region). Germanic expansion west of the Rhine was halted for a generation."},
            {"lat": 50.4, "lng": 7.6, "name": "Crossing the Rhine", "desc": "55 BCE. To intimidate the Germanic Suebi, Caesar built a timber bridge across the Rhine near Coblenz in just ten days — an engineering marvel of the ancient world. He crossed, ravaged for 18 days, then returned and demolished it."},
            {"lat": 51.1, "lng": 1.3, "name": "First Invasion of Britain", "desc": "August 55 BCE. A reconnaissance in force. Caesar landed on the Kent coast (Deal/Dover) but storms wrecked his transport fleet and cavalry. After a skirmish he withdrew — claiming success before the Senate."},
            {"lat": 51.2, "lng": 1.0, "name": "Second Invasion of Britain", "desc": "54 BCE. A larger expedition with five legions. Caesar crossed the Thames, defeated Cassivellaunus, and extracted tribute and hostages. Britain was not conquered — but the Mediterranean world had its first detailed account of the island."},
            {"lat": 47.54, "lng": 4.49, "name": "Alesia", "desc": "September-October 52 BCE. The climax of the Gallic Wars. Vercingetorix holed up in the hillfort of Alesia (Alise-Sainte-Reine). Caesar built an 18km double wall — besieging the besiegers. Despite a relief army of 250,000 Gauls, Vercingetorix surrendered. Gaul was Roman."},
            {"lat": 44.0, "lng": 12.4, "name": "Crossing the Rubicon", "desc": "January 10, 49 BCE. 'Iacta alea est' — 'Let the die be cast.' Caesar, with the 13th Legion, crossed the Rubicon (a small river on his province's border), committing treason against the Senate and igniting civil war. Pompey fled Italy."},
            {"lat": 42.1, "lng": 13.85, "name": "Corfinium", "desc": "February 49 BCE. Caesar besieged the city held by Pompey's officer Domitius Ahenobarbus. The city fell; Caesar famously pardoned Ahenobarbus and his men — establishing the pattern of clementia Caesaris that won him support."},
            {"lat": 40.64, "lng": 17.94, "name": "Brundisium", "desc": "March 49 BCE. Caesar pursued Pompey to Brundisium (Brindisi), the chief port to Greece. Pompey escaped by sea. Caesar, lacking a fleet, returned to Rome and was appointed dictator — the first time of many."},
            {"lat": 39.30, "lng": 22.38, "name": "Pharsalus", "desc": "August 9, 48 BCE. The decisive battle. Pompey's 45,000 infantry and 7,000 cavalry outnumbered Caesar's 22,000 — but Caesar's veteran 4th line countered the cavalry charge. Pompey fled to Egypt. He was assassinated upon landing in Alexandria."},
            {"lat": 31.20, "lng": 29.92, "name": "Alexandria", "desc": "48-47 BCE. Caesar arrived in pursuit of Pompey — and found him dead, a gift from Ptolemy XIII. Caesar was trapped in the palace by Alexandrian mobs. Met Cleopatra (smuggled in rolled in a carpet) and fathered Caesarion. Won the Siege of Alexandria."},
            {"lat": 40.30, "lng": 35.89, "name": "Zela", "desc": "May 47 BCE. Marched 200 miles in 5 days to crush Pharnaces II (son of Mithridates) in Pontus. The lightning victory inspired the famous dispatch to Rome: 'Veni, vidi, vici' — 'I came, I saw, I conquered.'"},
            {"lat": 35.38, "lng": 11.07, "name": "Thapsus", "desc": "April 46 BCE. In Africa, the Pompeians regrouped with King Juba of Numidia. Caesar crushed them at Thapsus (Ras Dimas). Cato the Younger took his own life at Utica rather than seek Caesar's pardon."},
            {"lat": 37.58, "lng": -4.38, "name": "Munda", "desc": "March 17, 45 BCE. Caesar's hardest-fought and final battle — in Spain, against Pompey's sons Gnaeus and Sextus. It nearly cost him his life. After Munda, the war was over. Caesar returned to Rome in triumph."},
            {"lat": 41.90, "lng": 12.49, "name": "Rome — The Ides of March", "desc": "March 15, 44 BCE. Caesar was named dictator perpetuo (dictator for life) in February. A conspiracy led by Brutus and Cassius assassinated him in the Senate on the Ides of March — 23 stab wounds. His adopted heir Octavian (Augustus) would inherit both his name and his wars."},
        ],
    },
    "pytheas": {
        "id": "pytheas",
        "name": "Pytheas",
        "title": "Pytheas' Voyage to Thule",
        "description": "Pytheas of Massalia (Marseille), a Greek geographer and navigator, around 325 BCE sailed out of the Mediterranean and into the uncharted Atlantic — reaching Britain, the Scottish isles, and a land six days' sail north he called 'Thule', where the summer sun never set. His lost work On the Ocean survives only in fragments quoted — often with contempt — by later writers like Strabo and Polybius. It is the first recorded voyage of a Mediterranean explorer beyond the Pillars of Hercules.",
        "color": "#26a69a",
        "factFile": {
            "source": "Pytheas, On the Ocean (c. 320 BCE) — lost; surviving fragments quoted in Strabo's Geography Book 4, Polybius' Histories Book 34, Diodorus Siculus, Pliny's Natural History, and Geminus of Rhodes",
            "period": "c. 325-320 BCE (the era of Alexander the Great)",
            "distance": "Approx. 7,000+ miles round trip from Marseille",
            "duration": "Several years (c. 325-320 BCE)",
            "keyThemes": "Geographical discovery, the limits of the oikoumene (known world), the midnight sun, the 'sea lung' (drifting pack ice), the tin and amber trade, navigation by the sun",
            "notableTexts": "On the Ocean — surviving only in hostile quotations, mostly in Strabo's Geography and Polybius",
            "legacy": "'Thule' became the classical symbol of the uttermost edge of the world — the Romans' ultima Thule, later a name for Iceland and Greenland. Pytheas' 'sea lung' is the first description of polar ice in Western literature. His latitude measurements were remarkably accurate. For centuries, his voyage was dismissed as fantasy — until modern scholarship vindicated him.",
            "keyScholars": "Sir Barry Cunliffe (The Extraordinary Voyage of Pytheas the Greek, 2001), Rhys Carpenter, S. Marinatos, D.W. Roller, S. Bianchetti",
        },
        "stops": [
            {"lat": 43.30, "lng": 5.37, "name": "Massalia (Marseille)", "desc": "c. 325 BCE. Pytheas, a citizen of Massalia, departs — perhaps as part of a tin-trading expedition, perhaps as a scientific explorer. He took detailed measurements of latitude, tides, and the sun's height all along his route."},
            {"lat": 36.0, "lng": -5.35, "name": "Pillars of Hercules (Gibraltar)", "desc": "Passed through the Strait of Gibraltar — the edge of the Mediterranean. Later geographers doubted Pytheas could have passed the Carthaginian guard-ships that watched the strait; he may have traveled overland through Gaul to Brittany instead."},
            {"lat": 36.53, "lng": -6.29, "name": "Gades (Cadiz)", "desc": "Visited the great Phoenician port of Gades, the center of the tuna fisheries and a trading hub for Atlantic tin. Pytheas noted the remarkably high tides here, unknown in the Mediterranean."},
            {"lat": 42.9, "lng": -9.27, "name": "Cape Finisterre (Galicia)", "desc": "Sailed north along the Atlantic coast of Iberia. Pytheas described the coast of the Artabri and the rich trade in tin and gold at the river-mouths of northwestern Spain."},
            {"lat": 48.46, "lng": -5.12, "name": "Ushant (Brittany)", "desc": "Reached the land of the Ostimii, the 'people of the mouth of the ocean'. Pytheas described an immense tidal bore — likely the tidal range of the Bay of Biscay and Channel, double what he had seen at Cadiz."},
            {"lat": 50.07, "lng": -5.71, "name": "Belerion (Cornwall)", "desc": "Reached the tin-producing peninsula of Cornwall. Pytheas gave a detailed account of how the Britons mined tin, refined it, and traded it overland to the Mediterranean — confirming the source of the bronze-age tin trade."},
            {"lat": 51.5, "lng": -2.0, "name": "Circumnavigating Britain", "desc": "Pytheas circumnavigated the island, describing it as triangular with three capes (Kent, Cornwall, north Scotland) — a shape recognizably accurate. He estimated its circumference at perhaps 4,000 miles. He noted the long summer days."},
            {"lat": 55.0, "lng": -3.0, "name": "Northern Britain", "desc": "Sailed up the west coast of Britain. Pytheas reported the people of the north subsisted on millet, roots, and fish — and that the summer night was short enough to be 'almost lost'. Some of his latitude observations were within 1° of modern values."},
            {"lat": 58.98, "lng": -2.96, "name": "Orcades (Orkney)", "desc": "Reached the Orkney Islands, which Pytheas described as a cluster of islands off the northernmost tip of Britain. He called them 'Orcades' — a name still used today. From here he turned north into the open sea."},
            {"lat": 63.43, "lng": 10.40, "name": "Thule", "desc": "Six days' sail north of Britain — near the Arctic Circle. Pytheas reported that at the summer solstice the sun never set (the midnight sun) and at the winter solstice barely rose. Likely Trondheim in Norway (or possibly Iceland). The most northerly point any Greek had ever reached."},
            {"lat": 66.0, "lng": 11.0, "name": "The 'Sea Lung' (Polar Ice)", "desc": "Beyond Thule, Pytheas reported, the sea became 'a lung' — neither land nor water, on which one could neither walk nor sail. This is the first description in Western literature of drifting pack ice (pancake ice) at the edge of the polar sea — a place where Mediterranean man had no frame of reference."},
            {"lat": 54.18, "lng": 7.89, "name": "Abalus (Amber Island)", "desc": "On his return, Pytheas visited an island where amber was washed up on the shore — he identified it as congealed sea-foam. Likely Heligoland or the coast of the Baltic. He learned amber was traded to the Mediterranean by long overland routes."},
            {"lat": 43.30, "lng": 5.37, "name": "Return to Massalia", "desc": "After years abroad, Pytheas returned home to Massalia and wrote On the Ocean. The work was met with skepticism in his lifetime and is now lost — surviving only in fragments quoted by later geographers, several of whom (like Strabo) called him a liar. Modern scholarship has largely vindicated his remarkable voyage."},
        ],
    },
    "paul": {
        "id": "paul",
        "name": "Paul of Tarsus",
        "title": "The Missionary Journeys of Paul",
        "description": "Paul of Tarsus (c. 5-64/67 CE) — a Hellenized Jewish Pharisee, Roman citizen, and follower of Jesus of Nazareth — undertook three missionary journeys across the eastern Mediterranean, and a final voyage as a prisoner to Rome. Recorded in the Acts of the Apostles and Paul's own letters, his travels founded the first Christian communities in Asia Minor, Greece, and Italy — turning a small Jewish sect into a religion of the Greco-Roman world.",
        "color": "#7986cb",
        "factFile": {
            "source": "Acts of the Apostles (c. 80-90 CE), chapters 9, 13-28; the Pauline Epistles (c. 50-60 CE): Romans, 1 & 2 Corinthians, Galatians, Ephesians, Philippians, 1 Thessalonians, Philemon",
            "period": "46-60 CE",
            "distance": "Approx. 10,000+ miles (cumulative, by land and sea)",
            "duration": "14 years of travel (46-60 CE)",
            "keyThemes": "The spread of a new faith across the Empire, Hellenistic Judaism, Roman citizenship, the road network (the Via Egnatia), the perils of ancient sea travel",
            "notableTexts": "Acts 13-28 (the journey narratives); Paul's letters — among the earliest Christian writings, predating the gospels",
            "legacy": "Paul's journeys transformed a movement within Judaism into a world religion. His letters to his congregations are the earliest Christian texts — older than the gospels — and shaped Western theology for two millennia. The cities he visited (Ephesus, Corinth, Philippi) and even the route of his shipwreck on Malta are documented archaeologically.",
            "keyScholars": "F.F. Bruce, Martin Hengel, James D.G. Dunn, E.P. Sanders, N.T. Wright, Craig Keener",
        },
        "stops": [
            {"lat": 36.20, "lng": 36.16, "name": "Antioch on the Orontes", "desc": "46 CE. The first journey begins. Antioch — the third city of the Empire, where the term 'Christian' was first coined (Acts 11:26) — sent Paul and Barnabas off, fasting and laying hands on them."},
            {"lat": 35.19, "lng": 33.92, "name": "Salamis (Cyprus)", "desc": "Sailed first to Salamis, on the east coast of Cyprus, Barnabas' home island. Preached in the synagogues. John Mark, a young relative of Barnabas, traveled as their assistant."},
            {"lat": 34.77, "lng": 32.42, "name": "Paphos", "desc": "At the Roman capital of Cyprus, the proconsul Sergius Paulus summoned Paul — but was opposed by a Jewish sorcerer, Elymas. Paul struck him blind. Sergius Paulus believed. Paul's name shifts here from 'Saul' to 'Paulus' — possibly the proconsul's patronage."},
            {"lat": 36.96, "lng": 30.85, "name": "Perga (Pamphylia)", "desc": "Crossed to the mainland. John Mark abandoned the journey here and returned to Jerusalem — a desertion Paul would later bitterly recall."},
            {"lat": 38.25, "lng": 31.18, "name": "Pisidian Antioch", "desc": "Climbed into the highlands. In the synagogue, Paul preached the first recorded Christian sermon — that Jesus fulfilled the prophets. Many Gentiles begged to hear more. The Jews drove him out."},
            {"lat": 37.87, "lng": 32.48, "name": "Iconium", "desc": "Preached to a divided city — Jews and Gentiles. A plot to stone him forced him to flee."},
            {"lat": 37.65, "lng": 32.30, "name": "Lystra", "desc": "Healed a man lame from birth. The crowd, astonished, declared Paul 'Hermes' and Barnabas 'Zeus' — and tried to offer them sacrifice. Then Jews from Antioch turned the crowd; Paul was stoned and left for dead. He rose and went back into the city."},
            {"lat": 37.40, "lng": 33.10, "name": "Derbe — Return to Antioch", "desc": "Won many disciples in Derbe. Then retraced his steps through Lystra, Iconium, and Pisidian Antioch — appointing elders in each church. The first journey (46-48 CE) ended where it began, at Antioch."},
            {"lat": 39.72, "lng": 26.18, "name": "Troas (2nd Journey, 49 CE)", "desc": "After the Jerusalem Council (c. 49 CE), Paul set out again with Silas. In Troas — near ancient Troy — Paul dreamed of a Macedonian crying, 'Come over to Macedonia and help us!' He sailed at once. The gospel crossed into Europe."},
            {"lat": 41.01, "lng": 24.28, "name": "Philippi", "desc": "The first European convert: Lydia, a dealer in purple cloth from Thyatira, by the river. Paul cast a spirit of divination out of a slave girl — and was beaten and imprisoned. An earthquake opened the doors; the jailer, about to kill himself, was converted instead. Paul, a Roman citizen, demanded an apology."},
            {"lat": 40.64, "lng": 22.94, "name": "Thessalonica", "desc": "Preached three Sabbaths in the synagogue. Many Greeks believed — but a riot forced him out by night. He wrote to the Thessalonians from Corinth — possibly the earliest surviving Christian text."},
            {"lat": 40.52, "lng": 22.20, "name": "Berea (Veria)", "desc": "The Jews of Berea 'examined the Scriptures daily' to test Paul's message — praised as nobler than the Thessalonians. But Thessalonian Jews came and stirred up trouble; Paul was sent on to the coast."},
            {"lat": 37.98, "lng": 23.73, "name": "Athens", "desc": "Waited in Athens for Silas and Timothy. Distressed by the city's idols, he debated in the marketplace with Stoics and Epicureans, and was summoned to the Areopagus. His sermon there — invoking an altar 'To an Unknown God' — converted few but became one of the most famous speeches in history."},
            {"lat": 37.94, "lng": 22.93, "name": "Corinth", "desc": "Stayed 18 months with the tentmakers Aquila and Priscilla — Jews expelled from Rome by Claudius. He wrote 1 and 2 Thessalonians here. Brought before the proconsul Gallio (whose term, AD 51-52, dates the journey precisely). The church he founded would receive his longest letter."},
            {"lat": 37.94, "lng": 27.34, "name": "Ephesus (3rd Journey, 53 CE)", "desc": "Returned on his third journey and stayed nearly three years. Taught in the lecture hall of Tyrannus. Wrote 1 Corinthians here. The silversmith Demetrius — whose idol trade suffered — stirred a riot in the great theater. 'Great is Artemis of the Ephesians!' the crowd shouted for two hours."},
            {"lat": 39.72, "lng": 26.18, "name": "Troas — Eutychus", "desc": "On his way back to Jerusalem, Paul preached late into the night at Troas. A young man named Eutychus, sitting in the window, fell asleep and fell three stories to his death. Paul embraced him and restored him to life."},
            {"lat": 37.53, "lng": 27.28, "name": "Miletus", "desc": "Called the elders of the Ephesian church to meet him here — rather than returning to Ephesus. He delivered a tearful farewell, predicting he would see them no more: 'I do not count my life of any value...so that I may finish my course.'"},
            {"lat": 31.78, "lng": 35.22, "name": "Jerusalem (Arrest, 57 CE)", "desc": "Despite warnings, Paul went up to Jerusalem for Pentecost. He was seized in the Temple by a mob — accused of bringing a Gentile inside. Rescued by Roman soldiers, he gave his defense — and revealed he was a Roman citizen. This entitled him to appeal to Caesar."},
            {"lat": 32.50, "lng": 34.90, "name": "Caesarea Maritima", "desc": "Held two years (c. 57-59 CE) in Herod's palace at Caesarea — the Roman capital of Judaea. Argued his case before Felix, Festus, and Herod Agrippa II. When Festus proposed a trial in Jerusalem, Paul invoked his right as a citizen: 'I appeal to Caesar.' To Rome he would go."},
            {"lat": 36.25, "lng": 29.97, "name": "Myra & Crete (Voyage to Rome)", "desc": "Sailed as a prisoner on a grain ship — first to Sidon, then to Myra in Lycia, where he transferred to an Alexandrian grain freighter. They put in at Fair Havens on Crete. Paul warned against continuing; the centurion ignored him."},
            {"lat": 35.95, "lng": 14.40, "name": "Malta — The Shipwreck", "desc": "A 'northeaster' (the Euroclydon) drove the ship for 14 days. The vessel struck a sandbar and broke apart. All 276 aboard swam or floated to shore — the island of Malta. Paul was bitten by a viper; the locals called him a murderer, then a god. He healed the governor Publius' father and stayed the winter."},
            {"lat": 37.07, "lng": 15.29, "name": "Syracuse", "desc": "Spring 60 CE. Sailed on an Alexandrian ship (the Twin Brothers) — first to Syracuse, the great Greek city of Sicily, where Paul stayed three days."},
            {"lat": 40.83, "lng": 14.12, "name": "Puteoli (Pozzuoli)", "desc": "Sailed up the Italian coast to Puteoli — the chief port of Rome. Here believers welcomed Paul for a week. Word of his arrival reached Rome."},
            {"lat": 41.90, "lng": 12.49, "name": "Rome", "desc": "60-62 CE. Paul arrived in Rome — under guard, but allowed to live in his own rented house. For two years he preached 'with all boldness and without hindrance'. Tradition holds he was martyred here under Nero (c. 64-67 CE). The journey that began at Antioch had reached the heart of the Empire."},
        ],
    },
    "spartacus": {
        "id": "spartacus",
        "name": "Spartacus",
        "title": "The Third Servile War (Spartacus)",
        "description": "Spartacus, a Thracian gladiator enslaved at the school of Capua, led the greatest slave revolt of antiquity — the Third Servile War (73-71 BCE). From a break-out of 70 gladiators, his army of escaped slaves grew to perhaps 120,000, defeating legion after legion as they marched the length of Italy. They were finally crushed by Marcus Licinius Crassus. 6,000 captives were crucified along the Appian Way between Capua and Rome.",
        "color": "#8d6e63",
        "factFile": {
            "source": "Plutarch, Life of Crassus 8-11 (the fullest account); Appian, Civil Wars 1.116-120; Sallust, Histories (fragments); Florus, Epitome of Roman History 2.8; Orosius, Against the Pagans",
            "period": "73-71 BCE",
            "distance": "Approx. 1,500+ miles (marching up and down the length of Italy)",
            "duration": "2+ years (73-71 BCE)",
            "keyThemes": "Slavery and resistance, gladiatorial combat, Roman military panic (tumultus), the fragility of the Republic's social order, the Roman fear of the servile",
            "notableTexts": "Plutarch's Life of Crassus (the primary source), Appian's Civil Wars, Sallust's Histories (surviving fragments)",
            "legacy": "Spartacus became the enduring symbol of resistance to oppression. The 19th-century novel Raffaello Giovagnoli's Spartaco and the 1960 Kirk Douglas film cemented his myth. In antiquity, Rome lived in such dread of another Spartacus that laws restricting gladiatorial schools were passed — and the word 'servile war' became a watchword for slave insurrection.",
            "keyScholars": "Aldo Schiavone (Spartacus, 2011), Keith Bradley, Theresa Urbainczyk, M.J. Trow, Allen M. Ward",
        },
        "stops": [
            {"lat": 41.08, "lng": 14.25, "name": "Capua — The Break-Out", "desc": "73 BCE. In the gladiator school (ludus) of Lentulus Batiatus at Capua — where Spartacus, Crixus, and Oenomaus were trained to kill for sport — about 70 gladiators broke out using kitchen knives and spits. They seized gladiatorial weapons and fled."},
            {"lat": 40.82, "lng": 14.43, "name": "Mount Vesuvius", "desc": "The fugitives fortified themselves on the dormant volcano. The Romans sent 3,000 men under praetor Claudius Glaber, who simply blockaded the single path. Spartacus' men wove ladders of wild vines, climbed down the cliff face, and ambushed Glaber from behind — routing him. The revolt was now a war."},
            {"lat": 40.5, "lng": 15.0, "name": "Lucania — Two Praetors Defeated", "desc": "Spartacus' army swelled with escaped slaves, herdsmen, and dispossessed. He defeated two more praetors — Varinius and his deputies — seizing their fasces and lictors. The slaves now had proper Roman weapons, armor, and horses."},
            {"lat": 41.3, "lng": 14.6, "name": "March on the Alps", "desc": "Spartacus' aim was to lead his people over the Alps and home — to Thrace, Gaul, or wherever they had come from. He marched north through Samnium, gathering wagons, supplies, and recruits at every step."},
            {"lat": 44.65, "lng": 10.92, "name": "Mutina (Modena)", "desc": "71 BCE. At Mutina, the slaves routed a Roman army under the consul Gaius Cassius Longinus and the proconsul Gnaeus Manlius. The road to the Alps — and freedom — lay open. But Spartacus turned south. He had no intention of leaving Italy."},
            {"lat": 43.0, "lng": 11.5, "name": "Turn Back South", "desc": "Rather than cross the Alps, Spartacus turned his army around. Sources disagree why — perhaps he feared the Gauls' loyalty, perhaps he saw opportunity in Italy's weakness. The march south was the fateful decision of the war."},
            {"lat": 42.85, "lng": 13.58, "name": "Picenum", "desc": "In central Italy, Spartacus defeated the consular armies of Lentulus and Gellius — killing Crixus, his old comrade, who had split off with a Gaulish contingent. Spartacus forced Roman captives to fight as gladiators in funeral games for Crixus — a bitter inversion."},
            {"lat": 39.75, "lng": 16.50, "name": "Thurii (Sibari)", "desc": "Retreated to the south. At Thurii, Spartacus established a base — issuing his own coinage. He tried to negotiate with Cilician pirates for ships to cross to Sicily, but the pirates betrayed him. He was now trapped in the toe of Italy."},
            {"lat": 38.8, "lng": 16.2, "name": "Bruttium — Crassus' Wall", "desc": "Crassus, appointed to crush the revolt, trapped Spartacus in the Bruttium peninsula by building a wall and ditch across the toe of Italy — 55 km (37 miles) long, from sea to sea. Spartacus crucified a Roman prisoner before the wall in defiance."},
            {"lat": 39.5, "lng": 16.0, "name": "Break-Out at the Wall", "desc": "In a snowstorm, Spartacus broke through Crassus' wall with a third of his army. He inflicted heavy losses on the Romans in the Lucanian mountains — but Pompey was returning from Spain, and Crassus wanted the victory for himself."},
            {"lat": 40.25, "lng": 15.20, "name": "The Silarus River (Final Battle)", "desc": "71 BCE. On the Silarus (Sele) river, near Paestum, Spartacus turned to face Crassus. He killed his horse before the battle, declaring that if he won he would have many. He fought in the front rank and fell, struck down by missiles. His body was never found. The revolt was over."},
            {"lat": 41.25, "lng": 13.6, "name": "The Appian Way — Crucifixions", "desc": "6,000 surviving slaves were crucified along the 200 km of the Appian Way from Capua to Rome. They hung there for years, a warning to every slave in Italy. Pompey, returning from Spain, mopped up 5,000 fugitives — and claimed credit for ending the war. Crassus was awarded an ovation; Pompey a full triumph."},
        ],
    },
}

# ---------------------------------------------------------------------------
# ANCIENT SOURCE CONNECTIONS — historical events cross-referenced in
# literature and material culture. Each event lists the sources that mention
# it, with a citation and an explanation of *why* that source raises it.
# ---------------------------------------------------------------------------
EVENTS = {
    "actium": {
        "id": "actium",
        "name": "Battle of Actium",
        "date": "September 2, 31 BCE",
        "location": "Ionian Sea, off the coast of Epirus (Greece)",
        "lat": 38.93, "lng": 20.74,
        "summary": "The decisive naval engagement of the Final War of the Roman Republic. Octavian's fleet, commanded by Marcus Vipsanius Agrippa, defeated the combined fleets of Mark Antony and Cleopatra VII of Egypt. Antony's heavier eastern fleet could not manoeuvre in the bay of Ambracia; when Cleopatra's Egyptian squadron broke through and fled, Antony followed. The victory left Octavian master of the Mediterranean and ended a century of civil war. Within three years he was Augustus, first Roman emperor.",
        "keyFigures": ["Octavian (Augustus)", "Marcus Vipsanius Agrippa", "Mark Antony", "Cleopatra VII"],
        "consequences": "End of the Roman Republic; founding of the Principate under Augustus; annexation of Egypt as a Roman province; death of Antony and Cleopatra the following year.",
        "sources": [
            {
                "type": "literature",
                "author": "Virgil",
                "work": "Aeneid",
                "citation": "Book 8, lines 675-713 (the Shield of Aeneas)",
                "reference": "Augustus Caesar stands at Actium on the shield forged by Vulcan; Apollo's temple overlooks the battle, and the Egyptian fleet — with their strange gods and Cleopatra's sistrum-rattling — is driven back. The Nile mourns.",
                "why": "Written c. 29-19 BCE under Augustus' patronage, the Aeneid turns Actium into mythic history: Augustus is shown as the fulfilment of Aeneas' destiny. The battle on the shield is the political and theological centrepiece of the poem — it reframes a civil war as a war of Roman gods against eastern monsters.",
            },
            {
                "type": "literature",
                "author": "Horace",
                "work": "Odes",
                "citation": "Odes 1.37 (the 'Nunc est bibendum' ode)",
                "reference": "'Now we must drink — the time has come to dance.' Horace celebrates Cleopatra's defeat, expecting her to lead a Roman triumph. Instead, she killed herself — and the poem ends praising her courage: 'a woman not to be humbled.'",
                "why": "Horace, a client of Maecenas (Augustus' minister), wrote public celebration poetry. This ode captures the public mood in 30 BCE and strikingly turns from contempt for the 'fatale monstrum' (doomed monster) to admiration for Cleopatra's noble suicide — a literary feat.",
            },
            {
                "type": "inscription",
                "author": "Augustus",
                "work": "Res Gestae Divi Augusti",
                "citation": "§25-26 (the Achievements of the Divine Augustus)",
                "reference": "'I entirely subdued the regions of the sea and land...by which battle I captured the enemy fleet.' Augustus claims he won by his own command — omitting Agrippa, who actually directed the fleet. He also boasts of a victory at Actium dedicated on the site as the Nicopolis monument.",
                "why": "The Res Gestae is Augustus' own political autobiography, inscribed on bronze outside his mausoleum and copied across the Empire. It is the template of imperial propaganda — presenting a civil war as a foreign war against Egypt, not fellow Romans.",
            },
            {
                "type": "literature",
                "author": "Cassius Dio",
                "work": "Roman History",
                "citation": "Book 50, chapters 12-35",
                "reference": "Dio's detailed account covers the preliminaries, the battle, and the flight of Antony and Cleopatra. He notes Antony's larger ships were unable to manoeuvre, that Cleopatra fled first, and that Antony followed her rather than continue the fight. He preserves the rumour that Cleopatra was fleeing as a pre-arranged signal.",
                "why": "Writing in the early 3rd century CE, Dio had access to sources now lost (including Augustus' own memoirs and the histories of Asinius Pollio). He gives the most complete surviving narrative and is sceptical of Augustus' self-presentation, treating Actium as a civil war rather than a foreign victory.",
            },
            {
                "type": "literature",
                "author": "Plutarch",
                "work": "Life of Antony",
                "citation": "Chapters 65-68",
                "reference": "Plutarch describes Antony's despondency before the battle, his flight after Cleopatra, and the terrible aftermath. He preserves the famous detail that when Antony's infantry surrendered, Octavian allowed them to intermingle with his own men so as not to humiliate them.",
                "why": "Plutarch's 'Life of Antony' (early 2nd c. CE) is the literary counterpoint to Augustan propaganda. It humanises Antony, makes the love story with Cleopatra tragic rather than political, and was the chief source Shakespeare later used for his play.",
            },
            {
                "type": "material",
                "author": "(Augustan builders)",
                "work": "Nicopolis Victory Monument",
                "citation": "Nicopolis, Epirus (modern Greece) — founded 29 BCE",
                "reference": "Augustus founded the city of Nicopolis ('Victory City') on the site of his camp, dedicating the spoils of Actium. The monument featured bronze rams from the captured Egyptian fleet set in a wall, and the site hosted the Actian Games every five years.",
                "why": "The monumental spoils (some rams are now identified in excavations) are the physical embodiment of Augustus' victory. The victory monument and the games institutionalised Actium as the founding event of the regime — a sacred place of pilgrimage for the new imperial order.",
            },
        ],
    },
    "thermopylae": {
        "id": "thermopylae",
        "name": "Battle of Thermopylae",
        "date": "August 480 BCE",
        "location": "Thermopylae pass, central Greece",
        "lat": 38.80, "lng": 22.56,
        "summary": "In the second Persian invasion of Greece, the Spartan king Leonidas and roughly 7,000 Greeks held the narrow coastal pass of Thermopylae against Xerxes' army, perhaps 150,000 strong. After two days of holding, they were betrayed by Ephialtes, who showed the Persians a mountain path (the Anopaea path) that allowed them to turn the Greek position. Leonidas dismissed most of the army and stayed with 300 Spartans, 700 Thespians, and 400 Thebans. They fought to the last man. The stand bought time for the Greek fleet and became the emblem of self-sacrifice for a free polity.",
        "keyFigures": ["Leonidas I (Sparta)", "Xerxes I (Persia)", "Ephialtes (traitor)", "Demophilus (Thespiae)"],
        "consequences": "Temporary Persian breakthrough into central Greece; sack of Athens; but the delay allowed the Greek fleet to withdraw and regroup, leading to victory at Salamis weeks later — the turning point of the war.",
        "sources": [
            {
                "type": "literature",
                "author": "Herodotus",
                "work": "Histories",
                "citation": "Book 7, chapters 175-234",
                "reference": "The founding account. Herodotus records Leonidas' dispatch of the dismissable allies, the role of the 700 Thespians who refused to leave, the betrayal by Ephialtes, and the final stand. He preserves the epitaph composed by Simonides: 'Stranger, go tell the Spartans that here, obedient to their laws, we lie.'",
                "why": "Herodotus wrote within living memory (c. 440 BCE) and likely spoke with survivors' descendants. For him, Thermopylae demonstrates the Greek principle that free men fighting for law will outfight subjects driven by the lash — the moral thesis of the entire Histories.",
            },
            {
                "type": "material",
                "author": "(Simonides of Ceos, attributed)",
                "work": "Epitaph of the Spartans",
                "citation": "Stone inscription at the site (a Hellenistic or Roman copy survives in the British Museum)",
                "reference": "'Ὦ ξεῖν', ἀγγέλλειν Λακεδαιμονίοις ὅτι τῇδε κείμεθα, τοῖς κείνων ῥήμασι πειθόμενοι.' — 'Stranger, go tell the Spartans that here we lie, obedient to their orders.'",
                "why": "The most famous epitaph in Greek literature and one of the most quoted lines of antiquity. It distilled the Spartan ethos — obedience to law over life — and made the 300 a permanent symbol. The survival of the inscription's text allowed the legend to outlast the battle.",
            },
            {
                "type": "literature",
                "author": "Diodorus Siculus",
                "work": "Bibliotheca historica",
                "citation": "Book 11, chapters 4-11",
                "reference": "Diodorus follows Ephorus' account. He adds the detail that Leonidas ordered the allies to depart because provisions were exhausted — and that the Thespians refused to leave, declaring they would not abandon Leonidas.",
                "why": "Diodorus (1st c. BCE) preserves the 4th-century historian Ephorus, now lost. His account is a corrective to the romanticisation of the 300 Spartans — the 700 Thespians who stayed voluntarily deserve equal honour, and Diodorus preserves this.",
            },
            {
                "type": "literature",
                "author": "Plutarch",
                "work": "Moralia — 'Sayings of Spartans'",
                "citation": "Sayings of Spartans 225 (Leonidas)",
                "reference": "Plutarch preserves aphorisms attributed to Leonidas. When his wife Gorgo asked what she should do, he said: 'Marry a good man and bear good children.' When told the Persian arrows would blot out the sun, he replied: 'Then we shall fight in the shade.'",
                "why": "Plutarch (1st-2nd c. CE) collects the laconic Spartan tradition. These sayings shaped the cultural memory of Thermopylae — the image of the laconic, fearless Spartan was forged as much in these apophthegms as in Herodotus.",
            },
            {
                "type": "material",
                "author": "(Greek League)",
                "work": "Polyandrion (collective tomb) of the Thespians",
                "citation": "Excavated at the site in modern times; a free-standing lion monument also marked the Spartan tomb",
                "reference": "A stone lion honoured the Spartans (Plutarch records it was funded from Persian spoils). The Thespian dead received their own polyandrion — a communal burial mound — whose excavation in the 20th century revealed the human cost beneath the legend.",
                "why": "The monuments are the material witness that the dead were honoured as a group, not merely as propaganda. The lion of Thermopylae inspired the modern reconstruction; the Thespian mound restores the non-Spartans to the historical record that Spartan-centric sources downplay.",
            },
        ],
    },
    "salamis": {
        "id": "salamis",
        "name": "Battle of Salamis",
        "date": "September 480 BCE",
        "location": "Straits of Salamis, near Athens",
        "lat": 37.96, "lng": 23.51,
        "summary": "A naval battle in the straits between Salamis and the mainland, in which the Greek fleet of about 370 triremes defeated a larger Persian fleet. Themistocles lured the Persians into the narrow strait where their numerical advantage became a liability. Xerxes watched from a throne on the mainland. The victory ended the Persian threat to Greece and established Athens as a naval power — the foundation of the Delian League and the Athenian empire that followed.",
        "keyFigures": ["Themistocles (Athens)", "Xerxes I (Persia)", "Aristides (Athens)", "Eurybiades (Sparta, nominal commander)"],
        "consequences": "Persian naval power broken; Xerxes withdraws to Asia with much of his army; Athens rebuilt and enters its golden age under the Delian League; the seeds of the Peloponnesian War are sown by Athenian naval supremacy.",
        "sources": [
            {
                "type": "literature",
                "author": "Aeschylus",
                "work": "The Persians",
                "citation": "Lines 353-432 (the Messenger's speech)",
                "reference": "Aeschylus — who fought at Salamis — stages the battle through the voice of a Persian messenger reporting the disaster to Xerxes' mother Atossa. The cries of 'O sons of the Greeks' as the Greek fleet advanced are preserved verbatim.",
                "why": "The Persians (472 BCE) is the only surviving Greek tragedy on a contemporary event, performed eight years after the battle. It is the earliest surviving account of Salamis — and unique in presenting the victory from the enemy's perspective, making Greek triumph a meditation on the fragility of human fortune.",
            },
            {
                "type": "literature",
                "author": "Herodotus",
                "work": "Histories",
                "citation": "Book 8, chapters 40-96",
                "reference": "Herodotus recounts Themistocles' ruse (a fake message luring Xerxes to attack), the narrow fighting where the Persian fleet could not manoeuvre, and the rout. He records that the Greeks 'fought in good order' while the Persians 'showed no less courage but were unarmed and unskilled.'",
                "why": "Herodotus wrote c. 440 BCE, with access to participants. He frames Salamis as the proof that Greek liberty and skill defeated Persian numbers — the moral thesis of his work. He also preserves the dispute over which Greek city deserved the prize for valour (each voted for itself).",
            },
            {
                "type": "material",
                "author": "(Athenian state)",
                "work": "Themistocles Decree (Troezen inscription)",
                "citation": "Inscription found at Troezen, 1959; 3rd-century BCE copy of a 480 BCE decree",
                "reference": "The decree records Themistocles' evacuation of Athens: 'the city shall be entrusted to Athena...and the gods...the women and children shall be evacuated to Troezen.' It also recalls the fleet and the imprecation to trust 'the wooden walls' (the ships).",
                "why": "This inscription is among the most important documents of Greek history — a near-contemporary (3rd c. BCE) copy of the actual decree that mobilised Athens for Salamis. It grounds Herodotus' literary account in state record-keeping and reveals the mechanics of the evacuation.",
            },
            {
                "type": "literature",
                "author": "Plutarch",
                "work": "Life of Themistocles",
                "citation": "Chapters 12-15",
                "reference": "Plutarch describes Themistocles' stratagem — sending his slave Sicinnus to Xerxes with the false message that the Greeks were about to flee — and the subsequent debate in which the allies nearly withdrew before Themistocles forced the engagement.",
                "why": "Plutarch (c. 100 CE) draws on sources now lost and gives the human face of the battle: Themistocles' cunning, the resentment of his peers, and the long-term jealousy that would later ostracise him. Salamis made Themistocles — and ultimately destroyed him.",
            },
        ],
    },
    "pharsalus": {
        "id": "pharsalus",
        "name": "Battle of Pharsalus",
        "date": "August 9, 48 BCE",
        "location": "Plain of Pharsalus, Thessaly (Greece)",
        "lat": 39.30, "lng": 22.38,
        "summary": "The decisive battle of Caesar's Civil War. Pompey the Great, with perhaps 45,000 infantry and 7,000 cavalry, outnumbered Caesar's roughly 22,000 infantry and 1,000 cavalry two-to-one. Pompey's cavalry under Labienus attempted to outflank Caesar's right — but Caesar had concealed a fourth line of veteran infantry, who drove off the cavalry with their pila used as spears. Pompey's lines collapsed. He fled to Egypt and was assassinated. The Republic effectively died at Pharsalus.",
        "keyFigures": ["Julius Caesar", "Gnaeus Pompeius Magnus (Pompey)", "Titus Labienus", "Mark Antony"],
        "consequences": "Effective end of Roman Republican government; Pompey's murder in Egypt days later; Caesar becomes master of Rome; the path to the imperial autocracy is open.",
        "sources": [
            {
                "type": "literature",
                "author": "Julius Caesar",
                "work": "Commentarii de Bello Civili (Civil War)",
                "citation": "Book 3, chapters 88-99",
                "reference": "Caesar's own account, written in the third person. He describes Pompey's cavalry charge, his concealed fourth line, the rout, and — uniquely — expresses regret: 'They had wished for this — that I, Gaius Caesar, after so many great services, should be driven to my death by my own soldiers.' He claims Pompey fled to his camp without a word.",
                "why": "Caesar's Commentarii are propaganda written as objective history, presenting his enemies as the aggressors. Pharsalus is presented as the moment Caesar was 'forced' to victory — but his own regret, written in, is the closest Caesar comes to acknowledging the civil war's tragedy.",
            },
            {
                "type": "literature",
                "author": "Lucan",
                "work": "Pharsalia (De Bello Civili)",
                "citation": "Book 7, lines 387-872",
                "reference": "Lucan's epic poem makes Pharsalus the climax of his anti-epic. He describes the battle in grotesque detail — the fourth line's ambush, Pompey's flight — then apostrophises the field: 'O Pharsalia, cruel and accursed field!' The gods look on in horror as Rome destroys itself.",
                "why": "Lucan (39-65 CE) wrote under Nero and turned Caesar's Civil War into an epic where there are no heroes — only the death of liberty. Pharsalus is the wound in Roman history. The poem's pessimism — 'victrix causa deis placuit, sed victa Catoni' (the winning side pleased the gods, the losing side Cato) — became the definitive anti-Caesarian verdict.",
            },
            {
                "type": "literature",
                "author": "Plutarch",
                "work": "Life of Pompey & Life of Caesar",
                "citation": "Pompey ch. 68-72; Caesar ch. 42-46",
                "reference": "Plutarch gives the human story: Pompey's disquiet the night before, Caesar's near-despair when his cavalry fled, his rebuke of the standard-bearer who fled. After the battle Caesar declared: 'They would have it so — I, Gaius Caesar, after so many great achievements, would have been condemned had I not sought aid from my army.'",
                "why": "Plutarch (c. 100 CE) had access to now-lost sources and writes paired Lives that highlight character. Pompey at Pharsalus is the man who forgot how to win; Caesar is the man who never doubted. The battle becomes the moral hinge of both lives.",
            },
            {
                "type": "literature",
                "author": "Appian",
                "work": "Civil Wars",
                "citation": "Book 2 (Emphylia), chapters 60-76",
                "reference": "Appian's account adds detail on the pre-battle manoeuvres and Pompey's overconfidence, blaming his advisors for refusing to starve Caesar out. He preserves Caesar's famous order to his men to spare Roman citizens in the rout — 'spare your fellow citizens.'",
                "why": "Writing in the mid-2nd century CE, Appian sought the causes of Rome's decline in its civil wars. Pharsalus is for him the moment the Republic was lost not by one battle but by the choice to fight it — and his global view treats it as a tragedy beyond Caesar's personal victory.",
            },
            {
                "type": "literature",
                "author": "Cassius Dio",
                "work": "Roman History",
                "citation": "Book 41, chapters 51-63",
                "reference": "Dio's narrative gives the longest surviving account. He records Caesar's prayer to Mars before the battle and his tearful speech to his men — 'this is the day on which I shall either win your freedom or die.' Dio notes Caesar's defeat would have meant the death of Roman liberty as well, but the victory established the chain of Caesars that persists to his own day.",
                "why": "Dio (early 3rd c. CE) writes from a senator of the imperial age, weighing what the Republic lost at Pharsalus against the Empire it produced. His account is both military narrative and political eulogy.",
            },
        ],
    },
    "marathon": {
        "id": "marathon",
        "name": "Battle of Marathon",
        "date": "September 490 BCE",
        "location": "Plain of Marathon, Attica (Greece)",
        "lat": 38.15, "lng": 24.00,
        "summary": "The first Persian invasion of Greece ended at Marathon. A force of about 10,000 Athenians and 1,000 Plataeans, commanded by the polemarch Callimachus and the strategos Miltiades, defeated a Persian expeditionary force of perhaps 20,000-25,000 under Datis and Artaphernes. The Athenians weakened their centre to strengthen the wings — their flanks broke the Persians and then turned inward to crush the centre. The Persians fled to their ships. The messenger Pheidippides' legendary run to Athens gave the modern marathon its name.",
        "keyFigures": ["Miltiades (Athens)", "Callimachus (Athens)", "Datis (Persia)", "Artaphernes (Persia)"],
        "consequences": "Persian invasion repelled for ten years; Athens' confidence and self-image as defender of Greece forged; the wealth that built the Parthenon came from the silver mines that funded the fleet; Plataea's loyalty secured an enduring Athenian ally.",
        "sources": [
            {
                "type": "literature",
                "author": "Herodotus",
                "work": "Histories",
                "citation": "Book 6, chapters 102-117",
                "reference": "The principal ancient account. Herodotus describes the Athenian line extending to match the Persians by thinning the centre, the flanks' victory and the centre's near-rout, the Persian flight to the ships, and the death of Callimachus. He reports 192 Athenian dead to 6,400 Persian.",
                "why": "Herodotus wrote within two generations of the battle, with access to veterans. Marathon confirmed his thesis that free men fighting for their own land will defeat the subjects of a despot — and he preserves the casualty figures as proof of Greek superiority in close fighting.",
            },
            {
                "type": "material",
                "author": "(Athenian state)",
                "work": "Tumulus (Soros) of the Athenians",
                "citation": "The burial mound at the battlefield, still visible today",
                "reference": "The Athenian dead were buried on the field under a great earthwork — the Soros — which still stands. Excavation in the 19th century revealed the cremated remains of about 192 men, matching Herodotus' casualty count.",
                "why": "The Soros is the material witness to Marathon. Burial on the field (rather than in Athens' cemeteries) was a rare honour, treating the dead as the founders of a new Athens. The mound's existence anchors Herodotus' literary account to the ground.",
            },
            {
                "type": "material",
                "author": "(Athenian state / Pheidias' workshop)",
                "work": "Painted Stoa Poikile",
                "citation": "Agora of Athens; painting by Panainos and Polynotus, c. 460 BCE (lost, described by Pausanias)",
                "reference": "A monumental painting of the battle of Marathon was displayed in the Stoa Poikile (Painted Porch) of the Athenian Agora. Pausanias (1.15) describes it in detail — including the divine appearances of Athena, Heracles, and the hero Marathon, and the suicide of the traitor Cynaegyrus.",
                "why": "The Stoa Poikile turned Marathon into a public icon. Athenians walked past it daily; Stoic philosophy took its name from it. The painting made Marathon the visual foundation myth of imperial Athens — the moment the city claimed leadership of Greece.",
            },
            {
                "type": "literature",
                "author": "Plutarch",
                "work": "Moralia — 'On the Glory of Athens' & 'Life of Aristides'",
                "citation": "Glory of Athens 350A; Aristides 5-9",
                "reference": "Plutarch recounts the argument of Aristides before the battle — when the polemarch Callimachus held the casting vote, Aristides spoke in favour of Miltiades' plan to attack. He also preserves the tale that the Athenians thought they saw the hero Theseus leading the charge.",
                "why": "Plutarch (c. 100 CE) collects traditions that elevate Marathon's moral significance. The apparition of Theseus frames Marathon as a return of the city's founder, binding the new democracy to its mythic past. Marathon in Plutarch is the proof of Athenian virtue.",
            },
            {
                "type": "literature",
                "author": "Cornelius Nepos",
                "work": "Life of Miltiades",
                "citation": "Chapters 5-6",
                "reference": "Nepos gives a brief Latin biography of Miltiades that focuses on his generalship at Marathon. He notes the thinning of the Athenian centre and the defeat of the Persian wings, and the subsequent failed attempt to take Paros — for which Miltiades was fined, not executed.",
                "why": "Nepos (1st c. BCE) is writing for Roman readers and turns Marathon into a moral exemplum of the great general — and the fickleness of democracies toward their saviours. The battle's fame now depended on Roman as well as Greek readers.",
            },
        ],
    },
    "troy": {
        "id": "troy",
        "name": "Fall of Troy (Sack of Troy)",
        "date": "Traditional date: c. 1184 BCE",
        "location": "Hisarlik, near the Dardanelles (Turkey)",
        "lat": 39.96, "lng": 26.24,
        "summary": "The legendary climax of the Trojan War, in which the Greek army — after a ten-year siege — used the stratagem of the Wooden Horse to enter Troy and sack it by night. The men of fighting age were killed; the women and children were enslaved. The fall became the founding myth of Roman identity, since the Trojan prince Aeneas was said to have escaped and led his people to Italy. The historicity of the war was debated for millennia — until Heinrich Schliemann's excavations at Hisarlik (1870-90) revealed a real Bronze Age city destroyed by fire around the traditional date.",
        "keyFigures": ["Odysseus (stratagem)", "Menelaus & Agamemnon", "Aeneas (survivor)", "Priam, Hector, Paris (Troy)", "Heinrich Schliemann (excavator)"],
        "consequences": "In myth: diaspora of Trojan heroes, foundation of new dynasties (Aeneas to Rome, Antenor to Padua). In history: the destruction of Troy VIIa around 1200 BCE coincides with the wider Late Bronze Age collapse; the legend became the cultural memory of the Greek dark age.",
        "sources": [
            {
                "type": "literature",
                "author": "Homer",
                "work": "Iliad & Odyssey",
                "citation": "Iliad Book 22 (death of Priam's son Hector); Odyssey Book 4.271-289, Book 8.492-520 (the Wooden Horse)",
                "reference": "The Iliad does not narrate the sack itself — it ends with Hector's funeral. The Wooden Horse episode is recounted in the Odyssey by the singer Demodocus and by Menelaus, describing how the Greeks hid inside the horse, sacked the city by night, and enslaved the women.",
                "why": "Homer (8th c. BCE) created the literary Troy that defined Greek culture for a millennium. By ending the Iliad with Hector's funeral, he preserved the city's dignity — the actual sack is recalled only in song within the Odyssey, keeping it mythic and distanced.",
            },
            {
                "type": "literature",
                "author": "Virgil",
                "work": "Aeneid",
                "citation": "Book 2 (the entire book is Aeneas' account of the sack)",
                "reference": "Aeneas narrates the fall from the Trojan side: the wooden horse dragged within the walls, the Greek sortie, the death of Priam at the altar, the ghost of Creusa lost in the burning city. 'It was the last night of the Trojan people.'",
                "why": "Virgil (c. 25-19 BCE) inverts Homer — telling the sack from the perspective of the defeated. Written for Augustus, the Aeneid makes the destruction of Troy the necessary prelude to Rome's foundation: out of Troy's ashes comes the imperial destiny of the Roman people.",
            },
            {
                "type": "literature",
                "author": "Quintus Smyrnaeus",
                "work": "Posthomerica",
                "citation": "Book 12 (the sack), Book 13 (the Wooden Horse)",
                "reference": "Quintus' 4th-century CE epic fills the gap between the Iliad and the Odyssey. He narrates the construction of the horse, the debate over Sinon's lying story, Laocoon's death by sea-serpent, and the night of the sack — including the murder of Priam at the altar of Zeus Herkeios.",
                "why": "Quintus (4th c. CE) preserves later Greek epic traditions now lost (the Little Iliad, the Sack of Troy / Iliupersis). His account is the fullest surviving narrative of the actual sack, combining Arctinus and Lesches' lost epics into a continuous story.",
            },
            {
                "type": "material",
                "author": "(Heinrich Schliemann & successors)",
                "work": "Excavations at Hisarlik",
                "citation": "Troy levels VI/VIIa — destruction layer c. 1200 BCE",
                "reference": "Excavations since 1870 have revealed a stratified city. Troy VIIa shows a flourishing Late Bronze Age city destroyed by fire and warfare around 1200 BCE — broadly consistent with the traditional date of the war. Bronze Age weapons, fortifications, and the 'treasure of Priam' (now controversially dated) were found.",
                "why": "Hisarlik is the most contested site in classical archaeology. The discovery of a real destroyed Late Bronze Age city — in roughly the right place and time — was the first material corroboration of a tradition long dismissed as pure myth. It transformed the study of Homer.",
            },
            {
                "type": "literature",
                "author": "Euripides",
                "work": "The Trojan Women",
                "citation": "The entire tragedy",
                "reference": "Euripides (415 BCE) stages the aftermath of the sack from the perspective of the Trojan women — Hecuba, Cassandra, Andromache — awaiting allotment as slaves to the Greek captains. The arrival of Astyanax's body, torn from the towers, ends the play.",
                "why": "Produced in 415 BCE — the year Athens sacked Melos and enslaved its women — the Trojan Women turns the myth of Troy into a savage indictment of imperial war. It is the most powerful ancient anti-war statement and demonstrates how the sack of Troy remained a living moral metaphor centuries after Homer.",
            },
        ],
    },
    "rubicon": {
        "id": "rubicon",
        "name": "Crossing the Rubicon",
        "date": "January 10, 49 BCE",
        "location": "Rubicon river (northern Italy, exact course debated)",
        "lat": 44.0, "lng": 12.4,
        "summary": "Julius Caesar, at the head of the 13th Legion, crossed the small river that marked the southern boundary of his province of Cisalpine Gaul into Italy proper. To lead an army across that boundary without senatorial authorisation was treason. The act initiated the Great Roman Civil War and destroyed the Roman Republic. 'Let the die be cast.' The phrase, in every modern European language, dates from this moment.",
        "keyFigures": ["Julius Caesar", "Mark Antony (tribune)", "Pompey (opponent)", "the Senate (Cato, Bibulus)"],
        "consequences": "Outbreak of the Civil War; flight of Pompey and the senatorial party from Italy; Caesar's capture of Rome within weeks; the constitutional order of the Republic begins to collapse.",
        "sources": [
            {
                "type": "literature",
                "author": "Julius Caesar",
                "work": "Commentarii de Bello Civili (Civil War)",
                "citation": "Book 1, chapters 7-8",
                "reference": "Caesar describes his approach to the Rubicon and his address to his officers. Famously, however, he does not describe the actual crossing in any detail — he merely states 'he determined to advance into Italy with his army.' He omits the famous words.",
                "why": "Caesar writes his own account as political justification — presenting himself as the defender of his rights and the tribunes (Antony and Cassius) who had been expelled from Rome. By minimising the crossing, he downplays its treasonous character — his propagandistic framing of the war as a defensive last resort.",
            },
            {
                "type": "literature",
                "author": "Suetonius",
                "work": "Life of the Divine Julius",
                "citation": "Chapter 31-32",
                "reference": "Suetonius gives the iconic account: Caesar halted at the Rubicon, hesitated, and reasoned with himself about the consequences. Then, casting aside delay, he uttered the Greek words 'ἀνερρίφθω κύβος' — 'let the die be cast' — and crossed. The phrase comes from Menander, a favourite poet of Caesar's.",
                "why": "Suetonius (early 2nd c. CE) had access to imperial archives and earlier historians. His biography captures the dramatic instant that the Republic crossed into autocracy. The Menandrian quotation — preserved in Greek — gives us the phrase that became proverbial.",
            },
            {
                "type": "literature",
                "author": "Plutarch",
                "work": "Life of Caesar",
                "citation": "Chapters 32-33",
                "reference": "Plutarch gives a similar account of hesitation at the river, but records Caesar's words as Latin: 'Iacta alea est' — 'the die is cast.' He adds that Caesar addressed his troops: 'We can still draw back — but once we cross that little bridge, everything will be decided by the sword.'",
                "why": "Plutarch (c. 100 CE) supplies the moral weight Caesar omits. The crossing is presented as a deliberate ethical choice — the moment Caesar chose power over the Republic. Plutarch's Caesar knew what he was doing, and Plutarch holds him to account.",
            },
            {
                "type": "literature",
                "author": "Lucan",
                "work": "Pharsalia",
                "citation": "Book 1, lines 183-229",
                "reference": "Lucan stages Caesar at the Rubicon as an apparition of Rome's great enemy, the goddess Roma herself rising from the river to forbid him. He crosses anyway. 'Here, here is the peace, here the impious omen, here the borders of laws — and here the river of crime.'",
                "why": "Lucan (39-65 CE) makes the Rubicon the moral epicentre of his poem. The crossing is sacrilege, the river is personified as Rome herself crying out. Lucan's Pharsalia transforms a forgotten small river into the symbolic threshold where Roman liberty was lost.",
            },
            {
                "type": "literature",
                "author": "Appian",
                "work": "Civil Wars",
                "citation": "Book 2, chapters 34-35",
                "reference": "Appian notes the legal context: the Senate had passed the senatus consultum ultimum (the final decree) and named Caesar an enemy of the state. Crossing the Rubicon was therefore the formal beginning of war — Caesar's officers hesitated; some deserted; he proceeded with the 13th Legion.",
                "why": "Appian (mid-2nd c. CE) places the crossing in its constitutional frame. The Rubicon is not just a river but the line between lawful command and treason. Appian, a Greek Egyptian writing in Rome, sees the crossing as the moment when Roman law was sacrificed to one man's ambition.",
            },
        ],
    },
    "cannae": {
        "id": "cannae",
        "name": "Battle of Cannae",
        "date": "August 2, 216 BCE",
        "location": "Cannae, Apulia (southern Italy)",
        "lat": 41.5, "lng": 15.5,
        "summary": "The greatest defeat in Roman history. Hannibal's army of about 50,000 encircled and annihilated a Roman army of perhaps 80,000-90,000 in a double envelopment — the 'Cannae model' still taught in military academies. Rome lost perhaps 50,000-70,000 men in a single afternoon — more than at any battle in the city's history, and proportionally more dead than the United States suffered in the entire Vietnam War. Hannibal's deliberate weakening of his centre drew the Romans forward, while his African infantry on the wings turned inward to crush the Roman flanks. Roman survivors were few; the dead included 80 senators.",
        "keyFigures": ["Hannibal Barca (Carthage)", "Lucius Aemilius Paullus (Rome, killed)", "Gaius Terentius Varro (Rome)", "Maharbal (Carthage)"],
        "consequences": "Southern Italy wavers; Capua and Tarentum defect to Hannibal; Philip V of Macedon allies with Carthage; Rome refuses to ransom prisoners and raises new armies from slaves and criminals — the desperate resolve that ultimately won the war.",
        "sources": [
            {
                "type": "literature",
                "author": "Polybius",
                "work": "Histories",
                "citation": "Book 3, chapters 107-117",
                "reference": "Polybius gives the fullest tactical account. He records Hannibal's deployment of his Spanish and Celtic cavalry on the left to break the Roman cavalry, his Numidian light horse on the right, and the deliberate convex formation of his centre — the Gauls and Spaniards, weakest troops, giving ground as the Romans pressed forward, until the African infantry on the wings turned inward and enveloped them.",
                "why": "Polybius (c. 200-118 BCE) wrote as a Greek hostage in Rome who interviewed survivors and walked the battlefield. His account is the military theorist's: Cannae demonstrates that generalship can turn inferior numbers into overwhelming victory — the foundation of the classical theory of envelopment.",
            },
            {
                "type": "literature",
                "author": "Livy",
                "work": "Ab Urbe Condita (History of Rome)",
                "citation": "Book 22, chapters 44-51",
                "reference": "Livy gives the moral narrative. He records the terror in Rome, the consul Varro's flight to Venusia, and the senatorial reaction — refusing Hannibal's offer to ransom prisoners and instead raising fresh armies. He preserves Maharbal's famous remark that Hannibal knew 'how to win a victory but not how to use one.'",
                "why": "Livy (59 BCE-17 CE) writes the Augustan national history of Rome. Cannae is the test of Roman character: the city's refusal to surrender after an annihilating defeat becomes for Livy the defining virtue of Rome — the unyielding resolve that built the Empire.",
            },
            {
                "type": "literature",
                "author": "Plutarch",
                "work": "Life of Fabius Maximus & Life of Aemilius Paullus",
                "citation": "Fabius ch. 16-17; Aemilius Paullus ch. 18-22",
                "reference": "Plutarch focuses on character: Aemilius Paullus, the consul who fell at Cannae, refusing to flee and dying in the slaughter; Fabius Maximus, the 'Cunctator' (delayer) whose strategy of avoidance had been rejected — and vindicated at Cannae. After the disaster, Rome returned to Fabius' strategy.",
                "why": "Plutarch (c. 100 CE) writes paired Lives that turn Cannae into a moral contrast — the rashness that lost vs the caution that would ultimately win. Cannae teaches that patience, not courage, wins wars of attrition. Fabius' vindication is the lesson of the battle.",
            },
            {
                "type": "literature",
                "author": "Appian",
                "work": "Hannibalic War",
                "citation": "Book 7 (§25-30)",
                "reference": "Appian's account is briefer and includes the subsequent effect: the defection of Capua and other allies, and Hannibal's march to within three miles of Rome (a later episode). He preserves the rumour that Hannibal released the Roman allies without ransom to divide them from Rome — but the allies refused to abandon the city.",
                "why": "Appian (mid-2nd c. CE) writes from the imperial age and sees Cannae as the test of the Roman alliance system. The loyalty of the Italian allies after the disaster — against all expectation — is for Appian what truly saved Rome, more than any general.",
            },
            {
                "type": "material",
                "author": "(Roman state)",
                "work": "Lectisternium of 217 BCE & the Field of Blood",
                "citation": "Livy 22.10 (rite); battlefield archaeology at Cannae (recent surveys)",
                "reference": "Livy records the desperate public rites in Rome — a lectisternium where gods were banqueted in the streets, and live Gauls and Greeks buried alive in the Forum. Modern geophysical surveys at the site have revealed mass burials and bone deposits consistent with the aftermath of a great slaughter.",
                "why": "The Roman religious response shows how unprecedented the fear was — human sacrifice, abandoned after Cannae, was the ultimate appeal to the gods. Modern archaeological work on the battlefield is now confirming the literary scale of the slaughter, returning Cannae from text to ground.",
            },
        ],
    },
    "ithaca": {
        "id": "ithaca",
        "name": "Return of Odysseus (Nostos)",
        "date": "Traditional date: c. 1170 BCE; poem composed c. 750-700 BCE",
        "location": "Ithaca, Ionian Sea (Greece)",
        "lat": 38.38, "lng": 20.65,
        "summary": "The homecoming (nostos) of Odysseus to Ithaca after the Trojan War — the central myth of Homer's Odyssey. After a ten-year war and a further ten years of wandering, Odysseus arrives disguised as a beggar to find his palace overrun by 108 suitors seeking his wife Penelope. With his son Telemachus and two loyal servants, he strings the great bow, reveals himself, and slaughters the suitors. The nostos gave Greek literature its word for 'homecoming' and every European language the word 'odyssey.'",
        "keyFigures": ["Odysseus", "Penelope", "Telemachus", "Eurycleia (nurse)", "Eumaeus (swineherd)"],
        "consequences": "In myth: the restoration of the Ithacan throne; the reconciliation with the families of the suitors at the close of the Odyssey. In literature: the paradigmatic homecoming story, the foundation of the Western novel, and the model for countless later narratives from the Aeneid to Joyce's Ulysses.",
        "sources": [
            {
                "type": "literature",
                "author": "Homer",
                "work": "Odyssey",
                "citation": "Books 13-24 (the Ithacan books)",
                "reference": "Books 13-24 narrate the return. Odysseus wakes on Ithaca (Book 13), disguises himself with Athena's help, is recognised by Eurycleia's scar (Book 19), strings the bow (Book 21), slaughters the suitors (Book 22), is recognised by Penelope (Book 23), and reconciles with the suitors' families (Book 24).",
                "why": "The Odyssey (c. 750-700 BCE) is the foundational narrative of return in Western literature. The Ithacan half turns the heroic world of the Iliad inward — a hero not winning glory but reclaiming home. Every later nostos story draws on Homer's structure of disguise, recognition, and revenge.",
            },
            {
                "type": "literature",
                "author": "Tennyson",
                "work": "Ulysses",
                "citation": "The entire poem (1842)",
                "reference": "'It little profits that an idle king...Matched with an aged wife, I mete and dole / Unequal laws unto a savage race.' Tennyson's Ulysses, restless after his return, resolves to sail again: 'to strive, to seek, to find, and not to yield.'",
                "why": "Tennyson inverts Homer — the return is not the end of restlessness but its beginning. The Victorian poem reads Ithaca not as a goal achieved but as a place that no longer satisfies the questing soul. The reception shows how the Odyssey becomes a metaphor for the human condition itself.",
            },
            {
                "type": "literature",
                "author": "James Joyce",
                "work": "Ulysses",
                "citation": "The novel (1922)",
                "reference": "Joyce transposes Odysseus' return to a single day in Dublin (June 16, 1904). Leopold Bloom — a Jewish advertising canvasser — is Odysseus; Stephen Dedalus is Telemachus; Molly Bloom is Penelope. The 'Ithaca' episode is a catechism of Bloom's return home; the 'Penelope' episode is Molly's final monologue.",
                "why": "Joyce's Ulysses demonstrated that the structure of the Odyssey was so universal it could frame the inner life of a modern Dubliner. The novel's dates — 'Bloomsday' — is still celebrated worldwide. Joyce's work secured the Odyssey's place as the modernist template of human consciousness.",
            },
            {
                "type": "material",
                "author": "(School of Apelles / Roman copies)",
                "work": "Frescoes from the Esquiline and Borgia collection",
                "citation": "Roman wall paintings (1st c. BCE - 1st c. CE)",
                "reference": "Roman houses preserved frescoes of Odysseus' return — recognising the scar, the bow contest, the slaughter of the suitors. The 'Odyssey Landscapes' (Vatican Museums) depict episodes from Books 10-12 in a continuous frieze — the earliest surviving continuous pictorial narrative of the Odyssey.",
                "why": "The Roman frescoes show the Odyssey as visual culture of the imperial household. The Ithacan scenes were domestic decoration — a Roman aristocrat dined under images of Odysseus' vengeance. The myth had become not just literature but the everyday visual furniture of Roman life.",
            },
            {
                "type": "material",
                "author": "(Bronze Age site)",
                "work": "Excavations on Ithaki (School of Homer)",
                "citation": "Excavations at Agios Athanasios, Ithaki, 2010-present",
                "reference": "Recent excavations on Ithaki have revealed a substantial Bronze Age complex — sometimes identified with the 'School of Homer' — that may date to the period of the Odyssey's composition. Finds include a Mycenaean-style structure and an apparent cult of Odysseus in later periods.",
                "why": "The archaeology of Ithaca is contested — modern Ithaki does not perfectly match Homer's description, and some scholars place Homeric Ithaca on Leucas. But the recent finds demonstrate that the island has Bronze Age remains consistent with a real polity behind the myth — and a cult of Odysseus by the Hellenistic period.",
            },
        ],
    },
    "nero-rome-fire": {
        "id": "nero-rome-fire",
        "name": "Great Fire of Rome",
        "date": "July 64 CE",
        "location": "Rome (mostly the valley between the Palatine and Esquiline)",
        "lat": 41.89, "lng": 12.49,
        "summary": "A fire broke out in the shops around the Circus Maximus on the night of July 19, 64 CE, and burned for nine days. Of Rome's fourteen districts, four were destroyed and seven more damaged. The emperor Nero — away at Antium when it began — returned to organise relief, opened public buildings and his own gardens to refugees, and imported food. Yet rumour blamed him, especially after he built his vast new Golden House (Domus Aurea) on the cleared land. To deflect suspicion, he blamed the Christians — the first recorded persecution by the Roman state.",
        "keyFigures": ["Nero (emperor)", "Tigellinus (praetorian prefect)", "St. Peter & St. Paul (victims, tradition)", "the Christians"],
        "consequences": "The first state persecution of Christians; the building of the Domus Aurea (Nero's vast palace); the rebuilding of Rome with wider streets and better fire regulations; the consolidation of Nero's unpopularity that would lead to his fall four years later.",
        "sources": [
            {
                "type": "literature",
                "author": "Tacitus",
                "work": "Annals",
                "citation": "Book 15, chapters 38-44",
                "reference": "The principal account. Tacitus records the fire's course, Nero's relief efforts, and the persecution of the Christians. He explicitly states Nero was not in Rome when it began and notes 'whether accidental or treacherously contrived by the prince is doubtful' — a careful historian. He then describes the brutal executions of Christians, for whom he feels no sympathy yet admits Nero used them as scapegoats.",
                "why": "Tacitus (c. 56-120 CE) wrote as a senator of the next generation and had access to the senatorial records. His account is balanced — Nero's relief efforts are noted, his guilt is left open — but the persecution of the Christians is presented as the abuse of imperial power. The Annals give us the earliest surviving account of Christians at Rome.",
            },
            {
                "type": "literature",
                "author": "Suetonius",
                "work": "Life of Nero",
                "citation": "Chapters 38-39",
                "reference": "Suetonius is less cautious: he states outright that Nero 'set fire to the city' out of disgust at its ugliness and a desire for new building. He adds the famous detail that Nero watched the fire from the Tower of Maecenas and 'sang the Sack of Ilium' dressed as a tragedian.",
                "why": "Suetonius (c. 69-122 CE) wrote biographies, not history — he preserves the hostile senatorial tradition that condemned Nero. The fiddle story (Nero was playing the lyre, not a fiddle) comes from this hostile tradition. Suetonius crystallised the popular image of Nero the arsonist.",
            },
            {
                "type": "literature",
                "author": "Cassius Dio",
                "work": "Roman History",
                "citation": "Book 62, chapters 16-18",
                "reference": "Dio's account, preserved in epitome, also accuses Nero directly. He adds that Nero's men were seen torching buildings — and that he watched from the Palatine. Dio includes the Christians' persecution as part of the broader tyrannical pattern.",
                "why": "Dio (c. 155-235 CE) wrote in the early 3rd century and had access to lost sources. His hostility to Nero reflects the senatorial tradition of three generations later — by his time, the Christians' original identity as a Jewish sect was fading, and the persecution was part of Nero's general tyranny.",
            },
            {
                "type": "material",
                "author": "(Neronian builders)",
                "work": "Domus Aurea (Golden House)",
                "citation": "Excavated on the Oppian Hill, Rome",
                "reference": "After the fire, Nero built a vast palace — the Domus Aurea — across the cleared centre of Rome. Its surviving rooms on the Oppian Hill contain the frescoes that inspired Raphael's grotesques in the Vatican Logge. The Colosseum was later built on the site of the palace's ornamental lake.",
                "why": "The Domus Aurea is the material evidence that someone — almost certainly Nero — profited from the cleared land. Its scale (the palace covered up to 300 acres in the heart of Rome) explains the rumour: no other Roman would have dared build on such a scale after a fire. The frescoes preserved the visual culture that fed the Renaissance.",
            },
            {
                "type": "literature",
                "author": "(Christian tradition)",
                "work": "1 Clement (Letter of the Church of Rome to the Corinthians)",
                "citation": "Chapter 5-6 (c. 96 CE)",
                "reference": "1 Clement, written within a generation of Nero's persecution, refers to Peter and Paul as 'the greatest and most righteous pillars' who suffered under 'jealousy and envy' — generally read as a reference to their martyrdom under Nero after the fire. The letter is the earliest Christian document to mention their deaths.",
                "why": "1 Clement is the first Christian echo of the events Tacitus records. The tradition that Peter was crucified upside down and Paul beheaded — under Nero — became foundational to the Roman church's identity. The fire and its aftermath bound the Christian story to the city of Rome itself.",
            },
        ],
    },
}

# ---------------------------------------------------------------------------
# CLASSICS GAMES — trivia, word scramble, matching
# ---------------------------------------------------------------------------
TRIVIA_QUESTIONS = [
    {"q": "Who wrote the Aeneid?", "choices": ["Virgil", "Ovid", "Horace", "Lucan"], "answer": 0, "explain": "Virgil composed the Aeneid between c. 29-19 BCE at Augustus' request."},
    {"q": "What body of water did Caesar cross saying 'the die is cast'?", "choices": ["Tiber", "Rubicon", "Rhine", "Po"], "answer": 1, "explain": "Crossing the Rubicon in 49 BCE meant treason — and civil war."},
    {"q": "How many men did Leonidas have at Thermopylae (approximately)?", "choices": ["300", "7,000", "1,000", "12,000"], "answer": 1, "explain": "The 300 were the Spartan elite; the total Greek force was about 7,000."},
    {"q": "Which emperor allegedly fiddled while Rome burned?", "choices": ["Caligula", "Nero", "Commodus", "Domitian"], "answer": 1, "explain": "Nero was at Antium when the fire began in 64 CE; he later blamed the Christians."},
    {"q": "What is the opening word of Homer's Iliad in Greek?", "choices": ["ἄνδρα (man)", "μῆνιν (rage)", "θέα (goddess)", "ἔννεπε (tell)"], "answer": 1, "explain": "'Μῆνιν ἄειδε θεά' — 'Sing, goddess, of the rage of Achilles'."},
    {"q": "Which Carthaginian general crossed the Alps with elephants?", "choices": ["Hamilcar Barca", "Hannibal", "Hasdrubal", "Mago"], "answer": 1, "explain": "Hannibal crossed the Alps in 218 BCE with 26,000 men and war elephants."},
    {"q": "What was the name of Odysseus' homeland?", "choices": ["Sparta", "Ithaca", "Pylos", "Mycenae"], "answer": 1, "explain": "Odysseus spent ten years trying to return to Ithaca after Troy."},
    {"q": "Who was the first Roman emperor?", "choices": ["Julius Caesar", "Augustus", "Tiberius", "Nero"], "answer": 1, "explain": "Augustus (Octavian) became princeps in 27 BCE; Caesar was never emperor."},
    {"q": "Which god is associated with the Oracle at Delphi?", "choices": ["Zeus", "Apollo", "Athena", "Hermes"], "answer": 1, "explain": "Apollo slew the Python at Delphi and claimed the oracle as his own."},
    {"q": "What does 'Veni, vidi, vici' mean?", "choices": ["I came, I saw, I conquered", "I came, I saw, I left", "I came, I waited, I won", "I saw, I came, I ruled"], "answer": 0, "explain": "Caesar's famous dispatch after the Battle of Zela in 47 BCE."},
    {"q": "Which Roman general defeated Hannibal at Zama?", "choices": ["Scipio Africanus", "Fabius Maximus", "Marcellus", "Flaminius"], "answer": 0, "explain": "Scipio turned Hannibal's own envelopment tactic against him in 202 BCE."},
    {"q": "What is the Latin word for 'war'?", "choices": ["pax", "bellum", "arma", "legio"], "answer": 1, "explain": "'Bellum' gives us 'bellicose' and 'rebellion'."},
    {"q": "Who was the last pharaoh of Egypt?", "choices": ["Nefertiti", "Hatshepsut", "Cleopatra VII", "Ramses II"], "answer": 2, "explain": "Cleopatra VII died in 30 BCE after Actium; Egypt became a Roman province."},
    {"q": "Which Greek city-state was known for its military discipline?", "choices": ["Athens", "Sparta", "Corinth", "Thebes"], "answer": 1, "explain": "Spartan boys entered the agoge (military training) at age 7."},
    {"q": "What was the Roman name for the Mediterranean Sea?", "choices": ["Oceanus", "Mare Nostrum", "Mare Internum", "Pontus"], "answer": 1, "explain": "'Mare Nostrum' means 'Our Sea' — Rome controlled all of it by 30 BCE."},
    {"q": "Who wrote the 'Commentarii de Bello Gallico'?", "choices": ["Cicero", "Julius Caesar", "Sallust", "Livy"], "answer": 1, "explain": "Caesar wrote his own war memoirs in the third person — brilliant propaganda."},
    {"q": "Which structure was one of the Seven Wonders located in Alexandria?", "choices": ["The Colossus", "The Pharos", "The Hanging Gardens", "The Mausoleum"], "answer": 1, "explain": "The Pharos lighthouse guided sailors for over 1,500 years."},
    {"q": "What does 'carpe diem' mean?", "choices": ["seize the day", "trust the gods", "make peace", "come and see"], "answer": 0, "explain": "From Horace's Odes 1.11 — the original 'YOLO'."},
    {"q": "Who was the king of Troy during the Trojan War?", "choices": ["Agamemnon", "Priam", "Hector", "Paris"], "answer": 1, "explain": "Priam ruled Troy for decades; he was killed by Neoptolemus during the sack."},
    {"q": "What was the name of the Roman senate house?", "choices": ["Curia", "Basilica", "Forum", "Comitium"], "answer": 0, "explain": "The Curia Julia, built by Caesar and completed by Augustus, still stands in the Forum."},
    {"q": "Which philosopher taught Alexander the Great?", "choices": ["Plato", "Socrates", "Aristotle", "Pythagoras"], "answer": 2, "explain": "Aristotle tutored Alexander from age 13 to 16 at Mieza."},
    {"q": "What was the Roman legion's standard called?", "choices": ["Vexillum", "Aquila", "Signum", "Imago"], "answer": 1, "explain": "The aquila (eagle) was sacred; losing it was the ultimate disgrace."},
    {"q": "Who wrote 'The Histories' — the first work of Western history?", "choices": ["Thucydides", "Herodotus", "Polybius", "Livy"], "answer": 1, "explain": "Herodotus (c. 484-425 BCE) earned the title 'Father of History' from Cicero."},
    {"q": "What does 'alea iacta est' mean?", "choices": ["the die is cast", "all is lost", "fortune favors the bold", "the gods decide"], "answer": 0, "explain": "Caesar's words at the Rubicon — originally a line from Menander."},
    {"q": "Which battle ended the Roman Republic?", "choices": ["Cannae", "Actium", "Pharsalus", "Zama"], "answer": 2, "explain": "At Pharsalus (48 BCE), Caesar defeated Pompey; the Republic never recovered."},
]

TRUE_FALSE_QUESTIONS = [
    {"q": "The Romans used concrete in their construction.", "answer": True, "explain": "Roman concrete (opus caementicium) used volcanic ash — some structures are still standing."},
    {"q": "Spartacus was a Roman citizen.", "answer": False, "explain": "Spartacus was a Thracian, enslaved as a gladiator in the ludus at Capua."},
    {"q": "The Colosseum could be flooded for naval battles.", "answer": True, "explain": "The earliest emperors staged naumachiae (mock sea battles) before the hypogeum was built."},
    {"q": "Julius Caesar was the first Roman emperor.", "answer": False, "explain": "Caesar was dictator perpetuo but never emperor — that was his adopted heir Augustus."},
    {"q": "The Library of Alexandria still stands today.", "answer": False, "explain": "It was destroyed in stages; the final destruction was in 642 CE during the Arab conquest."},
    {"q": "Homer was blind.", "answer": True, "explain": "Tradition depicts Homer as blind — the 'blind bard' is a stock figure in Greek poetry."},
    {"q": "The Parthenon was originally painted in bright colors.", "answer": True, "explain": "Greek temples were vibrantly painted; the white marble look is weathering, not design."},
    {"q": "Cleopatra was ethnically Egyptian.", "answer": False, "explain": "She was a Ptolemy — descended from a Macedonian Greek general of Alexander the Great."},
    {"q": "The Rubicon still exists and can be visited.", "answer": True, "explain": "The Fiumicino river near Rimini is generally accepted as the ancient Rubicon."},
    {"q": "Vindolanda writing tablets were found on Hadrian's Wall.", "answer": True, "explain": "The thin wooden tablets preserve Roman soldiers' letters — including a birthday invitation."},
    {"q": "The Aeneid was finished before Virgil died.", "answer": False, "explain": "Virgil asked on his deathbed to burn it as unfinished; Augustus ordered it published."},
    {"q": "Socrates wrote down his own philosophy.", "answer": False, "explain": "Socrates wrote nothing — we know him through Plato's dialogues and Xenophon's memoirs."},
    {"q": "The Romans crucified 6,000 of Spartacus' men along the Appian Way.", "answer": True, "explain": "After the final battle in 71 BCE, Crassus ordered the mass crucifixion from Capua to Rome."},
    {"q": "Augustus' Res Gestae was his autobiography.", "answer": True, "explain": "The 'Achievements of the Divine Augustus' was inscribed on his mausoleum and copied across the Empire."},
    {"q": "The Battle of Marathon gave its name to the modern race.", "answer": True, "explain": "The legend of Pheidippides' run inspired the modern marathon (though his actual route was longer)."},
]

SCRAMBLE_WORDS = [
    {"scrambled": "RUBICNO", "answer": "RUBICON", "hint": "Caesar crossed this river in 49 BCE"},
    {"scrambled": "EIDNEA", "answer": "AENEID", "hint": "Virgil's epic about a Trojan's journey to Italy"},
    {"scrambled": "SLEISOS", "answer": "ILIOS", "hint": "Greek name for the city at the heart of the Trojan War"},
    {"scrambled": "OSCIRSUE", "answer": "ODYSSEUS", "hint": "His nostos took ten years"},
    {"scrambled": "BAINHLA", "answer": "HANNIBAL", "hint": "Carthaginian who crossed the Alps"},
    {"scrambled": "SPEAPALRR", "answer": "PALIMPSEST", "hint": "A manuscript scraped clean and reused — from Greek 'again-scraped'"},
    {"scrambled": "VEODINSINI", "answer": "NEVIIDIVI", "hint": "An anagram of Caesar's famous three-word dispatch at Zela"},
    {"scrambled": "AIMUROT", "answer": "MAIORUM", "hint": "The 'mos ___' was the Roman way of the ancestors"},
    {"scrambled": "PPEISCO", "answer": "SCIPIO", "hint": "Roman general who defeated Hannibal at Zama"},
    {"scrambled": "FIDODELHP", "answer": "DELPHI", "hint": "Home of the most famous oracle in the Greek world"},
    {"scrambled": "ILIV", "answer": "LIVY", "hint": "Roman historian who wrote Ab Urbe Condita"},
    {"scrambled": "KSSNOOS", "answer": "KNOSSOS", "hint": "Minoan palace excavated by Arthur Evans"},
    {"scrambled": "ASOEYRPL", "answer": "POMPEII", "hint": "Anagram! City buried by Vesuvius in 79 CE"},
    {"scrambled": "RAXEELND", "answer": "ALEXANDR", "hint": "Start of a city name founded by a Macedonian king in Egypt"},
    {"scrambled": "ATCIUM", "answer": "ACTIUM", "hint": "Naval battle that ended the Roman Republic"},
]

MATCHING_SETS = [
    {
        "title": "Match each author to their work",
        "pairs": [
            {"left": "Virgil", "right": "Aeneid"},
            {"left": "Homer", "right": "Odyssey"},
            {"left": "Ovid", "right": "Metamorphoses"},
            {"left": "Caesar", "right": "De Bello Gallico"},
            {"left": "Herodotus", "right": "Histories"},
            {"left": "Livy", "right": "Ab Urbe Condita"},
        ],
    },
    {
        "title": "Match each god to their symbol",
        "pairs": [
            {"left": "Poseidon", "right": "Trident"},
            {"left": "Athena", "right": "Owl"},
            {"left": "Apollo", "right": "Lyre"},
            {"left": "Hermes", "right": "Caduceus"},
            {"left": "Ares", "right": "Spear"},
            {"left": "Artemis", "right": "Bow"},
        ],
    },
    {
        "title": "Match each Roman emperor to their deed",
        "pairs": [
            {"left": "Augustus", "right": "Founded the Principate"},
            {"left": "Nero", "right": "Persecuted Christians"},
            {"left": "Hadrian", "right": "Built the Wall"},
            {"left": "Trajan", "right": "Conquered Dacia"},
            {"left": "Constantine", "right": "Legalized Christianity"},
            {"left": "Marcus Aurelius", "right": "Wrote Meditations"},
        ],
    },
    {
        "title": "Match each Latin phrase to its meaning",
        "pairs": [
            {"left": "Veni, vidi, vici", "right": "I came, I saw, I conquered"},
            {"left": "Carpe diem", "right": "Seize the day"},
            {"left": "Alea iacta est", "right": "The die is cast"},
            {"left": "Memento mori", "right": "Remember you must die"},
            {"left": "Sic transit gloria mundi", "right": "Thus passes the glory of the world"},
            {"left": "Labor omnia vincit", "right": "Work conquers all"},
        ],
    },
    {
        "title": "Match each battle to its victor",
        "pairs": [
            {"left": "Marathon", "right": "Athens"},
            {"left": "Thermopylae", "right": "Persia"},
            {"left": "Salamis", "right": "Greece"},
            {"left": "Cannae", "right": "Carthage"},
            {"left": "Zama", "right": "Rome"},
            {"left": "Actium", "right": "Octavian"},
        ],
    },
]

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
# AUTHENTICATION
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("welcome"))
        return f(*args, **kwargs)
    return decorated


@app.route("/welcome")
def welcome():
    if "user_id" in session:
        return redirect(url_for("index"))
    return render_template("welcome.html")


@app.route("/signup", methods=["POST"])
def signup():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not username or not email or not password:
        return render_template("welcome.html", mode="signup", error="All fields are required.", username=username, email=email)
    if len(username) < 3:
        return render_template("welcome.html", mode="signup", error="Username must be at least 3 characters.", username=username, email=email)
    if len(password) < 6:
        return render_template("welcome.html", mode="signup", error="Password must be at least 6 characters.", username=username, email=email)

    if find_user_by_username(username):
        return render_template("welcome.html", mode="signup", error="That username is already taken.", email=email)
    if find_user_by_email(email):
        return render_template("welcome.html", mode="signup", error="An account with that email already exists.", username=username)

    user = create_user(username, email, password)

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["total_points"] = 0
    session["action_counts"] = {}
    session["bio"] = ""
    session["interests"] = ""
    session["avatar"] = ""
    session["saved_items"] = []
    session["game_levels"] = {}
    session["followers"] = []
    session["following"] = []
    return redirect(url_for("index"))


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        return render_template("welcome.html", mode="login", error="Please enter your username and password.")

    user = find_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("welcome.html", mode="login", error="Invalid username or password.")

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["total_points"] = user.get("total_points", 0)
    session["action_counts"] = user.get("action_counts", {})
    session["bio"] = user.get("bio", "")
    session["interests"] = user.get("interests", "")
    session["avatar"] = user.get("avatar", "")
    session["saved_items"] = user.get("saved_items", [])
    session["game_levels"] = user.get("game_levels", {})
    session["followers"] = user.get("followers", [])
    session["following"] = user.get("following", [])
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    if "user_id" in session:
        save_user_progress(session["user_id"])
    session.clear()
    return redirect(url_for("welcome"))


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def index():
    return render_template("index.html")

def query_ai(passage, api_key):
    prompt = (
        "You are a world-class classical philologist and archaeologist with deep knowledge of ancient Greek and Latin literature. "
        "Identify the following passage. It may be ancient Greek or Latin, possibly fragmentary or obscure. "
        "Think step by step: consider the language, style, metre, vocabulary, and any recognizable references.\n\n"
        "Return ONLY valid JSON with these fields (or the subset you can determine):\n"
        "- text: the exact passage provided\n"
        "- work: the title of the work (be specific)\n"
        "- author: the author's full name\n"
        "- book: book number (integer)\n"
        "- section: section number (integer, if applicable)\n"
        "- line: line number (integer, if known from the text)\n"
        "- description: a detailed explanation of the passage in context (2-3 sentences)\n"
        "- historicalContext: historical background of when and why this was written (1-2 sentences)\n"
        "- culturalSignificance: why this passage matters in classical literature/culture (1-2 sentences)\n"
        "- archaeologicalContext: any known archaeological evidence related to this work or its setting (1-2 sentences)\n"
        "- translations: an object with 2-3 translator/edition names as keys and short quotes as values. If you don't know specific translations, use well-known ones.\n\n"
        "Take your time and be thorough. Even obscure or fragmentary texts can be identified. "
        "If you truly cannot identify it at all, return: {\"matched\": false}\n\n"
        "Passage: '''" + passage + "'''"
    )
    url = "https://api.aiand.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "deepseek-ai/deepseek-v4-pro",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1500,
    }
    r = requests.post(url, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    resp = r.json()
    raw = resp["choices"][0]["message"]["content"]
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()
    data = json.loads(raw)
    if data.get("matched") is False:
        return None
    return data

@app.route("/api/excavations")
@login_required
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

_NEWS_CACHE = None
_NEWS_CACHE_DATE = ""

@app.route("/api/news")
@login_required
def api_news():
    global _NEWS_CACHE, _NEWS_CACHE_DATE
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    six_am_today = now.replace(hour=6, minute=0, second=0, microsecond=0)
    should_refresh = (
        _NEWS_CACHE is None
        or _NEWS_CACHE_DATE != today_str
        or (_NEWS_CACHE_DATE == today_str and now >= six_am_today and now.hour == 6 and now.minute < 5)
    )
    if not should_refresh:
        return jsonify({"articles": _NEWS_CACHE})
    feeds = [
        "https://news.google.com/rss/search?q=archaeology+excavation+ancient&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=archaeological+discovery&hl=en-US&gl=US&ceid=US:en",
    ]
    seen = set()
    articles = []
    for feed_url in feeds:
        try:
            r = requests.get(feed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
            root = ET.fromstring(r.text)
            for item in root.findall(".//item"):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub = item.findtext("pubDate", "")
                src = item.findtext("source", "")
                desc = item.findtext("description", "")
                if not title or not link or link in seen:
                    continue
                seen.add(link)
                desc_clean = re.sub(r"<[^>]+>", "", desc or "").strip()
                articles.append({
                    "title": title,
                    "url": link,
                    "source": src or "Google News",
                    "date": pub[:16] if pub else "",
                    "snippet": desc_clean[:300] if desc_clean else "",
                })
        except Exception:
            continue
        if len(articles) >= 15:
            break
    _NEWS_CACHE = articles[:20]
    _NEWS_CACHE_DATE = today_str
    return jsonify({"articles": articles[:20]})

@app.route("/api/journeys")
@login_required
def api_journeys():
    journey_id = request.args.get("id", "")
    if journey_id and journey_id in JOURNEYS:
        return jsonify(JOURNEYS[journey_id])
    return jsonify(list(JOURNEYS.values()))

@app.route("/api/sources")
@login_required
def api_sources():
    event_id = request.args.get("id", "")
    if event_id and event_id in EVENTS:
        return jsonify(EVENTS[event_id])
    return jsonify(list(EVENTS.values()))

def query_ai_event_search(query, api_key):
    catalog = []
    for eid, ev in EVENTS.items():
        catalog.append(
            f"- id: {eid} | name: {ev['name']} | date: {ev['date']} | location: {ev['location']} | "
            f"figures: {', '.join(ev.get('keyFigures', []))} | "
            f"sources: {', '.join(s['author'] + ' (' + s['work'] + ')' for s in ev['sources'])} | "
            f"summary: {ev['summary']}"
        )
    prompt = (
        "You are a world-class classical historian. The user is searching a database of historical events "
        "from the ancient Mediterranean world. Each event is listed below with its id, name, date, location, "
        "key figures, ancient sources that mention it, and a summary.\n\n"
        "The user's search query may be natural language (e.g. 'battles where the underdog won', "
        "'events involving Cleopatra', 'naval battles', 'the fall of a city'). "
        "Match the query to the most relevant events — considering themes, outcomes, figures, and context, "
        "not just literal keywords.\n\n"
        "Return ONLY valid JSON: a list of objects, each with:\n"
        '- "id": the event id from the catalog\n'
        '- "reason": a short explanation (1 sentence) of why this event matches the query\n\n'
        "If no events match, return an empty list: []\n"
        "Do not include events not in the catalog. Order by relevance (most relevant first).\n\n"
        "Event catalog:\n" + "\n".join(catalog) + "\n\n"
        "User query: '''" + query + "'''"
    )
    url = "https://api.aiand.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "deepseek-ai/deepseek-v4-pro",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1000,
    }
    r = requests.post(url, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    resp = r.json()
    raw = resp["choices"][0]["message"]["content"]
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()
    data = json.loads(raw)
    if not isinstance(data, list):
        return []
    valid_ids = set(EVENTS.keys())
    return [m for m in data if m.get("id") in valid_ids]

@app.route("/api/search-events", methods=["POST"])
@login_required
def api_search_events():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"matches": [], "source": "none"})

    ai_key = os.environ.get("AIAND_API_KEY", "")
    if ai_key:
        try:
            matches = query_ai_event_search(query, ai_key)
            award_points("ai_search", query)
            return jsonify({"matches": matches, "source": "ai"})
        except Exception as e:
            logger.error(f"AI event search error: {e}")

    return jsonify({"matches": [], "source": "fallback", "message": "AI search unavailable"})

@app.route("/api/identify", methods=["POST"])
@login_required
def api_identify():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    ai_key = os.environ.get("AIAND_API_KEY", "")
    if ai_key:
        try:
            result = query_ai(text, ai_key)
            if result:
                award_points("identify_text", result.get("work", ""))
                return jsonify({"matched": True, "source": "ai", **result})
        except Exception as e:
            logger.error(f"AI API error: {e}")

    match = find_text_match(text)
    if match:
        award_points("identify_text", match.get("work", ""))
        return jsonify({"matched": True, "source": "library", **match})

    return jsonify({"matched": False, "message": "No classical text match found."})

@app.route("/api/users")
@login_required
def api_users():
    users = _load_users()
    my_id = session["user_id"]
    my_following = session.get("following", [])
    result = []
    for u in users:
        u_followers = u.get("followers", [])
        result.append({
            "id": u.get("id"),
            "username": u.get("username", ""),
            "bio": u.get("bio", ""),
            "interests": u.get("interests", ""),
            "avatar": _clean_avatar(u.get("avatar", "")),
            "total_points": u.get("total_points", 0),
            "saved_items_count": len(u.get("saved_items", [])),
            "created_at": u.get("created_at", ""),
            "follower_count": len(u_followers),
            "is_following": u.get("id") in my_following,
        })
    return jsonify({"users": result})

@app.route("/api/users/<int:user_id>")
@login_required
def api_user_detail(user_id):
    users = _load_users()
    my_following = session.get("following", [])
    for u in users:
        if u.get("id") == user_id:
            u_followers = u.get("followers", [])
            return jsonify({
                "id": u.get("id"),
                "username": u.get("username", ""),
                "bio": u.get("bio", ""),
                "interests": u.get("interests", ""),
                "avatar": _clean_avatar(u.get("avatar", "")),
                "total_points": u.get("total_points", 0),
                "saved_items": u.get("saved_items", []),
                "created_at": u.get("created_at", ""),
                "follower_count": len(u_followers),
                "is_following": user_id in my_following,
            })
    return jsonify({"error": "User not found"}), 404


@app.route("/api/profile")
@login_required
def api_profile():
    users = _load_users()
    for u in users:
        if u.get("id") == session.get("user_id"):
            return jsonify({
                "username": u.get("username", ""),
                "email": u.get("email", ""),
                "bio": u.get("bio", ""),
                "interests": u.get("interests", ""),
                "avatar": _clean_avatar(u.get("avatar", "")),
                "saved_items": u.get("saved_items", []),
            })
    return jsonify({"error": "User not found"}), 404


@app.route("/api/profile", methods=["POST"])
@login_required
def api_profile_update():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    users = _load_users()
    for u in users:
        if u.get("id") == session.get("user_id"):
            u["bio"] = data.get("bio", u.get("bio", ""))[:500]
            u["interests"] = data.get("interests", u.get("interests", ""))[:300]
            if "avatar" in data:
                av = data["avatar"]
                # extract src from <img> tag if present
                img_match = re.search(r'<img[^>]+src="([^"]+)"', av)
                if img_match:
                    av = img_match.group(1)
                # strip protocol+host to get relative path if full URL
                if av.startswith("http"):
                    parsed = urlparse(av)
                    if parsed.path:
                        av = parsed.path
                u["avatar"] = av[:200]
                session["avatar"] = u["avatar"]
            with _persist_lock:
                _persist_users()
            return jsonify({"saved": True})
    return jsonify({"error": "User not found"}), 404

@app.route("/api/upload-avatar", methods=["POST"])
@login_required
def api_upload_avatar():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file"}), 400
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Allowed: png, jpg, jpeg, gif, webp"}), 400
    filename = f"avatar_{session.get('user_id')}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    url = f"/static/uploads/{filename}"
    users = _load_users()
    for u in users:
        if u.get("id") == session.get("user_id"):
            u["avatar"] = url
            session["avatar"] = url
            with _persist_lock:
                _persist_users()
            return jsonify({"url": url})
    return jsonify({"error": "User not found"}), 404

@app.route("/api/saved-items", methods=["GET"])
@login_required
def api_get_saved_items():
    users = _load_users()
    for u in users:
        if u.get("id") == session.get("user_id"):
            return jsonify({"items": u.get("saved_items", [])})
    return jsonify({"error": "User not found"}), 404

@app.route("/api/saved-items", methods=["POST"])
@login_required
def api_add_saved_item():
    data = request.get_json()
    if not data or "type" not in data or "content" not in data:
        return jsonify({"error": "type and content required"}), 400
    item_type = data["type"]
    if item_type not in ("article", "image", "note"):
        return jsonify({"error": "Invalid type"}), 400
    users = _load_users()
    for u in users:
        if u.get("id") == session.get("user_id"):
            items = u.get("saved_items", [])
            item = {
                "id": uuid.uuid4().hex[:12],
                "type": item_type,
                "content": data["content"][:1000],
                "title": data.get("title", "")[:100],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            items.append(item)
            u["saved_items"] = items
            session["saved_items"] = items
            with _persist_lock:
                _persist_users()
            return jsonify({"saved": True, "item": item})
    return jsonify({"error": "User not found"}), 404

@app.route("/api/saved-items/<item_id>", methods=["DELETE"])
@login_required
def api_delete_saved_item(item_id):
    users = _load_users()
    for u in users:
        if u.get("id") == session.get("user_id"):
            items = u.get("saved_items", [])
            u["saved_items"] = [i for i in items if i.get("id") != item_id]
            session["saved_items"] = u["saved_items"]
            with _persist_lock:
                _persist_users()
            return jsonify({"saved": True})
    return jsonify({"error": "User not found"}), 404

@app.route("/api/stats")
@login_required
def api_stats():
    return jsonify(get_user_stats())


@app.route("/api/game-levels", methods=["GET"])
@login_required
def api_get_game_levels():
    return jsonify({"game_levels": session.get("game_levels", {})})


@app.route("/api/game-levels", methods=["POST"])
@login_required
def api_set_game_levels():
    data = request.get_json()
    if not data or "game_levels" not in data:
        return jsonify({"error": "No game_levels"}), 400
    session["game_levels"] = data["game_levels"]
    session.modified = True
    return jsonify({"saved": True})


@app.route("/api/follow/<int:target_id>", methods=["POST"])
@login_required
def api_follow(target_id):
    user_id = session["user_id"]
    if user_id == target_id:
        return jsonify({"error": "Cannot follow yourself"}), 400
    users = _load_users()
    current = next((u for u in users if u.get("id") == user_id), None)
    target = next((u for u in users if u.get("id") == target_id), None)
    if not current or not target:
        return jsonify({"error": "User not found"}), 404
    following = current.setdefault("following", [])
    if target_id in following:
        following.remove(target_id)
        session["following"] = following
        target_followers = target.setdefault("followers", [])
        if user_id in target_followers:
            target_followers.remove(user_id)
        with _persist_lock:
            _persist_users()
        return jsonify({"following": False, "follower_count": len(target_followers)})
    else:
        following.append(target_id)
        session["following"] = following
        target_followers = target.setdefault("followers", [])
        if user_id not in target_followers:
            target_followers.append(user_id)
        with _persist_lock:
            _persist_users()
        return jsonify({"following": True, "follower_count": len(target_followers)})


@app.route("/api/save-progress", methods=["POST"])
@login_required
def api_save_progress():
    save_user_progress(session["user_id"])
    return jsonify({"saved": True})

@app.route("/api/award", methods=["POST"])
@login_required
def api_award():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    action = data.get("action", "")
    detail = data.get("detail", "")[:200]
    if action not in POINTS:
        return jsonify({"error": "Invalid action"}), 400
    entry = award_points(action, detail)
    stats = get_user_stats()
    return jsonify({
        "awarded": entry is not None,
        "points": entry["points"] if entry else 0,
        "total_points": stats["total_points"],
        "achievements_unlocked": stats["achievements_unlocked"],
        "all_achievements": stats["achievements"],
    })

@app.route("/api/quiz/trivia")
@login_required
def api_quiz_trivia():
    import random
    count = int(request.args.get("count", "5"))
    count = min(count, len(TRIVIA_QUESTIONS))
    indices = random.sample(range(len(TRIVIA_QUESTIONS)), count)
    questions = [{"qid": i, "q": TRIVIA_QUESTIONS[i]["q"], "choices": TRIVIA_QUESTIONS[i]["choices"]} for i in indices]
    return jsonify({"questions": questions})

@app.route("/api/quiz/truefalse")
@login_required
def api_quiz_truefalse():
    import random
    count = int(request.args.get("count", "5"))
    count = min(count, len(TRUE_FALSE_QUESTIONS))
    indices = random.sample(range(len(TRUE_FALSE_QUESTIONS)), count)
    questions = [{"qid": i, "q": TRUE_FALSE_QUESTIONS[i]["q"]} for i in indices]
    return jsonify({"questions": questions})

@app.route("/api/quiz/check", methods=["POST"])
@login_required
def api_quiz_check():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    game_type = data.get("type", "")
    answers = data.get("answers", [])
    if not answers:
        return jsonify({"error": "No answers"}), 400

    if game_type == "trivia":
        correct = 0
        results = []
        for ans in answers:
            qid = ans.get("qid", -1)
            q = TRIVIA_QUESTIONS[qid] if 0 <= qid < len(TRIVIA_QUESTIONS) else None
            if not q:
                continue
            is_correct = ans.get("choice") == q["answer"]
            if is_correct:
                correct += 1
            results.append({"correct": is_correct, "explain": q["explain"], "answer": q["answer"]})
        points = correct * 5 - (len(answers) - correct) * 2
        if correct == len(answers) and len(answers) > 0:
            points += 20
        adjust = adjust_points(points, f"trivia: {correct}/{len(answers)}")
        stats = get_user_stats()
        return jsonify({"correct": correct, "total": len(answers), "points": points, "results": results, "total_points": stats["total_points"]})

    elif game_type == "truefalse":
        correct = 0
        results = []
        for ans in answers:
            qid = ans.get("qid", -1)
            q = TRUE_FALSE_QUESTIONS[qid] if 0 <= qid < len(TRUE_FALSE_QUESTIONS) else None
            if not q:
                continue
            is_correct = ans.get("answer") == q["answer"]
            if is_correct:
                correct += 1
            results.append({"correct": is_correct, "explain": q["explain"], "answer": q["answer"]})
        points = correct * 4 - (len(answers) - correct) * 2
        if correct == len(answers) and len(answers) > 0:
            points += 15
        adjust = adjust_points(points, f"truefalse: {correct}/{len(answers)}")
        stats = get_user_stats()
        return jsonify({"correct": correct, "total": len(answers), "points": points, "results": results, "total_points": stats["total_points"]})

    elif game_type == "scramble":
        correct = 0
        results = []
        for ans in answers:
            word = next((w for w in SCRAMBLE_WORDS if w["answer"].upper() == ans.get("answer", "").upper()), None)
            is_correct = word is not None
            if is_correct:
                correct += 1
            results.append({"correct": is_correct, "answer": word["answer"] if word else ans.get("answer", "")})
        points = correct * 6 - (len(answers) - correct) * 3
        if correct == len(answers) and len(answers) > 0:
            points += 25
        adjust = adjust_points(points, f"scramble: {correct}/{len(answers)}")
        stats = get_user_stats()
        return jsonify({"correct": correct, "total": len(answers), "points": points, "results": results, "total_points": stats["total_points"]})

    elif game_type == "matching":
        correct = 0
        results = []
        for ans in answers:
            is_correct = _check_match(ans.get("setId", 0), ans.get("left", ""), ans.get("matched", ""))
            if is_correct:
                correct += 1
            results.append({"correct": is_correct})
        points = correct * 4 - (len(answers) - correct) * 2
        if correct == len(answers) and len(answers) > 0:
            points += 20
        adjust = adjust_points(points, f"matching: {correct}/{len(answers)}")
        stats = get_user_stats()
        return jsonify({"correct": correct, "total": len(answers), "points": points, "results": results, "total_points": stats["total_points"]})

    return jsonify({"error": "Invalid game type"}), 400


def _check_match(set_id, left, matched):
    if set_id >= len(MATCHING_SETS):
        return False
    for pair in MATCHING_SETS[set_id]["pairs"]:
        if pair["left"].lower() == left.lower() and pair["right"].lower() == matched.lower():
            return True
    return False


@app.route("/api/quiz/scramble")
@login_required
def api_quiz_scramble():
    import random
    count = int(request.args.get("count", "5"))
    count = min(count, len(SCRAMBLE_WORDS))
    words = random.sample(SCRAMBLE_WORDS, count)
    return jsonify({"words": [{"scrambled": w["scrambled"], "hint": w["hint"]} for w in words]})


@app.route("/api/quiz/matching")
@login_required
def api_quiz_matching():
    import random
    count = int(request.args.get("count", "1"))
    count = min(count, len(MATCHING_SETS))
    sets = random.sample(MATCHING_SETS, count)
    result = []
    for i, s in enumerate(sets):
        rights = [p["right"] for p in s["pairs"]]
        shuffled_rights = rights[:]
        random.shuffle(shuffled_rights)
        result.append({
            "setId": MATCHING_SETS.index(s),
            "title": s["title"],
            "lefts": [p["left"] for p in s["pairs"]],
            "rights": shuffled_rights,
        })
    return jsonify({"sets": result})


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    data = request.get_json()
    if not data or not data.get("message", "").strip():
        return jsonify({"reply": "Please say something!"})
    message = data["message"].strip()[:1000]
    ai_key = os.environ.get("AIAND_API_KEY", "")
    if not ai_key:
        return jsonify({"reply": "The AI assistant is not available right now."})
    try:
        prompt = (
            "You are a helpful assistant for an ancient world exploration app called Excavatio. "
            "You can answer questions about ancient history, archaeology, classical literature, mythology, "
            "and the app's features. Be concise, informative, and friendly. If you don't know something, say so.\n\n"
            f"User: {message}"
        )
        url = "https://api.aiand.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {ai_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": "deepseek-ai/deepseek-v4-pro",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 600,
        }
        r = requests.post(url, json=body, headers=headers, timeout=30)
        r.raise_for_status()
        resp = r.json()
        reply = resp["choices"][0]["message"]["content"].strip()
        return jsonify({"reply": reply})
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({"reply": "Sorry, I couldn't process that right now. Try again later."})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
