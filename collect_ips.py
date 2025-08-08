import requests
from bs4 import BeautifulSoup
import re
import os
import time

# 目标URL列表
urls = [
    'https://ip.164746.xyz', 
    'https://cf.090227.xyz', 
    'https://stock.hostmonit.com/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html'
]

ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'

if os.path.exists('ip.txt'):
    os.remove('ip.txt')

unique_ips = set()

for url in urls:
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            html_content = response.text
            ip_matches = re.findall(ip_pattern, html_content, re.IGNORECASE)
            unique_ips.update(ip_matches)
    except requests.exceptions.RequestException as e:
        print(f'请求 {url} 失败: {e}')
        continue

# 对IP排序
sorted_ips = sorted(unique_ips, key=lambda ip: [int(part) for part in ip.split('.')])

# 国家编号
country_count = {}
annotated_ips = []

for ip in sorted_ips:
    try:
        time.sleep(1.2)  # 防止触发频率限制！
        geo_res = requests.get(f'http://ip-api.com/json/{ip}?lang=zh-CN', timeout=5)
        geo_data = geo_res.json()
        country = geo_data.get('country', '未知')
    except Exception as e:
        country = '未知'

    if not country:
        country = '未知'

    if country not in country_count:
        country_count[country] = 1
    else:
        country_count[country] += 1

    number = f'{country_count[country]:03d}'
    annotated_ips.append(f'{ip}#{country}{number}')
    print(f"IP: {ip} => {country}{number}")  # 调试用

with open('ip.txt', 'w', encoding='utf-8') as f:
    for line in annotated_ips:
        f.write(line + '\n')

print(f'共保存 {len(annotated_ips)} 个IP 到 ip.txt')
