import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import sqlite3
import logging
import threading
import sys
import atexit
import random
import psutil
import platform
import json
from typing import Dict, List, Tuple, Optional

# ================================
# KONFIGURASYON
# ================================
TOKEN = '8865805280:AAFynzBE34i_-MRHMRNb0sP05oJSxRS9KuM'
OWNER_ID = 8610336203
ADMIN_ID = 8610336203
BOT_NAME = '@ankaptolamasikokmibot'

# DOSYA YAPILARI
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'data')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

# LOG SISTEMI
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot_activity.log'), encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# VERI YAPILARI
bot_scripts = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
pending_approvals = {}
verified_users = set()
system_stats = {
    'start_time': datetime.now(),
    'total_commands': 0,
    'total_uploads': 0,
    'total_errors': 0
}

# VERITABANI
def init_db():
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT, 
                      status TEXT DEFAULT 'pending', upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
                      join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS bot_stats
                     (stat_key TEXT PRIMARY KEY, stat_value TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS command_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, command TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        conn.close()
        logger.info("Veritabani baslatildi!")
    except Exception as e:
        logger.error(f"Veritabani hatasi: {e}")

init_db()

# SISTEM ISTATISTIKLERI
def get_system_stats():
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        return {
            'cpu': cpu_percent,
            'ram': {'total': memory.total, 'used': memory.used, 'free': memory.free, 'percent': memory.percent},
            'disk': {'total': disk.total, 'used': disk.used, 'free': disk.free, 'percent': disk.percent},
            'uptime': str(datetime.now() - system_stats['start_time']).split('.')[0],
            'processes': len(psutil.pids()),
            'connections': len(psutil.net_connections())
        }
    except:
        return {'cpu': 0, 'ram': {'percent': 0}, 'disk': {'percent': 0}, 'uptime': 'Bilinmiyor'}

def format_bytes(bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} PB"

# KLAVYELER
def create_main_keyboard(user_id):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if user_id in admin_ids:
        buttons = ['📤 DOSYA YUKLE', '📁 DOSYALARIM', '⚡ SISTEM', '📊 ISTATISTIK', '👑 ONAYLAR', '🔄 YENILE', 'ℹ️ YARDIM']
        keyboard.row(buttons[0], buttons[1])
        keyboard.row(buttons[2], buttons[3])
        keyboard.row(buttons[4], buttons[5])
        keyboard.row(buttons[6])
    else:
        buttons = ['📤 DOSYA YUKLE', '📁 DOSYALARIM', '⚡ SISTEM', '📊 ISTATISTIK', '🔄 YENILE', 'ℹ️ YARDIM']
        keyboard.row(buttons[0], buttons[1])
        keyboard.row(buttons[2], buttons[3])
        keyboard.row(buttons[4], buttons[5])
    return keyboard

def create_files_keyboard(user_id):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    user_files_list = user_files.get(user_id, [])
    buttons = []
    for file_name, file_type, status in user_files_list[:8]:
        if status == 'approved':
            is_running = is_bot_running(user_id, file_name)
            status_emoji = '🚀' if is_running else '⏸️'
        elif status == 'pending':
            status_emoji = '⏳'
        else:
            status_emoji = '❌'
        display_name = file_name[:12] + '...' if len(file_name) > 12 else file_name
        buttons.append(f"{status_emoji} {display_name}")
    for i in range(0, len(buttons), 2):
        if i+1 < len(buttons):
            keyboard.row(buttons[i], buttons[i+1])
        else:
            keyboard.row(buttons[i])
    keyboard.row('🏠 ANA MENU')
    return keyboard

def create_file_control_keyboard(file_name, status, is_running):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if status == 'approved':
        if is_running:
            buttons = ['⏸️ DURDUR', '🔄 YENIDEN BASLAT', '📋 LOGLAR', '🗑️ SIL']
            keyboard.row(buttons[0], buttons[1])
            keyboard.row(buttons[2], buttons[3])
        else:
            buttons = ['🚀 BASLAT', '🗑️ SIL', '🔙 GERI']
            keyboard.row(buttons[0], buttons[1])
            keyboard.row(buttons[2])
    else:
        keyboard.row('🔙 GERI')
    keyboard.row('🏠 ANA MENU')
    return keyboard

def create_approval_keyboard(file_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ ONAYLA", callback_data=f"approve_{file_id}"),
        types.InlineKeyboardButton("❌ REDDET", callback_data=f"reject_{file_id}")
    )
    return keyboard

# YARDIMCI FONKSIYONLAR
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = script_info['process']
            return proc.poll() is None
        except:
            return False
    return False

def save_user_file(user_id, file_name, file_type, status='pending'):
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type, status) VALUES (?, ?, ?, ?)',
                  (user_id, file_name, file_type, status))
        conn.commit()
        conn.close()
        if user_id not in user_files:
            user_files[user_id] = []
        user_files[user_id] = [(fn, ft, st) for fn, ft, st in user_files[user_id] if fn != file_name]
        user_files[user_id].append((file_name, file_type, status))
        return True
    except Exception as e:
        logger.error(f"Dosya kaydetme hatasi: {e}")
        return False

def run_bot_process(user_id, file_name, file_path, file_type):
    def target():
        script_key = f"{user_id}_{file_name}"
        try:
            if script_key in bot_scripts:
                old_proc = bot_scripts[script_key].get('process')
                if old_proc and old_proc.poll() is None:
                    old_proc.terminate()
                    time.sleep(1)
            if file_type == 'py':
                proc = subprocess.Popen([sys.executable, file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)
            elif file_type == 'js':
                proc = subprocess.Popen(['node', file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)
            else:
                return
            bot_scripts[script_key] = {
                'process': proc,
                'file_name': file_name,
                'user_id': user_id,
                'file_type': file_type,
                'start_time': datetime.now(),
                'log_file': os.path.join(LOGS_DIR, f"{user_id}_{file_name}.log")
            }
            logger.info(f"Bot baslatildi: {script_key}")
            def read_output(proc, script_key):
                try:
                    with open(bot_scripts[script_key]['log_file'], 'w', encoding='utf-8') as log_file:
                        while True:
                            line = proc.stdout.readline()
                            if line:
                                clean_line = line.strip()
                                if clean_line:
                                    log_file.write(f"{datetime.now()} - {clean_line}\n")
                                    log_file.flush()
                            elif proc.poll() is not None:
                                break
                except Exception as e:
                    logger.error(f"Log okuma hatasi: {e}")
                finally:
                    if script_key in bot_scripts:
                        del bot_scripts[script_key]
            threading.Thread(target=read_output, args=(proc, script_key), daemon=True).start()
        except Exception as e:
            logger.error(f"Bot baslatma hatasi: {e}")
    threading.Thread(target=target, daemon=True).start()

# START KOMUTU
@bot.message_handler(commands=['start', 'help'])
def command_start(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO users (user_id, username, first_name, last_active) VALUES (?, ?, ?, ?)',
                  (user_id, message.from_user.username, user_name, datetime.now()))
        conn.commit()
        conn.close()
    except:
        pass
    active_users.add(user_id)
    is_admin = "👑 SAHIP" if user_id == OWNER_ID else "🔧 ADMIN" if user_id in admin_ids else "👤 KULLANICI"
    welcome_msg = f"""🌟 **HOS GELDIN {user_name}!** 🌟

🤖 **Bot Adi:** {BOT_NAME}
👤 **Seviye:** {is_admin}
📁 **Dosyalar:** {get_user_file_count(user_id)}

⚡ **OZELLIKLER:**
• Python & Node.js bot calistirma
• ZIP destegi
• Gercek CPU/RAM istatistikleri
• Gelismis dosya yonetimi

📌 **Baslamak icin** bir buton secin!"""
    bot.send_message(user_id, welcome_msg, parse_mode='Markdown', reply_markup=create_main_keyboard(user_id))
    logger.info(f"Yeni kullanici: {user_id} ({user_name})")

# MESAJ HANDLER
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.from_user.id
    text = message.text
    if not text:
        return
    logger.info(f"Mesaj: {user_id} -> {text}")
    system_stats['total_commands'] += 1
    
    if text == '🏠 ANA MENU' or text == '🔙 GERI':
        command_start(message)
    elif text in ['📤 DOSYA YUKLE', '📤 Dosya Yukle']:
        handle_upload(message)
    elif text in ['📁 DOSYALARIM', '📁 Dosyalarim']:
        handle_my_files(message)
    elif text in ['⚡ SISTEM', '⚡ Sistem']:
        handle_system_stats(message)
    elif text in ['📊 ISTATISTIK', '📊 Istatistik']:
        handle_stats(message)
    elif text == '👑 ONAYLAR' and user_id in admin_ids:
        handle_pending_approvals(message)
    elif text == '🔄 YENILE':
        command_start(message)
    elif text == 'ℹ️ YARDIM':
        handle_help(message)
    elif text in ['🚀 BASLAT', '⏸️ DURDUR', '🔄 YENIDEN BASLAT', '🗑️ SIL', '📋 LOGLAR']:
        handle_file_action(message, text)
    else:
        user_files_list = user_files.get(user_id, [])
        for file_name, file_type, status in user_files_list:
            display_name = file_name[:12] + '...' if len(file_name) > 12 else file_name
            possible_buttons = [f"🚀 {display_name}", f"⏸️ {display_name}", f"⏳ {display_name}", f"❌ {display_name}", f"✅ {display_name}"]
            if text in possible_buttons:
                handle_file_control(message, user_id, file_name, file_type, status)
                return
        bot.send_message(user_id, "❌ Anlamadim!\n\nLutfen butonlari kullan veya /start yaz.", reply_markup=create_main_keyboard(user_id))

def handle_upload(message):
    user_id = message.from_user.id
    current_files = get_user_file_count(user_id)
    if current_files >= 20:
        bot.send_message(user_id, f"❌ **LIMIT DOLDU!**\n\n📊 Mevcut: {current_files}/20\n\n💡 Premium icin adminle iletisime gec!", parse_mode='Markdown', reply_markup=create_main_keyboard(user_id))
        return
    bot.send_message(user_id, f"📤 **DOSYA YUKLE**\n\n✨ Desteklenenler: `.py`, `.js`, `.zip`\n📦 Max boyut: 20MB\n🎯 Limit: {current_files}/20\n\n👇 Dosyani gonder:", parse_mode='Markdown')

def handle_my_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.send_message(user_id, "📭 **HENUZ DOSYA YOK**\n\n✨ Ilk botunu yuklemek icin 'DOSYA YUKLE' butonuna bas! 🚀", reply_markup=create_main_keyboard(user_id))
        return
    files_text = f"📁 **DOSYALARIN** ({len(user_files_list)})\n\n"
    for idx, (file_name, file_type, status) in enumerate(user_files_list, 1):
        if status == 'approved':
            is_running = is_bot_running(user_id, file_name)
            status_text = "🚀 CALISIYOR" if is_running else "⏸️ DURDU"
            emoji = "🟢" if is_running else "🟡"
        elif status == 'pending':
            status_text = "⏳ BEKLIYOR"
            emoji = "🟠"
        else:
            status_text = "❌ REDDEDILDI"
            emoji = "🔴"
        files_text += f"{emoji} `{file_name}`\n   📝 {file_type.upper()} | {status_text}\n\n"
    bot.send_message(user_id, files_text, parse_mode='Markdown', reply_markup=create_files_keyboard(user_id))

def handle_file_control(message, user_id, file_name, file_type, status):
    if status == 'pending':
        text = f"⏳ **BEKLIYOR**\n\n📄 `{file_name}`\n🎯 {file_type.upper()}\n\n✨ Admin onayi bekleniyor..."
    elif status == 'rejected':
        text = f"❌ **REDDEDILDI**\n\n📄 `{file_name}`\n\n💔 Bu dosya admin tarafindan reddedildi."
    elif status == 'approved':
        is_running = is_bot_running(user_id, file_name)
        if is_running:
            text = f"🚀 **CALISIYOR**\n\n📄 `{file_name}`\n🎯 {file_type.upper()}\n\n✨ Bot aktif calisiyor!"
        else:
            text = f"⏸️ **DURDU**\n\n📄 `{file_name}`\n🎯 {file_type.upper()}\n\n💡 Bot su anda durdurulmus."
    else:
        text = f"❓ **BILINMIYOR**\n\n📄 `{file_name}`"
    is_running = is_bot_running(user_id, file_name) if status == 'approved' else False
    bot.send_message(user_id, text, parse_mode='Markdown', reply_markup=create_file_control_keyboard(file_name, status, is_running))

def handle_file_action(message, action):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.send_message(user_id, "❌ Hic dosya bulunamadi!")
        return
    target_file = None
    for file_name, file_type, status in user_files_list:
        if status == 'approved':
            target_file = (file_name, file_type)
            break
    if not target_file:
        bot.send_message(user_id, "❌ Onaylanmis dosya bulunamadi!")
        return
    file_name, file_type = target_file
    
    if action == '🚀 BASLAT':
        user_folder = get_user_folder(user_id)
        file_path = os.path.join(user_folder, file_name)
        if os.path.exists(file_path):
            run_bot_process(user_id, file_name, file_path, file_type)
            bot.send_message(user_id, f"🚀 **BASLATILIYOR**\n\n`{file_name}`\n\n✨ Bot baslatildi!")
        else:
            bot.send_message(user_id, f"❌ Dosya bulunamadi: `{file_name}`")
    elif action == '⏸️ DURDUR':
        script_key = f"{user_id}_{file_name}"
        if script_key in bot_scripts:
            proc = bot_scripts[script_key]['process']
            try:
                proc.terminate()
                time.sleep(1)
                bot.send_message(user_id, f"⏸️ **DURDURULDU**\n\n`{file_name}`")
            except:
                bot.send_message(user_id, f"❌ Durdurma hatasi!")
        else:
            bot.send_message(user_id, f"❌ Bot zaten calismiyor!")
    elif action == '🔄 YENIDEN BASLAT':
        script_key = f"{user_id}_{file_name}"
        if script_key in bot_scripts:
            proc = bot_scripts[script_key]['process']
            try:
                proc.terminate()
                time.sleep(2)
            except:
                pass
        user_folder = get_user_folder(user_id)
        file_path = os.path.join(user_folder, file_name)
        if os.path.exists(file_path):
            run_bot_process(user_id, file_name, file_path, file_type)
            bot.send_message(user_id, f"🔄 **YENIDEN BASLATILIYOR**\n\n`{file_name}`")
        else:
            bot.send_message(user_id, f"❌ Dosya bulunamadi!")
    elif action == '🗑️ SIL':
        user_folder = get_user_folder(user_id)
        file_path = os.path.join(user_folder, file_name)
        script_key = f"{user_id}_{file_name}"
        if script_key in bot_scripts:
            try:
                bot_scripts[script_key]['process'].terminate()
                time.sleep(1)
                del bot_scripts[script_key]
            except:
                pass
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute('DELETE FROM user_files WHERE user_id=? AND file_name=?', (user_id, file_name))
            conn.commit()
            conn.close()
            if user_id in user_files:
                user_files[user_id] = [(fn, ft, st) for fn, ft, st in user_files[user_id] if fn != file_name]
            bot.send_message(user_id, f"🗑️ **SILINDI**\n\n`{file_name}`\n\n✅ Dosya basariyla silindi!")
        except Exception as e:
            bot.send_message(user_id, f"❌ Silme hatasi: {str(e)[:100]}")
    elif action == '📋 LOGLAR':
        script_key = f"{user_id}_{file_name}"
        if script_key in bot_scripts:
            log_file = bot_scripts[script_key].get('log_file')
            if log_file and os.path.exists(log_file):
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        logs = f.read()[-1000:]
                        if logs:
                            bot.send_message(user_id, f"📋 **LOGLAR**\n\n```\n{logs}\n```", parse_mode='Markdown')
                        else:
                            bot.send_message(user_id, "📋 Loglar bos!")
                except:
                    bot.send_message(user_id, "❌ Log okuma hatasi!")
            else:
                bot.send_message(user_id, "📋 Log dosyasi bulunamadi!")
        else:
            bot.send_message(user_id, "⏸️ Bot calismiyor!")

def handle_system_stats(message):
    user_id = message.from_user.id
    stats = get_system_stats()
    cpu_bar = "█" * int(stats['cpu'] / 5) + "░" * (20 - int(stats['cpu'] / 5))
    ram_percent = stats['ram']['percent']
    ram_bar = "█" * int(ram_percent / 5) + "░" * (20 - int(ram_percent / 5))
    disk_percent = stats['disk']['percent']
    disk_bar = "█" * int(disk_percent / 5) + "░" * (20 - int(disk_percent / 5))
    stats_msg = f"""⚡ **SISTEM ISTATISTIKLERI** ⚡

🖥️ **CPU Kullanimi:**
`{cpu_bar}` {stats['cpu']:.1f}%

💾 **RAM Kullanimi:**
`{ram_bar}` {ram_percent:.1f}%
📦 Toplam: {format_bytes(stats['ram']['total'])}
📤 Kullanilan: {format_bytes(stats['ram']['used'])}
📥 Bos: {format_bytes(stats['ram']['free'])}

💿 **Disk Kullanimi:**
`{disk_bar}` {disk_percent:.1f}%
📦 Toplam: {format_bytes(stats['disk']['total'])}
📤 Kullanilan: {format_bytes(stats['disk']['used'])}
📥 Bos: {format_bytes(stats['disk']['free'])}

⏱️ **Calisma Suresi:** {stats['uptime']}
🔄 **Islem Sayisi:** {stats['processes']}
🔗 **Baglantilar:** {stats['connections']}

🤖 **Bot Durumu:**
🚀 Calisan Bot: {sum(1 for s in bot_scripts.values() if s.get('process', {}).poll() is None)}
📁 Toplam Dosya: {sum(len(files) for files in user_files.values())}
👥 Aktif Kullanici: {len(active_users)}"""
    bot.send_message(user_id, stats_msg, parse_mode='Markdown')

def handle_stats(message):
    user_id = message.from_user.id
    total_files = sum(len(files) for files in user_files.values())
    running_bots = sum(1 for s in bot_scripts.values() if s.get('process', {}).poll() is None)
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        total_users = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM command_logs WHERE DATE(timestamp) = DATE("now")')
        today_commands = c.fetchone()[0]
        conn.close()
    except:
        total_users = len(active_users)
        today_commands = 0
    stats_msg = f"""📊 **BOT ISTATISTIKLERI** 📊

👥 **Kullanicilar:**
• Toplam: {total_users}
• Aktif: {len(active_users)}

📁 **Dosyalar:**
• Toplam: {total_files}
• Onay Bekleyen: {len(pending_approvals)}
• Calisan: {running_bots}

📈 **Aktivite:**
• Toplam Komut: {system_stats['total_commands']}
• Bugunku Komut: {today_commands}
• Hata Sayisi: {system_stats['total_errors']}

⏰ **Baslangic:** {system_stats['start_time'].strftime('%d.%m.%Y %H:%M')}
🔄 **Calisma Suresi:** {str(datetime.now() - system_stats['start_time']).split('.')[0]}"""
    bot.send_message(user_id, stats_msg, parse_mode='Markdown')

def handle_pending_approvals(message):
    user_id = message.from_user.id
    if user_id not in admin_ids:
        bot.send_message(user_id, "❌ Bu islem icin yetkin yok!")
        return
    if not pending_approvals:
        bot.send_message(user_id, "✅ Su anda bekleyen onay yok!")
        return
    text = f"⏳ **BEKLEYEN ONAYLAR** ({len(pending_approvals)})\n\n"
    for file_id, info in list(pending_approvals.items())[:5]:
        text += f"""👤 `{info['user_name']}`
📄 `{info['file_name']}`
🎯 {info['file_type'].upper()}
⏰ {info['upload_time'].strftime('%H:%M')}
────────────
"""
    if len(pending_approvals) > 5:
        text += f"\n... ve {len(pending_approvals) - 5} daha bekliyor."
    bot.send_message(user_id, text, parse_mode='Markdown')

def handle_help(message):
    help_msg = """ℹ️ **YARDIM MENUSU** ℹ️

📤 **DOSYA YUKLE**
Python/Node.js botlarini yukleyin
Desteklenen: .py, .js, .zip

📁 **DOSYALARIM**
Yuklediginiz tum dosyalari gorun
Calistirin, durdurun veya silin

⚡ **SISTEM**
Gercek CPU, RAM, Disk istatistikleri
Sistem durumunu gosterir

📊 **ISTATISTIK**
Bot istatistikleri
Kullanici, dosya, komut sayilari

👑 **ONAYLAR** (Admin)
Bekleyen dosyalari onaylayin veya reddedin

🔄 **YENILE**
Menuyu yenileyin

📝 **KOMUTLAR:**
/start - Ana menu
/help - Bu yardim

💡 **IPUCU:** Her sey butonlarla kontrol edilir!"""
    bot.send_message(message.from_user.id, help_msg, parse_mode='Markdown', reply_markup=create_main_keyboard(message.from_user.id))

# DOSYA YUKLEME HANDLER
@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    doc = message.document
    file_name = doc.file_name
    if not file_name:
        bot.reply_to(message, "❌ Dosya adi yok!")
        return
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "❌ Sadece `.py`, `.js`, `.zip` dosyalari kabul edilir!")
        return
    current_files = get_user_file_count(user_id)
    if current_files >= 20:
        bot.reply_to(message, f"❌ Dosya limiti doldu! ({current_files}/20)")
        return
    if doc.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, "❌ Dosya cok buyuk! Max 20MB")
        return
    try:
        bot.reply_to(message, f"📥 **YUKLENIYOR**\n\n`{file_name}`\n\n⏳ Lutfen bekle...")
        file_info = bot.get_file(doc.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        if file_ext == '.zip':
            handle_zip_file(downloaded_file, file_name, message, user_id, user_folder)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f:
                f.write(downloaded_file)
            file_type = 'py' if file_ext == '.py' else 'js'
            if save_user_file(user_id, file_name, file_type, 'pending'):
                file_id = f"{user_id}_{file_name}_{int(time.time())}"
                pending_approvals[file_id] = {
                    'user_id': user_id,
                    'user_name': message.from_user.first_name,
                    'file_name': file_name,
                    'file_type': file_type,
                    'file_path': file_path,
                    'upload_time': datetime.now()
                }
                admin_msg = f"""📤 **YENI DOSYA**

👤 {message.from_user.first_name}
🆔 {user_id}
📄 {file_name}
🎯 {file_type.upper()}"""
                try:
                    with open(file_path, 'rb') as f:
                        bot.send_document(ADMIN_ID, f, caption=admin_msg, reply_markup=create_approval_keyboard(file_id))
                except:
                    bot.send_message(ADMIN_ID, admin_msg, reply_markup=create_approval_keyboard(file_id))
                system_stats['total_uploads'] += 1
                bot.reply_to(message, f"✅ **YUKLENDI!**\n\n`{file_name}`\n\n⏳ Admin onayi bekleniyor...")
            else:
                bot.reply_to(message, "❌ Kayit sirasinda hata olustu!")
    except Exception as e:
        logger.error(f"Dosya yukleme hatasi: {e}")
        system_stats['total_errors'] += 1
        bot.reply_to(message, f"❌ Hata: {str(e)[:100]}")

def handle_zip_file(downloaded_file_content, file_name_zip, message, user_id, user_folder):
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"zip_{user_id}_")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as f:
            f.write(downloaded_file_content)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        extracted = os.listdir(temp_dir)
        py_files = [f for f in extracted if f.lower().endswith('.py')]
        js_files = [f for f in extracted if f.lower().endswith('.js')]
        main_script = None
        file_type = None
        for name in ['main.py', 'bot.py', 'app.py', 'index.py']:
            if name in py_files:
                main_script = name
                file_type = 'py'
                break
        if not main_script:
            for name in ['index.js', 'main.js', 'bot.js', 'app.js']:
                if name in js_files:
                    main_script = name
                    file_type = 'js'
                    break
        if not main_script:
            if py_files:
                main_script = py_files[0]
                file_type = 'py'
            elif js_files:
                main_script = js_files[0]
                file_type = 'js'
        if not main_script:
            bot.reply_to(message, "❌ ZIP'te script dosyasi bulunamadi!")
            return
        for item in os.listdir(temp_dir):
            src = os.path.join(temp_dir, item)
            dst = os.path.join(user_folder, item)
            if os.path.exists(dst):
                try:
                    if os.path.isfile(dst):
                        os.remove(dst)
                    else:
                        shutil.rmtree(dst)
                except:
                    pass
            try:
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                else:
                    shutil.copytree(src, dst)
            except Exception as e:
                logger.error(f"Dosya kopyalama hatasi {item}: {e}")
        if save_user_file(user_id, main_script, file_type, 'pending'):
            file_path = os.path.join(user_folder, main_script)
            file_id = f"{user_id}_{main_script}_{int(time.time())}"
            pending_approvals[file_id] = {
                'user_id': user_id,
                'user_name': message.from_user.first_name,
                'file_name': main_script,
                'file_type': file_type,
                'file_path': file_path,
                'upload_time': datetime.now()
            }
            admin_msg = f"""📦 **YENI ZIP**

👤 {message.from_user.first_name}
🆔 {user_id}
📄 {main_script}
🎯 {file_type.upper()}
🗜️ {file_name_zip}"""
            try:
                with open(file_path, 'rb') as f:
                    bot.send_document(ADMIN_ID, f, caption=admin_msg, reply_markup=create_approval_keyboard(file_id))
            except:
                bot.send_message(ADMIN_ID, admin_msg, reply_markup=create_approval_keyboard(file_id))
            bot.reply_to(message, f"✅ **ZIP ACILDI!**\n\n📄 `{main_script}`\n🎯 {file_type.upper()}\n\n⏳ Admin onayi bekleniyor...")
        else:
            bot.reply_to(message, "❌ Kayit sirasinda hata!")
    except zipfile.BadZipFile:
        bot.reply_to(message, "❌ Gecersiz ZIP dosyasi!")
    except Exception as e:
        logger.error(f"ZIP isleme hatasi: {e}")
        bot.reply_to(message, f"❌ ZIP hatasi: {str(e)[:100]}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass

# CALLBACK HANDLER
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data
    if data.startswith("approve_") or data.startswith("reject_"):
        if user_id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ Yetkiniz yok!", show_alert=True)
            return
        action, file_id = data.split("_", 1)
        if file_id not in pending_approvals:
            bot.answer_callback_query(call.id, "✅ Zaten islendi!", show_alert=True)
            return
        file_info = pending_approvals[file_id]
        target_user_id = file_info['user_id']
        file_name = file_info['file_name']
        file_type = file_info['file_type']
        if action == "approve":
            if save_user_file(target_user_id, file_name, file_type, 'approved'):
                try:
                    bot.send_message(target_user_id, f"🎉 **DOSYAN ONAYLANDI!**\n\n✅ `{file_name}`\n\nArtik botunu baslatabilirsin! 🚀", parse_mode='Markdown')
                except:
                    pass
                try:
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"✅ **ONAYLANDI**\n👤 {file_info['user_name']}\n📄 {file_name}\n🎯 {file_type.upper()}", reply_markup=None)
                except:
                    pass
                bot.answer_callback_query(call.id, "✅ Onaylandi!")
            else:
                bot.answer_callback_query(call.id, "❌ Hata olustu!", show_alert=True)
        elif action == "reject":
            user_folder = get_user_folder(target_user_id)
            file_path = os.path.join(user_folder, file_name)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            try:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute('DELETE FROM user_files WHERE user_id=? AND file_name=?', (target_user_id, file_name))
                conn.commit()
                conn.close()
                if target_user_id in user_files:
                    user_files[target_user_id] = [(fn, ft, st) for fn, ft, st in user_files[target_user_id] if fn != file_name]
                try:
                    bot.send_message(target_user_id, f"❌ **DOSYAN REDDEDILDI**\n\n`{file_name}`\n\nDosyan admin tarafindan reddedildi.", parse_mode='Markdown')
                except:
                    pass
                try:
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"❌ **REDDEDILDI**\n👤 {file_info['user_name']}\n📄 {file_name}", reply_markup=None)
                except:
                    pass
                bot.answer_callback_query(call.id, "❌ Reddedildi!")
            except Exception as e:
                logger.error(f"Reddetme hatasi: {e}")
                bot.answer_callback_query(call.id, "❌ Hata olustu!", show_alert=True)
        if file_id in pending_approvals:
            del pending_approvals[file_id]

# TEMIZLIK
def cleanup():
    logger.warning("Bot kapatiliyor...")
    for script_key, script_info in list(bot_scripts.items()):
        try:
            proc = script_info.get('process')
            if proc and proc.poll() is None:
                proc.terminate()
                logger.info(f"Bot durduruldu: {script_key}")
        except:
            pass
    bot_scripts.clear()
    logger.info("Temizlik tamamlandi!")

atexit.register(cleanup)

# ANA CALISTIRMA
if __name__ == '__main__':
    logger.info("="*50)
    logger.info("FRANSA BOT BASLATILIYOR...")
    logger.info("="*50)
    logger.info(f"Bot: {BOT_NAME}")
    logger.info(f"Owner: {OWNER_ID}")
    logger.info(f"Admin: {ADMIN_ID}")
    logger.info("="*50)
    try:
        bot_info = bot.get_me()
        logger.info(f"Bot baglantisi basarili! @{bot_info.username}")
    except Exception as e:
        logger.error(f"Bot baglanti hatasi: {e}")
        exit(1)
    logger.info("Polling baslatiliyor...")
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=30)
        except Exception as e:
            logger.critical(f"KRITIK HATA: {e}")
            logger.info("10 saniye sonra yeniden baslatiliyor...")
            time.sleep(10)
