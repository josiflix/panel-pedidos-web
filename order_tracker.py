import cloudscraper
import json
import os
import pickle
import base64
from datetime import datetime

CONFIG = {
    'opticalh': {
        'api_key': 'JQ2WS8YAC8GIPJHHW3WYRFD47QKCWLSY',
        'url': 'https://www.opticalh.com',
        'prefix': ''
    },
    'gafascanarias': {
        'api_key': '5XGV9YW2234IC2MXT2UEN421UFBEMHB9',
        'url': 'https://gafascanarias.com',
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
    
    def get_orders(self, store, limit=10):
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
                    new_orders.append({
                        'id': f"{config['prefix']}{order_id}",
                        'store': store,
                        'total': float(order.get('total_paid_real', 0)),
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
            json.dump(orders, f)