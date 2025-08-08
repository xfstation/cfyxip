import requests
import re
import os
import time

# 你的 ipinfo.io token
IPINFO_TOKEN = '你的token填这里'

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

# 抓取IP地址
for url in urls:
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            html = response.text
            ip_matches = re.findall(ip_pattern, html)
            unique_ips.update(ip_matches)
    except Exception as e:
        print(f'请求失败: {url} -> {e}')

# 排序
sorted_ips = sorted(unique_ips, key=lambda ip: [int(part) for part in ip.split('.')])

# 国家编号计数器
country_count = {}
annotated_ips = []

# 国家码到中文名映射
country_map = {
    'US': '美国',
    'CA': '加拿大',
    'GB': '英国',
    'DE': '德国',
    'FR': '法国',
    'SG': '新加坡',
    'JP': '日本',
    'KR': '韩国',
    # ... 可继续扩展
}

# 逐个查询国家归属
for ip in sorted_ips:
    try:
        res = requests.get(f'https://ipinfo.io/{ip}?token={IPINFO_TOKEN}', timeout=5)
        data = res.json()
        country_code = data.get('country')
        country = country_map.get(country_code) if country_code else None
    except Exception as e:
        country = None

    if country:
        # 有国家名，编号
        if country not in country_count:
            country_count[country] = 1
        else:
            country_count[country] += 1
        number = f'{country_count[country]:03d}'
        annotated_ips.append(f'{ip}#{country}{number}')
        print(f"{ip} => {country}{number}")
    else:
        # 没国家名，直接输出IP
        annotated_ips.append(ip)
        print(f"{ip} => 无国家信息")

    time.sleep(0.3)  # 防止触发API限速

# 写入文件
with open('ip.txt', 'w', encoding='utf-8') as f:
    for line in annotated_ips:
        f.write(line + '\n')

print(f'共保存 {len(annotated_ips)} 个IP 到 ip.txt')
