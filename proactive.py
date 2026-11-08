"""Laila'nın kendiliğinden mesaj gönderme sistemi.

Telegram botunun ana akışı main.py'de kalır. Bu modül, proaktif kontrol
zamanlamasını ve mesaj üretim/gönderim döngüsünü bağımlılıkları dışarıdan
alacak şekilde yönetir; böylece main.py ile döngüsel import oluşmaz.
"""
import asyncio
import logging
import random
import time
from datetime import datetime


async def proaktif_kontrol(app, b):
    """Uygun kullanıcıları kontrol eder ve koşullar sağlanırsa mesaj gönderir.

    b, main.py tarafından sağlanan fonksiyon ve ayarları içeren sözlüktür.
    """
    simdi = datetime.now(b["TZ"])
    (bas_s, bas_d), (bit_s, bit_d) = b["PROAKTIF_SAAT_ARALIGI"]
    dakika = simdi.hour * 60 + simdi.minute
    if not (bas_s * 60 + bas_d <= dakika < bit_s * 60 + bit_d):
        return

    bugun = simdi.strftime("%Y-%m-%d")
    for user_id, d in list(b["kullanici_durumu"].items()):
        if not d.get("chat_id"):
            continue
        if d.get("cevapsiz", 0) >= 2:  # İki kez cevapsız kaldıysa kullanıcı yazana kadar bekler.
            continue
        if d.get("proaktif_gun") != bugun:
            d["proaktif_gun"] = bugun
            d["proaktif_sayi"] = 0
        if d.get("proaktif_sayi", 0) >= b["PROAKTIF_GUNLUK_LIMIT"]:
            continue

        sessizlik = time.time() - d.get("son_etkilesim", time.time())
        if sessizlik < d.get("proaktif_esik", float("inf")):
            continue

        karakter_key = d["karakter"]
        karakter = b["KARAKTERLER"][karakter_key]
        chat_id = d["chat_id"]
        saat = max(1, int(sessizlik // 3600))
        sev = b["yakinlik_seviyesi"](b["yakinlik_puani"](d, karakter_key))
        foto_atsin = (
            random.random() < b["PROAKTIF_FOTO_ORANLARI"][sev]
            and time.time() - d.get("son_proaktif_foto", 0) > b["PROAKTIF_FOTO_ARALIK"]
        )

        ekstra = (
            f"Kullanıcı yaklaşık {saat} saattir sana yazmadı. Onun yazmasını BEKLEMEDEN ilk mesajı sen at. "
            "Çok kısa ve doğal ol: biraz özlemiş olabilirsin, ne yaptığını merak edebilirsin ya da şu anki durumundan bir kesit paylaşabilirsin "
            "(örneğin 'nerdesin ya', 'az önce şunu gördüm'). Kendini tanıtma, selam verip nutuk atma; en fazla 1-2 kısa mesaj yaz. KESİN KURAL: Hareketler *yıldız* içinde. Türkçe cevap ver, İngilizce düşünce yazma. İnsan karakterleri için: kuyruk sallama, havlama gibi hayvan davranışı yasak."
        )
        if d.get("stil", "hikaye") == "hikaye":
            ekstra = (
                f"Kullanıcı yaklaşık {saat} saattir hikâyeye dönmedi. Hikâyeyi sen canlandır: mevcut sahnede küçük bir gelişme anlat (*hareket*) "
                "ve kullanıcıya sözle seslen. Kısa ol (2-3 cümle), kendini tanıtma."
            )
        if foto_atsin:
            ekstra += " Mesajının yanında bir fotoğraf da göndereceksin, bunu kısaca ima edebilirsin."

        try:
            dusunce, cevap = await b["llm_cevap"](
                karakter_key,
                b["hafiza_al"](d),
                "(Bir süredir sessizlik var. İlk mesajı sen at.)",
                ekstra_sistem=ekstra,
                puan=b["yakinlik_puani"](d, karakter_key),
                stil=d.get("stil", "hikaye"),
                sahne=d.get("sahneler", {}).get(karakter_key),
                duygu_notu=b["duygu_ozeti"](d, karakter_key),
                dunya_notu=b["dunya_ozeti"](d, karakter_key),
            )
            await b["cevabi_ilet"](app.bot, chat_id, dusunce, cevap)
            if foto_atsin:
                try:
                    await b["foto_gonder"](app.bot, chat_id, karakter, yakinlik=sev)
                    d["son_proaktif_foto"] = time.time()
                except Exception as img_error:
                    logging.error(f"Proaktif görsel hatası: {img_error}")

            d_hafiza = b["hafiza_al"](d)
            d_hafiza.append({"role": "assistant", "content": b["hafiza_kaydi"](dusunce, cevap)})
            b["hafizayi_kirp"](d_hafiza)
            d["cevapsiz"] = d.get("cevapsiz", 0) + 1
            d["proaktif_sayi"] = d.get("proaktif_sayi", 0) + 1
            d["son_etkilesim"] = time.time()
            b["esik_belirle"](d)
            await b["durum_kaydet"](user_id)
            logging.info(f"{karakter['isim']} kendiliğinden mesaj attı.")
        except Exception as e:
            logging.error(f"Proaktif mesaj hatası: {e}")
            # 15 dakika sonra tekrar dene.
            d["son_etkilesim"] = time.time() - d.get("proaktif_esik", 0) + 900


async def proaktif_dongu(app, baglam):
    """Bot çalıştığı sürece beş dakikada bir proaktif kontrol yapar."""
    await asyncio.sleep(60)
    while True:
        try:
            await proaktif_kontrol(app, baglam)
        except Exception as e:
            logging.error(f"Proaktif döngü hatası: {e}")
        await asyncio.sleep(300)
