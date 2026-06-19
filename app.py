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
    match = find_text_match(text)
    if not match:
        return jsonify({"matched": False, "message": "No classical text match found."})
    return jsonify({"matched": True, **match})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
