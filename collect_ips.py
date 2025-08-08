import requests
from bs4 import BeautifulSoup
import re
import os
import concurrent.futures

# 目标URL列表
urls = [
    'https://ip.164746.xyz', 
    'https://cf.090227.xyz', 
    'https://stock.hostmonit.com/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html'
]

# 正则表达式用于匹配IP地址
ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'

# 删除旧文件
if os.path.exists('ip.txt'):
    os.remove('ip.txt')

# 去重的IP集合
unique_ips = set()

# 抓取IP地址
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

# 国家编号计数器
country_count = {}
result_list = []
lock = None

# 查询 IP 所属国家
def get_country(ip):
    try:
        response = requests.get(f'http://ip-api.com/json/{ip}?lang=zh-CN', timeout=5)
        data = response.json()
        country = data.get('country', '未知')
    except Exception:
        country = '未知'
    return ip, country

# 开始并发处理
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
    future_to_ip = {executor.submit(get_country, ip): ip for ip in sorted_ips}
    
    for future in concurrent.futures.as_completed(future_to_ip):
        ip, country = future.result()
        if country not in country_count:
            country_count[country] = 1
        else:
            country_count[country] += 1
        number = f'{country_count[country]:03d}'
        result_list.append(f'{ip}#{country}{number}')

# 写入结果
if result_list:
    with open('ip.txt', 'w', encoding='utf-8') as f:
        for line in result_list:
            f.write(line + '\n')
    print(f'已保存 {len(result_list)} 个注释IP到 ip.txt 文件。')
else:
    print('未找到有效的IP地址。')
