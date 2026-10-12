from flask import Flask, request, jsonify
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, UsernameInvalidError, UsernameNotOccupiedError
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
import asyncio
import os
import time
import random
import requests
import uuid
from datetime import datetime, timedelta

app = Flask(__name__)

# ============================================
# TELEGRAM CONFIG
# ============================================
API_ID = int(os.environ.get('API_ID', '36879151'))
API_HASH = os.environ.get('API_HASH', '45360a236343352099ffa29570f48700')
SESSION_STRING = os.environ.get('SESSION_STRING', '1BVtsOMQBu8B5k-vpEYTBDBxXX20SdK8kApAbT08lt4vzuQIIqsycH00oxKNPZGOc7HcAje_4qUF5Kk6FQ0JGMqjH9LdThnlXrVwxO98Z7gjM0w874HVa6U3Y8LCBLu2SpbifYQ7K4MIe3Li-BVtcQr9YNRJTkW12WWOuetNloXWIiAq51TOn3kTADJM_59k8E2bCO2i_nYxGKFfjzS7zm36s0pxckPdXBqft69GrTRXkkFuwabix3LSmYjoc0HB9_Zsuzxp0qwkZViMFCay68tdxFS57peSLSXnCSXpiwkjXAtc3dNnPJUqyYqC2khHdrqVz9HiWRCoUf5Zu6IcFedVS1BWaMC4=')

# ============================================
# PROXY SYSTEM
# ============================================
proxy_pool = []
proxy_last_fetch = 0
PROXY_CACHE_TIME = 300

def fetch_live_proxies():
    global proxy_pool, proxy_last_fetch
    if time.time() - proxy_last_fetch < PROXY_CACHE_TIME and proxy_pool:
        return proxy_pool
    
    proxies = []
    sources = [
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=all&anonymity=all",
        "https://www.proxy-list.download/api/v1/get?type=http",
    ]
    for url in sources:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                for line in r.text.strip().split('\n'):
                    line = line.strip()
                    if line and ':' in line:
                        proxies.append(line)
        except:
            pass
    
    proxies = list(set(proxies))
    if proxies:
        proxy_pool = proxies
        proxy_last_fetch = time.time()
    return proxy_pool

def get_random_proxy():
    proxies = fetch_live_proxies()
    return random.choice(proxies) if proxies else None

# ============================================
# CACHE SYSTEM
# ============================================
cache = {}
CACHE_TTL = 3600  # 1 hour (info changes fast)

def get_cached(key):
    if key in cache:
        result, timestamp = cache[key]
        if datetime.now() - timestamp < timedelta(seconds=CACHE_TTL):
            return result
    return None

def set_cached(key, result):
    cache[key] = (result, datetime.now())

# ============================================
# TELEGRAM CLIENT
# ============================================
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, loop=loop)

# ============================================
# HELPER FUNCTIONS
# ============================================
def safe_get(obj, attr, default=None):
    """Safely get attribute"""
    try:
        val = getattr(obj, attr, default)
        return val if val is not None else default
    except:
        return default

def format_date(dt):
    """Format datetime to string"""
    if dt is None:
        return None
    try:
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except:
        return str(dt)

async def get_entity_with_retry(identifier, retry_count=0):
    await client.connect()
    if not await client.is_user_authorized():
        raise Exception("Client not authorized")
    
    try:
        if identifier.startswith('@'):
            e = await client.get_entity(identifier)
        elif identifier.lstrip('-').isdigit():
            e = await client.get_entity(int(identifier))
        else:
            e = await client.get_entity(f"@{identifier}")
        return e
    except FloodWaitError as e:
        if retry_count < 2 and e.seconds <= 30:
            await asyncio.sleep(e.seconds)
            return await get_entity_with_retry(identifier, retry_count + 1)
        raise Exception(f"Flood wait: {e.seconds}s")

# ============================================
# MAIN INFO EXTRACTOR - 20+ FIELDS
# ============================================
async def get_full_info(identifier):
    """Extract 20+ real info about user/channel/group"""
    entity = await get_entity_with_retry(identifier)
    
    info = {
        "status": "success",
        "credit": "@BRONX_ULTRA",
        "query": identifier,
        "extracted_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    
    # ===== BASIC INFO =====
    info["chat_id"] = entity.id
    info["access_hash"] = safe_get(entity, 'access_hash')
    info["username"] = safe_get(entity, 'username')
    info["usernames"] = []
    
    # Multiple usernames (Telegram allows up to 2)
    if hasattr(entity, 'usernames'):
        try:
            info["usernames"] = [u.username for u in entity.usernames]
        except:
            pass
    
    # ===== TYPE DETECTION =====
    if isinstance(entity, types.User):
        info["type"] = "user"
    elif isinstance(entity, types.Channel):
        info["type"] = "channel" if safe_get(entity, 'broadcast') else "supergroup"
    elif isinstance(entity, types.Chat):
        info["type"] = "group"
    else:
        info["type"] = "unknown"
    
    # ============================================
    # USER INFO
    # ============================================
    if isinstance(entity, types.User):
        info["first_name"] = safe_get(entity, 'first_name')
        info["last_name"] = safe_get(entity, 'last_name')
        info["full_name"] = f"{safe_get(entity, 'first_name', '')} {safe_get(entity, 'last_name', '')}".strip()
        info["phone"] = safe_get(entity, 'phone')
        info["is_bot"] = safe_get(entity, 'bot', False)
        info["is_premium"] = safe_get(entity, 'premium', False)
        info["is_verified"] = safe_get(entity, 'verified', False)
        info["is_scam"] = safe_get(entity, 'scam', False)
        info["is_fake"] = safe_get(entity, 'fake', False)
        info["is_restricted"] = safe_get(entity, 'restricted', False)
        info["is_deleted"] = safe_get(entity, 'deleted', False)
        info["is_mutual_contact"] = safe_get(entity, 'mutual_contact', False)
        info["status"] = str(type(entity.status).__name__) if hasattr(entity, 'status') else None
        info["language_code"] = safe_get(entity, 'lang_code')
        info["min"] = safe_get(entity, 'min', False)
        info["support"] = safe_get(entity, 'support', False)
        info["bot_info_version"] = safe_get(entity, 'bot_info_version')
        
        # ===== PROFILE PHOTO =====
        try:
            photos = await client.get_profile_photos(entity, limit=1)
            info["has_photo"] = len(photos) > 0
            info["photo_count"] = len(await client.get_profile_photos(entity, limit=0))
        except:
            info["has_photo"] = False
            info["photo_count"] = 0
        
        # ===== FULL USER INFO =====
        try:
            full = await client(GetFullUserRequest(entity))
            full_user = full.full_user
            
            info["about"] = safe_get(full_user, 'about', '')
            info["common_chats_count"] = safe_get(full_user, 'common_chats_count', 0)
            info["blocked"] = safe_get(full_user, 'blocked', False)
            info["phone_calls_available"] = safe_get(full_user, 'phone_calls_available', False)
            info["phone_calls_private"] = safe_get(full_user, 'phone_calls_private', False)
            info["can_pin_message"] = safe_get(full_user, 'can_pin_message', False)
            info["has_scheduled"] = safe_get(full_user, 'has_scheduled', False)
            info["video_calls_available"] = safe_get(full_user, 'video_calls_available', False)
            info["voice_messages_forbidden"] = safe_get(full_user, 'voice_messages_forbidden', False)
            info["ttl_period"] = safe_get(full_user, 'ttl_period')
            info["theme_emoticon"] = safe_get(full_user, 'theme_emoticon')
            info["private_forward_name"] = safe_get(full_user, 'private_forward_name')
            
            # Bot info
            bot_info = safe_get(full_user, 'bot_info')
            if bot_info:
                info["bot_description"] = safe_get(bot_info, 'description')
                info["bot_commands"] = [
                    {"command": c.command, "description": c.description}
                    for c in safe_get(bot_info, 'commands', [])
                ]
            
            # Personal channel
            personal_chat = safe_get(full_user, 'personal_chat')
            if personal_chat:
                info["personal_channel"] = {
                    "id": personal_chat.id,
                    "title": safe_get(personal_chat, 'title'),
                    "username": safe_get(personal_chat, 'username')
                }
        except Exception as e:
            info["full_info_error"] = str(e)
    
    # ============================================
    # CHANNEL / GROUP INFO
    # ============================================
    elif isinstance(entity, (types.Channel, types.Chat)):
        info["title"] = safe_get(entity, 'title')
        info["is_verified"] = safe_get(entity, 'verified', False)
        info["is_scam"] = safe_get(entity, 'scam', False)
        info["is_fake"] = safe_get(entity, 'fake', False)
        info["is_restricted"] = safe_get(entity, 'restricted', False)
        info["date_created"] = format_date(safe_get(entity, 'date'))
        info["creator"] = safe_get(entity, 'creator', False)
        info["left"] = safe_get(entity, 'left', False)
        info["megagroup"] = safe_get(entity, 'megagroup', False)
        info["broadcast"] = safe_get(entity, 'broadcast', False)
        info["gigagroup"] = safe_get(entity, 'gigagroup', False)
        info["slowmode_enabled"] = safe_get(entity, 'slowmode_enabled', False)
        info["join_to_send"] = safe_get(entity, 'join_to_send', False)
        info["join_request"] = safe_get(entity, 'join_request', False)
        info["signatures"] = safe_get(entity, 'signatures', False)
        info["pre_history_hidden"] = safe_get(entity, 'pre_history_hidden', False)
        info["restricted"] = safe_get(entity, 'restricted', False)
        info["participants_hidden"] = safe_get(entity, 'participants_hidden', False)
        info["noforwards"] = safe_get(entity, 'noforwards', False)
        info["default_banned_rights"] = str(safe_get(entity, 'default_banned_rights'))
        info["has_link"] = safe_get(entity, 'has_link', False)
        info["has_geo"] = safe_get(entity, 'has_geo', False)
        
        # ===== FULL CHANNEL INFO =====
        try:
            if isinstance(entity, types.Channel):
                full = await client(GetFullChannelRequest(entity))
                full_chat = full.full_chat
            else:
                full = await client(GetFullChatRequest(entity.id))
                full_chat = full.full_chat
            
            info["about"] = safe_get(full_chat, 'about', '')
            info["participants_count"] = safe_get(full_chat, 'participants_count', 0)
            info["admins_count"] = safe_get(full_chat, 'admins_count')
            info["kicked_count"] = safe_get(full_chat, 'kicked_count')
            info["banned_count"] = safe_get(full_chat, 'banned_count')
            info["online_count"] = safe_get(full_chat, 'online_count')
            info["read_inbox_max_id"] = safe_get(full_chat, 'read_inbox_max_id')
            info["read_outbox_max_id"] = safe_get(full_chat, 'read_outbox_max_id')
            info["unread_count"] = safe_get(full_chat, 'unread_count')
            info["pinned_msg_id"] = safe_get(full_chat, 'pinned_msg_id')
            info["folder_id"] = safe_get(full_chat, 'folder_id')
            info["slowmode_seconds"] = safe_get(full_chat, 'slowmode_seconds')
            info["ttl_period"] = safe_get(full_chat, 'ttl_period')
            info["call"] = safe_get(full_chat, 'call') is not None
            info["can_set_username"] = safe_get(full_chat, 'can_set_username', False)
            info["can_view_participants"] = safe_get(full_chat, 'can_view_participants', False)
            info["can_set_stickers"] = safe_get(full_chat, 'can_set_stickers', False)
            info["hidden_prehistory"] = safe_get(full_chat, 'hidden_prehistory', False)
            info["sticker_set_id"] = safe_get(full_chat, 'stickerset')
            info["available_reactions"] = safe_get(full_chat, 'available_reactions')
            
            # Linked chat
            linked = safe_get(full_chat, 'linked_chat_id')
            if linked:
                info["linked_chat_id"] = linked
            
            # Bot info
            bot_info = safe_get(full_chat, 'bot_info', [])
            if bot_info:
                info["bot_info"] = [
                    {"user_id": b.user_id, "description": b.description}
                    for b in bot_info
                ]
        except Exception as e:
            info["full_info_error"] = str(e)
        
        # ===== GET OWNER/CREATOR =====
        try:
            if isinstance(entity, types.Channel):
                admins = await client.get_participants(entity, filter=types.ChannelParticipantsAdmins, limit=5)
                info["admins_list"] = [
                    {
                        "id": a.id,
                        "username": safe_get(a, 'username'),
                        "first_name": safe_get(a, 'first_name'),
                        "is_bot": safe_get(a, 'bot', False)
                    }
                    for a in admins
                ]
        except:
            pass
        
        # ===== PROFILE PHOTO =====
        try:
            photos = await client.get_profile_photos(entity, limit=1)
            info["has_photo"] = len(photos) > 0
        except:
            info["has_photo"] = False
    
    # ============================================
    # PROXY & CACHE INFO
    # ============================================
    info["proxy_pool_size"] = len(proxy_pool)
    info["cached"] = False
    
    return info

# ============================================
# ROUTES
# ============================================
@app.route('/')
def home():
    proxy_count = len(fetch_live_proxies())
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>BRONX ULTRA API v2.0</title>
        <style>
            body {{ background: #000; color: #0ff; font-family: monospace; text-align: center; padding: 30px; }}
            code {{ background: #111; padding: 8px; color: #fa0; border-radius: 5px; display: block; margin: 10px auto; max-width: 700px; }}
            .stat {{ color: #0f0; margin: 8px; }}
            h1 {{ color: #f0f; text-shadow: 0 0 20px #f0f; }}
            h3 {{ color: #ff0; }}
            .box {{ border: 1px solid #0ff; padding: 20px; margin: 20px auto; max-width: 800px; border-radius: 10px; }}
        </style>
    </head>
    <body>
        <h1>🚀 BRONX ULTRA API v2.0</h1>
        <h3>🔥 20+ REAL INFO EXTRACTOR 🔥</h3>
        <div class="box">
            <p class="stat">🛡️ Live Proxies: {proxy_count}</p>
            <p class="stat">💾 Cache: 1 Hour</p>
            <p class="stat">⚡ Unlimited Requests</p>
        </div>
        <div class="box">
            <h3>📌 ENDPOINTS</h3>
            <code>GET /full-info?username=USERNAME</code>
            <code>GET /chatid?username=USERNAME</code>
            <code>GET /proxies</code>
            <code>GET /refresh-proxies</code>
            <code>GET /clear-cache</code>
            <code>GET /health</code>
        </div>
        <p style="color:#f0f; margin-top:30px; font-size: 20px;">💀 @BRONX_ULTRA 💀</p>
    </body>
    </html>
    """

@app.route('/full-info')
def full_info():
    """Get 20+ real info about user/channel/group"""
    identifier = request.args.get('username') or request.args.get('id') or request.args.get('query', '')
    identifier = identifier.strip()
    
    if not identifier:
        return jsonify({
            "status": "error",
            "message": "Missing 'username' or 'id' parameter",
            "credit": "@BRONX_ULTRA"
        }), 400
    
    cache_key = f"full:{identifier.lower()}"
    cached = get_cached(cache_key)
    if cached:
        cached["cached"] = True
        return jsonify(cached)
    
    async def get():
        return await get_full_info(identifier)
    
    try:
        result = loop.run_until_complete(get())
        set_cached(cache_key, result)
        return jsonify(result)
    except FloodWaitError as e:
        return jsonify({
            "status": "error",
            "message": f"Flood wait: {e.seconds}s",
            "credit": "@BRONX_ULTRA"
        }), 429
    except (UsernameInvalidError, UsernameNotOccupiedError):
        return jsonify({
            "status": "error",
            "message": "Username invalid or not occupied",
            "credit": "@BRONX_ULTRA"
        }), 404
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "credit": "@BRONX_ULTRA"
        }), 404

@app.route('/chatid')
def chatid():
    """Simple chat ID endpoint"""
    username = request.args.get('username', '').strip()
    if not username:
        return jsonify({"status": "error", "message": "Missing username", "credit": "@BRONX_ULTRA"}), 400
    
    cache_key = f"chatid:{username.lower()}"
    cached = get_cached(cache_key)
    if cached:
        cached["cached"] = True
        return jsonify(cached)
    
    async def get():
        e = await get_entity_with_retry(username)
        result = {
            "status": "success",
            "chat_id": e.id,
            "username": safe_get(e, 'username', username.replace('@', '')),
            "credit": "@BRONX_ULTRA",
            "cached": False,
        }
        if isinstance(e, types.User):
            result["type"] = "user"
            result["name"] = f"{safe_get(e, 'first_name', '')} {safe_get(e, 'last_name', '')}".strip()
        else:
            result["type"] = "channel" if safe_get(e, 'broadcast') else "group"
            result["title"] = safe_get(e, 'title')
        return result
    
    try:
        result = loop.run_until_complete(get())
        set_cached(cache_key, result)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "credit": "@BRONX_ULTRA"
        }), 404

@app.route('/proxies')
def list_proxies():
    proxies = fetch_live_proxies()
    return jsonify({
        "status": "success",
        "total_proxies": len(proxies),
        "proxies": proxies[:20],
        "credit": "@BRONX_ULTRA"
    })

@app.route('/refresh-proxies')
def refresh_proxies():
    global proxy_last_fetch
    proxy_last_fetch = 0
    proxies = fetch_live_proxies()
    return jsonify({
        "status": "success",
        "total_proxies": len(proxies),
        "message": "Proxy pool refreshed",
        "credit": "@BRONX_ULTRA"
    })

@app.route('/clear-cache')
def clear_cache():
    cache.clear()
    return jsonify({
        "status": "success",
        "message": "Cache cleared",
        "credit": "@BRONX_ULTRA"
    })

@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "cached_entries": len(cache),
        "proxies": len(proxy_pool),
        "credit": "@BRONX_ULTRA"
    })

# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    fetch_live_proxies()
    
    async def init():
        await client.connect()
        if await client.is_user_authorized():
            print("✅ BRONX ULTRA API v2.0 - RUNNING")
            print(f"🛡️ Proxies loaded: {len(proxy_pool)}")
            print("🔥 20+ Real Info Extractor Ready!")
        else:
            print("⚠️ Client not authorized!")
    
    try:
        loop.run_until_complete(init())
    except Exception as e:
        print(f"Init error: {e}")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
