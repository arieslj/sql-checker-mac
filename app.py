from flask import Flask, request, jsonify, send_from_directory
app = Flask(__name__, static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = 128 * 1024
app.config['TRUSTED_HOSTS'] = ['127.0.0.1', 'localhost']
@app.after_request
def secure(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
@app.get('/')
def index(): return send_from_directory(app.static_folder, 'index.html')
@app.post('/api/<action>')
def api(action):
    if request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'):
        return jsonify(error='拒绝跨站请求'), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('sql'), str): return jsonify(error='请提交 SQL 文本'), 400
    sql = data['sql']
    if not sql.strip(): return jsonify(error='请先输入 SQL'), 400
    if len(sql) > 50000: return jsonify(error='SQL 超过 50,000 字符，请拆分检查'), 400
    try:
        from checker import analyze, format_sql
        if action == 'check': return jsonify(analyze(sql))
        if action == 'format': return jsonify(sql=format_sql(sql))
        return jsonify(error='未知操作'), 404
    except ValueError as e: return jsonify(error=str(e)), 400
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8765, debug=False)
