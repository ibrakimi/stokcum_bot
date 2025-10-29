import logging
import json
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    ConversationHandler 
)
import os

# ----------------------------------------------------------------------
# 1. YAPILANDIRMA VE SABİT DEĞERLER
# ----------------------------------------------------------------------

TOKEN = os.environ.get("TELEGRAM_TOKEN", "7241140480:AAFkzFSgwDw6amZHWkRorcfbxD4HuISyhVc") 
IZINLI_KULLANICILAR_STR = os.environ.get("IZINLI_KULLANICILAR", "948469975") 
try:
    IZINLI_KULLANICILAR = [int(id.strip()) for id in IZINLI_KULLANICILAR_STR.split(',') if id.strip()]
except ValueError:
    IZINLI_KULLANICILAR = []

STOK_DOSYASI = "stok_kayit_global.json" # Yeni dosya adı
VARSAYILAN_ADET = 5

# Konuşma Durumları (States)
KOD_EKLE_KATEGORI_BEKLE = 1
KOD_EKLE_KOD_BEKLE = 2
KOD_EKLE_ISIM_BEKLE = 3

KOD_SILME_BEKLE = 4
ONAY_BEKLE = 5

# Varsayılan Ürün Kataloğu (Başlangıç Verisi)
URUN_KATALOGU = {
    "PROTEUS PREMIX": ["8006901000", "8006901001"],
    "CALORA PREMIX": ["8006901005", "8006901006"],
    "CITIUS PREMIX": ["8006901010", "8006901000"], # 8006901000 ortak kullanılıyor
}
# Varsayılan Global Stok Tanımları
GLOBAL_STOK_TANIMLARI = {
    "8006901000": "Emniyet Ventili",
    "8006901001": "Basınç Sensörü",
    "8006901005": "Türbin",
    "8006901006": "Debi Ayar Vanası",
    "8006901010": "Röle Kartı",
}


# Loglama ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# 2. VERİ YÖNETİMİ VE YÜKLEME (Global Yapıya Uyarlandı)
# ----------------------------------------------------------------------
global ana_stok
global kategori_haritasi

def _varsayilan_stok_olustur():
    ana_stok = {}
    kategori_haritasi = {}
    
    # 1. Global Stoğu Doldur
    for kod, isim in GLOBAL_STOK_TANIMLARI.items():
        ana_stok[kod] = {'isim': isim, 'adet': VARSAYILAN_ADET}
        
    # 2. Kategori Haritasını Doldur
    for kategori, kod_listesi in URUN_KATALOGU.items():
        kategori_haritasi[kategori] = kod_listesi
        
    return ana_stok, kategori_haritasi

def kaydet_stok(ana_stok_data, kategori_haritasi_data):
    # Veriyi tek bir JSON dosyasında iki anahtar olarak sakla
    veri = {'ana_stok': ana_stok_data, 'kategori_haritasi': kategori_haritasi_data}
    try:
        with open(STOK_DOSYASI, 'w', encoding='utf-8') as f:
            json.dump(veri, f, ensure_ascii=False, indent=4) 
    except Exception as e:
        logger.error(f"Stok kaydetme hatası: {e}")

def yukle_stok():
    try:
        with open(STOK_DOSYASI, 'r', encoding='utf-8') as f:
            veri = json.load(f)
            return veri.get('ana_stok', {}), veri.get('kategori_haritasi', {})
    except FileNotFoundError:
        return {}, {}
    except json.JSONDecodeError:
        return {}, {} 
    except Exception as e:
        return {}, {}

# Veriyi yükle
ana_stok, kategori_haritasi = yukle_stok()

if not ana_stok or not kategori_haritasi:
    ana_stok, kategori_haritasi = _varsayilan_stok_olustur()
    kaydet_stok(ana_stok, kategori_haritasi)

# ----------------------------------------------------------------------
# 3. YARDIMCI FONKSİYONLAR
# ----------------------------------------------------------------------

def yetki_kontrol(update: Update):
    user_id = update.effective_user.id
    return user_id in IZINLI_KULLANICILAR

def _kod_hangi_kategorilerde(urun_kod):
    """Verilen kodun listelendiği tüm kategorileri döndürür."""
    bulunan_kategoriler = []
    for kategori, kod_listesi in kategori_haritasi.items():
        if urun_kod in kod_listesi:
            bulunan_kategoriler.append(kategori)
    return bulunan_kategoriler

# ----------------------------------------------------------------------
# 4. BOT KOMUT İŞLEYİCİLERİ
# ----------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if yetki_kontrol(update):
        kategori_listesi = '\n• ' + '\n• '.join(kategori_haritasi.keys())
        await update.message.reply_text(
            '👋 Global Stok Botu aktif. \n\n'
            '📋 **Temel Komutlar:**\n'
            '• Tüm stok: `/stok`\n'
            f'• Kategori Sorgulama (Örn: `PROTEUS PREMIX`):\n{kategori_listesi}\n'
            '• **Ürün Ekleme/Tanımlama:** `/ekle`\n'
            '• **Ürün Kodu Silme:** `/sil`\n'
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
    
    if not kategori_haritasi:
        mesaj += "Stok listesi şu an boş."
    else:
        for kategori, kod_listesi in sorted(kategori_haritasi.items()):
            mesaj += f"**📦 Kategori: {kategori}**\n"
            
            sirali_kodlar = sorted(kod_listesi, key=lambda x: int(x))
            
            for urun_kod in sirali_kodlar:
                if urun_kod in ana_stok:
                    urun_bilgi = ana_stok[urun_kod]
                    adet = urun_bilgi['adet']
                    isim = urun_bilgi['isim']
                    mesaj += f"  • `{urun_kod}`: **{isim}** (Adet: **{adet}**)\n"
            mesaj += "\n" 
    
    await update.message.reply_text(mesaj, parse_mode='Markdown')

# ----------------------------------------------------------------------
# 5. YENİ ÜRÜN EKLEME (CONVERSATION HANDLER - Global Stok Kontrolü)
# ----------------------------------------------------------------------

async def ekle_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not yetki_kontrol(update):
        await update.message.reply_text("⛔ Bu işlemi yapmaya yetkiniz yok.")
        return ConversationHandler.END

    kategori_listesi = '\n• ' + '\n• '.join(sorted(kategori_haritasi.keys()))
    await update.message.reply_text(
        f"➕ **Ürün Ekleme Başlatıldı.**\n\n"
        f"Lütfen ürünün ait olacağı kategoriyi seçiniz veya yazınız:\n"
        f"{kategori_listesi}\n\n"
        f"İşlemi iptal etmek için `/iptal` yazın.",
        parse_mode='Markdown'
    )
    return KOD_EKLE_KATEGORI_BEKLE 

async def urun_kodu_al(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    global kategori_haritasi
    kategori = update.message.text.strip().upper()

    if kategori not in kategori_haritasi:
        kategori_haritasi[kategori] = []
        kaydet_stok(ana_stok, kategori_haritasi)
        await update.message.reply_text(f"✅ Yeni kategori **{kategori}** başarıyla oluşturuldu.")
        
    context.user_data['kategori'] = kategori
    
    await update.message.reply_text(
        f"Kategori: **{kategori}**\n\n"
        "Şimdi lütfen eklemek istediğiniz **ürün kodunu (sadece sayı)** yazınız.",
        parse_mode='Markdown'
    )
    return KOD_EKLE_KOD_BEKLE

async def urun_isim_al(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ürün kodunu alır, var olup olmadığını kontrol eder ve sonraki adımı belirler."""
    urun_kod = update.message.text.strip()
    kategori = context.user_data.get('kategori')
    
    if not urun_kod.isdigit():
        await update.message.reply_text("❌ Ürün kodu sadece sayılardan oluşmalıdır. Lütfen tekrar deneyin.")
        return KOD_EKLE_KOD_BEKLE

    context.user_data['urun_kod'] = urun_kod

    if urun_kod in ana_stok:
        # Kod zaten GLOBAL STOK'ta var!
        context.user_data['mevcut_kod'] = True
        
        # Sadece Kategori Listesine Ekle ve Bitir
        if urun_kod not in kategori_haritasi[kategori]:
            kategori_haritasi[kategori].append(urun_kod)
            kaydet_stok(ana_stok, kategori_haritasi)
            
            bulundugu_yerler = _kod_hangi_kategorilerde(urun_kod)
            
            await update.message.reply_text(
                f"✅ **ORTAK KOD KULLANILDI!**\n\n"
                f"`{urun_kod}` zaten **{ana_stok[urun_kod]['isim']}** olarak tanımlıydı.\n"
                f"Kod, **{kategori}** kategorisine eklendi. (Stok: {ana_stok[urun_kod]['adet']})\n"
                f"Şu an listelendiği yerler: {', '.join(bulundugu_yerler)}",
                parse_mode='Markdown'
            )
        else:
            # Kod, kategoride zaten listeleniyorsa
            await update.message.reply_text(
                f"⚠️ **{urun_kod}** kodu zaten **{kategori}** kategorisinde listeleniyor. İşlem iptal edildi.",
                parse_mode='Markdown'
            )
        
        context.user_data.clear()
        return ConversationHandler.END # Direkt bitir
    
    else:
        # Kod yeni, isim girmesini iste
        context.user_data['mevcut_kod'] = False
        await update.message.reply_text(
            f"Ürün Kodu: **{urun_kod}**\n\n"
            "Kod sistemde bulunamadı. Lütfen eklemek istediğiniz **ürün adını** yazınız.",
            parse_mode='Markdown'
        )
        return KOD_EKLE_ISIM_BEKLE

async def ekle_bitir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ürün adını alır, GLOBAL STOK'a kaydeder ve konuşmayı sonlandırır."""
    global ana_stok
    global kategori_haritasi
    
    urun_isim = update.message.text.strip()
    kategori = context.user_data.get('kategori')
    urun_kod = context.user_data.get('urun_kod')

    if not kategori or not urun_kod:
        await update.message.reply_text("Hata: Önceki adımlardan veri alınamadı. Lütfen `/ekle` komutu ile tekrar başlayınız.")
        return ConversationHandler.END
        
    # 1. Global Stoğu Güncelle
    ana_stok[urun_kod] = {
        'isim': urun_isim,
        'adet': VARSAYILAN_ADET 
    }
    
    # 2. Kategori Haritasına Ekle
    kategori_haritasi[kategori].append(urun_kod)
    
    kaydet_stok(ana_stok, kategori_haritasi)
    
    cevap = (
        f"🎉 **Yeni Ürün Başarıyla Eklendi!** (Global Stok Tanımı)\n\n"
        f"• Kategoriye Eklendi: **{kategori}**\n"
        f"• Ürün Kodu: **{urun_kod}**\n"
        f"• Ürün Adı: **{urun_isim}**\n"
        f"• Başlangıç Stoğu: **{VARSAYILAN_ADET}**"
    )
        
    await update.message.reply_text(cevap, parse_mode='Markdown')

    context.user_data.clear()
    return ConversationHandler.END

async def ekle_iptal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('İşlem iptal edildi.', )
    context.user_data.clear()
    return ConversationHandler.END


# ----------------------------------------------------------------------
# 6. STOK SİLME (Global Stok Silme)
# ----------------------------------------------------------------------
async def sil_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not yetki_kontrol(update):
        await update.message.reply_text("⛔ Bu işlemi yapmaya yetkiniz yok.")
        return ConversationHandler.END

    await update.message.reply_text(
        f"🗑️ **Stok Silme Başlatıldı.**\n\n"
        f"Lütfen silmek istediğiniz **ürün kodunu (sadece sayı)** yazınız. (Bu işlem kodu **tüm kategorilerden** ve **global stoktan** silecektir.)\n\n"
        f"İşlemi iptal etmek için `/iptal` yazın.",
        parse_mode='Markdown'
    )
    
    return KOD_SILME_BEKLE

async def onay_al(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    urun_kod = update.message.text.strip()
    
    if not urun_kod.isdigit():
        await update.message.reply_text("❌ Ürün kodu sadece sayılardan oluşmalıdır. Lütfen tekrar deneyin.")
        return KOD_SILME_BEKLE

    bulunan_kategoriler = _kod_hangi_kategorilerde(urun_kod)

    if not bulunan_kategoriler:
        await update.message.reply_text(f"❌ **{urun_kod}** adında bir stok kodu bulunamadı. Lütfen kontrol ediniz.")
        return KOD_SILME_BEKLE
    
    context.user_data['urun_kod_sil'] = urun_kod
    
    await update.message.reply_text(
        f"⚠️ **SON ONAY GEREKİR!**\n\n"
        f"`{urun_kod}` kodlu ürün **GLOBAL STOKTAN VE TÜM KATEGORİLERDEN** silinecektir. Şu an listelendiği yerler: **{', '.join(bulunan_kategoriler)}**\n\n"
        f"Onaylıyor musunuz? **EVET** yazarak onaylayın veya `/iptal` yazın.",
        parse_mode='Markdown'
    )
    
    return ONAY_BEKLE

async def silme_bitir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    onay = update.message.text.strip().upper()
    
    if onay != 'EVET':
        await update.message.reply_text("Silme işlemi onaylanmadı ve iptal edildi.")
        context.user_data.clear()
        return ConversationHandler.END

    urun_kod = context.user_data.get('urun_kod_sil')
    global ana_stok
    global kategori_haritasi

    if not urun_kod:
        await update.message.reply_text("Hata: Silinecek ürün kodu bulunamadı. Lütfen `/sil` ile tekrar başlayın.")
        context.user_data.clear()
        return ConversationHandler.END
    
    # 1. Global Stoktan Sil
    if urun_kod in ana_stok:
        del ana_stok[urun_kod]
    
    # 2. Tüm Kategori Listelerinden Sil
    silinen_kategori_sayisi = 0
    for kategori in kategori_haritasi.keys():
        if urun_kod in kategori_haritasi[kategori]:
            kategori_haritasi[kategori].remove(urun_kod)
            silinen_kategori_sayisi += 1

    kaydet_stok(ana_stok, kategori_haritasi)
    
    await update.message.reply_text(
        f"✅ **{urun_kod}** kodlu ürün, GLOBAL STOKTAN ve **{silinen_kategori_sayisi}** kategoriden başarıyla silindi.",
        parse_mode='Markdown'
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# ----------------------------------------------------------------------
# 7. STOK DEĞİŞTİRME (+/- ve Sorgu İşlemleri)
# ----------------------------------------------------------------------
async def islem_yap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not yetki_kontrol(update):
        return

    text = update.message.text.strip().upper()

    # Kategori Sorgulama Kontrolü (Aynı kalır)
    if text in kategori_haritasi:
        kategori = text
        mesaj = f"📦 **{kategori}** Kategorisindeki Ürünler:\n\n"
        kod_listesi = kategori_haritasi[kategori]
        
        if not kod_listesi:
            mesaj += "Bu kategoride ürün bulunmamaktadır."
        else:
            sirali_kodlar = sorted(kod_listesi, key=lambda x: int(x))
            for urun_kod in sirali_kodlar:
                if urun_kod in ana_stok:
                    urun_bilgi = ana_stok[urun_kod]
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

    # Kod Global Stokta var mı?
    if urun_kod not in ana_stok:
        return await update.message.reply_text(f"❌ **{urun_kod}** adında bir stok kodu bulunamadı.")
    
    urun_bilgi = ana_stok[urun_kod]
    mevcut_adet = urun_bilgi['adet'] 
    urun_isim = urun_bilgi['isim']
    bulundugu_kategoriler = _kod_hangi_kategorilerde(urun_kod)

    if islem == 'SORGU':
        await update.message.reply_text(
            f"🔍 **{urun_kod}** ({urun_isim}) için GLOBAL Stok: **{mevcut_adet}** adet\n"
            f"Listelendiği Kategoriler: {', '.join(bulundugu_kategoriler)}",
            parse_mode='Markdown'
        )

    elif islem == '+':
        ana_stok[urun_kod]['adet'] += 1
        yeni_adet = ana_stok[urun_kod]['adet']
        kaydet_stok(ana_stok, kategori_haritasi)
        
        await update.message.reply_text(
            f"✅ **{urun_kod}** ({urun_isim}) GLOBAL stoku 1 artırıldı.\n"
            f"Yeni Adet: **{yeni_adet}**",
            parse_mode='Markdown'
        )
        
    elif islem == '-':
        if mevcut_adet > 0:
            ana_stok[urun_kod]['adet'] -= 1
            yeni_adet = ana_stok[urun_kod]['adet']
            kaydet_stok(ana_stok, kategori_haritasi)

            await update.message.reply_text(
                f"✅ **{urun_kod}** ({urun_isim}) GLOBAL stoku 1 azaltıldı.\n"
                f"Yeni Adet: **{yeni_adet}**",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"⚠️ **{urun_kod}** stoku zaten 0. Daha fazla azaltılamaz.",
                parse_mode='Markdown'
            )


# ----------------------------------------------------------------------
# 8. ANA PROGRAM BAŞLATICISI
# ----------------------------------------------------------------------

def main() -> None:
    
    application = Application.builder().token(TOKEN).build()

    ekle_handler = ConversationHandler(
        entry_points=[CommandHandler("ekle", ekle_baslat)],
        states={
            KOD_EKLE_KATEGORI_BEKLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, urun_kodu_al)], 
            KOD_EKLE_KOD_BEKLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, urun_isim_al)], 
            KOD_EKLE_ISIM_BEKLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ekle_bitir)], 
        },
        fallbacks=[CommandHandler("iptal", ekle_iptal)],
    )

    sil_handler = ConversationHandler(
        entry_points=[CommandHandler("sil", sil_baslat)],
        states={
            KOD_SILME_BEKLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, onay_al)],
            ONAY_BEKLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, silme_bitir)],
        },
        fallbacks=[CommandHandler("iptal", ekle_iptal)],
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stok", stok_goster))
    
    application.add_handler(ekle_handler)
    application.add_handler(sil_handler)
    
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, islem_yap)
    )

    logger.info("Global Stok Botu çalışıyor...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
