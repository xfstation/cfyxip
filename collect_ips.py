import requests
from bs4 import BeautifulSoup
import re
import os
import ssl
from requests.adapters import HTTPAdapter

class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

urls = [
    'https://monitor.gacjie.cn/page/cloudflare/ipv4.html',
    'https://ip.164746.xyz'
]
ip_pattern = r'\d{1,3}(?:\.\d{1,3}){3}'

session = requests.Session()
session.mount('https://', TLSAdapter())

# Step 1: 获取所有 IP（去重）
all_ips = set()
for url in urls:
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[错误] 请求失败 {url}：{e}")
        continue

    soup = BeautifulSoup(r.text, 'html.parser')
    elements = soup.find_all('tr') if url in urls else soup.find_all('li')

    for elem in elements:
        all_ips.update(re.findall(ip_pattern, elem.get_text()))

all_ips = list(all_ips)
print(f"共抓取到 {len(all_ips)} 个唯一 IP")

# Step 2: 批量查询归属地（ip-api.com 每次最多 100 个）
country_counters = {}
output = []

for i in range(0, len(all_ips), 100):
    batch = all_ips[i:i+100]
    try:
        resp = requests.post(
            "http://ip-api.com/batch?fields=query,country",
            json=batch,
            timeout=10
        ).json()
    except Exception as e:
        print(f"[错误] 批量查询失败：{e}")
        continue

    for item in resp:
        ip = item.get("query")
        country = item.get("country", "未知")
        country_counters[country] = country_counters.get(country, 0) + 1
        seq = country_counters[country]
        output.append(f"{ip}#{country}{seq:03d}")

# Step 3: 写入文件
if os.path.exists('ip.txt'):
    os.remove('ip.txt')
with open('ip.txt', 'w') as f:
    f.write("\n".join(output))

print("✅ 保存完毕，每个国家的 IP 都从 001 开始排序")
