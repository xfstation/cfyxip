#!/usr/bin/env python3
# collect_ips.py — 针对 GitHub Actions 的修正版
import os, sys, subprocess, requests, ipaddress, json, time

# ----------------- 配置 -----------------
DB_PATH = "./GeoLite2-Country.mmdb"
DOWNLOAD_URL = "https://git.io/GeoLite2-Country.mmdb"  # community shortlink; 若失效请手动放置 mmdb
CF_IPV4 = "https://www.cloudflare.com/ips-v4"
OUTPUT_FILE = "ip.txt"
CACHE_FILE = "ip_country_cache.json"
SAMPLES_PER_CIDR = 1   # 每个 CIDR 取多少个代表 IP（>=1），默认1
# 简短中文映射（常用）
CN_MAP = {
    'US':'美国','CA':'加拿大','GB':'英国','DE':'德国','FR':'法国','SG':'新加坡',
    'JP':'日本','KR':'韩国','CN':'中国','NL':'荷兰','SE':'瑞典','CH':'瑞士',
    'AU':'澳大利亚','RU':'俄罗斯','IN':'印度','BR':'巴西','ZA':'南非','HK':'香港','TW':'台湾'
}
# ----------------------------------------

# 自动安装依赖 geoip2, pycountry（若未安装）
def ensure_pkgs():
    need = []
    try:
        import geoip2.database  # noqa: F401
    except Exception:
        need.append("geoip2")
    try:
        import pycountry  # noqa: F401
    except Exception:
        need.append("pycountry")
    if need:
        print("Installing packages:", need)
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + need)

ensure_pkgs()
import geoip2.database
import pycountry

# 尝试下载 GeoLite2 数据库（若已有则跳过）
def ensure_db():
    if os.path.exists(DB_PATH):
        return True
    try:
        print("尝试自动下载 GeoLite2 数据库…")
        r = requests.get(DOWNLOAD_URL, timeout=30)
        r.raise_for_status()
        with open(DB_PATH, "wb") as f:
            f.write(r.content)
        print("数据库已下载到", DB_PATH)
        return True
    except Exception as e:
        print("自动下载 GeoLite2 失败：", e)
        return False

db_ok = ensure_db()
reader = None
if db_ok:
    try:
        reader = geoip2.database.Reader(DB_PATH)
    except Exception as e:
        print("打开 GeoLite2 数据库失败：", e)
        reader = None
else:
    print("没有可用的 GeoLite2 数据库，后续会尝试使用 ipinfo 回退（需设置 IPINFO_TOKEN）")

# 载入缓存（减少重复解析）
cache = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as cf:
            cache = json.load(cf)
    except Exception:
        cache = {}

def country_name_from_iso(iso):
    if not iso:
        return None
    name = CN_MAP.get(iso)
    if name:
        return name
    try:
        pc = pycountry.countries.get(alpha_2=iso)
        if pc:
            return pc.name
    except Exception:
        pass
    return iso

def lookup_by_db(ip):
    if not reader:
        return None
    try:
        resp = reader.country(ip)
        iso = resp.country.iso_code
        return country_name_from_iso(iso)
    except Exception:
        return None

def lookup_by_ipinfo(ip):
    token = os.environ.get("IPINFO_TOKEN")
    if not token:
        return None
    try:
        r = requests.get(f"https://ipinfo.io/{ip}?token={token}", timeout=6)
        r.raise_for_status()
        data = r.json()
        code = data.get("country")
        return country_name_from_iso(code)
    except Exception:
        return None

# 获取 Cloudflare IPv4 列表（CIDR）
try:
    r = requests.get(CF_IPV4, timeout=15)
    r.raise_for_status()
    lines = [ln.strip() for ln in r.text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
except Exception as e:
    print("获取 Cloudflare 列表失败：", e)
    lines = []

if not lines:
    print("没有抓到任何 CIDR，退出。")
    sys.exit(0)

results = []
country_count = {}

for cidr in lines:
    # 把 CIDR 解析为一个或多个代表 IP
    rep_ips = []
    try:
        net = ipaddress.ip_network(cidr, strict=False)
        # 取前 SAMPLES_PER_CIDR 个可用主机
        host_iter = net.hosts()
        for _ in range(max(1, SAMPLES_PER_CIDR)):
            try:
                rep_ips.append(str(next(host_iter)))
            except StopIteration:
                break
        # 如果没有 hosts（/32 或不可用），退回网络地址
        if not rep_ips:
            rep_ips = [str(net.network_address)]
    except Exception:
        # 解析失败就把原始字符串当作IP（不太可能）
        rep_ips = [cidr]

    # 对每个代表IP分别查并输出（如果你只想每个 CIDR 一条记录，SAMPLES_PER_CIDR=1）
    for rep_ip in rep_ips:
        country = None
        if rep_ip in cache:
            country = cache.get(rep_ip)
        else:
            # 先用本地 DB
            country = lookup_by_db(rep_ip)
            # 若无结果，尝试 ipinfo 回退（需 env IPINFO_TOKEN）
            if not country:
                country = lookup_by_ipinfo(rep_ip)
            cache[rep_ip] = country
            # 少量睡眠避免外部API速率问题（ipinfo）
            time.sleep(0.12)

        if country:
            country_count[country] = country_count.get(country, 0) + 1
            num = f"{country_count[country]:03d}"
            out = f"{rep_ip}#{country}{num}"
            results.append(out)
            print(f"{rep_ip} => {country}{num}")
        else:
            results.append(rep_ip)
            print(f"{rep_ip} => (无国家信息)")

# 保存缓存
try:
    with open(CACHE_FILE, "w", encoding="utf-8") as cf:
        json.dump(cache, cf, ensure_ascii=False, indent=2)
except Exception:
    pass

# 写入输出文件
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(results))

if reader:
    reader.close()

print(f"共保存 {len(results)} 条到 {OUTPUT_FILE}")
