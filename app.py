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
}

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

def query_gemini(passage, api_key):
    prompt = (
        "You are a classical philologist. Identify the following ancient Greek or Latin passage. "
        "Return ONLY valid JSON with these fields (or the subset you can determine):\n"
        "- text: the exact passage provided\n"
        "- work: the title of the work\n"
        "- author: the author's name\n"
        "- book: book number (integer)\n"
        "- section: section number (integer, if applicable)\n"
        "- line: line number (integer, if known from the text)\n"
        "- description: a brief explanation of the passage in context (1-2 sentences)\n"
        "- translations: an object with 2-3 translator/edition names as keys and short quotes as values. If you don't know specific translations, use well-known ones.\n\n"
        "If you cannot identify it at all, return: {\"matched\": false}\n\n"
        "Passage: '''" + passage + "'''"
    )
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 800},
    }
    r = requests.post(url, json=body, timeout=20)
    r.raise_for_status()
    resp = r.json()
    raw = resp["candidates"][0]["content"]["parts"][0]["text"]
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

@app.route("/api/journeys")
def api_journeys():
    journey_id = request.args.get("id", "")
    if journey_id and journey_id in JOURNEYS:
        return jsonify(JOURNEYS[journey_id])
    return jsonify(list(JOURNEYS.values()))

@app.route("/api/identify", methods=["POST"])
def api_identify():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            result = query_gemini(text, gemini_key)
            if result:
                return jsonify({"matched": True, "source": "ai", **result})
        except Exception:
            pass

    match = find_text_match(text)
    if match:
        return jsonify({"matched": True, "source": "library", **match})

    return jsonify({"matched": False, "message": "No classical text match found."})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
