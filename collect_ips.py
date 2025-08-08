#!/usr/bin/env python3
# collect_ips.py (修正版)
import re
import os
import sys
import time
import json
import requests
import ipaddress

# 尝试导入 geoip2 / pycountry（若未安装，前面 workflow 已安装）
try:
    import geoip2.database as geoip2_database
    geoip2_available = True
except Exception:
    geoip2_database = None
    geoip2_available = False

try:
    import pycountry
except Exception:
    pycountry = None

# ---------- CONFIG ----------
URLS = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz',
    'https://stock.hostmonit.com/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html'
]
IP_PATTERN = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
OUTPUT_FILE = 'ip.txt'
CACHE_FILE = 'ip_country_cache.json'
GEO_DB_PATH = './GeoLite2-Country.mmdb'
GEO_DOWNLOAD_SHORTLINK = 'https://git.io/GeoLite2-Country.mmdb'
IPINFO_SLEEP = 0.18
REQUEST_TIMEOUT = 12
MAX_RETRIES = 3
# 常用 UA 列表（遇 403 可切换）
UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15"
]
# 简短国家映射
COUNTRY_MAP = {
    'US': '美国', 'CA': '加拿大', 'GB': '英国', 'DE': '德国', 'FR': '法国',
    'SG': '新加坡', 'JP': '日本', 'KR': '韩国', 'CN': '中国', 'NL': '荷兰',
    'AU': '澳大利亚', 'RU': '俄罗斯', 'IN': '印度', 'BR': '巴西', 'ZA': '南非',
    'HK': '香港', 'TW': '台湾'
}
# -----------------------------

def numeric_sort_key(ip):
    return [int(p) for p in ip.split('.')]

def ensure_geolite_db():
    if os.path.exists(GEO_DB_PATH):
        return True
    # 尝试下载，多次重试
    for attempt in range(1, 4):
        try:
            print(f"尝试自动下载 GeoLite2 数据库（第 {attempt} 次）...")
            r = requests.get(GEO_DOWNLOAD_SHORTLINK, timeout=30)
            r.raise_for_status()
            with open(GEO_DB_PATH, 'wb') as f:
                f.write(r.content)
            print("GeoLite2 数据库下载完成。")
            return True
        except Exception as e:
            print("下载尝试失败:", e)
            time.sleep(2 * attempt)
    print("自动下载 GeoLite2 失败，请手动放置 GeoLite2-Country.mmdb 到脚本目录。")
    return False

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(c):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(c, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存缓存失败:", e)

def map_iso_to_chinese(iso):
    if not iso:
        return None
    iso = iso.upper()
    if iso in COUNTRY_MAP:
        return COUNTRY_MAP[iso]
    if pycountry:
        try:
            pc = pycountry.countries.get(alpha_2=iso)
            if pc:
                return pc.name
        except Exception:
            pass
    return iso

def geoip_lookup(reader, ip):
    try:
        resp = reader.country(ip)
        iso = resp.country.iso_code
        return map_iso_to_chinese(iso)
    except Exception:
        return None

def ipinfo_lookup(ip):
    try:
        r = requests.get(f'https://ipinfo.io/{ip}/json', timeout=8, headers={'User-Agent': UAS[0]})
        if r.status_code != 200:
            return None
        j = r.json()
        iso = j.get('country')
        return map_iso_to_chinese(iso)
    except Exception:
        return None

def fetch_page(url):
    session = requests.Session()
    for ua in UAS:
        headers = {'User-Agent': ua}
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                # 成功
                if r.status_code == 200:
                    return r.text
                # 429: retry with backoff
                if r.status_code == 429:
                    wait = 2 ** attempt
                    print(f"请求 {url} 返回 429，等待 {wait}s 后重试（第 {attempt} 次）")
                    time.sleep(wait)
                    continue
                # 403: 尝试下一个 UA（break attempt loop, try next UA）
                if r.status_code == 403:
                    print(f"请求 {url} 返回 403，尝试使用其他 User-Agent")
                    break
                print(f"请求 {url} 返回状态 {r.status_code}")
                break
            except requests.RequestException as e:
                print(f"请求 {url} 失败（尝试 {attempt}）：{e}")
                time.sleep(1 + attempt)
    return None

def main():
    # 1) 抓取 IP 列表
    ips = set()
    for url in URLS:
        txt = fetch_page(url)
        if not txt:
            print(f"抓取 {url} 返回空或失败")
            continue
        found = re.findall(IP_PATTERN, txt)
        if found:
            ips.update(found)
        else:
            # 有些页面返回 CIDR/特殊格式，先输出提示
            if '/' in txt and 'ips' in url:
                # 如果你想从 CIDR 解析代表IP，这里可以扩展
                pass

    if not ips:
        print("未抓到任何 IP，退出。")
        return

    unique_ips = sorted(ips, key=numeric_sort_key)
    print(f"抓到 {len(unique_ips)} 个去重 IP（排序后共 {len(unique_ips)} 个）。")

    # 2) GeoLite2 准备
    reader = None
    if geoip2_available:
        if ensure_geolite_db():
            try:
                reader = geoip2_database.Reader(GEO_DB_PATH)
                print("已打开 GeoLite2 本地数据库。")
            except Exception as e:
                print("打开 GeoLite2 数据库失败：", e)
                reader = None
        else:
            print("没有可用 GeoLite2 数据库，将回退到 ipinfo（无 token）。")
    else:
        print("geoip2 模块不可用，直接使用 ipinfo（无 token）回退。")

    cache = load_cache()
    results = []
    country_count = {}

    for ip in unique_ips:
        country = None
        if ip in cache:
            country = cache[ip]
        else:
            if reader:
                country = geoip_lookup(reader, ip)
            if not country:
                # ipinfo 回退（无 token）
                country = ipinfo_lookup(ip)
                time.sleep(IPINFO_SLEEP)
            cache[ip] = country

        if country:
            country_count[country] = country_count.get(country, 0) + 1
            num = f"{country_count[country]:03d}"
            out = f"{ip}#{country}{num}"
            results.append(out)
            print(f"{ip} => {country}{num}")
        else:
            results.append(ip)
            print(f"{ip} => (无国家信息)")

    save_cache(cache)

    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(results))
        print(f"共保存 {len(results)} 条到 {OUTPUT_FILE}")
    except Exception as e:
        print("写入文件失败：", e)

    if reader:
        try:
            reader.close()
        except Exception:
            pass

if __name__ == '__main__':
    main()
