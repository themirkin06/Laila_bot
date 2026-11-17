"""Explicit, per-user scene continuity with conservative location updates."""
import re
import time


_TURKIC = r"\u00c7\u011e\u0130\u00d6\u015e\u00dc\u00e7\u011f\u0131\u00f6\u015f\u00fc"
_TOKEN = rf"[\w{_TURKIC}'\u2019.-]+"
_MOVE = (
    r"gid(?:iyorum|iyoruz|iyor|elim|in|ecek|dim|dik)|"
    r"git(?:tim|tik|iyorum|iyoruz)|"
    r"ge\u00e7(?:tim|tik|iyorum|iyoruz|iyor|elim|ece\u011fiz)|"
    r"vard\u0131k|geldik"
)
_DESTINATION_BEFORE = re.compile(rf"\b(?P<place>{_TOKEN}(?:\s+{_TOKEN})?)\s+(?:{_MOVE})\b", re.IGNORECASE)
_DESTINATION_AFTER = re.compile(rf"\b(?:{_MOVE})\s+(?:\u015fimdi\s+)?(?P<place>{_TOKEN})", re.IGNORECASE)
_NON_PLACES = {
    "sana", "bana", "ona", "eve", "biraz", "sonra", "\u015fimdi", "d\u0131\u015far\u0131", "i\u00e7eri",
    "uyumaya", "\u00e7al\u0131\u015fmaya", "yemek", "kahve", "y\u00fcr\u00fcy\u00fc\u015f", "oraya", "buraya",
}
_COMMON_PLACES = {
    "ev", "evim", "eve", "mutfak", "mutfa\u011fa", "mutfaga", "salon", "salona", "oda", "odaya",
    "yatak odas\u0131", "balkon", "balkona", "bah\u00e7e", "bah\u00e7eye", "park", "parka", "kafe", "kafeye",
    "cafe", "ofis", "ofise", "i\u015f yeri", "i\u015fyerine", "okul", "okula", "\u00fcniversite", "\u00fcniversiteye",
    "kamp\u00fcs", "kamp\u00fcse", "k\u00fct\u00fcphane", "k\u00fct\u00fcphaneye", "kitap\u00e7\u0131", "kitap\u00e7\u0131ya", "market", "markete",
    "sahil", "sahile", "restoran", "restorana", "lokanta", "lokantaya", "spor salonu", "orman", "ormana",
    "s\u00fcr\u00fc evi", "ta\u015f \u00e7ember", "arabaya", "arabamla",
}
_TRANSLATE = str.maketrans({
    "\u00e7": "c", "\u011f": "g", "\u0131": "i", "\u00f6": "o", "\u015f": "s", "\u00fc": "u",
})


def _clean_place(value: str) -> str | None:
    place = " ".join((value or "").strip(" \t,.;:!?*\"\u201c\u201d()[]{}").split())
    folded = place.casefold()
    if not place or len(place) > 80 or folded in _NON_PLACES:
        return None
    common_folded = {item.translate(_TRANSLATE) for item in _COMMON_PLACES}
    if folded.translate(_TRANSLATE) not in common_folded and not place[0].isupper():
        return None
    if len(place.split()) > 2:
        return None
    return place


def _fold(value: str) -> str:
    return str(value or "").casefold().translate(_TRANSLATE)


def _is_known_person(place: str, known_people) -> bool:
    candidate = _fold(place)
    candidate = candidate.split("'")[0].split("\u2019")[0]
    for name in known_people or []:
        person = _fold(name).strip()
        if candidate == person:
            return True
        if candidate.startswith(person) and candidate[len(person):] in {
            "e", "a", "ye", "ya", "nin", "nın", "nun", "nün", "in", "ın", "un", "ün",
        }:
            return True
    return False


def explicit_destination(text: str, known_people=()) -> str | None:
    """Return only a short, explicit destination; ambiguous movement yields None."""
    source = str(text or "")
    for pattern in (_DESTINATION_BEFORE, _DESTINATION_AFTER):
        for match in pattern.finditer(source):
            candidate = match.group("place")
            for value in (candidate, candidate.split()[-1]):
                place = _clean_place(value)
                if place and _is_known_person(place, known_people):
                    continue
                if place:
                    return place
    return None


def update_scene_state(state: dict, character_key: str, text: str, companions=None, known_people=()) -> bool:
    """Record explicit destination and current cast in a character's user-scoped state."""
    scenes = state.setdefault("scene_states", {})
    if not isinstance(scenes, dict):
        scenes = state["scene_states"] = {}
    record = scenes.setdefault(character_key, {"location": None, "companions": [], "last_transition": None})
    if not isinstance(record, dict):
        record = scenes[character_key] = {"location": None, "companions": [], "last_transition": None}
    changed = False
    destination = explicit_destination(text, known_people)
    if destination:
        record["location"] = destination
        record["last_transition"] = {"to": destination, "at": int(time.time()), "statement": str(text)[:500]}
        changed = True
    if companions is not None:
        names = list(dict.fromkeys(str(name) for name in companions if name))
        if record.get("companions", []) != names:
            record["companions"] = names
            changed = True
    return changed


def scene_state_context(state: dict, character_key: str) -> str:
    scenes = state.get("scene_states", {})
    record = scenes.get(character_key, {}) if isinstance(scenes, dict) else {}
    if not isinstance(record, dict):
        record = {}
    location = record.get("location")
    companions = record.get("companions") or []
    location_text = str(location) if location else "bilinmiyor (konum uydurma; son bilinen durumu koru)"
    companions_text = ", ".join(companions) if companions else "kay\u0131tl\u0131 yan karakter yok"
    return (
        "[KALICI SAHNE DURUMU] Son a\u00e7\u0131k\u00e7a belirtilen konum: " + location_text + ". "
        "Sahnede kay\u0131tl\u0131 yan karakterler: " + companions_text + ". "
        "Bu durum kullan\u0131c\u0131ya ait Redis kayd\u0131nda korunur. A\u00e7\u0131k\u00e7a belirtilmemi\u015f bir yer veya geli\u015f/ayr\u0131l\u0131\u015f uydurma; "
        "konu\u015fmada net bir ge\u00e7i\u015f olursa bunu k\u0131sa ve tutarl\u0131 bi\u00e7imde anlat."
    )

