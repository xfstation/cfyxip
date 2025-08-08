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

# 正则表达式用于匹配IP地址
ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'

# 删除旧文件
if os.path.exists('ip.txt'):
    os.remove('ip.txt')

# 使用集合存储IP地址实现自动去重
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

# 国家统计字典
country_count = {}
annotated_ips = []

# 对IP地址排序
sorted_ips = sorted(unique_ips, key=lambda ip: [int(part) for part in ip.split('.')])

for ip in sorted_ips:
    try:
        # 查询 IP 所属国家（使用免费API，速度有限，必要时加延迟）
        geo_res = requests.get(f'http://ip-api.com/json/{ip}?lang=zh-CN', timeout=5)
        geo_data = geo_res.json()
        
        country = geo_data.get('country', '未知')
        if not country:
            country = '未知'
    except Exception as e:
        country = '未知'

    # 更新国家编号计数器
    if country not in country_count:
        country_count[country] = 1
    else:
        country_count[country] += 1

    # 格式化编号（3位数）
    number = f'{country_count[country]:03d}'
    annotated_ips.append(f'{ip}#{country}{number}')

    # 可选：防止API请求过快被限制（免费接口限制频率）
    time.sleep(0.5)

# 写入文件
if annotated_ips:
    with open('ip.txt', 'w', encoding='utf-8') as file:
        for line in annotated_ips:
            file.write(line + '\n')
    print(f'已保存 {len(annotated_ips)} 个注释IP到 ip.txt 文件。')
else:
    print('未找到有效的IP地址。')
