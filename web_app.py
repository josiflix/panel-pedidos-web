from flask import Flask, render_template_string, jsonify
import subprocess
import json
import os
import pickle
import sys

app = Flask(__name__)

HTML = """<!DOCTYPE html>
<html lang='es'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>Panel de Pedidos</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#F9FAFB;padding:20px}
.container{max-width:800px;margin:0 auto}
.header{background:linear-gradient(135deg,#4F46E5,#4338CA);color:white;padding:30px;border-radius:16px;text-align:center;margin-bottom:24px}
.btn-main{background:#4F46E5;color:white;border:none;padding:18px 32px;font-size:16px;border-radius:12px;cursor:pointer;width:100%}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:24px 0}
.stat-card{background:white;padding:20px;border-radius:12px;text-align:center}
.stat-value{font-size:24px;font-weight:700;color:#4F46E5}
</style>
</head>
<body>
<div class='container'>
<div class='header'><h1>🛒 Panel de Pedidos</h1></div>
<button class='btn-main' onclick='runCheck()'>Verificar Pedidos</button>
<div class='stats'>
<div class='stat-card'><p>OpticalH</p><p class='stat-value' id='opt'>--</p></div>
<div class='stat-card'><p>GafasCanarias</p><p class='stat-value' id='gaf'>--</p></div>
<div class='stat-card'><p>Nuevos</p><p class='stat-value' id='new'>0</p></div>
</div>
<div id='result'></div>
</div>
<script>
async function runCheck(){
const res=await fetch('/api/run',{method:'POST'});
const data=await res.json();
document.getElementById('opt').textContent=data.stats.opticalh;
document.getElementById('gaf').textContent='GC-'+data.stats.gafascanarias;
document.getElementById('new').textContent=data.new_orders.length;
if(data.new_orders.length>0){
document.getElementById('result').innerHTML='<p>✅ '+data.new_orders.length+' pedidos nuevos</p>';
}
}
fetch('/api/stats').then(r=>r.json()).then(d=>{
document.getElementById('opt').textContent=d.opticalh||'--';
document.getElementById('gaf').textContent='GC-'+d.gafascanarias;
});
</script>
</body>
</html>"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/run', methods=['POST'])
def run():
    subprocess.run([sys.executable, 'order_tracker.py'])
    orders = []
    if os.path.exists('new_orders.json'):
        with open('new_orders.json') as f:
            orders = json.load(f)
    stats = {'opticalh': 0, 'gafascanarias': 0}
    if os.path.exists('last_order_ids.pkl'):
        with open('last_order_ids.pkl', 'rb') as f:
            stats = pickle.load(f)
    return jsonify({'new_orders': orders, 'stats': stats})

@app.route('/api/stats')
def stats():
    stats = {'opticalh': 0, 'gafascanarias': 0}
    if os.path.exists('last_order_ids.pkl'):
        with open('last_order_ids.pkl', 'rb') as f:
            stats = pickle.load(f)
    return jsonify(stats)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)