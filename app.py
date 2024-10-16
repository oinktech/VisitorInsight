from flask import Flask, request, jsonify, make_response,render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
import csv
import logging

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///visits.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 设置日志
logging.basicConfig(filename='error.log', level=logging.ERROR)

# 语言翻译字典
translations = {
    'en': {
        'visit_logged': 'Visit logged',
        'ip_address_required': 'IP address required',
        'ip_blacklisted': 'IP {ip} has been blacklisted',
        'visits': 'Visits',
        'visit_details': 'Visit details',
        'total_visits': 'Total visits',
        'unique_visitors': 'Unique visitors',
        'download_visits': 'Download visits',
        'message': 'An internal error occurred'
    },
    'zh-Hant': {
        'visit_logged': '訪問已記錄',
        'ip_address_required': '需要IP地址',
        'ip_blacklisted': 'IP {ip}已被列入黑名單',
        'visits': '訪問',
        'visit_details': '訪問詳細信息',
        'total_visits': '總訪問次數',
        'unique_visitors': '獨立訪客',
        'download_visits': '下載訪問記錄',
        'message': '發生內部錯誤'
    }
}

class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(15), nullable=False)
    location = db.Column(db.String(100), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def as_dict(self):
        return {
            'id': self.id,
            'ip_address': self.ip_address,
            'location': self.location,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

class Blacklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(15), nullable=False, unique=True)

@app.before_first_request
def create_tables():
    db.create_all()

API_KEY = "YOUR_SECRET_API_KEY"
@app.route('/')
def home():
    return render_template('index.html')
@app.before_request
def check_api_key():
    if request.endpoint in ['log_visit', 'get_visits', 'get_visit_details', 'get_stats']:
        api_key = request.headers.get('x-api-key')
        if api_key != API_KEY:
            return jsonify({'message': 'Unauthorized'}), 401

def get_language():
    """获取请求中的语言设置，默认使用英文"""
    lang = request.path.split('/')[2]  # 从URL获取语言
    return translations.get(lang, translations['en'])

@app.route('/api/<lang>/visit', methods=['GET'])
def log_visit(lang):
    messages = get_language()
    
    ip_address = request.remote_addr
    if ip_address == '127.0.0.1':
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)

    include_location = request.args.get('include_location', 'true').lower() == 'true'
    location = None

    if include_location:
        try:
            response = requests.get(f'https://ipinfo.io/{ip_address}/json?token=YOUR_TOKEN')
            location_data = response.json()
            location = location_data.get('city', 'Unknown') + ', ' + location_data.get('region', 'Unknown')
        except Exception:
            location = 'Unknown'

    new_visit = Visit(ip_address=ip_address, location=location)
    db.session.add(new_visit)
    db.session.commit()
    
    return jsonify({'message': messages['visit_logged'], 'ip': ip_address, 'location': location}), 200

@app.route('/api/<lang>/visits', methods=['GET'])
def get_visits(lang):
    messages = get_language()
    visits = Visit.query.all()
    return jsonify({messages['visits']: [visit.as_dict() for visit in visits]}), 200

@app.route('/api/<lang>/visits/<ip>', methods=['GET'])
def get_visit_details(lang, ip):
    messages = get_language()
    visits = Visit.query.filter_by(ip_address=ip).all()
    return jsonify({messages['visit_details']: [visit.as_dict() for visit in visits]}), 200

@app.route('/api/<lang>/stats', methods=['GET'])
def get_stats(lang):
    messages = get_language()
    total_visits = Visit.query.count()
    unique_visitors = Visit.query.distinct(Visit.ip_address).count()
    return jsonify({
        messages['total_visits']: total_visits,
        messages['unique_visitors']: unique_visitors
    }), 200

@app.route('/api/<lang>/blacklist', methods=['POST'])
def add_to_blacklist(lang):
    messages = get_language()
    ip_address = request.json.get('ip_address')
    if not ip_address:
        return jsonify({'message': messages['ip_address_required']}), 400

    blacklisted_ip = Blacklist(ip_address=ip_address)
    db.session.add(blacklisted_ip)
    db.session.commit()
    return jsonify({'message': messages['ip_blacklisted'].format(ip=ip_address)}), 201

@app.route('/api/<lang>/blacklist', methods=['GET'])
def get_blacklist(lang):
    messages = get_language()
    blacklisted_ips = Blacklist.query.all()
    return jsonify([ip.ip_address for ip in blacklisted_ips]), 200

@app.route('/api/<lang>/report', methods=['GET'])
def get_report(lang):
    messages = get_language()
    visits = db.session.query(Visit.ip_address, db.func.count(Visit.id)).group_by(Visit.ip_address).all()
    report_data = {ip: count for ip, count in visits}
    return jsonify(report_data), 200

@app.route('/api/<lang>/download_visits', methods=['GET'])
def download_visits(lang):
    messages = get_language()
    visits = Visit.query.all()
    
    output = make_response()
    writer = csv.writer(output)
    writer.writerow(['ID', 'IP Address', 'Location', 'Timestamp'])
    for visit in visits:
        writer.writerow([visit.id, visit.ip_address, visit.location, visit.timestamp.strftime('%Y-%m-%d %H:%M:%S')])
    
    output.headers["Content-Disposition"] = "attachment; filename=visits.csv"
    output.headers["Content-Type"] = "text/csv"
    
    return output

@app.errorhandler(Exception)
def handle_exception(e):
    logging.error(f"An error occurred: {e}")
    lang = request.path.split('/')[2]
    messages = translations.get(lang, translations['en'])
    return jsonify({'message': messages['message']}), 500

if __name__ == '__main__':
    app.run(debug=True,host='0.0.0.0',port=10000)
