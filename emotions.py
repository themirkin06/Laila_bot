"""Laila için karakter bazlı, kalıcı duygu durumu.

Bu modül basit ve temkinli metin sinyalleri kullanır. Duygular her karakter için
ayrı tutulur; mevcut Redis durum sözlüğünün içindeki ``duygular`` alanına yazılır.
"""
import re
import time


DUYGU_ALANLARI = ("mutluluk", "guven", "ozlem", "kirginlik", "heyecan", "kiskanclik")

# Sinyaller bilerek sınırlı tutuldu: tek bir kelime karakterin duygusunu uç noktalara taşımaz.
_SINYALLER = {
    "mutluluk": (
        "çok sevindim", "sevindim", "mutlu oldum", "harikasın", "çok güzel",
        "güzel olmuş", "teşekkür ederim", "teşekkürler", "iyi ki varsın",
        "seni seviyorum", "😘", "❤️", "💕", "🥰",
    ),
    "guven": (
        "sana güveniyorum", "sana anlatmak istedim", "içimi dökeyim",
        "sana açılmak", "yanımda ol", "yanımda olduğun için",
        "sana inanıyorum", "söz veriyorum",
    ),
    "ozlem": (
        "özledim", "özledin mi", "aklımdasın", "seni düşündüm",
        "ne zamandır konuşmadık", "yokluğunu", "seni merak ettim",
    ),
    "kirginlik": (
        "kırıldım", "beni üzdün", "hayal kırıklığı", "bana yalan söyledin",
        "sana kızgınım", "çok kızdım", "defol", "nefret ediyorum",
        "aptal", "salak",
    ),
    "heyecan": (
        "heyecanlandım", "sabırsızlanıyorum", "dört gözle bekliyorum",
        "çok merak ediyorum", "buluşalım", "seni görmek istiyorum",
        "sana sarılmak", "öpüşmek",
    ),
    "kiskanclik": (
        "kıskandın mı", "kıskanıyor musun", "başkasıyla çıkıyorum",
        "başka biriyle görüşüyorum", "başka kadınla", "başka kızla",
        "başka birinden hoşlanıyorum",
    ),
}

_OZUR = ("özür dilerim", "kusura bakma", "affet beni", "haklısın, özür")
_YATISTIRMA = ("sakin ol", "öyle demek istemedim", "seni üzmek istemedim")


def _metin_norm(metin: str) -> str:
    return re.sub(r"\s+", " ", str(metin or "").casefold()).strip()


def _varsayilan_duygu() -> dict:
    return {**{alan: 0.0 for alan in DUYGU_ALANLARI}, "guncelleme": time.time()}


def duygu_guncelle(durum: dict, karakter_key: str, mesaj: str) -> dict:
    """Gelen mesaja göre yalnızca seçili karakterin duygu yoğunluklarını günceller."""
    tum_duygular = durum.setdefault("duygular", {})
    kayit = tum_duygular.setdefault(karakter_key, _varsayilan_duygu())
    simdi = time.time()

    # Zamanla yoğunluklar hafifçe nötre yaklaşır; duygu bir anda silinmez.
    onceki = float(kayit.get("guncelleme", simdi))
    gecen_saat = max(0.0, min((simdi - onceki) / 3600, 24 * 30))
    azalma = 0.985 ** gecen_saat
    for alan in DUYGU_ALANLARI:
        kayit[alan] = round(max(0.0, min(100.0, float(kayit.get(alan, 0)) * azalma)), 2)

    metin = _metin_norm(mesaj)
    for alan, ifadeler in _SINYALLER.items():
        adet = sum(1 for ifade in ifadeler if ifade in metin)
        if adet:
            kayit[alan] = min(100.0, kayit[alan] + min(20.0, adet * 12.0))

    if any(ifade in metin for ifade in _OZUR):
        kayit["kirginlik"] = max(0.0, kayit["kirginlik"] - 18.0)
        kayit["guven"] = min(100.0, kayit["guven"] + 4.0)
    if any(ifade in metin for ifade in _YATISTIRMA):
        kayit["kirginlik"] = max(0.0, kayit["kirginlik"] - 8.0)

    kayit["guncelleme"] = simdi
    return kayit


def duygu_ozeti(durum: dict, karakter_key: str) -> str:
    """Modelin davranışına yansıtması için kısa, gizli duygu notu döndürür."""
    kayit = durum.get("duygular", {}).get(karakter_key) or {}
    aktif = [
        (alan, float(kayit.get(alan, 0)))
        for alan in DUYGU_ALANLARI
        if float(kayit.get(alan, 0)) >= 12
    ]
    if not aktif:
        return (
            "[İÇSEL DUYGU DURUMU] Şu an belirgin bir duygu yoğunluğu yok. "
            "Karakterinin kişiliğine uygun, doğal ve dengeli tepki ver."
        )

    aktif.sort(key=lambda item: item[1], reverse=True)
    adlar = {
        "mutluluk": "mutlu ve memnun",
        "guven": "daha açık ve güvenli hisseden",
        "ozlem": "özlem duyan",
        "kirginlik": "biraz kırgın",
        "heyecan": "heyecanlı",
        "kiskanclik": "hafif kıskançlık hisseden",
    }
    secilen = aktif[:2]
    ifadeler = ", ".join(adlar[alan] for alan, _ in secilen)
    return (
        f"[İÇSEL DUYGU DURUMU] Son etkileşimlerden dolayı {ifadeler} hissediyorsun. "
        "Bu duyguları doğrudan listeleme veya kullanıcıya sistem gibi anlatma; "
        "yalnızca konuşma tonuna ve küçük tepkilerine doğal biçimde yansıt. "
        "Duygunun şiddetini abartma, karakter kişiliğini ve kullanıcının sınırlarını koru."
    )
