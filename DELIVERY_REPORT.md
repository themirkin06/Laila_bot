# Laila bot - degisiklik raporu

Tarih: 17 Kasim 2026

## Uygulananlar

1. **Konum ve sahne hafizasi:** Her kullanici ve ana karakter icin son acikca belirtilen hedef, sahnedeki yan karakterler ve son gecis kaydi Redis'te kullanici durumuyla saklanir. Belirsiz veya taninmayan bir hedef mevcut konumu degistirmez. Model talimatlari da konum uydurmamasini ve gecisleri kisa anlatmasini ister.
2. **Ses:** Ucretsiz Edge-TTS akisi karakterin temel hiz/perde profiline ek olarak metindeki basit duygu ipuclarina gore kucuk hiz/perde degisiklikleri uygular. Sinir: karakterlerin hepsi ayni `tr-TR-EmelNeural` sesini kullanir; bu ayarlar ayri ses timbri, kelime bazinda vurgu veya oyunculuk saglamaz. Edge-TTS'in gercekci duygusal performans garantisi yoktur.
3. **Yetiskin sohbet dili:** Kurgusal yetiskin karakterler karsilikli istek ve baglama gore daha acik sozlu, argo veya kufurlu konusabilir. Kisilik korunur; her sohbet cinsellestirilmez ve isteksizlikte geri cekilir.
4. **Konusma tarzi:** Kisa ve yerinde hareket anlatimi, daha dolu dogal diyalog, gereksiz roman betimlemelerinden kacınma ve sabit kelime siniri olmamasi yonergeleri eklendi.
5. **Dinamik sosyal dunya:** Sabit liste yerine hikayede adi ve iliskisi tanitilan NPC'ler olusur. Kimlikleri ve iliskileri ayri Redis anahtarinda; kullaniciya ozel ortak konusma hafizalari ve canli sahne katilimcilari kullanici Redis kaydinda saklanir. `/davet`, `/yalniz` ve `/yanlar` komutlariyla katilim yonetilir. Ortak foto icin var olan img2img akisi kullanilir; ilk kullanimda kisilerin yuz referansi gerekir.

## Korunan ayarlar ve kapsam

- Metin saglayicisi AI Horde olarak sabitlendi.
- Secili model: `koboldcpp/G4-MeroMero-26B-A4B-it-uncensored-heretic`.
- Pollinations etkin degil; saglayici yedegi eklenmedi.
- Yeni ucretli API, servis, secret veya maliyet eklenmedi.
- Gorsel anlama koduna dokunulmadi.
- GitHub'a push ve Render deploy yapilmadi.

## Dogrulama

- `python -m unittest discover -s tests -v`: 30 test basarili.
- Degistirilen Python modulleri `compileall` ile derlendi.
- Testler Redis veya canli Edge-TTS servisine baglanmadi; sahne kaliciligi JSON/Redis veri yapisi seviyesinde birim testleriyle kontrol edildi.

