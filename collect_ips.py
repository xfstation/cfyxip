import os
import sys
import subprocess
import requests
from bs4 import BeautifulSoup

# 自动安装 geoip2
try:
    import geoip2.database
except ImportError:
    print("缺少 geoip2 库，正在安装...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "geoip2"])
    import geoip2.database

# 下载 GeoLite2 数据库
DB_PATH = "./GeoLite2-Country.mmdb"
if not os.path.exists(DB_PATH):
    print("正在下载 GeoLite2-Country 数据库...")
    url = "https://git.io/GeoLite2-Country.mmdb"
    r = requests.get(url)
    with open(DB_PATH, "wb") as f:
        f.write(r.content)

reader = geoip2.database.Reader(DB_PATH)

def get_country(ip):
    """根据IP获取国家名，获取不到就返回空字符串"""
    try:
        response = reader.country(ip)
        country_name = response.country.names.get('zh-CN', '') or response.country.name or ''
        return country_name
    except:
        return ""

def collect_ips():
    url = "https://www.cloudflare.com/ips-v4"
    res = requests.get(url)
    soup = BeautifulSoup(res.text, "html.parser")
    ip_list = res.text.strip().split("\n")

    results = []
    count = 1
    for ip in ip_list:
        country = get_country(ip)
        if country:
            results.append(f"{ip}#{country}{count:03d}")
        else:
            results.append(f"{ip}")
        print(f"IP: {ip} => {country}{count:03d}" if country else f"IP: {ip}")
        count += 1

    # 保存
    with open("ip.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(results))

    print(f"共保存 {len(results)} 个IP 到 ip.txt")

if __name__ == "__main__":
    collect_ips()
