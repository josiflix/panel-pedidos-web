import os
import json
import base64
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template_string, jsonify, Response, request
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
        .warning{color:#F59E0B}
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
        <div class='logs' id="logs">Listo para sincronizar...</div>
    </div>
    <script>
        async function run(){
            const btn = document.getElementById('btn');
            const logs = document.getElementById('logs');
            btn.disabled = true;
            btn.innerText = "⏳ Conectando...";
            logs.innerHTML = "🚀 Iniciando sincronización...\\n";
            
            try {
                const res = await fetch('/api/run', {method:'POST'});
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                
                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                
                while(true) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    const text = decoder.decode(value);
                    const lines = text.split('\\n');
                    lines.forEach(l => { 
                        if(l.trim()) logs.innerHTML += `<div>${l}</div>`; 
                    });
                    logs.scrollTop = logs.scrollHeight;
                }
                btn.innerText = "✅ COMPLETADO";
            } catch(e) {
                logs.innerHTML += `<div class='error'>❌ Error: ${e.message}</div>`;
                btn.innerText = "❌ ERROR";
            }
            setTimeout(() => { 
                btn.disabled = false; 
                btn.innerText = "🔄 EJECUTAR SINCRONIZACIÓN"; 
            }, 3000);
        }
        
        fetch('/api/stats')
            .then(r => r.json())
            .then(d => {
                document.getElementById('opt').innerText = d.opticalh || '--';
                document.getElementById('gc').innerText = d.gafascanarias || '--';
            })
            .catch(() => {});
    </script>
</body>
</html>
"""

STATE_FILE = '/tmp/last_ids.pkl'

def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'rb') as f:
                return pickle.load(f)
    except:
        pass
    return {'opticalh': 38227, 'gafascanarias': 100}

def save_state(data):
    try:
        with open(STATE_FILE, 'wb') as f:
            pickle.dump(data, f)
    except:
        pass

def create_session():
    """Crea sesión con reintentos y headers realistas"""
    session = requests.Session()
    
    # Configurar reintentos
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    
    # Headers realistas
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    })
    
    return session

class OrderSystem:
    def __init__(self):
        self.session = create_session()
        self.last_ids = load_state()
        self.sheet = None
        self.existing_ids = []
        self.google_connected = False

    def connect_google(self):
        """Conecta a Google Sheets. Retorna True/False."""
        try:
            json_creds = os.environ.get('GOOGLE_JSON')
            
            if not json_creds:
                if os.path.exists('google_credentials.json'):
                    with open('google_credentials.json') as f:
                        creds_dict = json.load(f)
                    yield "💻 Modo local detectado\n"
                else:
                    yield "<span class='error'>❌ ERROR: Variable GOOGLE_JSON no configurada</span>\n"
                    return
            else:
                creds_dict = json.loads(json_creds)
                yield "☁️ Modo nube detectado\n"

            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            
            self.sheet = client.open_by_key('1BlQQjahxpJO208gR5Z3PSX9YErwXRauxdfbAQuI8QUw').sheet1
            self.existing_ids = [x for x in self.sheet.col_values(1) if x]
            self.google_connected = True
            
            yield f"✅ Google Sheets conectado ({len(self.existing_ids)} pedidos existentes)\n"
            
        except Exception as e:
            yield f"<span class='error'>❌ Error Google Sheets: {e}</span>\n"

    def get_country(self, cfg, address_id):
        """Obtiene el país de una dirección"""
        try:
            auth = base64.b64encode(f"{cfg['api_key']}:".encode()).decode()
            headers = {'Authorization': f'Basic {auth}'}
            
            # Obtener dirección
            addr_url = f"{cfg['url']}/api/addresses/{address_id}?output_format=JSON"
            r = self.session.get(addr_url, headers=headers, timeout=15)
            
            if r.status_code != 200:
                return "Desconocido"
            
            data = r.json()
            if 'address' not in data:
                return "Desconocido"
                
            country_id = data['address'].get('id_country')
            if not country_id:
                return "Desconocido"
            
            # Obtener país
            country_url = f"{cfg['url']}/api/countries/{country_id}?output_format=JSON"
            r = self.session.get(country_url, headers=headers, timeout=15)
            
            if r.status_code != 200:
                return "Internacional"
            
            data = r.json()
            if 'country' not in data:
                return "Internacional"
                
            name = data['country'].get('name', 'Internacional')
            if isinstance(name, list) and len(name) > 0:
                return name[0].get('value', 'Internacional')
            return name if isinstance(name, str) else "Internacional"
            
        except Exception:
            return "Internacional"

    def process_store(self, store):
        """Procesa una tienda y yield los resultados"""
        cfg = CONFIG[store]
        count = 0
        
        yield f"🔍 Consultando {store}...\n"
        
        # Usar autenticación Basic en lugar de ws_key en URL
        auth = base64.b64encode(f"{cfg['api_key']}:".encode()).decode()
        headers = {'Authorization': f'Basic {auth}'}
        
        url = f"{cfg['url']}/api/orders?output_format=JSON&display=full&sort=[id_DESC]&limit=10"
        
        try:
            r = self.session.get(url, headers=headers, timeout=30)
            
            if r.status_code == 401:
                yield f"<span class='error'>❌ {store}: API Key inválida o sin permisos</span>\n"
                return 0
            elif r.status_code == 403:
                yield f"<span class='warning'>⚠️ {store}: Acceso bloqueado (403). Posible bloqueo de IP/Cloudflare</span>\n"
                yield f"<span class='warning'>   → Verifica que la IP de Render esté en whitelist del Webservice</span>\n"
                return 0
            elif r.status_code != 200:
                yield f"<span class='error'>❌ {store}: Error HTTP {r.status_code}</span>\n"
                return 0
            
            # Verificar que es JSON
            content_type = r.headers.get('Content-Type', '')
            if 'application/json' not in content_type and 'text/json' not in content_type:
                if 'text/html' in content_type:
                    yield f"<span class='warning'>⚠️ {store}: Recibido HTML (posible Cloudflare)</span>\n"
                    return 0
            
            try:
                data = r.json()
            except json.JSONDecodeError:
                yield f"<span class='error'>❌ {store}: Respuesta no es JSON válido</span>\n"
                return 0
            
            orders = data.get('orders', [])
            if isinstance(orders, dict):
                orders = [orders]
            
            if not orders:
                yield f"ℹ️ {store}: Sin pedidos nuevos\n"
                return 0
            
            # Ordenar por ID ascendente
            orders.sort(key=lambda x: int(x.get('id', 0)))
            
            for order in orders:
                oid = int(order.get('id', 0))
                fid = f"{cfg['prefix']}{oid}"
                
                # Saltar si ya existe
                if fid in self.existing_ids:
                    if oid > self.last_ids.get(store, 0):
                        self.last_ids[store] = oid
                    continue
                
                # Calcular total en EUR
                total = float(order.get('total_paid_real', 0))
                rate = float(order.get('conversion_rate', 1) or 1)
                eur = round(total / rate, 2) if rate > 0 else total
                
                # Obtener país
                addr_id = order.get('id_address_delivery')
                country = self.get_country(cfg, addr_id) if addr_id else "Desconocido"
                
                # Insertar en Google Sheets
                if self.sheet:
                    row = len(self.existing_ids) + 1
                    self.sheet.update(range_name=f"A{row}:C{row}", values=[[fid, country, eur]])
                    self.existing_ids.append(fid)
                
                yield f"✅ <b>{fid}</b> | {country} | {eur}€\n"
                
                if oid > self.last_ids.get(store, 0):
                    self.last_ids[store] = oid
                count += 1
                
        except requests.Timeout:
            yield f"<span class='error'>❌ {store}: Timeout de conexión</span>\n"
        except requests.ConnectionError:
            yield f"<span class='error'>❌ {store}: Error de conexión</span>\n"
        except Exception as e:
            yield f"<span class='error'>❌ {store}: {str(e)}</span>\n"
        
        return count

    def process(self):
        """Proceso principal de sincronización"""
        # Conectar a Google
        for msg in self.connect_google():
            yield msg
        
        if not self.google_connected:
            yield "<span class='error'>❌ No se pudo conectar a Google Sheets. Abortando.</span>\n"
            return
        
        total_count = 0
        
        # Procesar cada tienda
        for store in ['opticalh', 'gafascanarias']:
            for msg in self.process_store(store):
                yield msg
        
        save_state(self.last_ids)
        
        yield "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        yield f"🏁 Sincronización completada\n"


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/api/run', methods=['POST'])
def run_api():
    def generate():
        system = OrderSystem()
        for msg in system.process():
            yield msg
    
    return Response(generate(), mimetype='text/plain; charset=utf-8')


@app.route('/api/stats')
def stats_api():
    return jsonify(load_state())


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/api/webhook-internal', methods=['POST'])
def webhook_internal():
    """Recibe pedidos desde Mac Mini y procesa"""
    try:
        data = request.json
        store = data.get('store')
        orders = data.get('orders', [])
        
        if not orders:
            return jsonify({"status": "no_orders"}), 200
        
        # Conectar a Google Sheets
        json_creds = os.environ.get('GOOGLE_JSON')
        creds_dict = json.loads(json_creds)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key('1BlQQjahxpJO208gR5Z3PSX9YErwXRauxdfbAQuI8QUw').sheet1
        
        existing_ids = [x for x in sheet.col_values(1) if x]
        prefix = 'GC-' if store == 'gafascanarias' else ''
        count = 0
        
        for order in orders:
            oid = str(order.get('id', ''))
            fid = f"{prefix}{oid}"
            
            if fid in existing_ids:
                continue
            
            total = float(order.get('total_paid_real', 0))
            rate = float(order.get('conversion_rate', 1) or 1)
            eur = round(total / rate, 2) if rate > 0 else total
            
            row = len(existing_ids) + 1
            sheet.update(range_name=f"A{row}:C{row}", values=[[fid, "Procesando", eur]])
            existing_ids.append(fid)
            count += 1
        
        return jsonify({"status": "success", "processed": count}), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
