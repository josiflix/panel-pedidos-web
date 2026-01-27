#!/usr/bin/env python3
import cloudscraper
import json
import os
import pickle
import base64
from datetime import datetime

CONFIG = {
    'opticalh': {
        'api_key': 'JQ2WS8YAC8GIPJHHW3WYRFD47QKCWLSY',
        'url': 'https://www.opticalh.com/administracion',
        'prefix': ''
    },
    'gafascanarias': {
        'api_key': '5XGV9YW2234IC2MXT2UEN421UFBEMHB9',
        'url': 'https://gafascanarias.com/administracion',
        'prefix': 'GC-'
    }
}

class OrderTracker:
    def __init__(self):
        self.last_ids = self.load_last_ids()
        self.scraper = cloudscraper.create_scraper()
    
    def load_last_ids(self):
        if os.path.exists('last_order_ids.pkl'):
            with open('last_order_ids.pkl', 'rb') as f:
                return pickle.load(f)
        return {'opticalh': 0, 'gafascanarias': 0}
    
    def save_last_ids(self):
        with open('last_order_ids.pkl', 'wb') as f:
            pickle.dump(self.last_ids, f)

    def get_country_name(self, store, address_id):
        try:
            config = CONFIG[store]
            auth = base64.b64encode(f"{config['api_key']}:".encode()).decode()
            headers = {'Authorization': f'Basic {auth}'}
            
            r_addr = self.scraper.get(f"{config['url']}/api/addresses/{address_id}?output_format=JSON", headers=headers, timeout=10)
            if r_addr.status_code != 200:
                return "Desconocido"
            
            id_country = r_addr.json().get('address', {}).get('id_country')
            if not id_country:
                return "Desconocido"

            r_country = self.scraper.get(f"{config['url']}/api/countries/{id_country}?output_format=JSON", headers=headers, timeout=10)
            if r_country.status_code != 200:
                return "Desconocido"
            
            name_data = r_country.json().get('country', {}).get('name')
            if isinstance(name_data, list):
                for item in name_data:
                    if item.get('id') == '1':
                        return item.get('value')
                return name_data[0].get('value') if name_data else "Internacional"
            return name_data if isinstance(name_data, str) else "Internacional"
        except:
            return "Error"
    
    def get_orders(self, store, limit=20):
        config = CONFIG[store]
        api_url = f"{config['url']}/api/orders"
        credentials = f"{config['api_key']}:"
        auth = base64.b64encode(credentials.encode()).decode()
        headers = {'Authorization': f'Basic {auth}'}
        params = {'output_format': 'JSON', 'display': 'full', 'sort': '[id_DESC]', 'limit': limit}
        
        try:
            response = self.scraper.get(api_url, headers=headers, params=params, timeout=30)
            data = response.json()
            if 'orders' in data:
                return data['orders'] if isinstance(data['orders'], list) else [data['orders']]
        except:
            pass
        return []
    
    def check_new_orders(self):
        new_orders = []
        for store in ['opticalh', 'gafascanarias']:
            orders = self.get_orders(store)
            last_id = self.last_ids.get(store, 0)
            
            for order in orders:
                order_id = int(order.get('id', 0))
                if order_id > last_id:
                    config = CONFIG[store]
                    
                    total_original = float(order.get('total_paid_real', 0))
                    conversion_rate = float(order.get('conversion_rate', 1))
                    total_eur = round(total_original / conversion_rate, 2) if conversion_rate > 0 else total_original
                    
                    country = self.get_country_name(store, order.get('id_address_delivery'))
                    
                    new_orders.append({
                        'id': f"{config['prefix']}{order_id}",
                        'store': store,
                        'total': total_eur,
                        'country': country,
                        'date': order.get('date_add', '')
                    })
            
            if orders:
                latest = max(int(o.get('id', 0)) for o in orders)
                if latest > last_id:
                    self.last_ids[store] = latest
                    self.save_last_ids()
        return new_orders

if __name__ == '__main__':
    tracker = OrderTracker()
    orders = tracker.check_new_orders()
    if orders:
        with open('new_orders.json', 'w') as f:
            json.dump(orders, f, indent=2)
