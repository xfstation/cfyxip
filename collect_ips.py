#!/usr/bin/env python3
# collect_ips.py — 随查随用版本（仅用 ipinfo.io，无本地 GeoLite2）

import re
import os
import time
import json
import requests

# ---------- 配置 ----------
URLS = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz',
    'https://stock.hostmonit.com/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html'
]
IP_PATTERN = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
OUTPUT_FILE = 'ip.txt'
CACHE_FILE = 'ip_country_cache.json'   # 可选缓存文件（非数据库）
USE_CACHE = True                       # True: 使用并保存缓存；False: 每次都现场查询
REQUEST_DELAY = 0.5                    # 每次 ipinfo 请求后的间隔（秒），默认 0.5s，避免限速
REQUEST_TIMEOUT = 10                   # 请求超时（秒）
MAX_RETRIES = 3                        # 请求失败重试次数
# 常见国家 ISO -> 中文 映射（可按需扩展）
COUNTRY_MAP = {
    'US': '美国','CA':'加拿大','GB':'英国','DE':'德国','FR':'法国','SG':'新加坡',
    'JP':'日本','KR':'韩国','CN':'中国','NL':'荷兰','AU':'澳大利亚','RU':'俄罗斯',
    'IN':'印度','BR':'巴西','ZA':'南非','HK':'香港','TW':'台湾','SE':'瑞典',
    'CH':'瑞士','IT':'意大利','ES':'西班牙','BE':'比利时','PL':'波兰','NO':'挪威',
    'DK':'丹麦','FI':'芬兰','IE':'爱尔兰','PT':'葡萄牙','GR':'希腊','TR':'土耳其',
    'MX':'墨西哥','AR':'阿根廷','CL':'智利','CO':'哥伦比亚','ID':'印度尼西亚',
    'MY':'马来西亚','TH':'泰国','VN':'越南','PH':'菲律宾','IL':'以色列','AE':'阿联酋'
}
# 常用 User-Agent 列表（用于抓取页面以降低被屏蔽概率）
UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"
]
# --------------------------------

def numeric_sort_key(ip):
    return [int(p) for p in ip.split('.')]

def fetch_page_text(url):
    """抓取页面，支持多 UA、简单重试，并对 429 做指数退避"""
    session = requests.Session()
    for ua in UAS:
        headers = {'User-Agent': ua}
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    return r.text
                if r.status_code == 429:
                    wait = 2 ** attempt
                    print(f"请求 {url} 返回 429，等待 {wait}s 后重试（第{attempt}次）")
                    time.sleep(wait)
                    continue
                if r.status_code == 403:
                    # 换 UA 再试
                    print(f"请求 {url} 返回 403，尝试更换 User-Agent")
                    break
                print(f"请求 {url} 返回状态 {r.status_code}")
                break
            except requests.RequestException as e:
                print(f"请求 {url} 失败（尝试 {attempt}）：{e}")
                time.sleep(1 + attempt)
    return None

def ipinfo_country(ip):
    """使用 ipinfo.io 公开接口查询国家（无 token），返回中文名或 None"""
    url = f"https://ipinfo.io/{ip}/json"
    headers = {'User-Agent': UAS[0]}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                j = r.json()
                iso = j.get('country')
                if not iso:
                    return None
                iso = iso.upper()
                return COUNTRY_MAP.get(iso, iso)  # 返回中文名或 ISO 作为回退
            # 非 200 时：如果 429，退避；否则返回 None
            if r.status_code == 429:
                wait = 2 ** attempt
                print(f"ipinfo 对 {ip} 限速 429，等待 {wait}s 再试")
                time.sleep(wait)
                continue
            return None
        except requests.RequestException as e:
            print(f"查询 ipinfo {ip} 失败（尝试 {attempt}）：{e}")
            time.sleep(1 + attempt)
    return None

def load_cache():
    if not USE_CACHE:
        return {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    if not USE_CACHE:
        return
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存缓存失败：", e)

def main():
    # 1) 抓取 IP
    ips = set()
    for url in URLS:
        txt = fetch_page_text(url)
        if not txt:
            print(f"抓取 {url} 返回空或失败")
            continue
        found = re.findall(IP_PATTERN, txt)
        if found:
            ips.update(found)

    if not ips:
        print("未抓到任何 IP，退出。")
        return

    unique_ips = sorted(ips, key=numeric_sort_key)
    print(f"抓到 {len(unique_ips)} 个去重 IP，排序后共 {len(unique_ips)} 个。")

    # 2) 缓存加载
    cache = load_cache()
    country_count = {}
    results = []

    for ip in unique_ips:
        country = None
        if USE_CACHE and ip in cache:
            country = cache[ip]
        else:
            country = ipinfo_country(ip)
            # 即便是 None 也写入缓存以减少重复请求
            if USE_CACHE:
                cache[ip] = country
            # 请求间隔
            time.sleep(REQUEST_DELAY)

        if country:
            country_count[country] = country_count.get(country, 0) + 1
            idx = f"{country_count[country]:03d}"
            out = f"{ip}#{country}{idx}"
            results.append(out)
            print(f"{ip} => {country}{idx}")
        else:
            results.append(ip)
            print(f"{ip} => (无国家信息)")

    # 3) 保存缓存与输出
    save_cache(cache)
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(results))
        print(f"共保存 {len(results)} 条到 {OUTPUT_FILE}")
    except Exception as e:
        print("写入输出文件失败：", e)

if __name__ == '__main__':
    main()
