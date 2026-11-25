"""Muhafazakâr sahne/konum hafızası.

Yalnızca açıkça söylenen yer değişikliklerini kaydeder. Belirsiz hedefleri,
kişi adlarını ve yalnızca yola çıkmayı varış olarak kabul etmez.
"""
from __future__ import annotations

import re
import unicodedata


# Yaygın yer adları/yer türleri. Bilinmeyen özel yer adları da ek kalıpla yakalanır.
_KNOWN_PLACES = (
    "ev", "eve", "evde", "iş", "işe", "işte", "ofis", "ofise", "ofiste",
    "mutfak", "mutfağa", "mutfakta", "salon", "salona", "salonda",
    "oda", "odaya", "odada", "yatak odası", "balkon", "balkona", "balkonda",
    "bahçe", "bahçeye", "bahçede", "dışarı", "dışarıya", "park", "parka",
    "kafe", "kafeye", "kafede", "okul", "okula", "okulda", "market", "markete",
    "mağaza", "mağazaya", "hastane", "hastaneye", "restoran", "restorana",
    "kitapçı", "kitapçıya", "sahil", "sahile", "istasyon", "istasyona",
)

_MOVEMENT = r"(?:gectim|geciyorum|gidiyorum|gidiyoruz|gittim|vardim|ulastim|geldim|geliyorum|geliyoruz|dondum|donuyorum)"


def _clean(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.translate(str.maketrans({"ı": "i"}))
    return value.replace("’", "'")


def explicit_destination(text: str, known_people: list[str] | None = None) -> str | None:
    """Cümlede açıkça belirtilen hedefi döndürür; belirsiz hedefte None döner."""
    raw = _clean(text)
    if not raw:
        return None
    normalized = _norm(raw)
    people = {_norm(p) for p in (known_people or []) if _clean(p)}

    # Bilinen mekânlar içinde hareket fiiline en yakın açık hedefi seç.
    place_matches = []
    for place in _KNOWN_PLACES:
        p = re.escape(_norm(place))
        pattern = rf"\b({p})\b[^.!?;]{{0,45}}\b{_MOVEMENT}\b|\b{_MOVEMENT}\b[^.!?;]{{0,45}}\b({p})\b"
        for found in re.finditer(pattern, normalized):
            place_matches.append((found.start(), place))
    if place_matches:
        return max(place_matches, key=lambda item: item[0])[1]

    # Özel mekân adı: "Yıldız Parkı'na gidiyoruz" gibi. Kişi isimleri hariç.
    match = re.search(
        rf"\b([A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü]*(?:\s+[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü]*){{0,3}})(['’]?(?:na|ne|a|e|ya|ye))\s+{_MOVEMENT}\b",
        raw,
    )
    if match:
        candidate = _clean(match.group(1))
        if _norm(candidate) not in people and len(candidate) >= 3:
            return candidate + match.group(2).replace("’", "'")

    return None


def update_scene_state(
    state: dict,
    character: str,
    text: str,
    companions: list[str] | None = None,
    known_people: list[str] | None = None,
    *,
    speaker: str = "character",
) -> bool:
    """Sahne durumunu günceller. speaker='user' yalnızca geliş durumunu kaydeder."""
    if not isinstance(state, dict):
        return False
    character = _clean(character).casefold()
    if not character:
        return False

    all_states = state.setdefault("scene_states", {})
    if not isinstance(all_states, dict):
        all_states = {}
        state["scene_states"] = all_states
    entry = all_states.setdefault(character, {"location": None, "companions": []})
    if not isinstance(entry, dict):
        entry = {"location": None, "companions": []}
        all_states[character] = entry
    entry.setdefault("location", None)
    entry.setdefault("companions", [])

    raw = _clean(text)
    if not raw:
        return False
    changed = False

    n = _norm(raw)
    if speaker == "user":
        # Yola çıkma ile varışı kesin biçimde ayır.
        if re.search(r"\b(?:geliyorum|yanina geliyorum|size geliyorum|yola ciktim|yoldayim)\b", n):
            if entry.get("user_presence") != "yolda":
                entry["user_presence"] = "yolda"
                changed = True
        elif re.search(r"\b(?:geldim|kapidayim|iceri girdim|iceriye girdim|yanindayim|buradayim)\b", n):
            if entry.get("user_presence") != "birlikte":
                entry["user_presence"] = "birlikte"
                changed = True
        elif re.search(r"\b(?:eve dondum|evime dondum|ayrildim|ciktim)\b", n):
            if entry.get("user_presence") != "ayrı":
                entry["user_presence"] = "ayrı"
                changed = True
        return changed

    if speaker == "character":
        if re.search(r"\b(?:sana geliyorum|yanina geliyorum|evine geliyorum|sana dogru geliyorum|yola ciktim sana dogru)\b", n):
            if entry.get("character_presence") != "kullaniciya_yolda":
                entry["character_presence"] = "kullaniciya_yolda"
                changed = True
        elif re.search(r"\b(?:yanindayim|yanina geldim|yanina vardim|kapindayim)\b", n):
            if entry.get("character_presence") != "kullanicinin_yaninda":
                entry["character_presence"] = "kullanicinin_yaninda"
                changed = True

    destination = explicit_destination(raw, known_people=known_people)
    if destination and entry.get("location") != destination:
        entry["location"] = destination
        changed = True

    if companions is not None:
        clean_companions = []
        for person in companions:
            person = _clean(person)
            if person and person not in clean_companions:
                clean_companions.append(person)
        if entry.get("companions") != clean_companions:
            entry["companions"] = clean_companions
            changed = True

    return changed


def scene_state_context(state: dict, character: str) -> str:
    """Model için kısa, güvenli konum ve beraberlik bağlamı üretir."""
    character = _clean(character).casefold()
    all_states = state.get("scene_states", {}) if isinstance(state, dict) else {}
    entry = all_states.get(character, {}) if isinstance(all_states, dict) else {}
    if not isinstance(entry, dict):
        entry = {}

    lines = ["[OTOMATİK SAHNE/KONUM HAFIZASI]"]
    location = entry.get("location")
    if location:
        lines.append(f"Karakterin son açıkça belirtilen konumu: {location}.")
    else:
        lines.append("Karakterin konumu açıkça kaydedilmedi; yeni bir yer uydurma.")

    companions = entry.get("companions") or []
    if companions:
        lines.append("Son kayıtta birlikte bulunan kişiler: " + ", ".join(map(str, companions)) + ".")

    character_presence = entry.get("character_presence")
    if character_presence == "kullaniciya_yolda":
        lines.append("Karakter kullanıcıya doğru yolda; henüz varmış gibi davranma.")
    elif character_presence == "kullanicinin_yaninda":
        lines.append("Karakter kullanıcının yanına vardığını açıkça belirtti; bu buluşma durumunu koru.")

    presence = entry.get("user_presence")
    if presence == "yolda":
        lines.append("Kullanıcı yanına gelmek üzere yolda; henüz varmış veya yanında duruyormuş gibi davranma.")
    elif presence == "birlikte":
        lines.append("Kullanıcı açıkça geldiğini belirtti; bağlama uygunsa aynı ortamdasınız.")
    elif presence == "ayrı":
        lines.append("Kullanıcı ayrıldığını belirtti; tekrar buluştuğunuz açıkça söylenmedikçe ayrı yerlerdesiniz.")
    else:
        lines.append("Kullanıcının fiziksel olarak yanında olduğu varsayılmaz; aksi açıkça söylenmedikçe ayrı yerlerden mesajlaşıyorsunuz.")

    lines.append("Belirsiz veya varsayımsal ifadelerle konum değiştirme; son bilinen durumu koru.")
    return " ".join(lines)
