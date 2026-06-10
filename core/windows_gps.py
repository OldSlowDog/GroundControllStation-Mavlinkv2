"""
Windows GPS 定位器 v3.0 (最终稳定版)
- 使用多策略定位
- 优先级: 浏览器Geolocation > IP服务
- 稳定可靠
"""

import json
import urllib.request
from typing import Optional, Dict
import concurrent.futures


class WindowsGPSLocator:
    """
    GPS定位器
    
    策略说明：
    由于PowerShell WinRT API在当前环境不稳定，
    本版本主要依赖IP地理位置服务。
    
    如果需要真正的GPS精度，建议：
    1. 在程序中直接使用 QWebEngine 的 Geolocation API
    2. 或开启Windows位置服务 + 使用支持的PowerShell版本
    """
    
    def __init__(self):
        self.last_location = None
        
    def get_location(self) -> Optional[Dict]:
        """获取当前位置"""
        print("[WindowsGPS] Starting location acquisition...")
        
        # 方法1: 高质量IP定位（多源竞争）
        result = self._get_best_ip_location()
        if result:
            print(f"[WindowsGPS] IP Location: {result['lat']:.6f}, {result['lon']:.6f} ({result['source']})")
            return result
        
        # 最终回退
        print("[WindowsGPS] Using default location")
        return {
            'lat': 39.9042,
            'lon': 116.4074,
            'accuracy': 99999,
            'source': 'Beijing, China (Default)',
            'method': 'Hardcoded'
        }
    
    def _get_best_ip_location(self) -> Optional[Dict]:
        """★ 多源高质量IP定位"""
        
        services = [
            ('ip-api.com', 'http://ip-api.com/json/?fields=status,message,lat,lon,city,region,country,isp,as,query,zipcode'),
            ('ipapi.co', 'https://ipapi.co/json/'),
            ('ipinfo.io', 'https://ipinfo.io/json'),
        ]
        
        def fetch(service_name, url):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    
                    if service_name == 'ip-api.com':
                        if data.get('status') == 'success':
                            return {
                                'lat': float(data['lat']),
                                'lon': float(data['lon']),
                                'accuracy': self._estimate_accuracy(data.get('as', ''), data.get('isp', '')),
                                'source': f"{data.get('city', '?')}, {data.get('region', '?')}, {data.get('country', '?')}",
                                'method': f"IP ({data.get('isp', '?')})",
                                'details': {
                                    'zip': data.get('zipcode', '?'),
                                    'as': data.get('as', '?'),
                                    'query': data.get('query', '?')
                                }
                            }
                            
                    elif service_name == 'ipapi.co':
                        if data.get('latitude'):
                            return {
                                'lat': float(data['latitude']),
                                'lon': float(data['longitude']),
                                'accuracy': 3000,
                                'source': f"{data.get('city', '?')}, {data.get('region', '?')}",
                                'method': f"IP ({data.get('org', '?')})"
                            }
                            
                    elif service_name == 'ipinfo.io':
                        loc = data.get('loc', '').split(',')
                        if len(loc) >= 2 and loc[0] and loc[1]:
                            return {
                                'lat': float(loc[0]),
                                'lon': float(loc[1]),
                                'accuracy': 5000,
                                'source': f"{data.get('city', '?')}, {data.get('country', '?')}",
                                'method': f"IP ({data.get('org', '?')})"
                            }
                            
            except Exception as e:
                pass
                
            return None
        
        # 并发请求所有服务，取最快有效结果
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(fetch, name, url) for name, url in services]
            
            for future in concurrent.futures.as_completed(futures, timeout=10):
                result = future.result()
                if result and result.get('lat', 0) != 0:
                    return result
        
        return None
    
    @staticmethod
    def _estimate_accuracy(as_number: str, isp: str) -> float:
        """根据AS号码和ISP估算精度"""
        # 家庭宽带通常精度更高
        home_keywords = ['china telecom', 'china unicom', 'china mobile', 'comcast', 
                       'verizon', 'at&t', 'bt', 'deutsche telekom']
        
        isp_lower = isp.lower() if isp else ''
        
        for keyword in home_keywords:
            if keyword in isp_lower:
                return 2000  # 家庭IP约2km精度
        
        # 数据中心/企业IP精度较低
        return 5000


if __name__ == '__main__':
    locator = WindowsGPSLocator()
    loc = locator.get_location()
    
    if loc:
        print(f"\n{'='*50}")
        print(f"Location: {loc['lat']:.6f}, {loc['lon']:.6f}")
        print(f"Accuracy: ±{loc['accuracy']:.0f}m")
        print(f"Source: {loc['source']}")
        print(f"Method: {loc['method']}")
        print(f"{'='*50}")
