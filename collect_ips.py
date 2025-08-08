#!/usr/bin/env python3
# collect_with_geolite.py
import requests
import re
import os
import time
import ipaddress
import json

try:
    import geoip2.database
except Exception as e:
    print("缺少 geoip2 库，请先运行: pip install geoip2")
    raise

try:
    import pycountry
except Exception:
    print("缺少 pycountry 库，请先运行: pip install pycountry")
    raise

# ----------------- 配置 -----------------
GEO_DB_PATH = 'GeoLite2-Country.mmdb'   # 放好 GeoLite2-Country.mmdb 的路径
USE_CLOUDFLARE_CIDRS = False            # True: 使用 Cloudflare 官方 CIDR 列表；False: 爬你提供的页面获取IP
OUTPUT_FILE = 'ip.txt'
CACHE_FILE = 'ip_country_cache.json'   # 可选缓存，减少重复解析
# 爬取页面（当 USE_CLOUDFLARE_CIDRS=False 时使用）
URLS = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz',
    'https://stock.hostmonit.com/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html'
]
# Cloudflare 官方 CIDR 列表地址（若选择USE_CLOUDFLARE_CIDRS=True）
CF_IPV4 = 'https://www.cloudflare.com/ips-v4'
CF_IPV6 = 'https://www.cloudflare.com/ips-v6'
# ----------------------------------------

if not os.path.exists(GEO_DB_PATH):
    print(f'找不到 GeoIP 数据库文件: {GEO_DB_PATH}')
    print('请先从 MaxMind 下载 GeoLite2-Country.mmdb 并放到该路径。参考: https://dev.maxmind.com/geoip/geolite2-free-geolocation-data')
    raise SystemExit(1)

# 小型中文映射表（常见国家）
CN_MAP = {
    'US': '美国', 'CA': '加拿大', 'GB': '英国', 'DE': '德国', 'FR': '法国',
    'SG': '新加坡', 'JP': '日本', 'KR': '韩国', 'CN': '中国', 'NL': '荷兰',
    'SE': '瑞典', 'CH': '瑞士', 'AU': '澳大利亚', 'RU': '俄罗斯', 'IN': '印度',
    'BR': '巴西', 'ZA': '南非', 'HK': '香港', 'TW': '台湾'
}

ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'

def fetch_ips_from_pages(urls):
    ips = set()
    for url in urls:
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                found = re.findall(ip_pattern, r.text)
                ips.update(found)
            else:
                print(f'抓取 {url} 返回 {r.status_code}')
        except Exception as e:
            print(f'抓取 {url} 失败: {e}')
    return ips

def fetch_ips_from_cloudflare_cidrs():
    # 从 Cloudflare 官方 CIDR 列表获取每个网段的第一个可用IP（排除网络号）
    ips = set()
    try:
        r = requests.get(CF_IPV4, timeout=8)
        r.raise_for_status()
        lines = [ln.strip() for ln in r.text.splitlines() if ln.strip() and not ln.startswith('#')]
        for cidr in lines:
            try:
                net = ipaddress.ip_network(cidr, strict=False)
                # 选取第一个可用主机地址（如果网段很小要注意）
                if net.num_addresses >= 4:
                    ip = str(next(net.hosts()))
                else:
                    # 对于小网段，取网络地址+1（host）
                    ip = str(list(net.hosts())[0]) if list(net.hosts()) else str(net.network_address)
                ips.add(ip)
            except Exception as e:
                continue
    except Exception as e:
        print('获取 Cloudflare IPv4 列表失败:', e)

    # IPv6 忽略（如果需要可以类似处理）
    return ips

# 载入缓存（可选）
cache = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as cf:
            cache = json.load(cf)
    except Exception:
        cache = {}

# 获取初始 IP 列表
if USE_CLOUDFLARE_CIDRS:
    print('使用 Cloudflare 官方 CIDR 列表生成代表 IP...')
    raw_ips = fetch_ips_from_cloudflare_cidrs()
else:
    print('从页面抓取 IP 列表...')
    raw_ips = fetch_ips_from_pages(URLS)

if not raw_ips:
    print('未抓到任何 IP，退出。')
    raise SystemExit(0)

# 去重，排序
unique_ips = sorted(set(raw_ips), key=lambda ip: [int(p) for p in ip.split('.')])

# 打开 GeoIP 数据库
reader = geoip2.database.Reader(GEO_DB_PATH)

country_count = {}
results = []

for ip in unique_ips:
    # 先查缓存
    if ip in cache:
        iso = cache[ip]
    else:
        iso = None
        try:
            resp = reader.country(ip)
            iso = resp.country.iso_code  # 例如 'US'
        except geoip2.errors.AddressNotFoundError:
            iso = None
        except Exception as e:
            iso = None
        # 写缓存
        cache[ip] = iso

    if iso:
        # 尝试中文名映射，找不到就用 pycountry 的英文名
        country_name = CN_MAP.get(iso)
        if not country_name:
            try:
                pc = pycountry.countries.get(alpha_2=iso)
                country_name = pc.name if pc else iso
            except Exception:
                country_name = iso

        # 编号
        country_count[country_name] = country_count.get(country_name, 0) + 1
        number = f'{country_count[country_name]:03d}'
        out = f'{ip}#{country_name}{number}'
        results.append(out)
        print(f'IP: {ip} => {country_name}{number}')
    else:
        # 未查到归属：只输出IP（不加 #）
        results.append(ip)
        print(f'IP: {ip} => 未知（仅输出 IP）')

# 写回缓存
try:
    with open(CACHE_FILE, 'w', encoding='utf-8') as cf:
        json.dump(cache, cf, ensure_ascii=False, indent=2)
except Exception as e:
    print('保存缓存失败:', e)

# 写入输出文件
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    for line in results:
        f.write(line + '\n')

reader.close()
print(f'共处理 {len(results)} 条，保存到 {OUTPUT_FILE}')
