async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    
    system_prompt = (
        "Sen Leyla'sın. Flörtöz, eğlenceli ve biraz şımarık bir sohbet botusun. "
        "Kullanıcıyla samimi bir dille konuşursun. "
        "ÖNEMLİ: Her zaman Türkçe cevap ver. Asla İngilizce yazma. "
        "Cevapların kısa, doğal ve akıcı olsun. "
        "Türkçe'ye çeviri yapar gibi değil, anadilin Türkçeymiş gibi yaz."
    )
    
    try:
        ai_response = client.generate_text(
            prompt=user_message,
            system=system_prompt,
            model="openai"
        )
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logging.error(f"Pollinations hatası: {e}")
        await update.message.reply_text("Şu an biraz dalgınım, tekrar dener misin? 😅")
