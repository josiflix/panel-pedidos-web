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

# --- CONFIGURACIÓN TIENDAS ---
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

# --- HTML DEL PANEL ---
HTML = """
<!DOCTYPE html>
<html lang='es'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>Panel Pedidos Cloud</title>
    <style>
        body{font-family:-apple-system,system-ui,sans-serif;background:#f3f4f6;padding:20px;max-width:600px;margin:0 auto}
        .card{background:white;padding:24px;border-radius:16px;box-shadow:0 4px 6px rgba(0,0,0,0.1);text-align:center}
        h1{color:#111827;font-size:24px;margin-bottom:8px}
        .btn{background:#2563EB;color:white;border:none;padding:16px;width:100%;border-radius:12px;font-size:18px;font-weight:600;cursor:pointer;margin:20px 0}
        .btn:disabled{opacity:0.5;cursor:wait}
        .logs{background:#1f2937;color:#10b981;padding:16px;border-radius:12px;font-family:monospace;font-size:12px;text-align:left;height:200px;overflow-y:auto;margin-top:20px}
        .stat-box{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:20px}
        .stat{background:#f9fafb;padding:10px;border-radius:8px;border:1px solid #e5e7eb}
        .val{font-weight:bold;font-size:18px;color:#2563EB}
        .error{color:#EF4444}
    </style>
</head>
<body>
    <div class='card'>
        <h1>☁️ Panel Cloud</h1>
        <p style="color:#6b7280">Sistema integrado OpticalH & GC</p>
        
        <div class="stat-box">
            <div class="stat">OPT: <span class="val" id="opt">--</span></div>
            <div class="stat">GC: <span class="val" id="gc">--</span></div>
        </div>

        <button class='btn' id="btn" onclick='run()'>🔄 Verificar y Volcar</button>
        
        <div class='logs' id="logs">Esperando ejecución...</div>
    </div>
    <script>
        async function run(){
            const btn = document.getElementById('btn');
            const logs = document.getElementById('logs');
            btn.disabled = true;
            btn.innerText = "⏳ Procesando...";
            logs.innerHTML = "🚀 Iniciando proceso...<br>";
            
            try {
                const res = await fetch('/api/run', {method:'POST'});
                const data = await res.json();
                
                data.logs.forEach(line => {
                    logs.innerHTML += line + "<br>";
                });
                
                logs.scrollTop = logs.scrollHeight;
                document.getElementById('opt').innerText = data.stats.opticalh;
                document.getElementById('gc').innerText = data.stats.gafascanarias;
                
                if(data.success){
                    btn.innerText = "✅ Completado";
                } else {
                    btn.innerText = "❌ Error";
                }
            } catch(e) {
                logs.innerHTML += "<span class='error'>❌ Error de conexión: " + e + "</span>";
            }
            
            setTimeout(() => { btn.disabled = false; btn.innerText = "🔄 Verificar y Volcar"; }, 3000);
        }
        
        // Cargar stats al inicio
        fetch('/api/stats').then(r=>r.json()).then(d=>{
            document.getElementById('opt').innerText = d.opticalh;
            document.getElementById('gc').innerText = d.gafascanarias;
        });
    </script>
</body>
</html>
"""

# --- GESTOR DE ESTADO (MEMORIA) ---
STATE_FILE = '/tmp/last_ids.pkl'

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'rb') as f:
            return pickle.load(f)
    return {'opticalh': 38227, 'gafascanarias': 100}

def save_state(data):
    with open(STATE_FILE, 'wb') as f:
        pickle.dump(data, f)

# --- CLASE PRINCIPAL ---
class CloudSystem:
    def __init__(self):
        self.logs = []
        self.scraper = cloudscraper.create_scraper()
        self.last_ids = load_state()
        self.sheet = None
        self.existing_ids = []

    def log(self, msg):
        print(msg) 
        self.logs.append(msg)

    def connect_google(self):
        try:
            # 1. Obtener credenciales (Variable de entorno o archivo local)
            json_creds = os.environ.get('GOOGLE_JSON')
            
            if not json_creds:
                if os.path.exists('google_credentials.json'):
                    with open('google_credentials.json') as f:
                        creds_dict = json.load(f)
                        self.log("💻 Modo Local detectado")
                else:
                    self.log("<span class='error'>❌ ERROR: No se encuentra GOOGLE_JSON</span>")
                    return False
            else:
                creds_dict = json.loads(json_creds)
                self.log("☁️ Modo Nube detectado")

            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            self.sheet = client.open_by_key('1BlQQjahxpJO208gR5Z3PSX9YErwXRauxdfbAQuI8QUw').sheet1
            
            # --- CORRECCIÓN: LEER DATOS EXISTENTES PARA EVITAR DUPLICADOS Y HUECOS ---
            # Leemos toda la columna A. Filtramos celdas vacías.
            self.existing_ids = list(filter(None, self.sheet.col_values(1)))
            
            self.log(f"✅ Conectado a Google Sheets ({len(self.existing_ids)} pedidos existentes)")
            return True
        except Exception as e:
            self.log(f"<span class='error'>❌ Error Google Auth: {str(e)}</span>")
            return False

    def get_country(self, store, address_id):
        try:
            cfg = CONFIG[store]
            auth = base64.b64encode(f"{cfg['api_key']}:".encode()).decode()
            headers = {'Authorization': f'Basic {auth}'}
            
            r = self.scraper.get(f"{cfg['url']}/api/addresses/{address_id}?output_format=JSON", headers=headers)
            if r.status_code != 200: return "Desconocido"
            country_id = r.json().get('address', {}).get('id_country')
            
            r = self.scraper.get(f"{cfg['url']}/api/countries/{country_id}?output_format=JSON", headers=headers)
            name = r.json().get('country', {}).get('name')
            if isinstance(name, list): return name[0]['value']
            return name
        except:
            return "Inter."

    def process(self):
        if not self.connect_google(): return False
        
        count = 0
        for store in ['opticalh', 'gafascanarias']:
            self.log(f"🔍 Verificando {store}...")
            cfg = CONFIG[store]
            
            # Usamos ws_key en URL para evitar bloqueos
            url = f"{cfg['url']}/api/orders?ws_key={cfg['api_key']}&output_format=JSON&display=full&sort=[id_DESC]&limit=10"
            
            try:
                r = self.scraper.get(url)
                
                if r.status_code != 200:
                    self.log(f"⚠️ Error HTTP {r.status_code} en {store}")
                    continue

                orders = r.json().get('orders', [])
                if isinstance(orders, dict): orders = [orders]
                
                # Ordenar antiguos a nuevos
                orders.sort(key=lambda x: int(x['id']))
                
                for o in orders:
                    oid = int(o['id'])
                    formatted_id = f"{cfg['prefix']}{oid}"
                    
                    # 1. VERIFICAR SI YA EXISTE EN EL EXCEL (Para no duplicar)
                    if formatted_id in self.existing_ids:
                        # Si ya existe, actualizamos nuestra memoria local y saltamos
                        if oid > self.last_ids.get(store, 0):
                            self.last_ids[store] = oid
                        continue
                    
                    # 2. PROCESAR PEDIDO NUEVO
                    total = float(o['total_paid_real'])
                    rate = float(o.get('conversion_rate', 1))
                    total_eur = round(total / rate, 2) if rate > 0 else total
                    country = self.get_country(store, o['id_address_delivery'])
                    
                    # 3. INSERCIÓN INTELIGENTE (Sin huecos)
                    # Calculamos la siguiente fila disponible basándonos en los datos reales
                    next_row = len(self.existing_ids) + 1
                    
                    # Escribimos usando rangos específicos (Más seguro que append_row)
                    # Rango: A{fila}:C{fila} -> [ID, PAIS, PRECIO]
                    self.sheet.update(range_name=f"A{next_row}:C{next_row}", values=[[formatted_id, country, total_eur]])
                    
                    # Añadimos a la lista temporal para que el siguiente pedido sepa dónde ir
                    self.existing_ids.append(formatted_id)
                    
                    self.log(f"✅ <b>Volcado:</b> {formatted_id} ({country}) {total_eur}€")
                    
                    if oid > self.last_ids.get(store, 0):
                        self.last_ids[store] = oid
                    count += 1
                        
            except Exception as e:
                self.log(f"<span class='error'>❌ Error procesando {store}: {e}</span>")
        
        save_state(self.last_ids)
        if count == 0: self.log("ℹ️ No hay pedidos nuevos para volcar")
        else: self.log(f"🎉 Procesados {count} pedidos correctamente")
        return True

# --- FLASK ---
@app.route('/')
def index(): return render_template_string(HTML)

@app.route('/api/run', methods=['POST'])
def run_api():
    sys = CloudSystem()
    success = sys.process()
    return jsonify({'logs': sys.logs, 'stats': sys.last_ids, 'success': success})

@app.route('/api/stats')
def stats_api():
    return jsonify(load_state())

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
