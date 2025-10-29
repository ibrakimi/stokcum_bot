import logging  # <-- BU SATIRI EKLEYİN
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os # Yeni: Ortam değişkenlerini okumak için
# ... diğer import'lar

# ----------------------------------------------------------------------
# 1. YAPILANDIRMA VE SABİT DEĞERLER (Artık Ortam Değişkenlerinden Okunacak!)
# ----------------------------------------------------------------------

# TOKEN'ı ortam değişkeninden al.
# Eğer sunucuda tanımlanmamışsa varsayılan olarak None döner.
TOKEN = os.environ.get("TELEGRAM_TOKEN") 
if not TOKEN:
    print("HATA: TELEGRAM_TOKEN ortam değişkeni tanımlı değil!")
    # Bu kısmı sadece yerel test için kullanabilirsiniz, sunucuda kaldırılmalı
    # TOKEN = "7241140480:AAFkzFSgwDw6amZHWkRorcfbxD4HuISyhVc" 

# İzinli kullanıcı ID'lerini al. (Birden fazla ID virgülle ayrılmış olmalı)
IZINLI_KULLANICILAR_STR = os.environ.get("IZINLI_KULLANICILAR", "948469975")
try:
    # Virgülle ayrılmış ID'leri ayırıp sayı listesine dönüştür.
    IZINLI_KULLANICILAR = [int(id.strip()) for id in IZINLI_KULLANICILAR_STR.split(',')]
except ValueError:
    print("HATA: IZINLI_KULLANICILAR ortam değişkeni geçersiz formatta.")
    IZINLI_KULLANICILAR = [948469975,5115653688] # Hata durumunda yetkiyi kes

STOK_DOSYASI = "stok_kayit_kategorili.json" 
VARSAYILAN_ADET = 5

# KATEGORİ VE ÜRÜN KODU/İSİM TANIMLARI (Yeni Hiyerarşik Yapı)
URUN_KATALOGU = {
    "PROTEUS PREMIX": {
        "8006901000": "Emniyet Ventili",
        "8006901001": "Basınç Sensörü",
        "8006901002": "Akış Ölçer",
        "8006901003": "Termostatik Valf",
    },
    "CALORA PREMIX": {
        "8006901004": "Solenoid Bobin",
        "8006901005": "Türbin",  # Türbin eklendi
        "8006901006": "Debi Ayar Vanası",
    },
    "CITIUS PREMIX": {
        "8006901007": "Hava Filtresi",
        "8006901008": "Hız Kontrol Ünitesi",
        "8006901009": "Limit Anahtarı",
        "8006901010": "Röle Kartı",
    },
}

# Loglama ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Başlangıçta kullanılacak stok listesini oluşturma fonksiyonu
def _varsayilan_stok_olustur():
    """Tanımlı ürün kataloğuna göre varsayılan stok yapısını oluşturur."""
    stok = {}
    for kategori, urunler in URUN_KATALOGU.items():
        stok[kategori] = {}
        for kod, isim in urunler.items():
            stok[kategori][kod] = {'isim': isim, 'adet': VARSAYILAN_ADET}
    return stok

# ----------------------------------------------------------------------
# 2. VERİ YÖNETİMİ FONKSİYONLARI (Kalıcılık)
# ----------------------------------------------------------------------

def kaydet_stok(data):
    try:
        with open(STOK_DOSYASI, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4) 
    except Exception as e:
        logger.error(f"Stok kaydetme hatası: {e}")

def yukle_stok():
    try:
        with open(STOK_DOSYASI, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Stok dosyası bulunamadı. Varsayılan veri ile başlanıyor.")
        return {}
    except json.JSONDecodeError:
        logger.error("Stok dosyası bozuk. Varsayılan veri ile başlanıyor.")
        return {} 
    except Exception as e:
        logger.error(f"Stok yükleme hatası: {e}")
        return {}

# Bot çalışmaya başladığında veriyi yükle ve eksik/yeni ürünleri ekle
stok_veritabani = yukle_stok()

if not stok_veritabani:
    stok_veritabani = _varsayilan_stok_olustur()
    kaydet_stok(stok_veritabani)
else:
    # Dosya varsa, yeni eklenen ürünleri varsayılan adetle ekle ve isimleri güncelle
    guncellendi = False
    for kategori, urunler in URUN_KATALOGU.items():
        if kategori not in stok_veritabani:
            stok_veritabani[kategori] = {}
            guncellendi = True
        
        for kod, isim in urunler.items():
            if kod not in stok_veritabani[kategori]:
                stok_veritabani[kategori][kod] = {'isim': isim, 'adet': VARSAYILAN_ADET}
                guncellendi = True
            elif stok_veritabani[kategori][kod]['isim'] != isim:
                 stok_veritabani[kategori][kod]['isim'] = isim
                 guncellendi = True
    
    if guncellendi:
        kaydet_stok(stok_veritabani)
        logger.info("Stok veritabanı, yeni ürünler/isimlerle güncellendi.")


# ----------------------------------------------------------------------
# 3. YARDIMCI VE YETKİLENDİRME FONKSİYONLARI
# ----------------------------------------------------------------------

def yetki_kontrol(update: Update):
    user_id = update.effective_user.id
    return user_id in IZINLI_KULLANICILAR

def _urun_bul(urun_kod):
    """Tüm kategorilerde ürün kodunu arar ve kategori, ürün bilgisi döndürür."""
    for kategori, urunler in stok_veritabani.items():
        if urun_kod in urunler:
            return kategori, urunler[urun_kod]
    return None, None

# ----------------------------------------------------------------------
# 4. BOT KOMUT İŞLEYİCİLERİ
# ----------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start komutuna yanıt verir."""
    if yetki_kontrol(update):
        kategori_listesi = '\n• ' + '\n• '.join(URUN_KATALOGU.keys())
        await update.message.reply_text(
            '👋 Kategori Bazlı Stok Botu aktif. \n\n'
            '📋 **Kullanım Kılavuzu:**\n'
            '• Tüm listeyi gör: `/stok`\n'
            f'• Kategori Sorgulama (Örn: `PROTEUS PREMIX`):\n{kategori_listesi}\n'
            '• Stok artırmak için: `+8006901000`\n'
            '• Stok azaltmak için: `-8006901000`\n'
            '• Stok Sorgulama: `8006901000` (sadece kod)',
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("⛔ Bu botu kullanmaya yetkiniz yok.")

async def stok_goster(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/stok komutuna yanıt verir ve tüm stokları kategori bazlı listeler."""
    if not yetki_kontrol(update):
        return await update.message.reply_text("⛔ Yetkiniz yok.")

    mesaj = "📊 **Mevcut Tüm Stoklar** 📊\n\n"
    
    global stok_veritabani 
    
    if not stok_veritabani:
        mesaj += "Stok listesi şu an boş."
    else:
        for kategori, urunler in stok_veritabani.items():
            mesaj += f"**📦 Kategori: {kategori}**\n"
            
            # Kodları sayısal sıraya göre sıralar
            sirali_kodlar = sorted(urunler.keys(), key=lambda x: int(x))
            
            for urun_kod in sirali_kodlar:
                urun_bilgi = urunler[urun_kod]
                adet = urun_bilgi['adet']
                isim = urun_bilgi['isim']
                mesaj += f"  • `{urun_kod}`: **{isim}** (Adet: **{adet}**)\n"
            mesaj += "\n" # Kategori aralarını açmak için
    
    await update.message.reply_text(mesaj, parse_mode='Markdown')

# ----------------------------------------------------------------------
# 5. MESAJ İŞLEYİCİSİ (KATEGORİ, KOD, +, - KOMUTLARI)
# ----------------------------------------------------------------------

async def islem_yap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kategori, +, -, veya sadece ürün kodu mesajlarını işler."""
    if not yetki_kontrol(update):
        return

    text = update.message.text.strip().upper() # Gelen metni büyük harfe çevir

    global stok_veritabani
    
    # --- 5.1 Kategori Sorgulama Kontrolü ---
    if text in stok_veritabani:
        kategori = text
        mesaj = f"📦 **{kategori}** Kategorisindeki Ürünler:\n\n"
        urunler = stok_veritabani[kategori]
        
        if not urunler:
            mesaj += "Bu kategoride ürün bulunmamaktadır."
        else:
            sirali_kodlar = sorted(urunler.keys(), key=lambda x: int(x))
            for urun_kod in sirali_kodlar:
                urun_bilgi = urunler[urun_kod]
                adet = urun_bilgi['adet']
                isim = urun_bilgi['isim']
                mesaj += f"`{urun_kod}`: **{isim}** (Adet: **{adet}**)\n"
        
        return await update.message.reply_text(mesaj, parse_mode='Markdown')

    # --- 5.2 Kod Bazlı İşlem/Sorgulama Kontrolü ---
    
    islem = None
    urun_kod = None
    
    if text.startswith('+'):
        islem = '+'
        urun_kod = text[1:].strip()
    elif text.startswith('-'):
        islem = '-'
        urun_kod = text[1:].strip()
    elif text.isdigit():
        islem = 'SORGU'
        urun_kod = text.strip()
    else:
        return # İşleyeceğimiz bir komut değil

    # Ürünü tüm kategorilerde ara
    bulundugu_kategori, urun_bilgi = _urun_bul(urun_kod)

    if not urun_bilgi:
        return await update.message.reply_text(f"❌ **{urun_kod}** adında bir stok kodu bulunamadı.")
    
    mevcut_adet = urun_bilgi['adet'] 
    urun_isim = urun_bilgi['isim']

    if islem == 'SORGU':
        await update.message.reply_text(
            f"🔍 **{bulundugu_kategori}** kategorisindeki **{urun_kod}** ({urun_isim}) için mevcut adet: **{mevcut_adet}**",
            parse_mode='Markdown'
        )

    elif islem == '+':
        stok_veritabani[bulundugu_kategori][urun_kod]['adet'] += 1
        yeni_adet = stok_veritabani[bulundugu_kategori][urun_kod]['adet']
        kaydet_stok(stok_veritabani)
        
        await update.message.reply_text(
            f"✅ **{urun_kod}** ({urun_isim}) stoku 1 artırıldı.\n"
            f"Yeni Adet: **{yeni_adet}** (Kategori: {bulundugu_kategori})",
            parse_mode='Markdown'
        )
        
    elif islem == '-':
        if mevcut_adet > 0:
            stok_veritabani[bulundugu_kategori][urun_kod]['adet'] -= 1
            yeni_adet = stok_veritabani[bulundugu_kategori][urun_kod]['adet']
            kaydet_stok(stok_veritabani)

            await update.message.reply_text(
                f"✅ **{urun_kod}** ({urun_isim}) stoku 1 azaltıldı.\n"
                f"Yeni Adet: **{yeni_adet}** (Kategori: {bulundugu_kategori})",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"⚠️ **{urun_kod}** ({urun_isim}) stoku zaten 0. Daha fazla azaltılamaz.",
                parse_mode='Markdown'
            )

# ----------------------------------------------------------------------
# 6. ANA PROGRAM BAŞLATICISI
# ----------------------------------------------------------------------

def main() -> None:
    """Botu çalıştırır."""
    
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stok", stok_goster))
    
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, islem_yap)
    )

    logger.info("Kategori Bazlı Stok Botu çalışıyor...")
    print("Bot çalışıyor... Çıkış yapmak için Ctrl+C'ye basın.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
