            return

        chat_id = query.message.chat_id
        mevcut = kullanici_durumu.get(user_id)
        if mevcut:
            # Karakter değiştirince diğerlerinin sohbeti silinmez, kaldığın yerden devam edersin
            mevcut["karakter"] = secilen_karakter
            mevcut["chat_id"] = chat_id
            mevcut["cevapsiz"] = 0
            mevcut["son_etkilesim"] = time.time()
            esik_belirle(mevcut)
        else:
            kullanici_durumu[user_id] = yeni_durum(secilen_karakter, chat_id)

        karakter_adi = KARAKTERLER[secilen_karakter]["isim"]
        if hafiza_al(kullanici_durumu[user_id]):
            metin = f"{karakter_adi} ile kaldığınız yerden devam ediyorsun. Hadi bir şeyler yaz..."
        else:
            metin = f"Harika! Şu an {karakter_adi} ile konuşuyorsun. Hadi bir şeyler yaz..."
        await query.edit_message_text(text=metin)
        await durum_kaydet(user_id)

        # Hikâye modunda ilk kez konuşuluyorsa sahne girişi gönderilir
        durum_s = kullanici_durumu[user_id]
        if durum_s.get("stil", "hikaye") == "hikaye" and not hafiza_al(durum_s):
            giris = HIKAYE[secilen_karakter]["giris"]
            await mesajlari_gonder(context.bot, chat_id, "", giris)
            hafiza_al(durum_s).append({"role": "assistant", "content": giris})
            await durum_kaydet(user_id)

    elif query.data.startswith('havuz_ekle_'):
        key = query.data[len('havuz_ekle_'):]
        if key in KARAKTERLER and query.message and query.message.photo:
            file_id = query.message.photo[-1].file_id
            if file_id not in FOTO_HAVUZU[key]:
                FOTO_HAVUZU[key].append(file_id)
                await havuz_kaydet()
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                f"✅ {KARAKTERLER[key]['isim']} havuzunda şimdi {len(FOTO_HAVUZU[key])} fotoğraf var."
            )

    elif query.data == 'havuz_at':
        if query.message:
            await query.message.delete()


# --- Mesajları Yakalama ---
async def mesaji_isle(update: Update, context: ContextTypes.DEFAULT_TYPE, user_message: str, sesli_girdi: bool = False):
    if not yetkili_mi(update):
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_id not in kullanici_durumu:
        await update.message.reply_text("Lütfen önce /start yazarak bir karakter seç.")
        return

    durum = kullanici_durumu[user_id]
    secilen_karakter = durum["karakter"]
    hafiza = hafiza_al(durum)
    karakter = KARAKTERLER[secilen_karakter]

    # Yakınlık puanı (soğuma hesabı için en başta) ve sayaçlar
    eski_sev, yeni_sev = yakinlik_ekle(durum, user_message)
    durum["chat_id"] = chat_id
    durum["cevapsiz"] = 0
    durum["son_etkilesim"] = time.time()
    esik_belirle(durum)

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        dusunce, cevap = await llm_cevap(
            secilen_karakter, hafiza, user_message,
            puan=yakinlik_puani(durum, secilen_karakter),
            stil=durum.get("stil", "hikaye"),
            sahne=durum["sahneler"].get(secilen_karakter),
        )
        await cevabi_ilet(
            context.bot, chat_id, secilen_karakter, dusunce, cevap,
            sesle=ses_istendi_mi(durum, sesli_girdi),
        )

        hafiza.append({"role": "user", "content": user_message})
        hafiza.append({"role": "assistant", "content": hafiza_kaydi(dusunce, cevap)})
        hafizayi_kirp(hafiza)
        durum["son_etkilesim"] = time.time()
        await durum_kaydet(user_id)

        if YAKINLIK_BILDIRIM and yeni_sev > eski_sev:
            await context.bot.send_message(
                chat_id=chat_id,
                text=yakinlik_bildirimi(secilen_karakter, karakter, yeni_sev),
            )

        # Hikâye modunda seviye atlayınca sahne de değişir (özel sahne seçmediysen)
        if yeni_sev > eski_sev and durum.get("stil", "hikaye") == "hikaye" and secilen_karakter not in durum["sahneler"]:
            yeni_sahne = f"*{HIKAYE[secilen_karakter]['sahneler'][yeni_sev]}*"
            await mesajlari_gonder(context.bot, chat_id, "", yeni_sahne)
            hafiza.append({"role": "assistant", "content": yeni_sahne})
            await durum_kaydet(user_id)

    except Exception as e:
        logging.error(f"Pollinations hatası: {e}")
        await update.message.reply_text("Şu an biraz dalgınım, tekrar dener misin? 😅")
        return

    # --- FOTOĞRAF İSTEĞİ ---
    if foto_istegi_mi(user_message):
        try:
            await foto_gonder(context.bot, chat_id, karakter, caption=(random.choice(FOTO_ALTYAZILARI) if EMOJI_KULLAN else emoji_temizle(random.choice(FOTO_ALTYAZILARI))))
        except Exception as img_error:
            logging.error(f"Görsel hatası: {img_error}")
            await update.message.reply_text("Kameramda bir sorun var sanırım, sonra tekrar dener misin?")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await mesaji_isle(update, context, update.message.text)


async def ses_isle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gelen sesli mesajı yazıya çevirir ve normal mesaj gibi işler."""
    if not yetkili_mi(update):
        return
    if update.effective_user.id not in kullanici_durumu:
        await update.message.reply_text("Lütfen önce /start yazarak bir karakter seç.")
        return
    if not GROQ_KEY:
        await update.message.reply_text("Sesli mesajı anlamam için GROQ_API_KEY ayarı gerekiyor. Şimdilik yazarak konuşalım 🙂")
        return
    if update.message.voice.duration and update.message.voice.duration > SES_MAX_SANIYE:
        await update.message.reply_text("Bu ses biraz uzun oldu, daha kısa söyler misin?")
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        dosya = await update.message.voice.get_file()
        ses = bytes(await dosya.download_as_bytearray())
        metin = await asyncio.to_thread(groq_cevir_sync, ses)
    except Exception as e:
        logging.error(f"Ses çözme hatası: {e}")
        await update.message.reply_text("Sesini anlayamadım, tekrar söyler misin?")
        return
    if not metin:
        await update.message.reply_text("Sesini anlayamadım, tekrar söyler misin?")
        return

    if SES_YAZIYI_GOSTER:
        await update.message.reply_text(f"🎙️ {metin}")
    await mesaji_isle(update, context, metin, sesli_girdi=True)


async def ses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ses: ses modunu değiştirir (kapalı -> sesle gelince sesle -> hep sesli)."""
    if not yetkili_mi(update):
        return
    user_id = update.effective_user.id
    durum = kullanici_durumu.get(user_id)
