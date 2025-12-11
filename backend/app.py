from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import re
import json
from datetime import datetime
from models import Database, User, Rule, Command, AuditLog
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize database
db = Database()

def require_auth(f):
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        user = User.get_by_api_key(api_key)
        if not user:
            return jsonify({'error': 'Invalid API key'}), 401
        
        request.current_user = user
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def require_admin(f):
    def decorated_function(*args, **kwargs):
        if request.current_user['role'] != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/auth/verify', methods=['GET'])
@require_auth
def verify_auth():
    return jsonify({
        'user': {
            'id': request.current_user['id'],
            'name': request.current_user['name'],
            'role': request.current_user['role'],
            'credits': request.current_user['credits']
        }
    })

@app.route('/api/commands', methods=['POST'])
@require_auth
def submit_command():
    data = request.get_json()
    if not data or 'command' not in data:
        return jsonify({'error': 'Command text required'}), 400
    
    try:
        result = Command.submit(request.current_user['id'], data['command'])
        
        # Emit real-time update to all connected clients
        socketio.emit('command_executed', {
            'user_name': request.current_user['name'],
            'command': data['command'],
            'status': result['status'],
            'timestamp': datetime.now().isoformat(),
            'credits_used': 1 if result['status'] == 'EXECUTED' else 0
        }, room='admin_room')
        
        # Emit credit update to user
        socketio.emit('credit_update', {
            'credits': result.get('credits_remaining', request.current_user['credits'])
        }, room=f"user_{request.current_user['id']}")
        
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/commands', methods=['GET'])
@require_auth
def get_commands():
    commands = Command.get_user_commands(request.current_user['id'])
    return jsonify(commands)

@app.route('/api/users', methods=['POST'])
@require_auth
@require_admin
def create_user():
    data = request.get_json()
    if not data or 'name' not in data or 'role' not in data:
        return jsonify({'error': 'Name and role required'}), 400
    
    if data['role'] not in ['admin', 'member']:
        return jsonify({'error': 'Invalid role'}), 400
    
    credits = data.get('credits', Config.DEFAULT_CREDITS)
    
    try:
        user = User.create(data['name'], data['role'], credits)
        AuditLog.log(request.current_user['id'], 'USER_CREATED_BY_ADMIN', f'Created user {user["name"]}')
        return jsonify(user)
    except Exception as e:
        return jsonify({'error': 'Failed to create user'}), 500

@app.route('/api/users/<int:user_id>/credits', methods=['PUT'])
@require_auth
@require_admin
def update_user_credits(user_id):
    data = request.get_json()
    if not data or 'credits' not in data:
        return jsonify({'error': 'Credits amount required'}), 400
    
    try:
        User.update_credits(user_id, data['credits'])
        AuditLog.log(request.current_user['id'], 'CREDITS_UPDATED', f'Updated user {user_id} credits to {data["credits"]}')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': 'Failed to update credits'}), 500

@app.route('/api/rules', methods=['GET'])
@require_auth
@require_admin
def get_rules():
    rules = Rule.get_all_ordered()
    return jsonify(rules)

@app.route('/api/rules/validate', methods=['POST'])
@require_auth
@require_admin
def validate_rule_pattern():
    data = request.get_json()
    if not data or 'pattern' not in data:
        return jsonify({'error': 'Pattern required'}), 400
    
    validation_result = Rule.validate_regex_pattern(data['pattern'])
    return jsonify(validation_result)

@app.route('/api/rules/check-conflicts', methods=['POST'])
@require_auth
@require_admin
def check_rule_conflicts():
    data = request.get_json()
    if not data or 'pattern' not in data or 'action' not in data:
        return jsonify({'error': 'Pattern and action required'}), 400
    
    conflict_result = Rule.detect_rule_conflicts(data['pattern'], data['action'])
    return jsonify(conflict_result)

@app.route('/api/rules', methods=['POST'])
@require_auth
@require_admin
def create_rule():
    data = request.get_json()
    if not data or 'pattern' not in data or 'action' not in data:
        return jsonify({'error': 'Pattern and action required'}), 400
    
    if data['action'] not in ['AUTO_ACCEPT', 'AUTO_REJECT']:
        return jsonify({'error': 'Invalid action'}), 400
    
    try:
        result = Rule.create(data['pattern'], data['action'], request.current_user['id'])
        
        # Handle both old and new return formats
        if isinstance(result, dict):
            rule_id = result['id']
            conflicts = result['conflicts']
            
            response_data = {
                'id': rule_id,
                'success': True,
                'conflicts': conflicts
            }
            
            # If there are high-severity conflicts, include warning
            if conflicts['has_conflicts']:
                high_severity = [c for c in conflicts['conflicts'] if c['severity'] == 'HIGH']
                if high_severity:
                    response_data['warning'] = f"Rule created with {len(high_severity)} high-severity conflicts"
            
            return jsonify(response_data)
        else:
            # Old format compatibility
            return jsonify({'id': result, 'success': True})
            
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Failed to create rule'}), 500

@app.route('/api/audit-logs', methods=['GET'])
@require_auth
@require_admin
def get_audit_logs():
    logs = AuditLog.get_logs()
    return jsonify(logs)

@app.route('/api/pending-approvals', methods=['GET'])
@require_auth
@require_admin
def get_pending_approvals():
    commands = Command.get_pending_approvals()
    return jsonify(commands)

@app.route('/api/commands/<int:command_id>/approve', methods=['POST'])
@require_auth
@require_admin
def approve_command(command_id):
    data = request.get_json()
    if not data or 'approved' not in data:
        return jsonify({'error': 'Approval decision required'}), 400
    
    approved = data['approved']
    reason = data.get('reason', '')
    
    try:
        result = Command.approve_command(command_id, request.current_user['id'], approved, reason)
        
        if 'error' in result:
            return jsonify(result), 400
        
        # Emit real-time update for approval
        socketio.emit('approval_update', {
            'command_id': command_id,
            'status': result['status'],
            'admin_name': request.current_user['name'],
            'approved': approved,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        }, room='admin_room')
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': 'Failed to process approval'}), 500

@app.route('/api/analytics', methods=['GET'])
@require_auth
@require_admin
def get_analytics():
    conn = Database().get_connection()
    cursor = conn.cursor()
    
    # Get command statistics
    cursor.execute('''
        SELECT 
            COUNT(*) as total_commands,
            SUM(CASE WHEN status = 'EXECUTED' THEN 1 ELSE 0 END) as executed_commands,
            SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) as rejected_commands,
            SUM(credits_deducted) as total_credits_used
        FROM commands
        WHERE DATE(created_at) = DATE('now')
    ''')
    daily_stats = cursor.fetchone()
    
    # Get top commands
    cursor.execute('''
        SELECT command_text, COUNT(*) as count, status
        FROM commands 
        WHERE DATE(created_at) = DATE('now')
        GROUP BY command_text, status
        ORDER BY count DESC
        LIMIT 10
    ''')
    top_commands = cursor.fetchall()
    
    # Get user activity
    cursor.execute('''
        SELECT u.name, COUNT(c.id) as command_count
        FROM users u
        LEFT JOIN commands c ON u.id = c.user_id AND DATE(c.created_at) = DATE('now')
        GROUP BY u.id, u.name
        ORDER BY command_count DESC
    ''')
    user_activity = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'daily_stats': dict(daily_stats) if daily_stats else {},
        'top_commands': [dict(cmd) for cmd in top_commands],
        'user_activity': [dict(user) for user in user_activity]
    })

# WebSocket events
@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Client disconnected: {request.sid}')

@socketio.on('join_admin_room')
def handle_join_admin_room(data):
    api_key = data.get('api_key')
    if api_key:
        user = User.get_by_api_key(api_key)
        if user and user['role'] == 'admin':
            join_room('admin_room')
            emit('joined_admin_room', {'status': 'success'})

@socketio.on('join_user_room')
def handle_join_user_room(data):
    api_key = data.get('api_key')
    if api_key:
        user = User.get_by_api_key(api_key)
        if user:
            join_room(f"user_{user['id']}")
            emit('joined_user_room', {'status': 'success'})

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)