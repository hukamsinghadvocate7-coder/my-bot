import os
import sys
import json
import base64
import hashlib
import logging
import urllib.parse
import urllib3
import requests
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import MajoRLogin_pb2 as mLpB
    import MajorLoginRes_pb2 as mLrPb
except ImportError:
    pass

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Yahan apna Bot Token dalein:
BOT_TOKEN = "8921555395:AAErZkgn5mW0sopWAX3bLfZJeocrWNeUrt4"

(
    STATE_CHECK_INFO,
    STATE_BIND_TOKEN,
    STATE_BIND_EMAIL,
    STATE_BIND_OTP,
    STATE_BIND_SEC,
    STATE_UNBIND_METHOD,
    STATE_UNBIND_TOKEN,
    STATE_UNBIND_VAL,
    STATE_CHANGE_METHOD,
    STATE_CHANGE_TOKEN,
    STATE_CHANGE_VERIFY,
    STATE_CHANGE_NEW_EMAIL,
    STATE_CHANGE_NEW_OTP,
    STATE_CANCEL_TOKEN,
    STATE_EAT_INPUT,
    STATE_REVOKE_TOKEN,
    STATE_HISTORY_TOKEN,
    STATE_BOUND_TOKEN,
) = range(18)

AeSkEy = b'Yg&tc%DEuh6%Zc^8'
AeSiV  = b'6oyZDr22E3ychjM%'

PLATFORM_MAP_FULL = {
    1: "Garena", 3: "Facebook", 4: "Guest", 5: "VK", 
    6: "Huawei", 7: "Apple", 8: "Google", 10: "GameCenter / Line", 
    11: "X (Twitter)", 13: "Apple ID", 28: "Line", 35: "TikTok"
}

HEADERS_MSDK = {
    "User-Agent": "GarenaMSDK/4.0.30",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json"
}

def enc(d): return AES.new(AeSkEy, AES.MODE_CBC, AeSiV).encrypt(pad(d, 16))
def dec(d): return unpad(AES.new(AeSkEy, AES.MODE_CBC, AeSiV).decrypt(d), 16)

def convert_seconds(s):
    d, h = divmod(s, 86400)
    h, m = divmod(h, 3600)
    m, s = divmod(m, 60)
    return f"{d} Day {h} Hour {m} Min {s} Sec"

def get_player_bind_summary(access_token):
    uid, nickname, region = "Unknown", "Unknown", "Unknown"
    try:
        player_url = f"https://api-otrss.garena.com/support/callback/?access_token={access_token}"
        p_res = requests.get(player_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10, allow_redirects=True)
        params = urllib.parse.parse_qs(urllib.parse.urlparse(p_res.url).query)
        uid = params.get("account_id", ["Unknown"])[0]
        nickname = urllib.parse.unquote(params.get("nickname", ["Unknown"])[0])
        region = params.get("region", ["Unknown"])[0]
    except Exception:
        pass

    email, email_to_be, cd_str = "None", "None", "0 Sec"
    try:
        url = "https://100067.connect.garena.com/game/account_security/bind:get_bind_info"
        r = requests.get(url, params={'app_id': "100067", 'access_token': access_token}, headers=HEADERS_MSDK, timeout=10).json()
        email = r.get("email", "") or "None"
        email_to_be = r.get("email_to_be", "") or "None"
        cd_str = convert_seconds(r.get("request_exec_countdown", 0))
    except Exception:
        pass

    return uid, nickname, region, email, email_to_be, cd_str

def build_majorlogin(tok, open_id, p_type):
    m = mLpB.MajorLogin()
    m.event_time = str(datetime.now())[:-7]
    m.game_name = "free fire"
    m.platform_id = p_type
    m.client_version = "1.120.1"
    m.system_software = "Android OS 9 / API-28"
    m.system_hardware = "Handheld"
    m.telecom_operator = "Verizon"
    m.network_type = "WIFI"
    m.screen_width = 1920
    m.screen_height = 1080
    m.screen_dpi = "280"
    m.processor_details = "ARM64 FP ASIMD AES VMH | 2865 | 4"
    m.memory = 3003
    m.gpu_renderer = "Adreno (TM) 640"
    m.gpu_version = "OpenGL ES 3.1 v1.46"
    m.unique_device_id = "Google|34a7dcdf-a7d5-4cb6-8d7e-3b0e448a0c57"
    m.client_ip = "223.191.51.89"
    m.language = "en"
    m.open_id = open_id
    m.open_id_type = str(p_type)
    m.device_type = "Handheld"
    m.access_token = tok
    m.platform_sdk_id = 1
    m.client_using_version = "7428b253defc164018c604a1ebbfebdf"
    m.login_by = 3
    m.channel_type = 3
    m.cpu_type = 2
    m.cpu_architecture = "64"
    m.client_version_code = "2019118695"
    m.login_open_id_type = p_type
    m.origin_platform_type = str(p_type)
    m.primary_platform_type = str(p_type)
    return enc(m.SerializeToString())

def read_varint(data, offset):
    res = 0; shift = 0
    while True:
        if offset >= len(data): break
        b = data[offset]; offset += 1
        res |= (b & 0x7f) << shift
        if not (b & 0x80): break
        shift += 7
    return res, offset

def parse_record(data):
    rec = {}; offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        wt, f = tag & 7, tag >> 3
        if wt == 0:
            val, offset = read_varint(data, offset)
            if f == 1: rec['ts'] = val
            elif f == 2: rec['ram'] = val
        elif wt == 2:
            length, offset = read_varint(data, offset)
            val = data[offset:offset+length]; offset += length
            if f == 3: rec['dev'] = val.decode(errors='ignore')
            elif f == 4: rec['arch'] = val.decode(errors='ignore')
        else: break
    return rec

def parse_history_protobuf(data):
    records = []; offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        wt, f = tag & 7, tag >> 3
        if wt == 0: val, offset = read_varint(data, offset)
        elif wt == 2:
            length, offset = read_varint(data, offset)
            val = data[offset:offset+length]; offset += length
            if f == 1: records.append(parse_record(val))
        else: break
    return records

def get_cancel_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return to Menu", callback_data="back_menu")]])

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("1. Check Bind Info", callback_data="opt_1"), InlineKeyboardButton("2. Bind Email", callback_data="opt_2")],
        [InlineKeyboardButton("3. Unbind Email", callback_data="opt_3"), InlineKeyboardButton("4. Change Bind Email", callback_data="opt_4")],
        [InlineKeyboardButton("5. Cancel Bind Request", callback_data="opt_5"), InlineKeyboardButton("6. EAT To Access Token", callback_data="opt_6")],
        [InlineKeyboardButton("7. Revoke Access Token", callback_data="opt_7"), InlineKeyboardButton("8. Get Login History", callback_data="opt_8")],
        [InlineKeyboardButton("9. Check Bound Accounts", callback_data="opt_9"), InlineKeyboardButton("10. Owner Details", callback_data="opt_10")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    msg_text = (
        "⚡ *NEMI BIND TOOL BOT*\n\n"
        "Developer: `@NEMI SARAN`\n"
        "Channel: `https://t.me/nemi9568`\n"
        "Status: `SAFE & SECURE`\n\n"
        "Neeche diye gaye options me se select karein:"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(msg_text, reply_markup=get_main_menu(), parse_mode="Markdown")
    else:
        await update.message.reply_text(msg_text, reply_markup=get_main_menu(), parse_mode="Markdown")
    return ConversationHandler.END

async def opt_1_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("» *Enter Access Token:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_CHECK_INFO

async def opt_1_proc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tok = update.message.text.strip()
    wait = await update.message.reply_text("⏳ Fetching data...")
    uid, nick, reg, em, em_to_be, cd = get_player_bind_summary(tok)
    res = (
        f"≡ *Player Information*\n"
        f"● *UID:* `{uid}`\n"
        f"● *Nickname:* `{nick}`\n"
        f"● *Region:* `{reg}`\n\n"
        f"≡ *Bind Information*\n"
        f"● *Current Email:* `{em}`\n"
        f"● *Pending Email:* `{em_to_be}`\n"
        f"● *Countdown:* `{cd}`"
    )
    await wait.edit_text(res, reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return ConversationHandler.END

async def opt_2_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("» *Enter Access Token:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_BIND_TOKEN

async def opt_2_tok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tok"] = update.message.text.strip()
    await update.message.reply_text("» *Enter Email to Bind:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_BIND_EMAIL

async def opt_2_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    context.user_data["email"] = email
    tok = context.user_data["tok"]
    send_otp_url = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
    data = {"email": email, "locale": "en_PK", "region": "PK", "app_id": "100067", "access_token": tok}
    r = requests.post(send_otp_url, headers=HEADERS_MSDK, data=data)
    if r.json().get("result") == 0:
        await update.message.reply_text(f"📩 OTP sent to `{email}`.\n» *Enter OTP:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
        return STATE_BIND_OTP
    else:
        await update.message.reply_text(f"❌ Failed to send OTP: `{r.text}`", reply_markup=get_cancel_btn())
        return ConversationHandler.END

async def opt_2_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp = update.message.text.strip()
    tok = context.user_data["tok"]
    email = context.user_data["email"]
    verify_url = "https://100067.connect.garena.com/game/account_security/bind:verify_otp"
    data = {"app_id": "100067", "access_token": tok, "email": email, "code": otp, "otp": otp, "type": "1"}
    r = requests.post(verify_url, headers=HEADERS_MSDK, data=data)
    verifier_token = r.json().get("verifier_token")
    if verifier_token:
        context.user_data["verifier_token"] = verifier_token
        await update.message.reply_text("✅ OTP Verified!\n» *Set 6-digit Security Code:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
        return STATE_BIND_SEC
    else:
        await update.message.reply_text(f"❌ Verification Failed: `{r.text}`", reply_markup=get_cancel_btn())
        return ConversationHandler.END

async def opt_2_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    bind_url = "https://100067.connect.garena.com/game/account_security/bind:create_bind_request"
    data = {
        "email": context.user_data["email"],
        "app_id": "100067",
        "access_token": context.user_data["tok"],
        "verifier_token": context.user_data["verifier_token"],
        "secondary_password": code
    }
    r = requests.post(bind_url, headers=HEADERS_MSDK, data=data)
    if r.json().get("result") == 0:
        await update.message.reply_text("🎉 *Bind Request Created Successfully!*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Failed: `{r.text}`", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return ConversationHandler.END

async def opt_3_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    kb = [
        [InlineKeyboardButton("Via OTP", callback_data="unbind_otp")],
        [InlineKeyboardButton("Via Security Code", callback_data="unbind_code")],
        [InlineKeyboardButton("🔙 Return to Menu", callback_data="back_menu")]
    ]
    await update.callback_query.message.reply_text("Choose Unbind Method:", reply_markup=InlineKeyboardMarkup(kb))
    return STATE_UNBIND_METHOD

async def opt_3_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["unbind_method"] = query.data
    await query.message.reply_text("» *Enter Access Token:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_UNBIND_TOKEN

async def opt_3_tok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tok = update.message.text.strip()
    context.user_data["tok"] = tok
    url_info = "https://100067.connect.garena.com/game/account_security/bind:get_bind_info"
    r = requests.get(url_info, params={'app_id': "100067", 'access_token': tok}, headers=HEADERS_MSDK).json()
    email = r.get("email", "")
    if not email:
        await update.message.reply_text("❌ No bound email found on this account.", reply_markup=get_cancel_btn())
        return ConversationHandler.END
    context.user_data["old_email"] = email
    if context.user_data["unbind_method"] == "unbind_otp":
        send_otp_url = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
        requests.post(send_otp_url, headers=HEADERS_MSDK, data={"email": email, "locale": "en_PK", "region": "PK", "app_id": "100067", "access_token": tok})
        await update.message.reply_text(f"📩 OTP sent to `{email}`.\n» *Enter OTP:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    else:
        await update.message.reply_text("» *Enter 6-digit Security Code:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_UNBIND_VAL

async def opt_3_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    tok = context.user_data["tok"]
    email = context.user_data["old_email"]
    verify_url = "https://100067.connect.garena.com/game/account_security/bind:verify_identity"
    if context.user_data["unbind_method"] == "unbind_otp":
        v_data = {"email": email, "app_id": "100067", "access_token": tok, "otp": val}
    else:
        h_code = hashlib.sha256(val.encode('utf-8')).hexdigest()
        v_data = {"email": email, "app_id": "100067", "access_token": tok, "secondary_password": h_code}
    r = requests.post(verify_url, headers=HEADERS_MSDK, data=v_data).json()
    identity_token = r.get("identity_token")
    if not identity_token:
        await update.message.reply_text(f"❌ Verification failed: `{r}`", reply_markup=get_cancel_btn())
        return ConversationHandler.END
    unbind_url = "https://100067.connect.garena.com/game/account_security/bind:create_unbind_request"
    res = requests.post(unbind_url, headers=HEADERS_MSDK, data={"app_id": "100067", "access_token": tok, "identity_token": identity_token}).json()
    if res.get("result") == 0:
        await update.message.reply_text("✅ *Unbind Request Created Successfully!*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Failed: `{res}`", reply_markup=get_cancel_btn())
    return ConversationHandler.END

async def opt_4_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    kb = [
        [InlineKeyboardButton("Via OTP", callback_data="chg_otp")],
        [InlineKeyboardButton("Via Security Code", callback_data="chg_code")],
        [InlineKeyboardButton("🔙 Return to Menu", callback_data="back_menu")]
    ]
    await update.callback_query.message.reply_text("Choose Change Method:", reply_markup=InlineKeyboardMarkup(kb))
    return STATE_CHANGE_METHOD

async def opt_4_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["chg_method"] = query.data
    await query.message.reply_text("» *Enter Access Token:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_CHANGE_TOKEN

async def opt_4_tok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tok = update.message.text.strip()
    context.user_data["tok"] = tok
    url_info = "https://100067.connect.garena.com/game/account_security/bind:get_bind_info"
    r = requests.get(url_info, params={'app_id': "100067", 'access_token': tok}, headers=HEADERS_MSDK).json()
    email = r.get("email", "")
    if not email:
        await update.message.reply_text("❌ No bound email found!", reply_markup=get_cancel_btn())
        return ConversationHandler.END
    context.user_data["old_email"] = email
    if context.user_data["chg_method"] == "chg_otp":
        send_otp_url = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
        requests.post(send_otp_url, headers=HEADERS_MSDK, data={"email": email, "locale": "en_PK", "region": "PK", "app_id": "100067", "access_token": tok})
        await update.message.reply_text(f"📩 OTP sent to `{email}`.\n» *Enter OTP:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    else:
        await update.message.reply_text("» *Enter 6-digit Security Code:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_CHANGE_VERIFY

async def opt_4_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    tok = context.user_data["tok"]
    email = context.user_data["old_email"]
    verify_url = "https://100067.connect.garena.com/game/account_security/bind:verify_identity"
    if context.user_data["chg_method"] == "chg_otp":
        v_data = {"email": email, "app_id": "100067", "access_token": tok, "otp": val}
    else:
        h_code = hashlib.sha256(val.encode('utf-8')).hexdigest()
        v_data = {"email": email, "app_id": "100067", "access_token": tok, "secondary_password": h_code}
    r = requests.post(verify_url, headers=HEADERS_MSDK, data=v_data).json()
    identity_token = r.get("identity_token")
    if not identity_token:
        await update.message.reply_text(f"❌ Verification failed: `{r}`", reply_markup=get_cancel_btn())
        return ConversationHandler.END
    context.user_data["identity_token"] = identity_token
    await update.message.reply_text("» *Enter New Email:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_CHANGE_NEW_EMAIL

async def opt_4_new_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_email = update.message.text.strip()
    context.user_data["new_email"] = new_email
    tok = context.user_data["tok"]
    url_send = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
    data = {"email": new_email, "locale": "en_PK", "region": "PK", "app_id": "100067", "access_token": tok}
    requests.post(url_send, headers=HEADERS_MSDK, data=data)
    await update.message.reply_text(f"📩 OTP sent to `{new_email}`.\n» *Enter New Email OTP:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_CHANGE_NEW_OTP

async def opt_4_new_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp = update.message.text.strip()
    tok = context.user_data["tok"]
    new_email = context.user_data["new_email"]
    url_verify_otp = "https://100067.connect.garena.com/game/account_security/bind:verify_otp"
    data = {"email": new_email, "app_id": "100067", "access_token": tok, "otp": otp}
    r = requests.post(url_verify_otp, headers=HEADERS_MSDK, data=data).json()
    verifier_token = r.get("verifier_token")
    if not verifier_token:
        await update.message.reply_text(f"❌ Verifier token missing: `{r}`", reply_markup=get_cancel_btn())
        return ConversationHandler.END
    url_rebind = "https://100067.connect.garena.com/game/account_security/bind:create_rebind_request"
    rebind_data = {
        "identity_token": context.user_data["identity_token"],
        "email": new_email,
        "app_id": "100067",
        "verifier_token": verifier_token,
        "access_token": tok
    }
    res = requests.post(url_rebind, headers=HEADERS_MSDK, data=rebind_data).json()
    if res.get("result") == 0:
        await update.message.reply_text("🎉 *Rebind Request Created Successfully!*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Failed: `{res}`", reply_markup=get_cancel_btn())
    return ConversationHandler.END

async def opt_5_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("» *Enter Access Token to Cancel Request:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_CANCEL_TOKEN

async def opt_5_proc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tok = update.message.text.strip()
    url = "https://100067.connect.garena.com/game/account_security/bind:cancel_request"
    r = requests.post(url, headers=HEADERS_MSDK, data={"app_id": "100067", "access_token": tok}).json()
    if r.get("result") == 0:
        await update.message.reply_text("✅ *Bind Request Cancelled Successfully!*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Error: `{r}`", reply_markup=get_cancel_btn())
    return ConversationHandler.END

async def opt_6_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("» *Enter EAT Token OR Full EAT URL:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_EAT_INPUT

async def opt_6_proc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    eat_token = user_input
    if "http" in user_input or "?" in user_input:
        parsed_url = urllib.parse.urlparse(user_input)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        if 'eat' in query_params:
            eat_token = query_params['eat'][0]
    api_url = f"https://api-otrss.garena.com/support/callback/?access_token={eat_token}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(api_url, headers=headers, allow_redirects=True, timeout=15)
        final_params = urllib.parse.parse_qs(urllib.parse.urlparse(response.url).query)
        if 'access_token' in final_params:
            acc_tok = final_params['access_token'][0]
            acc_id = final_params.get('account_id', ['Unknown'])[0]
            nick = urllib.parse.unquote(final_params.get('nickname', ['Unknown'])[0])
            reg = final_params.get('region', ['Unknown'])[0]
            res = (
                f"✅ *SUCCESS*\n\n"
                f"● *Nickname:* `{nick}`\n"
                f"● *Account ID:* `{acc_id}`\n"
                f"● *Region:* `{reg}`\n"
                f"● *Access Token:*\n`{acc_tok}`"
            )
            await update.message.reply_text(res, reply_markup=get_cancel_btn(), parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Access Token not found. Token expired or invalid.", reply_markup=get_cancel_btn())
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}", reply_markup=get_cancel_btn())
    return ConversationHandler.END

async def opt_7_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("» *Enter Access Token to Revoke:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_REVOKE_TOKEN

async def opt_7_proc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tok = update.message.text.strip()
    refresh_token = "1380dcb63ab3a077dc05bdf0b25ba4497c403a5b4eae96d7203010eafa6c83a8"
    logout_url = f"https://100067.connect.garena.com/oauth/logout?access_token={tok}&refresh_token={refresh_token}"
    try:
        r = requests.get(logout_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code == 200 and "error" not in r.text:
            await update.message.reply_text("✅ *Successfully Logged Out & Revoked Token!*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Revoke Failed: `{r.text}`", reply_markup=get_cancel_btn())
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}", reply_markup=get_cancel_btn())
    return ConversationHandler.END

async def opt_8_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("» *Enter Access Token OR Game JWT Token:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_HISTORY_TOKEN

async def opt_8_proc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = update.message.text.strip()
    status_msg = await update.message.reply_text("⏳ Processing Login History...")
    jwt_token = None
    if token.startswith("ey") and "." in token:
        jwt_token = token
    else:
        oId = None
        try:
            r = requests.get(f"https://100067.connect.garena.com/oauth/token/inspect?token={token}", headers={"User-Agent": "Mozilla/5.0"}, timeout=5).json()
            oId = r.get("open_id")
        except: pass
        if not oId:
            try:
                uid_res = requests.get("https://prod-api.reward.ff.garena.com/redemption/api/auth/inspect_token/", headers={"access-token": token, "user-agent": "Mozilla/5.0"}, verify=False, timeout=5).json()
                uid = uid_res.get("uid")
                if uid:
                    op_res = requests.post("https://topup.pk/api/auth/player_id_login", json={"app_id": 100067, "login_id": str(uid)}, verify=False, timeout=5).json()
                    oId = op_res.get("open_id")
            except: pass
        if not oId:
            await status_msg.edit_text("❌ Failed to extract Open ID. Token invalid or expired.", reply_markup=get_cancel_btn())
            return ConversationHandler.END

        platforms = [8, 3, 4, 6]
        for p_type in platforms:
            pl = build_majorlogin(token, oId, p_type)
            try:
                mLhDr = {
                    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 11; SM-S908E Build/TP1A.220624.014)",
                    "Connection": "Keep-Alive", "Accept-Encoding": "gzip",
                    "Content-Type": "application/octet-stream", "Expect": "100-continue",
                    "X-GA": "v1 1", "X-Unity-Version": "2018.4.11f1", "ReleaseVersion": "OB54"
                }
                x = requests.post("https://loginbp.ggpolarbear.com/MajorLogin", headers=mLhDr, data=pl, timeout=10, verify=False)
                if x.status_code == 200:
                    res = mLrPb.MajorLoginRes()
                    try: res.ParseFromString(dec(x.content))
                    except: res.ParseFromString(x.content)
                    if res.token:
                        jwt_token = res.token
                        break
            except: continue
        if not jwt_token:
            await status_msg.edit_text("❌ MajorLogin failed across platforms. Token might be blocked.", reply_markup=get_cancel_btn())
            return ConversationHandler.END

    hH = {
        "Expect": "100-continue", "Authorization": f"Bearer {jwt_token}",
        "X-Unity-Version": "2018.4.11f1", "X-GA": "v1 1", "ReleaseVersion": "OB54",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; G011A Build/PI)",
        "Host": "client.ind.freefiremobile.com", "Connection": "close"
    }
    try:
        r = requests.post("https://client.ind.freefiremobile.com/GetLoginHistory", headers=hH, data=enc(b""), timeout=15, verify=False)
        try: d = dec(r.content)
        except: d = r.content
        records = parse_history_protobuf(d)
        if not records:
            await status_msg.edit_text("⚠️ No login history records found.", reply_markup=get_cancel_btn())
            return ConversationHandler.END
        out = "📜 *LOGIN HISTORY RECORDS*\n\n"
        for i, rec in enumerate(records[:10], 1):
            ts_raw = rec.get('ts', 0)
            try: date_str = datetime.fromtimestamp(ts_raw).strftime('%Y-%m-%d %H:%M:%S')
            except: date_str = "Invalid Format"
            out += (
                f"*{i}. Last Login:* `{date_str}`\n"
                f"   • Device: `{rec.get('dev', 'Unknown')}`\n"
                f"   • Arch: `{rec.get('arch', 'Unknown')}`\n"
                f"   • RAM: `{rec.get('ram', 0)} MB`\n\n"
            )
        await status_msg.edit_text(out, reply_markup=get_cancel_btn(), parse_mode="Markdown")
    except Exception as e:
        await status_msg.edit_text(f"❌ Error fetching history: {str(e)}", reply_markup=get_cancel_btn())
    return ConversationHandler.END

async def opt_9_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("» *Enter Access Token:*", reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return STATE_BOUND_TOKEN

async def opt_9_proc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tok = update.message.text.strip()
    url = "https://100067.connect.garena.com/bind/app/platform/info/get"
    headers = {"User-Agent": "GarenaMSDK/4.0.19P9(Redmi Note 5 ;Android 9;en;US;)", "Connection": "Keep-Alive"}
    try:
        r = requests.get(url, params={"access_token": tok}, headers=headers, timeout=10).json()
        bounded = r.get("bounded_accounts", [])
        avail = r.get("available_platforms", [])
        b_text = "\n".join([f"• {PLATFORM_MAP_FULL.get(i, f'Unknown ({i})')}" for i in bounded]) if bounded else "• None"
        a_text = "\n".join([f"• {PLATFORM_MAP_FULL.get(i, f'Unknown ({i})')}" for i in avail]) if avail else "• None"
        res = (
            f"🔗 *PLATFORM BINDS*\n\n"
            f"*Bound Accounts:*\n{b_text}\n\n"
            f"*Available Platforms:*\n{a_text}"
        )
        await update.message.reply_text(res, reply_markup=get_cancel_btn(), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}", reply_markup=get_cancel_btn())
    return ConversationHandler.END

async def opt_10_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    text = (
        "👑 *DEVELOPER & OWNER DETAILS*\n\n"
        "⊛ *Developer:* @NEMI SARAN\n"
        "⊛ *Telegram:* NEMI SARAN\n"
        "⊛ *Channel:* https://t.me/nemi9568\n"
        "⊛ *Status:* `SAFE & SECURE`\n"
        "⊛ *Version:* `v2.0 (Premium / Secure)`"
    )
    await update.callback_query.message.reply_text(text, reply_markup=get_cancel_btn(), parse_mode="Markdown")
    return ConversationHandler.END

async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Action cancel ho gaya. /start bhej kar menu kholein.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(start, pattern="^back_menu$"),
            CallbackQueryHandler(opt_1_start, pattern="^opt_1$"),
            CallbackQueryHandler(opt_2_start, pattern="^opt_2$"),
            CallbackQueryHandler(opt_3_start, pattern="^opt_3$"),
            CallbackQueryHandler(opt_4_start, pattern="^opt_4$"),
            CallbackQueryHandler(opt_5_start, pattern="^opt_5$"),
            CallbackQueryHandler(opt_6_start, pattern="^opt_6$"),
            CallbackQueryHandler(opt_7_start, pattern="^opt_7$"),
            CallbackQueryHandler(opt_8_start, pattern="^opt_8$"),
            CallbackQueryHandler(opt_9_start, pattern="^opt_9$"),
            CallbackQueryHandler(opt_10_start, pattern="^opt_10$"),
        ],
        states={
            STATE_CHECK_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_1_proc), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_BIND_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_2_tok), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_BIND_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_2_email), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_BIND_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_2_otp), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_BIND_SEC: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_2_sec), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_UNBIND_METHOD: [CallbackQueryHandler(opt_3_method, pattern="^unbind_"), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_UNBIND_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_3_tok), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_UNBIND_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_3_val), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_CHANGE_METHOD: [CallbackQueryHandler(opt_4_method, pattern="^chg_"), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_CHANGE_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_4_tok), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_CHANGE_VERIFY: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_4_verify), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_CHANGE_NEW_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_4_new_email), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_CHANGE_NEW_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_4_new_otp), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_CANCEL_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_5_proc), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_EAT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_6_proc), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_REVOKE_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_7_proc), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_HISTORY_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_8_proc), CallbackQueryHandler(start, pattern="^back_menu$")],
            STATE_BOUND_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, opt_9_proc), CallbackQueryHandler(start, pattern="^back_menu$")],
        },
        fallbacks=[CommandHandler("cancel", cancel_action), CommandHandler("start", start), CallbackQueryHandler(start, pattern="^back_menu$")],
    )
    app.add_handler(conv_handler)
    print("Bot chalu ho gaya... Telegram par /start karein.")
    app.run_polling()

if __name__ == "__main__":
    main()
