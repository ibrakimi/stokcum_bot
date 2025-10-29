import logging
import json
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    ConversationHandler 
)
import os

# ----------------------------------------------------------------------
# 1. YAPILANDIRMA VE SABİT DEĞERLER (Render Ortam Değişkenlerinden Okunur)
# ----------------------------------------------------------------------

# Bot Token'ı ortam değişkeninden okunur
TOKEN = os.environ.get("TELEGRAM_TOKEN", "7241140480:AAFkzFSgwDw6amZHWkRorcfbxD4HuISyhVc") 

# Yetkili Kullanıcı ID'leri ortam değişkeninden okunur (Örn: "ID1,ID2")
IZINLI_KULLANICILAR_STR = os.environ.get("IZINLI_KULLANICILAR", "948469975") 
try:
    # ID'ler boşluksuz virgülle ayrılmış olmalı
    IZINLI_KULLANICILAR = [int(id.strip()) for id in IZINLI_KULLANICILAR_STR.split(',') if id.strip()]
except ValueError:
    IZINLI_KULLANICILAR = []

STOK_DOSYASI = "stok_kayit_kategorili.json" 
VARSAYILAN_ADET = 5

# Konuşma Durumları (States) - 3 adıma çıkarıldı
URUN_KODU_BEKLE = 1
URUN_ISMI_BEKLE = 2
URUN_ADI_BEKLE = 3 # Yeni adım: Ürün adı bekleniyor

# Varsayılan Ürün Kataloğu (Sadece ilk çalıştırma için)
URUN_KATALOGU = {
    "PROTEUS PREMIX": {
        "8006901000": "Emniyet Ventili",
        "8006901001": "Basınç Sensörü",
    },
    "CALORA PREMIX": {
        "8006901005": "Türbin",  
        "8006901006": "Debi Ayar Vanası",
    },
    "CITIUS PREMIX": {
        "8006901010": "Röle Kartı",
    },
}

# Loglama ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# 2. VERİ YÖNETİMİ VE YÜKLEME (Aynı Kalır)
# ----------------------------------------------------------------------

def _varsayilan_stok_olustur():
    stok = {}
    for kategori, urunler in URUN_KATALOGU.items():
        stok[kategori] = {}
        for kod, isim in urunler.items():
            stok[kategori][kod] = {'isim': isim, 'adet': VARSAYILAN_ADET}
    return stok

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
        return {}
    except json.JSONDecodeError:
        return {} 
    except Exception as e:
        return {}

stok_veritabani = yukle_stok()

if not stok_veritabani:
    stok_veritabani = _varsayilan_stok_olustur()
    kaydet_stok(stok_veritabani)
else:
    # Veri bütünlüğü kontrolü (yeni kategoriler/ürünler eklenirse)
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

# ----------------------------------------------------------------------
# 3. YARDIMCI VE YETKİLENDİRME FONKSİYONLARI (Aynı Kalır)
# ----------------------------------------------------------------------

def yetki_kontrol(update: Update):
    user_id = update.effective_user.id
    return user_id in IZINLI_KULLANICILAR

def _tum_kategorilerde_urun_ara(urun_kod):
    """Verilen ürünü hangi kategorilerde bulduğunu listeler."""
    bulunan_kategoriler = []
    for kategori, urunler in stok_veritabani.items():
        if urun_kod in urunler:
            bulunan_kategoriler.append(kategori)
    return bulunan_kategoriler

# ----------------------------------------------------------------------
# 4. BOT KOMUT İŞLEYİCİLERİ (Temel Komutlar - Aynı Kalır)
# ----------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if yetki_kontrol(update):
        kategori_listesi = '\n• ' + '\n• '.join(stok_veritabani.keys())
        await update.message.reply_text(
            '👋 Stok Botu aktif. \n\n'
            '📋 **Temel Komutlar:**\n'
            '• Tüm stok: `/stok`\n'
            f'• Kategori Sorgulama (Örn: `PROTEUS PREMIX`):\n{kategori_listesi}\n'
            '• **Yeni Ürün Ekleme:** `/ekle`\n'
            '• Stok değiştir: `+8006901000` / `-8006901000`\n'
            '• Stok Sorgulama: `8006901000`',
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("⛔ Bu botu kullanmaya yetkiniz yok.")

async def stok_goster(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not yetki_kontrol(update):
        return await update.message.reply_text("⛔ Yetkiniz yok.")

    mesaj = "📊 **Mevcut Tüm Stoklar** 📊\n\n"
    
    global stok_veritabani 
    
    if not stok_veritabani:
        mesaj += "Stok listesi şu an boş."
    else:
        for kategori, urunler in sorted(stok_veritabani.items()):
            mesaj += f"**📦 Kategori: {kategori}**\n"
            
            sirali_kodlar = sorted(urunler.keys(), key=lambda x: int(x))
            
            for urun_kod in sirali_kodlar:
                urun_bilgi = urunler[urun_kod]
                adet = urun_bilgi['adet']
                isim = urun_bilgi['isim']
                mesaj += f"  • `{urun_kod}`: **{isim}** (Adet: **{adet}**)\n"
            mesaj += "\n" 
    
    await update.message.reply_text(mesaj, parse_mode='Markdown')

# ----------------------------------------------------------------------
# 5. YENİ ÜRÜN EKLEME (CONVERSATION HANDLER) - DÜZELTİLDİ
# ----------------------------------------------------------------------

async def ekle_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/ekle komutu ile konuşmayı başlatır ve kategoriyi ister."""
    if not yetki_kontrol(update):
        await update.message.reply_text("⛔ Bu işlemi yapmaya yetkiniz yok.")
        return ConversationHandler.END

    kategori_listesi = '\n• ' + '\n• '.join(sorted(stok_veritabani.keys()))
    await update.message.reply_text(
        f"➕ **Ürün Ekleme Başlatıldı.**\n\n"
        f"Lütfen ürünün ait olacağı kategoriyi seçiniz veya yazınız:\n"
        f"{kategori_listesi}\n\n"
        f"İşlemi iptal etmek için `/iptal` yazın.",
        parse_mode='Markdown'
    )
    
    # Adım 1: Kategori adını bekliyoruz
    return URUN_KODU_BEKLE 

async def urun_kodu_al(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kategori adını alır ve ürün kodunu ister."""
    global stok_veritabani
    kategori = update.message.text.strip().upper()

    if kategori not in stok_veritabani:
        # Yeni kategori oluşturma talebi
        stok_veritabani[kategori] = {}
        kaydet_stok(stok_veritabani)
        await update.message.reply_text(f"✅ Yeni kategori **{kategori}** başarıyla oluşturuldu.")
        
    context.user_data['kategori'] = kategori
    
    await update.message.reply_text(
        f"Kategori: **{kategori}**\n\n"
        "Şimdi lütfen eklemek istediğiniz **ürün kodunu (sadece sayı)** yazınız.",
        parse_mode='Markdown'
    )
    # Adım 2: Ürün kodunu bekliyoruz
    return URUN_ISMI_BEKLE

async def urun_isim_al(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ürün kodunu alır ve ürün adını ister."""
    urun_kod = update.message.text.strip()
    
    if not urun_kod.isdigit():
        await update.message.reply_text("❌ Ürün kodu sadece sayılardan oluşmalıdır. Lütfen tekrar deneyin.")
        return URUN_ISMI_BEKLE # Aynı durumda kal

    context.user_data['urun_kod'] = urun_kod

    await update.message.reply_text(
        f"Ürün Kodu: **{urun_kod}**\n\n"
        "Şimdi lütfen eklemek istediğiniz **ürün adını** (Örn: Emniyet Ventili) yazınız."
    )
    
    # Adım 3: Ürün adını bekliyoruz
    return URUN_ADI_BEKLE # Yeni durum

async def ekle_bitir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ürün adını alır, ürünü kaydeder ve konuşmayı sonlandırır."""
    global stok_veritabani
    
    urun_isim = update.message.text.strip()
    kategori = context.user_data.get('kategori')
    urun_kod = context.user_data.get('urun_kod')

    if not kategori or not urun_kod:
        await update.message.reply_text("Hata: Önceki adımlardan veri alınamadı. Lütfen `/ekle` komutu ile tekrar başlayınız.")
        return ConversationHandler.END
        
    # Ürünü kategoriye ekle
    stok_veritabani[kategori][urun_kod] = {
        'isim': urun_isim,
        'adet': VARSAYILAN_ADET # Başlangıç stoğu VARSAYILAN_ADET (5)
    }
    kaydet_stok(stok_veritabani)
    
    # Aynı ürün kodunun başka kategorilerde de olup olmadığını kontrol et
    bulunanlar = _tum_kategorilerde_urun_ara(urun_kod)
    
    cevap = (
        f"🎉 **Ürün Başarıyla Eklendi!**\n\n"
        f"• Kategori: **{kategori}**\n"
        f"• Ürün Kodu: **{urun_kod}**\n"
        f"• Ürün Adı: **{urun_isim}**\n"
        f"• Başlangıç Stoğu: **{VARSAYILAN_ADET}**"
    )
    
    if len(bulunanlar) > 1:
        cevap += (
            f"\n\n⚠️ **UYARI:** Bu ürün kodu ( `{urun_kod}` ) şu kategorilerde de listelenmektedir: "
            f"{', '.join(bulunanlar)}. Stok takibi her bir kategori için ayrı ayrı yapılacaktır."
        )
        
    await update.message.reply_text(cevap, parse_mode='Markdown')

    context.user_data.clear() # Konuşma verilerini temizle
    return ConversationHandler.END

async def ekle_iptal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/iptal komutu ile konuşmayı sonlandırır."""
    await update.message.reply_text('İşlem iptal edildi.', )
    context.user_data.clear()
    return ConversationHandler.END

# ----------------------------------------------------------------------
# 6. ESKİ İŞLEMLERİN YENİ DURUMA UYARLANMASI (Aynı Kalır)
# ----------------------------------------------------------------------

async def islem_yap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Bu fonksiyon, 5. adımdaki eklemeler hariç, aynı kalır.

    if not yetki_kontrol(update):
        return

    text = update.message.text.strip().upper()

    global stok_veritabani
    
    # Kategori Sorgulama Kontrolü
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
                mesaj += f"  • `{urun_kod}`: **{isim}** (Adet: **{adet}**)\n"
        
        return await update.message.reply_text(mesaj, parse_mode='Markdown')

    # Kod Bazlı İşlem/Sorgulama Kontrolü
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
        return

    bulunan_kategoriler = _tum_kategorilerde_urun_ara(urun_kod)

    if not bulunan_kategoriler:
        return await update.message.reply_text(f"❌ **{urun_kod}** adında bir stok kodu bulunamadı.")
    
    if islem == 'SORGU':
        sorgu_mesaj = f"🔍 **{urun_kod}** Kodu için Stok Durumları:\n"
        
        for kategori in bulunan_kategoriler:
            urun_bilgi = stok_veritabani[kategori][urun_kod]
            mevcut_adet = urun_bilgi['adet']
            urun_isim = urun_bilgi['isim']
            sorgu_mesaj += f"• **{kategori}** ({urun_isim}): **{mevcut_adet}** adet\n"
            
        return await update.message.reply_text(sorgu_mesaj, parse_mode='Markdown')

    elif islem == '+':
        # Tüm kategorilerdeki stoğu 1 artır
        for kategori in bulunan_kategoriler:
             stok_veritabani[kategori][urun_kod]['adet'] += 1
        
        yeni_adet = stok_veritabani[bulunan_kategoriler[0]][urun_kod]['adet']
        kaydet_stok(stok_veritabani)
        
        await update.message.reply_text(
            f"✅ **{urun_kod}** stoku 1 artırıldı.\n"
            f"Yeni Adet (Tüm Kategorilerde): **{yeni_adet}**",
            parse_mode='Markdown'
        )
        
    elif islem == '-':
        mevcut_adet = stok_veritabani[bulunan_kategoriler[0]][urun_kod]['adet']
        
        if mevcut_adet > 0:
            for kategori in bulunan_kategoriler:
                stok_veritabani[kategori][urun_kod]['adet'] -= 1
                
            yeni_adet = stok_veritabani[bulunan_kategoriler[0]][urun_kod]['adet']
            kaydet_stok(stok_veritabani)

            await update.message.reply_text(
                f"✅ **{urun_kod}** stoku 1 azaltıldı.\n"
                f"Yeni Adet (Tüm Kategorilerde): **{yeni_adet}**",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"⚠️ **{urun_kod}** stoku zaten 0. Daha fazla azaltılamaz.",
                parse_mode='Markdown'
            )

# ----------------------------------------------------------------------
# 7. ANA PROGRAM BAŞLATICISI
# ----------------------------------------------------------------------

def main() -> None:
    
    application = Application.builder().token(TOKEN).build()

    # YENİ ve DÜZELTİLMİŞ Konuşma İşleyicisi Tanımı
    ekle_handler = ConversationHandler(
        entry_points=[CommandHandler("ekle", ekle_baslat)],
        states={
            URUN_KODU_BEKLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, urun_kodu_al)], # Kategori alındı
            URUN_ISMI_BEKLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, urun_isim_al)], # Ürün kodu alındı
            URUN_ADI_BEKLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ekle_bitir)], # Ürün adı alındı ve işlem bitti
        },
        fallbacks=[CommandHandler("iptal", ekle_iptal)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stok", stok_goster))
    
    # Conversation Handler'ı diğerlerinden önce ekle
    application.add_handler(ekle_handler)
    
    # Tüm kalan mesajları işleyecek Handler
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, islem_yap)
    )

    logger.info("Gelişmiş Stok Botu çalışıyor...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
