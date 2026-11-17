# Ücretsiz sesli mesajlar

Bot, isteğe bağlı sesli mesajlar için `edge-tts` paketini kullanır. Edge-TTS, anahtar veya kart bilgisi gerektirmez; Microsoft Edge'in çevrimiçi Türkçe konuşma seslerini kullanır. Yerel ses modeli indirilmez. Ses dosyası geçici MP3 olarak oluşturulur, Telegram'a gönderilir ve işlem sonunda silinir.

## Telegram komutları

- `/ses <metin>`: seçili karakterin sesiyle tek seferlik sesli mesaj gönderir.
- `/ses aç`: normal ve kendiliğinden yanıtlara ses ekler.
- `/ses kapat`: otomatik ses eklemeyi kapatır (varsayılan).

Otomatik tercih kullanıcı durumuyla birlikte saklanır. Karakterlere aynı Türkçe neural ses atanır; hız ve perde karaktere göre, ayrıca metindeki belirgin duygu ipuçlarına göre hafifçe değişir. Noktalama doğal duraklamalara yardımcı olur. Bir istekte en fazla 1.200 karakter seslendirilir; aynı sohbete gönderimler arasında 30 saniye beklenir ve eşzamanlı ses üretimi iki işlemle sınırlıdır. Ağ veya servis hatasında mevcut yazılı yanıt gönderilmiş kalır.

Edge-TTS Microsoft Edge çevrimiçi konuşma servisine bağlanır; ücretsiz olsa da servis kullanılabilirliği ve kullanım koşulları Microsoft'a bağlıdır. Aynı ses kullanıldığı için perde ve hız ayarı karakterlere gerçek anlamda farklı ses tınısı kazandırmaz. Edge-TTS bu Türkçe ses için oyunculuk, kelime bazında vurgu veya ince duygu kontrolü sunmaz; metinden duygu seçimi basit ipuçlarına dayanır ve gerçekçi performans garantisi vermez. Daha doğal tını için ayrı ve ücretsiz yerel bir TTS modeli gerekir; bu teslimata böyle bir model veya yeni servis eklenmedi.

