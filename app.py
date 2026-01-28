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
