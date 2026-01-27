import os
import json
import base64
import cloudscraper
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template_string, jsonify
import sys
import pickle

app = Flask(__name__)

# --- CONFIGURACIÓN ---
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

HTML = """
<!DOCTYPE html>
<html lang='es'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>Panel Cloud</title>
    <style>
        body{font-family:-apple-system,system-ui,sans-serif;background:#111827;color:white;padding:20px;max-width:600px;margin:0 auto}
        .card{background:#1F2937;padding:24px;border-radius:16px;text-align:center}
        .btn{background:#3B82F6;color:white;border:none;padding:16px;width:100%;border-radius:12px;font-size:18px;font-weight:bold;cursor:pointer;margin:20px 0}
        .btn:disabled{opacity:0.5}
        .logs{background:black;color:#10B981;padding:15px;border-radius:8px;font-family:monospace;font-size:12px;text-align:left;height:300px;overflow-y:auto;border:1px solid #374151}
        .error{color:#EF4444}
        .stat-box{display:grid;grid-template-columns:1fr 1fr;gap:10px}
        .stat{background:#374151;padding:10px;border-radius:8px}
    </style>
</head>
<body>
    <div class='card'>
        <h1>☁️ Panel Pedidos</h1>
        <div class="stat-box">
            <div class="stat">OPT: <span id="opt">--</span></div>
            <div class="stat">GC: <span id="gc">--</span></div>
        </div>
        <button class='btn' id="btn" onclick='run()'>🔄 EJECUTAR SINCRONIZACIÓN</button>
        <div class='logs' id="logs">Listo...</div>
    </div>
    <script>
        async function run(){
            const btn = document.getElementById('btn');
            const logs = document.getElementById('logs');
            btn.disabled = true;
            btn.innerText = "⏳ Conectando...";
            logs.innerHTML = "🚀 Iniciando camuflaje...\n";
            
            try {
                const res = await fetch('/api/run', {method:'POST'});
                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                while(true) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    const text = decoder.decode(value);
                    const lines = text.split('\\n');
                    lines.forEach(l => { if(l) logs.innerHTML += `<div>${l}</div>`; });
                    logs.scrollTop = logs.scrollHeight;
                }
                btn.innerText = "✅ FIN";
            } catch(e) {
                logs.innerHTML += `<div class='error'>❌ Error JS: ${e}</div>`;
            }
            setTimeout(() => { btn.disabled = false; btn.innerText = "🔄 EJECUTAR SINCRONIZACIÓN"; }, 3000);
        }
        
        fetch('/api/stats').then(r=>r.json()).then(d=>{
            document.getElementById('opt').innerText = d.opticalh;
            document.getElementById('gc').innerText = d.gafascanarias;
        });
    </script>
</body>
</html>
"""

STATE_FILE = '/tmp/last_ids.pkl'

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'rb') as f: return pickle.load(f)
    return {'opticalh': 38227, 'gafascanarias': 100}

def save_state(data):
    with open(STATE_FILE, 'wb') as f: pickle.dump(data, f)

class OrderSystem:
    def __init__(self):
        # CAMUFLAJE: Imitamos un navegador de escritorio real
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        self.last_ids = load_state()
        self.sheet = None
        self.existing_ids = []

    def log(self, msg): return f"{msg}\n"

    def connect_google(self):
        try:
            json_creds = os.environ.get('GOOGLE_JSON')
            if not json_creds:
                if os.path.exists('google_credentials.json'):
                    with open('google_credentials.json') as f:
                        creds_dict = json.load(f)
                        yield self.log("💻 Local detectado")
                else:
                    yield self.log("<span class='error'>❌ ERROR: Falta GOOGLE_JSON</span>")
                    return False
            else:
                creds_dict = json.loads(json_creds)
                yield self.log("☁️ Nube detectada")

            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            self.sheet = client.open_by_key('1BlQQjahxpJO208gR5Z3PSX9YErwXRauxdfbAQuI8QUw').sheet1
            
            # Leemos IDs existentes para evitar duplicados
            self.existing_ids = list(filter(None, self.sheet.col_values(1)))
            yield self.log(f"✅ Google OK ({len(self.existing_ids)} pedidos)")
            return True
        except Exception as e:
            yield self.log(f"<span class='error'>❌ Google Error: {e}</span>")
            return False

    def get_country(self, url, headers):
        try:
            r = self.scraper.get(url, headers=headers)
            if r.status_code != 200: return "Desconocido"
            
            data = r.json()
            # Si es dirección
            if 'address' in data:
                cid = data['address']['id_country']
                # Llamada recursiva para el país
                return self.get_country(url.replace(f"addresses/{data['address']['id']}", f"countries/{cid}"), headers)
            
            # Si es país
            if 'country' in data:
                name = data['country']['name']
                if isinstance(name, list): return name[0]['value']
                return name
                
            return "Inter."
        except: return "Inter."

    def process(self):
        conn = self.connect_google()
        for msg in conn: 
            yield msg
            if "❌" in msg: return

        count = 0
        for store in ['opticalh', 'gafascanarias']:
            yield self.log(f"🔍 {store}...")
            cfg = CONFIG[store]
            
            # URL con Key incrustada (ws_key)
            url = f"{cfg['url']}/api/orders?ws_key={cfg['api_key']}&output_format=JSON&display=full&sort=[id_DESC]&limit=10"
            
            try:
                r = self.scraper.get(url)
                
                if r.status_code != 200:
                    yield self.log(f"<span class='error'>⚠️ Bloqueo {r.status_code} (Cloudflare?)</span>")
                    continue

                try:
                    orders = r.json().get('orders', [])
                except:
                    yield self.log(f"<span class='error'>⚠️ Recibido HTML en vez de JSON (Bloqueo)</span>")
                    continue

                if isinstance(orders, dict): orders = [orders]
                orders.sort(key=lambda x: int(x['id']))
                
                for o in orders:
                    oid = int(o['id'])
                    fid = f"{cfg['prefix']}{oid}"
                    
                    if fid in self.existing_ids:
                        if oid > self.last_ids.get(store, 0): self.last_ids[store] = oid
                        continue
                    
                    # PROCESAR
                    total = float(o['total_paid_real'])
                    rate = float(o.get('conversion_rate', 1))
                    eur = round(total / rate, 2) if rate > 0 else total
                    
                    # País (necesita auth header para sub-llamadas)
                    auth = base64.b64encode(f"{cfg['api_key']}:".encode()).decode()
                    head = {'Authorization': f'Basic {auth}'}
                    addr_url = f"{cfg['url']}/api/addresses/{o['id_address_delivery']}?output_format=JSON"
                    country = self.get_country(addr_url, head)
                    
                    # INSERCIÓN INTELIGENTE
                    row = len(self.existing_ids) + 1
                    self.sheet.update(range_name=f"A{row}:C{row}", values=[[fid, country, eur]])
                    self.existing_ids.append(fid)
                    
                    yield self.log(f"✅ <b>{fid}</b> | {country} | {eur}€")
                    
                    if oid > self.last_ids.get(store, 0): self.last_ids[store] = oid
                    count += 1
                        
            except Exception as e:
                yield self.log(f"<span class='error'>❌ Error {store}: {e}</span>")
        
        save_state(self.last_ids)
        if count == 0: yield self.log("ℹ️ Todo actualizado.")
        else: yield self.log(f"🎉 Subidos {count} pedidos.")

@app.route('/')
def index(): return render_template_string(HTML)

@app.route('/api/run', methods=['POST'])
def run_api():
    sys = OrderSystem()
    return app.response_class(sys.process(), mimetype='text/plain')

@app.route('/api/stats')
def stats_api(): return jsonify(load_state())

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
