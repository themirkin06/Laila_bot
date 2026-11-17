"""Dynamic, persistent supporting characters and per-user scene participation."""
import hashlib
import re
import time


WORLD_REDIS_KEY = "bot:sosyal_dunya:v1"
MEMORY_LIMIT_PER_CHARACTER = 40
EVENT_LIMIT_PER_USER = 60

_TRANSLATION = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"})
_INVITE_RE = re.compile(
    r"\b(cagir\w*|davet\w*|gelsin\w*|gelsene\w*|katil\w*|yanimiza\w*|bize gel\w*|"
    r"birlikte sohbet|beraber sohbet|ara\w*|sohbete katil\w*)\b", re.I,
)
_LEAVE_RE = re.compile(
    r"\b(git\w*|ayril\w*|eve don\w*|veda\w*|yalniz kal\w*|bas basa kal\w*|"
    r"ikimiz kal\w*|sahne\w*den cik\w*)\b", re.I,
)
_CLEAR_SCENE_RE = re.compile(r"\b(yalniz kal\w*|bas basa kal\w*|ikimiz kal\w*|herkes git\w*|hepsi git\w*)\b", re.I)
_ARRIVAL_RE = re.compile(r"\b(ziyarete gel\w*|yanimiza gel\w*|yanimda|yanimizda|burada|simdi geldi|geldi|geliyor|iceri girdi|katildi)\b", re.I)
_CAPITAL_NAME = r"[A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,20}"
_RELATION_RE = re.compile(
    r"\b(?P<relation>komşu(?:m|su)?|komsu(?:m|su)?|arkadaş(?:ım|ı)?|arkadas(?:im|i)?|iş arkadaşı|is arkadas(?:im|i)?|"
    r"universite arkadas(?:im|i)?|kuzen(?:im|i)?|teyze(?:m|si)?|hala(?:m|si)?|"
    r"kardes(?:im|i)?|abla(?:m|si)?|abi(?:m|si)?|ogretmen(?:im|i)?|patron(?:um|u)?)\s+"
    r"(?P<name>[A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,20})", re.I,
)
_REVERSE_RELATION_RE = re.compile(
    rf"(?P<name>{_CAPITAL_NAME})(?:'[^ ]*)?\s+(?:benim\s+)?(?P<relation>komşu|komsu|arkadaş|arkadas|iş arkadaşı|is arkadas|"
    r"universite arkadas|kuzen|teyze|hala|kardes|abla|abi|ogretmen|patron)\w*", re.I,
)
_INVITED_NAME_RE = re.compile(
    rf"\b(?P<name>{_CAPITAL_NAME})(?:['’]?(?:yi|yı|yu|yü|ye|ya|i|ı|u|ü|e|a))?\s+"
    r"(?:.{0,30}?\b)?(?:çağır|çağırsana|davet et|gelsin|gelsene|katılsın|katılsana|"
    r"bize gelsin|yanımıza gelsin)\b", re.I,
)
_PHOTO_NAME_RE = re.compile(
    rf"^\s*(?P<name>{_CAPITAL_NAME})(?:['’](?:nin|nın|nun|nün|in|ın|un|ün))?(?:[,!]?\s+).{{0,60}}?\b(?:foto|fotoğraf|resim|selfie)\w*\b",
    re.I | re.S,
)
_JOINT_PHOTO_RE = re.compile(r"\b(ortak|birlikte|ikimizin|ucumuz|dordumuz|ile|ve|yaninda|yanimda|de yaninda)\b.*\b(foto|fotograf|resim|selfie)\w*\b", re.I | re.S)
_CAPITALIZED_TOKEN_RE = re.compile(_CAPITAL_NAME)
_SPEAKER_RE = re.compile(rf"(?:^|\n|\|\|\|)\s*(?P<name>{_CAPITAL_NAME})\s*:")
_COMMON_CAPITAL_WORDS = {
    "bugün", "bence", "bir", "bana", "fotoğraf", "foto", "hemen", "şimdi", "lütfen", "acaba",
    "çağırsana", "davet", "davetet", "gelsin", "gelsene", "katılsın", "katılsana", "yanımıza",
}

_PERSONALITIES = (
    ("dikkatli ve gözlemci", "önce dinleyip sonra konuşur; kısa, yerinde yorumlar yapar"),
    ("canlı ve sıcakkanlı", "gündelik, samimi Türkçe kullanır; ölçülü şakalaşır"),
    ("sakin ve pratik", "net ve sade konuşur; abartılı anlatımdan kaçınır"),
    ("özgüvenli ve meraklı", "akıcı konuşur; başkalarının sözünü takip eder"),
    ("utangaç ama içten", "nazik ve doğal konuşur; alışınca daha rahat olur"),
)
_APPEARANCES = (
    "oval yüz, ela gözler, omuz hizasında koyu kestane saç ve doğal cilt dokusu",
    "yumuşak yüz hatları, kahverengi gözler, kısa dalgalı siyah saç ve hafif çiller",
    "belirgin kaşlar, koyu gözler, uzun düz koyu saç ve sıcak ten tonu",
    "yuvarlak yüz, yeşil-kahverengi gözler, kıvırcık kumral saç ve doğal yaş çizgileri",
    "köşeli yüz hatları, koyu kahverengi gözler, kısa kestane saç ve belirgin gamzeler",
)
_CLOTHING = (
    "sade günlük bir kıyafet",
    "rahat, mevsime uygun gündelik kıyafetler",
    "zarif ve abartısız bir günlük kombin",
    "işine ve ortamına uygun sade kıyafetler",
)
_SCENES = (
    "a neighborhood cafe in daylight",
    "a calm apartment living room",
    "a small local shop on a quiet street",
    "a sunny park walkway",
    "a familiar workplace lounge",
)
_LIVES = (
    "hafta sonları ailesini ziyaret eder, akşamları polisiye roman okur",
    "sabahları erken yürüyüş yapar, yeni tarifler denemeyi sever",
    "iş çıkışında arkadaşlarıyla kahve içer, birikim yapıp tatile çıkmayı planlar",
    "pazar günleri pazara gider, balkonundaki bitkilerle ilgilenir",
    "müzik dinleyerek ev işleri yapar, yakında yeni bir kursa yazılmayı düşünüyor",
)
_JOBS_BY_RELATION = {
    "komşu": ("emekli bir memur", "mahallede küçük bir terzi dükkânı işleten biri", "bir okulda çalışan öğretmen"),
    "iş arkadaşı": ("şirkette proje yöneticisi", "aynı ofiste finans analisti", "ürün ekibinde tasarımcı"),
    "üniversite arkadaşı": ("iletişim öğrencisi", "sosyoloji öğrencisi", "yarı zamanlı çalışan üniversite öğrencisi"),
    "arkadaş": ("bir yayınevinde editör", "serbest çalışan grafik tasarımcı", "yerel bir kafede yönetici"),
}


def empty_world() -> dict:
    """Create an empty world; supporting people are added only when story needs them."""
    return {"schema": 1, "characters": {}, "relationships": [], "events": []}


def normalize_world(value) -> dict:
    world = value if isinstance(value, dict) else empty_world()
    world.setdefault("schema", 1)
    world.setdefault("characters", {})
    world.setdefault("relationships", [])
    world.setdefault("events", [])
    if not isinstance(world["characters"], dict):
        world["characters"] = {}
    if not isinstance(world["relationships"], list):
        world["relationships"] = []
    if not isinstance(world["events"], list):
        world["events"] = []
    for key, character in list(world["characters"].items()):
        if isinstance(character, dict):
            character.setdefault("key", key)
            character.setdefault("iliski", [])
            character.setdefault("memory", [])
    return world


def _normalize_text(value: str) -> str:
    return str(value or "").casefold().translate(_TRANSLATION)


def _slug(value: str) -> str:
    text = _normalize_text(value)
    slug = re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:28] or "kisi"
    suffix = hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]
    return f"npc_{slug}_{suffix}"


def find_character_key(name: str, world: dict) -> str | None:
    target = _normalize_text(name).strip(" .,!?:;'’")
    characters = normalize_world(world)["characters"]
    exact = [
        key for key, character in characters.items()
        if target in {_normalize_text(character.get("isim")), _normalize_text(key)}
    ]
    if len(exact) == 1:
        return exact[0]
    partial = [
        key for key, character in characters.items()
        if target and _normalize_text(character.get("isim", "")).split()[0] == target
    ]
    return partial[0] if len(partial) == 1 else None


def _relationship_for(text: str, anchor_name: str) -> str:
    normalized = _normalize_text(text)
    for pattern, label in (
        (r"is arkadas", "iş arkadaşı"),
        (r"universite arkadas", "üniversite arkadaşı"),
        (r"komsu", "komşu"),
        (r"kuzen", "kuzen"),
        (r"teyze|hala|kardes|abla|abi", "akraba"),
        (r"arkadas", "arkadaş"),
    ):
        if re.search(pattern, normalized):
            return label
    return f"{anchor_name} ile aynı sosyal çevreden tanıdık"


def create_character(
    world: dict, name: str, relation: str, anchor_key: str, anchor_name: str | None = None,
) -> tuple[dict, bool]:
    """Create a stable, deterministic NPC profile; an existing name keeps its identity."""
    world = normalize_world(world)
    display_name = " ".join(str(name or "").strip().split())[:40]
    if not re.fullmatch(r"[A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü'’-]{1,39}(?:\s+[A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü'’-]{1,39})?", display_name):
        return {}, False
    existing = find_character_key(display_name, world)
    if existing:
        edge = {"source": anchor_key, "target": existing, "type": relation or "tanıdık"}
        if anchor_key != existing and edge not in world["relationships"]:
            world["relationships"].append(edge)
        return world["characters"][existing], False
    first_name_matches = [
        character for character in world["characters"].values()
        if _normalize_text(character.get("isim", "")).split()[:1] == [_normalize_text(display_name).split()[0]]
    ]
    if len(first_name_matches) > 1:
        return {}, False
    key = _slug(display_name)
    digest = hashlib.sha256(_normalize_text(display_name).encode("utf-8")).digest()
    personality, speech = _PERSONALITIES[digest[0] % len(_PERSONALITIES)]
    age = (24, 27, 31, 34, 38, 43, 47, 52)[digest[1] % 8]
    appearance = _APPEARANCES[digest[2] % len(_APPEARANCES)]
    clothing = _CLOTHING[digest[3] % len(_CLOTHING)]
    scene = _SCENES[digest[4] % len(_SCENES)]
    life = _LIVES[digest[5] % len(_LIVES)]
    relation = relation or "tanıdık"
    anchor_name = anchor_name or anchor_key
    job_options = next(
        (values for label, values in _JOBS_BY_RELATION.items() if label in relation),
        ("kendi işini yürüten yetişkin bir kadın", "bir kurumda çalışan yetişkin bir kadın"),
    )
    job = job_options[digest[6] % len(job_options)]
    profile = {
        "key": key,
        "isim": display_name,
        "yas": age,
        "seed": int.from_bytes(digest[:4], "big"),
        "meslek": job,
        "kisilik": personality,
        "gecmis": f"{anchor_name} karakterinin sosyal çevresinden {relation}. {job} olarak çalışıyor. {life.capitalize()}.",
        "gunluk_hayat": life,
        "konusma_tarzi": speech,
        "appearance_prompt": f"a {age}-year-old Turkish adult woman with {appearance}; same face and age in every photo",
        "default_clothing": clothing,
        "default_scene": scene,
        "prompt": (
            f"Senin adın {display_name}. {age} yaşında yetişkin bir Türk kadınsın. "
            f"{anchor_name} karakterinin sosyal çevresinden {relation}; mesleği {job}. "
            f"Gündelik hayatı: {life}. {personality}; "
            f"{speech}. Kendi hayatın, sorumlulukların ve planların var. "
            "Daha önce yaşanmamış bir olayı veya tanışıklığı olmuş gibi anlatma."
        ),
        "iliski": [],
        "memory": [],
        "created_at": int(time.time()),
    }
    world["characters"][key] = profile
    edge = {"source": anchor_key, "target": key, "type": relation}
    if edge not in world["relationships"]:
        world["relationships"].append(edge)
    return profile, True


def _extract_name_mentions(text: str) -> list[tuple[str, str]]:
    found = []
    for match in _RELATION_RE.finditer(text or ""):
        found.append((match.group("name"), match.group("relation")))
    for match in _REVERSE_RELATION_RE.finditer(text or ""):
        found.append((match.group("name"), match.group("relation")))
    for match in _INVITED_NAME_RE.finditer(text or ""):
        found.append((match.group("name"), "tanıdık"))
    for match in _SPEAKER_RE.finditer(text or ""):
        found.append((match.group("name"), "sohbete katılan kişi"))
    photo_match = _PHOTO_NAME_RE.search(text or "")
    if photo_match and _normalize_text(photo_match.group("name")) not in {
        _normalize_text(word) for word in _COMMON_CAPITAL_WORDS
    }:
        found.append((photo_match.group("name"), "fotoğrafı istenen tanıdık"))
    if _JOINT_PHOTO_RE.search(_normalize_text(text)):
        found.extend((match.group(0), "ortak fotoğraftaki tanıdık") for match in _CAPITALIZED_TOKEN_RE.finditer(text or ""))
    if _INVITE_RE.search(_normalize_text(text)):
        found.extend((match.group(0), "davet edilen tanıdık") for match in _CAPITALIZED_TOKEN_RE.finditer(text or ""))
    unique = {}
    for name, relation in found:
        norm = _normalize_text(name)
        if norm not in unique:
            unique[norm] = (name, relation)
    return list(unique.values())


def discover_from_text(
    world: dict, text: str, anchor_key: str, anchor_name: str, main_characters: dict | None = None,
) -> list[str]:
    """Remember only named people introduced with a social relation/invitation/speaker line."""
    world = normalize_world(world)
    keys = []
    for name, relation in _extract_name_mentions(text):
        if main_characters and any(
            _normalize_text(character.get("isim")) == _normalize_text(name)
            for character in main_characters.values()
        ):
            continue
        profile, created = create_character(world, name, relation, anchor_key, anchor_name)
        key = profile.get("key") if profile else None
        if key:
            keys.append(key)
    return list(dict.fromkeys(keys))


def mentioned_character_keys(text: str, world: dict, main_characters: dict) -> list[str]:
    normalized = _normalize_text(text)
    found = []
    for key, character in main_characters.items():
        name = _normalize_text(character.get("isim"))
        names = {name, name.split()[0] if name else ""}
        suffix = r"(?:['’]?(?:yi|yı|yu|yü|ye|ya|yle|yla|le|la|nin|nın|nun|nün|in|ın|un|ün|e|a|i|ı|u|ü))?"
        if any(candidate and re.search(rf"(?<!\w){re.escape(candidate)}{suffix}(?!\w)", normalized) for candidate in names):
            found.append(key)
    for key, character in normalize_world(world)["characters"].items():
        name = _normalize_text(character.get("isim"))
        names = {name, name.split()[0] if name else ""}
        suffix = r"(?:['’]?(?:yi|yı|yu|yü|ye|ya|yle|yla|le|la|nin|nın|nun|nün|in|ın|un|ün|e|a|i|ı|u|ü))?"
        if any(candidate and re.search(rf"(?<!\w){re.escape(candidate)}{suffix}(?!\w)", normalized) for candidate in names):
            found.append(key)
    return list(dict.fromkeys(found))


def speaker_character_keys(text: str, world: dict) -> list[str]:
    speakers = []
    for match in _SPEAKER_RE.finditer(text or ""):
        key = find_character_key(match.group("name"), world)
        if key:
            speakers.append(key)
    return list(dict.fromkeys(speakers))


def invitation_requested(text: str) -> bool:
    return bool(_INVITE_RE.search(_normalize_text(text)))


def departure_requested(text: str) -> bool:
    return bool(_LEAVE_RE.search(_normalize_text(text)))


def clear_scene_requested(text: str) -> bool:
    return bool(_CLEAR_SCENE_RE.search(_normalize_text(text)))


def arrival_stated(text: str) -> bool:
    return bool(_ARRIVAL_RE.search(_normalize_text(text)))


def update_scene_cast(state: dict, text: str, world: dict, main_characters: dict, anchor_key: str) -> tuple[list[str], list[str]]:
    """Update only current scene membership; return (joined, departed)."""
    discover_from_text(
        world, text, anchor_key,
        main_characters.get(anchor_key, {}).get("isim", anchor_key), main_characters,
    )
    current = state.setdefault("sahne_katilimcilari", [])
    if not isinstance(current, list):
        current = state["sahne_katilimcilari"] = []
    current[:] = [key for key in dict.fromkeys(current) if key in world.get("characters", {})]
    mentioned = mentioned_character_keys(text, world, main_characters)
    side_mentions = [key for key in mentioned if key in world.get("characters", {})]
    if departure_requested(text):
        remove = side_mentions or (list(current) if clear_scene_requested(text) else [])
        departed = [key for key in remove if key in current]
        current[:] = [key for key in current if key not in departed]
        return [], departed
    if not invitation_requested(text):
        if side_mentions and arrival_stated(text):
            joined = [key for key in side_mentions if key not in current]
            current.extend(joined)
            return joined, []
        return [], []
    joined = []
    if side_mentions:
        for key in side_mentions:
            if key not in current:
                current.append(key)
                joined.append(key)
    else:
        recent = state.get("son_yan_karakterler", [])
        for key in reversed(recent):
            if key in world.get("characters", {}) and key not in current:
                current.append(key)
                joined.append(key)
                break
        if joined:
            return joined, []
        if current:
            return [], []
        candidates = discover_from_text(
            world, text, anchor_key,
            main_characters.get(anchor_key, {}).get("isim", anchor_key), main_characters,
        )
        for key in candidates:
            if key not in current:
                current.append(key)
                joined.append(key)
    return joined, []


def append_scene_memories(state: dict, participant_keys: list[str], user_text: str, assistant_text: str):
    memories = state.setdefault("yan_karakter_hafizasi", {})
    for key in participant_keys:
        history = memories.setdefault(key, [])
        history.extend((
            {"role": "user", "content": str(user_text)[:2000]},
            {"role": "assistant", "content": str(assistant_text)[:3000]},
        ))
        del history[:-MEMORY_LIMIT_PER_CHARACTER]


def append_world_event(state: dict, people: list[str], text: str, kind: str = "scene"):
    events = state.setdefault("sosyal_olaylar", [])
    events.append({"at": int(time.time()), "people": list(dict.fromkeys(people)), "kind": kind, "text": str(text)[:1000]})
    del events[:-EVENT_LIMIT_PER_USER]


def social_scene_context(state: dict, world: dict, anchor_key: str, anchor_name: str) -> str:
    keys = [key for key in state.get("sahne_katilimcilari", []) if key in world.get("characters", {})]
    related = [
        edge.get("target") if edge.get("source") == anchor_key else edge.get("source")
        for edge in world.get("relationships", [])
        if anchor_key in (edge.get("source"), edge.get("target"))
    ]
    if not keys:
        recent = [key for key in reversed(state.get("son_yan_karakterler", [])) if key in world.get("characters", {})]
        known = list(dict.fromkeys(recent + related))[:4]
        guide = (
            "[SOSYAL ÇEVRE] Yan karakterler kendi hayatı ve ilişkileri olan kişiler; onları yalnızca olay doğal olarak gerektirdiğinde gündeme getir. "
            "Rastgele yeni kişi üretme, her yanıta yan karakter ekleme. Sahnede olmayan kişiyi konuşturma. Kullanıcı birini davet ederse sahneye katılmasını sağla."
        )
        if not known:
            return guide + " Henüz tanıtılmış bir yan karakter yok; birini ancak hikâyede anlamlı biçimde ilk kez karşılaştığınızda oluştur."
        return guide + "\nBu ana karakterin daha önce tanıştığı kişiler: " + "; ".join(
            f"{world['characters'][key]['isim']}: {world['characters'][key].get('gecmis', '')}"
            for key in known
        )
    sections = [
        "[CANLI SOSYAL SAHNE] Ana karakter sahnede: " + anchor_name + ".",
        "Aşağıdaki yan karakterler şu anda fiziksel olarak sahnede; hepsi kendi sesi ve hafızası olan ayrı kişilerdir.",
        "Sırayla veya doğal biçimde konuşabilir, birbirlerinin sözlerine cevap verebilirler. "
        "Yan karakterleri tek bir anlatıcıda birleştirme; kısa konuşma satırlarında ‘İsim: söz’ biçimini kullan. "
        "Sahnede bulunmayan kişiyi konuşturma. Bir kişi ayrılırsa ayrılışını doğal biçimde belirt ve sonraki turda onu sahnede tutma. "
        "Yeni kişi yaratmayı yalnızca olay gerçekten gerektiriyorsa yap; rastgele isim ekleme.",
    ]
    memories = state.get("yan_karakter_hafizasi", {})
    for key in keys:
        character = world["characters"][key]
        relation_text = "; ".join(
            f"{edge.get('source')} — {edge.get('type')} — {edge.get('target')}"
            for edge in world.get("relationships", [])
            if edge.get("source") == key or edge.get("target") == key
        )
        sections.append(
            f"\n[{character['isim']} — sahnede ve konuşabilir]\n{character['prompt']}\n"
            f"Fiziksel görünüşü: {character.get('appearance_prompt', 'doğal ve tutarlı bir yetişkin kadın görünümü')}.\n"
            f"İlişkiler: {relation_text or 'Henüz belirlenmedi.'}"
        )
        history = memories.get(key, [])[-8:]
        if history:
            sections.append(
                f"{character['isim']} için bu kullanıcıyla önceki ortak konuşmalar: "
                + " | ".join(f"{item.get('role')}: {item.get('content', '')}" for item in history)
            )
    events = state.get("sosyal_olaylar", [])[-8:]
    if events:
        sections.append("Bu kullanıcının son sosyal olayları: " + " | ".join(event.get("text", "") for event in events))
    return "\n".join(sections)


def photo_targets(text: str, world: dict, main_characters: dict, default_key: str) -> list[str]:
    mentioned = mentioned_character_keys(text, world, main_characters)
    return mentioned or [default_key]


