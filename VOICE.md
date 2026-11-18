# Ücretsiz sesli mesajlar

Bot, isteğe bağlı sesli mesajlar için `edge-tts` paketini kullanır. Edge-TTS, anahtar veya kart bilgisi gerektirmez; Microsoft Edge'in çevrimiçi Türkçe konuşma seslerini kullanır. Yerel ses modeli indirilmez. Ses dosyası geçici MP3 olarak oluşturulur, Telegram'a gönderilir ve işlem sonunda silinir.

## Telegram komutları

- `/ses <metin>`: seçili karakterin sesiyle tek seferlik sesli mesaj gönderir.
- `/ses aç`: normal ve kendiliğinden yanıtlara ses ekler.
- `/ses kapat`: otomatik ses eklemeyi kapatır (varsayılan).

Otomatik tercih kullanıcı durumuyla birlikte saklanır. Karakterler arasında aynı Türkçe neural ses kullanılır; konuşma hızı ve perde karaktere göre ayarlanır. Bir istekte en fazla 1.200 karakter seslendirilir; aynı sohbete gönderimler arasında 30 saniye beklenir ve eşzamanlı ses üretimi iki işlemle sınırlıdır. Ağ veya servis hatasında mevcut yazılı yanıt gönderilmiş kalır.

Edge-TTS Microsoft Edge çevrimiçi konuşma servisine bağlanır; ücretsiz olsa da servis kullanılabilirliği ve kullanım koşulları Microsoft'a bağlıdır.
