#!/usr/bin/env python3
# collect_ips.py
# 功能：从指定网站抓取 IPv4，去重排序，优先用 GeoLite2 本地库解析国家，回退到 ipinfo.io（无 token），
# 输出 ip.txt，每行为 IP 或 IP#国家NNN（每国从001开始），并使用本地缓存减少查询。

import re
import os
import sys
import time
import json
import requests
import ipaddress

# 尝试导入 geoip2 / pycountry（如果 Actions workflow 已预装则会成功）
try:
    import geoip2.database
except Exception:
    geoip2 = None
else:
    geoip2 = True

try:
    import pycountry
except Exception:
    pycountry = None

# ---------------- CONFIG ----------------
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
GEO_DOWNLOAD_SHORTLINK = 'https://git.io/GeoLite2-Country.mmdb'  # 社区短链（若失效可手动放 mmdb 到仓库）
IPINFO_SLEEP = 0.18  # 回退 ipinfo 请求间隔，避免速率问题
# ----------------------------------------

# 常见国家代码->中文名映射（覆盖常见/云节点国家）
COUNTRY_MAP = {
    'US': '美国', 'CA': '加拿大', 'GB': '英国', 'DE': '德国', 'FR': '法国',
    'SG': '新加坡', 'JP': '日本', 'KR': '韩国', 'CN': '中国', 'NL': '荷兰',
    'SE': '瑞典', 'CH': '瑞士', 'AU': '澳大利亚', 'RU': '俄罗斯', 'IN': '印度',
    'BR': '巴西', 'ZA': '南非', 'HK': '香港', 'TW': '台湾', 'BE': '比利时',
    'IT': '意大利', 'ES': '西班牙', 'PL': '波兰', 'AT': '奥地利', 'NO': '挪威',
    'DK': '丹麦', 'FI': '芬兰', 'IE': '爱尔兰', 'CZ': '捷克', 'TR': '土耳其',
    'MX': '墨西哥', 'CO': '哥伦比亚', 'AR': '阿根廷', 'IL': '以色列', 'AE': '阿联酋',
    'SA': '沙特阿拉伯', 'VN': '越南', 'TH': '泰国', 'MY': '马来西亚', 'ID': '印度尼西亚',
    'PH': '菲律宾', 'PT': '葡萄牙', 'GR': '希腊', 'HU': '匈牙利', 'RO': '罗马尼亚',
    'BG': '保加利亚', 'SI': '斯洛文尼亚', 'SK': '斯洛伐克', 'HR': '克罗地亚', 'EE': '爱沙尼亚',
    'LV': '拉脱维亚', 'LT': '立陶宛', 'LU': '卢森堡', 'IS': '冰岛', 'NZ': '新西兰',
    'CL': '智利', 'PE': '秘鲁', 'UY': '乌拉圭', 'CR': '哥斯达黎加', 'DO': '多米尼加',
    'PA': '巴拿马', 'PR': '波多黎各', 'NG': '尼日利亚', 'KE': '肯尼亚', 'EG': '埃及',
    'CI': '科特迪瓦', 'NG': '尼日利亚', 'TZ': '坦桑尼亚', 'PK': '巴基斯坦'
    # 若需要更多可手动扩展
}

# ---------- helpers ----------
def numeric_sort_key(ip):
    return [int(p) for p in ip.split('.')]

def ensure_geolite_db():
    """确保 GeoLite2 数据库存在。如果不存在尝试下载到 GEO_DB_PATH。返回 True/False"""
    if os.path.exists(GEO_DB_PATH):
        return True
    try:
        print("尝试自动下载 GeoLite2 数据库到", GEO_DB_PATH, "（若下载失败请手动放置 mmdb）")
        r = requests.get(GEO_DOWNLOAD_SHORTLINK, timeout=30)
        r.raise_for_status()
        with open(GEO_DB_PATH, 'wb') as f:
            f.write(r.content)
        print("GeoLite2 数据库下载完成。")
        return True
    except Exception as e:
        print("自动下载 GeoLite2 失败：", e)
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
        print("保存缓存失败：", e)

def map_iso_to_chinese(iso):
    if not iso:
        return None
    iso = iso.upper()
    if iso in COUNTRY_MAP:
        return COUNTRY_MAP[iso]
    # 回退使用 pycountry（英文）
    if pycountry:
        try:
            pc = pycountry.countries.get(alpha_2=iso)
            if pc:
                return pc.name  # 英文名作为回退
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
    # 无 token 公开接口
    try:
        r = requests.get(f'https://ipinfo.io/{ip}/json', timeout=6)
        if r.status_code != 200:
            return None
        j = r.json()
        iso = j.get('country')
        return map_iso_to_chinese(iso)
    except Exception:
        return None

# ---------- main ----------
def main():
    # 1) 抓取原始 IP（从页面）
    ips = set()
    for url in URLS:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200 and r.text:
                found = re.findall(IP_PATTERN, r.text)
                if found:
                    ips.update(found)
                else:
                    # 有些站点可能列出 CIDR 行（如 Cloudflare 官方），也尝试抓取 "x.x.x.x/yy"
                    # 但在本脚本我们只要 ipv4 host 格式。
                    pass
            else:
                print(f'抓取 {url} 返回状态 {r.status_code}')
        except Exception as e:
            print(f'抓取 {url} 失败: {e}')

    if not ips:
        print("未抓到任何 IP，退出。")
        return

    # 2) 去重并按数值排序
    unique_ips = sorted(ips, key=numeric_sort_key)
    print(f"抓到 {len(unique_ips)} 个去重 IP（未排序前），排序后共 {len(unique_ips)} 个。")

    # 3) 尝试加载 GeoLite2（如果可用）
    reader = None
    if geoip2:
        if ensure_geolite_db():
            try:
                reader = geoip2.database.Reader(GEO_DB_PATH)
                print("已打开 GeoLite2 本地数据库进行离线解析。")
            except Exception as e:
                print("打开 GeoLite2 数据库失败：", e)
                reader = None
        else:
            print("没有可用的 GeoLite2 数据库，后续将使用 ipinfo 回退（无 token）。")
    else:
        print("geoip2 模块不可用，后续将直接使用 ipinfo 回退（无 token）。")

    # 4) 加载缓存（ip->country_name_or_null）
    cache = load_cache()

    country_count = {}
    results = []

    for ip in unique_ips:
        country = None
        if ip in cache:
            country = cache[ip]
        else:
            # 优先本地 DB
            if reader:
                country = geoip_lookup(reader, ip)
            # 回退 ipinfo
            if not country:
                country = ipinfo_lookup(ip)
                # ipinfo 可能很慢或限速，适当睡眠
                time.sleep(IPINFO_SLEEP)
            # 保存进缓存（即便是 None）
            cache[ip] = country

        if country:
            # 为该国家编号（按中文名/回退名计数）
            country_count[country] = country_count.get(country, 0) + 1
            num = f"{country_count[country]:03d}"
            out = f"{ip}#{country}{num}"
            results.append(out)
            print(f"{ip} => {country}{num}")
        else:
            results.append(ip)
            print(f"{ip} => (无国家信息)")

    # 5) 写回缓存 & 输出文件
    save_cache(cache)
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(results))
        print(f"共保存 {len(results)} 条到 {OUTPUT_FILE}")
    except Exception as e:
        print("写入输出文件失败：", e)

    if reader:
        try:
            reader.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
