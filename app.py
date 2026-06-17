# app.py - Flask server with Authentication, RFID Entry/Exit Tracking & Temperature Prediction
# Enhanced with Firebase Firestore, user authentication, and role-based access control
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import pandas as pd
import joblib
import os
from datetime import datetime, timedelta
import numpy as np
import traceback
import json
from dotenv import load_dotenv
from database.auth_manager import (
    require_login, require_admin, login_user, logout_user,
    is_authenticated, get_current_user
)
from database.firebase_manager import EnhancedFirebaseManager
from database.scheduler_manager import (
    SchedulerManager,
    SensorDataCollector,
    PredictionScheduler
)

# Load environment variables
load_dotenv()

# ================= FLASK CONFIG =================
app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Enable CORS for all routes (required for ESP32 communication)
CORS(app, origins="*", allow_headers=["Content-Type"], methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# Initialize SocketIO for real-time updates
socketio = SocketIO(app, cors_allowed_origins="*")

app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-change-this-in-production-12345')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# ================= REQUEST LOGGING =================
@app.before_request
def log_request():
    """Log incoming requests"""
    print(f"[REQUEST] {request.method} {request.path}")
    if request.method == 'POST' and request.is_json:
        print(f"  Payload: {request.get_json()}")

@app.after_request
def log_response(response):
    """Log outgoing responses"""
    print(f"[RESPONSE] {request.method} {request.path} -> {response.status_code}")
    return response

# ================= MODEL CONFIG =================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "models", "model_BEST_RandomForest_20260326_140710.pkl")
SCALER_PATH = os.path.join(SCRIPT_DIR, "models", "scaler_20260326_140710.pkl")
FEATURES_PATH = os.path.join(SCRIPT_DIR, "models", "features_20260326_140710.pkl")

# ================= DATABASE CONFIG =================
print("[INFO] Initializing Firebase Firestore...")
try:
    firebase_db = EnhancedFirebaseManager(
        credentials_path=os.getenv('FIREBASE_CREDENTIALS', 'firebase-credentials.json')
    )
    print("[INFO] [OK] Firebase initialized successfully")
except Exception as e:
    print(f"[WARNING] Firebase initialization failed: {e}")
    print("[WARNING] Running in demo mode without Firebase storage")
    firebase_db = None

# Initialize scheduler
try:
    scheduler_manager = SchedulerManager()
except Exception as e:
    print(f"[WARNING] Scheduler initialization failed: {e}")
    scheduler_manager = None

# ================= GLOBAL VARIABLES =================
sensor_history = []
server_start_time = datetime.now()
# Initialize with default data so dashboard shows something on first load
last_sensor_data = {
    'status': 'success',
    'temperature': 0.0,
    'humidity': 0.0,
    'pressure': 0.0,
    'movement': 0,
    'prediction': 0.0,
    'confidence': 0.0,
    'occupancy': 0,
    'timestamp': datetime.now().isoformat()
}
predictions_history = []

# ================= FAN CONTROL STATE =================
# Two modes: manual (runtime in minutes) or automatic (temperature threshold + 10min prediction)
fan_control = {
    'mode': 'manual',                    # 'manual' or 'automatic'
    'fan_on': False,                     # Current fan state
    'manual_runtime_minutes': 30,        # Runtime duration for manual mode
    'temperature_threshold': 25.0,       # Threshold for automatic mode activation
    'deactivation_threshold': 20.0,      # Threshold for automatic mode deactivation
    'fan_start_time': None,              # When fan was turned on
    'auto_predict_time': None,           # When to check auto prediction (10min from start)
    'last_updated': datetime.now().isoformat(),
    'updated_by': 'system'
}

# ================= LOAD MODEL =================
try:
    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    features_list = joblib.load(FEATURES_PATH)
    print("[INFO] [OK] Model, scaler, and features loaded successfully!")
    print(f"[INFO] Expected features: {len(features_list)} features")
except Exception as e:
    print(f"[ERROR] Failed to load model: {e}")
    print("[WARNING] Running in demo mode without predictions")
    model = None
    scaler = None
    features_list = None

# ================= FEATURE ENGINEERING =================
def engineer_features(temp, hum, pressure, movement, occupancy):
    """Engineer all required features from sensor inputs"""
    
    feat = {}
    
    # Basic raw features
    feat['temp'] = temp
    feat['hum'] = hum
    feat['pressure'] = pressure
    feat['movement'] = movement
    feat['persons'] = occupancy
    
    # Time features
    now = datetime.now()
    feat['time_sec'] = now.second + now.minute * 60 + now.hour * 3600
    feat['hour_sin'] = np.sin(2 * np.pi * now.hour / 24)
    feat['hour_cos'] = np.cos(2 * np.pi * now.hour / 24)
    feat['minute_sin'] = np.sin(2 * np.pi * now.minute / 60)
    feat['minute_cos'] = np.cos(2 * np.pi * now.minute / 60)
    
    # Handle sensor history
    if len(sensor_history) == 0:
        # Initialize with current values
        feat['temp_lag1'] = feat['temp_lag2'] = feat['temp_lag3'] = temp
        feat['temp_lag5'] = feat['temp_lag10'] = feat['temp_lag15'] = temp
        feat['temp_lag20'] = feat['temp_lag30'] = temp
        
        feat['hum_lag1'] = feat['hum_lag2'] = feat['hum_lag3'] = hum
        feat['hum_lag5'] = hum
        
        for window in [3, 5, 10, 15, 20]:
            feat[f'temp_mean_{window}'] = temp
            feat[f'temp_std_{window}'] = 0
            feat[f'temp_min_{window}'] = temp
            feat[f'temp_max_{window}'] = temp
        
        feat['temp_diff'] = 0
        feat['temp_accel'] = 0
    else:
        # Extract recent values
        recent_temps = [h['temp'] for h in sensor_history[-30:]]
        recent_hums = [h['hum'] for h in sensor_history[-30:]]
        recent_pressures = [h['pressure'] for h in sensor_history]
        
        # Lag features
        feat['temp_lag1'] = recent_temps[-1] if len(recent_temps) > 0 else temp
        feat['temp_lag2'] = recent_temps[-2] if len(recent_temps) > 1 else temp
        feat['temp_lag3'] = recent_temps[-3] if len(recent_temps) > 2 else temp
        feat['temp_lag5'] = recent_temps[-5] if len(recent_temps) > 4 else temp
        feat['temp_lag10'] = recent_temps[-10] if len(recent_temps) > 9 else temp
        feat['temp_lag15'] = recent_temps[-15] if len(recent_temps) > 14 else temp
        feat['temp_lag20'] = recent_temps[-20] if len(recent_temps) > 19 else temp
        feat['temp_lag30'] = recent_temps[-30] if len(recent_temps) > 29 else temp
        
        feat['hum_lag1'] = recent_hums[-1] if len(recent_hums) > 0 else hum
        feat['hum_lag2'] = recent_hums[-2] if len(recent_hums) > 1 else hum
        feat['hum_lag3'] = recent_hums[-3] if len(recent_hums) > 2 else hum
        feat['hum_lag5'] = recent_hums[-5] if len(recent_hums) > 4 else hum
        
        # Rolling statistics
        for window in [3, 5, 10, 15, 20]:
            temps_window = recent_temps[-window:] if len(recent_temps) >= window else recent_temps
            feat[f'temp_mean_{window}'] = np.mean(temps_window)
            feat[f'temp_std_{window}'] = np.std(temps_window)
            feat[f'temp_min_{window}'] = np.min(temps_window)
            feat[f'temp_max_{window}'] = np.max(temps_window)
        
        # Rate of change
        feat['temp_diff'] = temp - feat['temp_lag1']
        feat['temp_accel'] = (temp - feat['temp_lag1']) - (feat['temp_lag1'] - feat['temp_lag2']) if len(recent_temps) > 1 else 0
        
        # Pressure features
        feat['pressure_diff'] = pressure - recent_pressures[-1] if len(recent_pressures) > 0 else 0
        feat['pressure_trend'] = np.mean(np.diff(recent_pressures)) if len(recent_pressures) > 1 else 0
    
    # Interaction features
    feat['temp_hum_product'] = temp * hum
    feat['pressure_temp'] = pressure * temp
    feat['activity_level'] = movement * occupancy
    feat['occupancy_intensity'] = occupancy * (hum / 50.0)
    
    # Time zone features
    feat['is_peak_hours'] = 1.0 if 9 <= now.hour <= 17 else 0.0
    feat['is_night'] = 1.0 if now.hour >= 22 or now.hour < 6 else 0.0
    
    # Ratio features
    feat['hum_temp_ratio'] = hum / (temp + 1) if temp > -1 else 0
    
    # Reorder features to match model expectations
    if features_list:
        feat_ordered = {}
        for feature in features_list:
            feat_ordered[feature] = feat.get(feature, 0)
        return feat_ordered
    
    return feat

# ================= AUTHENTICATION ROUTES =================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login with password or RFID"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            return render_template('login.html', error='Username and password required')
        
        # Authenticate user
        success, user_data = firebase_db.authenticate_user(username, password)
        
        if success:
            login_user(session, username, user_data.get('role'), user_data.get('email'))
            print(f"[AUTH] User logged in: {username} ({user_data.get('role')})")
            return redirect(url_for('dashboard'))
        else:
            error_msg = user_data.get('error', 'Authentication failed')
            print(f"[AUTH] Login failed for {username}: {error_msg}")
            return render_template('login.html', error=error_msg)
    
    # Check if already logged in
    if is_authenticated(session):
        return redirect(url_for('dashboard'))
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """New user registration with email verification"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        role = request.form.get('role', 'user').strip()
        
        # Validation
        if not all([username, email, password, confirm_password, role]):
            return render_template('signup.html', error='All fields required')
        
        if password != confirm_password:
            return render_template('signup.html', error='Passwords do not match')
        
        if len(password) < 6:
            return render_template('signup.html', error='Password must be at least 6 characters')
        
        if len(username) < 3:
            return render_template('signup.html', error='Username must be at least 3 characters')
        
        # Create user
        success, message = firebase_db.create_user(username, password, role, email)
        
        if success:
            print(f"[AUTH] New user created: {username} ({role})")
            return render_template('signup.html', message=f'Account created! A verification email has been sent to <strong>{email}</strong>. Please verify your email to activate your account.')
        else:
            return render_template('signup.html', error=message)
    
    # Check if already logged in
    if is_authenticated(session):
        return redirect(url_for('dashboard'))
    
    return render_template('signup.html')

@app.route('/verify-email', methods=['GET'])
def verify_email():
    """Verify email using token from email link"""
    try:
        token = request.args.get('token', '').strip()
        
        if not token:
            return render_template('base.html', error='Invalid verification link'), 400
        
        # Verify email using token
        success, message = firebase_db.verify_email(token)
        
        if success:
            return render_template('base.html', message=f'✓ {message} You can now login to your account.')
        else:
            return render_template('base.html', error=f'✗ Verification failed: {message}'), 400
            
    except Exception as e:
        print(f"[ERROR] Email verification error: {e}")
        return render_template('base.html', error=f'An error occurred: {str(e)}'), 500

@app.route('/resend-verification', methods=['GET', 'POST'])
def resend_verification():
    """Resend verification email to user"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        
        if not username:
            return render_template('login.html', error='Username required'), 400
        
        success, message = firebase_db.resend_verification_email(username)
        
        if success:
            return render_template('login.html', message=f'✓ {message} Please check your email.')
        else:
            return render_template('login.html', error=f'✗ {message}'), 400
    
    # Check if already logged in
    if is_authenticated(session):
        return redirect(url_for('dashboard'))
    
    return render_template('login.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Request password reset email"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        
        if not username:
            return render_template('forgot_password.html', error='Username required')
        
        success, message = firebase_db.request_password_reset(username)
        
        if success:
            return render_template('forgot_password.html', message=f'✓ {message}')
        else:
            return render_template('forgot_password.html', error=f'✗ {message}')
    
    # Check if already logged in
    if is_authenticated(session):
        return redirect(url_for('dashboard'))
    
    return render_template('forgot_password.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Reset password using reset token"""
    if request.method == 'POST':
        token = request.form.get('token', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        # Validation
        if not all([token, password, confirm_password]):
            return render_template('reset_password.html', token=token, error='All fields required')
        
        if password != confirm_password:
            return render_template('reset_password.html', token=token, error='Passwords do not match')
        
        if len(password) < 6:
            return render_template('reset_password.html', token=token, error='Password must be at least 6 characters')
        
        # Reset password
        success, message = firebase_db.reset_password(token, password)
        
        if success:
            return render_template('reset_password.html', message=f'✓ {message} <a href="/login">Return to login</a>')
        else:
            return render_template('reset_password.html', token=token, error=f'✗ {message}')
    
    # GET request - show reset form with token
    token = request.args.get('token', '').strip()
    if not token:
        return render_template('reset_password.html', error='Invalid password reset link'), 400
    
    # Check if already logged in
    if is_authenticated(session):
        return redirect(url_for('dashboard'))
    
    return render_template('reset_password.html', token=token)

@app.route('/logout')
def logout():
    """User logout"""
    username = session.get('username')
    logout_user(session)
    if username:
        print(f"[AUTH] User logged out: {username}")
    return redirect(url_for('login'))

# ================= MAIN ROUTES =================

@app.route('/')
def index():
    """Root route - redirect to dashboard or login"""
    if is_authenticated(session):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/dashboard')
@require_login
def dashboard():
    """Main dashboard page"""
    try:
        occupancy = firebase_db.get_current_occupancy() if firebase_db else 0
        settings = firebase_db.get_settings() if firebase_db else {}
    except Exception as e:
        print(f"[WARNING] Error loading dashboard data: {e}")
        occupancy = 0
        settings = {}
    
    return render_template('dashboard.html', 
                         occupancy=occupancy or 0,
                         settings=settings or {})

@app.route('/stats')
@require_login
def statistics():
    """User statistics page"""
    try:
        occupancy = firebase_db.get_current_occupancy() if firebase_db else 0
        rfids = firebase_db.list_rfid_devices() if firebase_db else []
        sensors = firebase_db.get_sensor_data_range(minutes=60) if firebase_db else []
        predictions = firebase_db.get_latest_predictions(limit=24) if firebase_db else []
    except Exception as e:
        print(f"[WARNING] Error loading stats: {e}")
        occupancy = 0
        rfids = []
        sensors = []
        predictions = []
    
    return render_template('stats.html',
                         occupancy=occupancy,
                         rfids=rfids or [],
                         sensors=sensors or [],
                         predictions=predictions or [])

@app.route('/init-admin', methods=['GET', 'POST'])
def init_admin():
    """Initialize admin account (disable after first setup for security)"""
    if request.method == 'GET':
        try:
            users = firebase_db.list_users() if firebase_db else []
            admin_exists = any(u.get('role') == 'admin' for u in users)
            return jsonify({
                'status': 'success',
                'admin_exists': admin_exists,
                'message': 'Admin account already exists - no setup needed' if admin_exists else 'Admin account not found - setup required',
                'total_users': len(users)
            })
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            username = data.get('username', 'admin').strip()
            password = data.get('password', 'admin123').strip()
            email = data.get('email', 'admin@system.local').strip()
            
            # Check if admin exists
            users = firebase_db.list_users() if firebase_db else []
            admin_exists = any(u.get('role') == 'admin' for u in users)
            
            if admin_exists:
                return jsonify({'status': 'error', 'message': 'Admin account already exists'}), 400
            
            # Create admin account
            success, message = firebase_db.create_user(username, password, 'admin', email)
            
            if success:
                print(f"[INIT] Admin account created: {username}")
                return jsonify({
                    'status': 'success',
                    'message': f'Admin account created: {username}',
                    'username': username,
                    'password_hint': password[:3] + '***'
                })
            else:
                return jsonify({'status': 'error', 'message': message}), 400
        except Exception as e:
            print(f"[ERROR] Admin initialization failed: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin')
@require_admin
def admin_panel():
    """Admin panel for system configuration"""
    try:
        users = firebase_db.list_users() if firebase_db else []
        rfids = firebase_db.list_rfid_devices() if firebase_db else []
        settings = firebase_db.get_settings() if firebase_db else {}
        attendance = firebase_db.get_attendance_log() if firebase_db else []
    except Exception as e:
        print(f"[WARNING] Error loading admin data: {e}")
        users = []
        rfids = []
        settings = {}
        attendance = []
    
    return render_template('admin.html',
                         users=users or [],
                         rfids=rfids or [],
                         settings=settings or {},
                         attendance=attendance or [])

@app.route('/settings')
@require_admin
def settings_page():
    """System settings page (admin only)"""
    settings = firebase_db.get_settings()
    return render_template('settings.html', settings=settings)

@app.route('/system-info')
@require_login
def system_info():
    """System information page"""
    try:
        settings = firebase_db.get_settings() if firebase_db else {}
    except Exception as e:
        print(f"[WARNING] Error loading settings: {e}")
        settings = {}
    
    return render_template('system_info.html', settings=settings)

@app.route('/predictions-history')
@require_login
def view_predictions_history():
    """Temperature predictions history page"""
    return render_template('predictions_history.html')

# ================= API - AUTHENTICATION =================

@app.route('/api/auth/user', methods=['GET'])
@require_login
def api_get_user():
    """Get current user info"""
    user = get_current_user(session)
    if user:
        return jsonify({'status': 'success', 'user': user})
    return jsonify({'status': 'error', 'message': 'Not authenticated'}), 401

# ================= API - ADMIN MANAGEMENT =================

@app.route('/api/admin/users/list', methods=['GET'])
@require_admin
def api_list_users():
    """List all users"""
    try:
        users = firebase_db.list_users()
        return jsonify({'status': 'success', 'users': users})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/users/create', methods=['POST'])
@require_admin
def api_create_user():
    """Create new user (admin only)"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        email = data.get('email', '').strip()
        role = data.get('role', 'user').strip()
        
        if not all([username, password, email, role]):
            return jsonify({'status': 'error', 'message': 'All fields required'}), 400
        
        success, message = firebase_db.create_user(username, password, role, email)
        
        if success:
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message}), 400
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/users/delete/<username>', methods=['POST'])
@require_admin
def api_delete_user(username):
    """Delete user (admin only)"""
    try:
        success, message = firebase_db.delete_user(username)
        
        if success:
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message}), 400
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/rfid/register', methods=['POST'])
@require_admin
def api_register_rfid():
    """Register new RFID device (admin only)"""
    try:
        data = request.get_json()
        rfid_code = data.get('rfid_code', '').strip()
        person_name = data.get('person_name', '').strip()
        assigned_user = data.get('assigned_user', '').strip() or None
        
        if not rfid_code or not person_name:
            return jsonify({'status': 'error', 'message': 'RFID code and person name required'}), 400
        
        success, message = firebase_db.register_rfid(rfid_code, person_name, assigned_user)
        
        if success:
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message}), 400
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/rfid/list', methods=['GET'])
@require_admin
def api_list_rfids():
    """List all RFID devices (admin only)"""
    try:
        rfids = firebase_db.list_rfid_devices()
        return jsonify({'status': 'success', 'rfids': rfids})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/rfid/remove/<rfid_code>', methods=['POST'])
@require_admin
def api_remove_rfid(rfid_code):
    """Remove RFID device (admin only)"""
    try:
        success, message = firebase_db.remove_rfid(rfid_code)
        
        if success:
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message}), 400
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/settings/update', methods=['POST'])
@require_admin
def api_update_settings():
    """Update system settings (admin only)"""
    try:
        data = request.get_json()
        
        # Validate settings
        fan_runtime = data.get('fan_runtime_minutes', 30)
        temp_threshold = data.get('temp_threshold', 25.0)
        
        if not isinstance(fan_runtime, (int, float)) or fan_runtime <= 0:
            return jsonify({'status': 'error', 'message': 'Invalid fan runtime'}), 400
        
        if not isinstance(temp_threshold, (int, float)) or temp_threshold < 0:
            return jsonify({'status': 'error', 'message': 'Invalid temperature threshold'}), 400
        
        settings_dict = {
            'fan_runtime_minutes': int(fan_runtime),
            'temp_threshold': float(temp_threshold),
            'vent_status': data.get('vent_status', False),
            'updated_by': session.get('username'),
        }
        
        success, message = firebase_db.update_settings(settings_dict)
        
        if success:
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message}), 400
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/settings', methods=['GET'])
@require_login
def api_get_settings():
    """Get current system settings"""
    try:
        settings = firebase_db.get_settings()
        return jsonify({'status': 'success', 'settings': settings})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ================= API - FAN CONTROL =================

@app.route('/api/fan/config', methods=['POST'])
@require_admin
def api_fan_config():
    """Configure fan control mode (manual or automatic)"""
    try:
        data = request.get_json()
        mode = data.get('mode', 'manual').lower()  # 'manual' or 'automatic'
        
        if mode not in ['manual', 'automatic']:
            return jsonify({'status': 'error', 'message': 'Invalid mode. Use: manual or automatic'}), 400
        
        global fan_control
        fan_control['mode'] = mode
        
        if mode == 'manual':
            # Set runtime in minutes
            runtime = data.get('runtime_minutes', 30)
            if not isinstance(runtime, (int, float)) or runtime <= 0 or runtime > 480:
                return jsonify({'status': 'error', 'message': 'Invalid runtime (1-480 minutes)'}), 400
            fan_control['manual_runtime_minutes'] = int(runtime)
            
        else:  # automatic
            # Set temperature threshold
            threshold = data.get('temperature_threshold', 25.0)
            if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 50:
                return jsonify({'status': 'error', 'message': 'Invalid threshold (0-50°C)'}), 400
            fan_control['temperature_threshold'] = float(threshold)
        
        fan_control['last_updated'] = datetime.now().isoformat()
        fan_control['updated_by'] = session.get('username', 'unknown')
        
        print(f"[FAN] Mode set to {mode} by {fan_control['updated_by']}")
        
        return jsonify({
            'status': 'success',
            'message': f'Fan mode changed to {mode}',
            'mode': fan_control['mode'],
            'runtime_minutes': fan_control.get('manual_runtime_minutes'),
            'temperature_threshold': fan_control.get('temperature_threshold')
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/fan/command', methods=['POST'])
@require_admin
def api_fan_command():
    """Turn fan ON or OFF"""
    try:
        data = request.get_json()
        action = data.get('action', '').lower()  # 'on' or 'off'
        
        if action not in ['on', 'off']:
            return jsonify({'status': 'error', 'message': 'Invalid action (on/off)'}), 400
        
        global fan_control
        fan_control['fan_on'] = (action == 'on')
        fan_control['last_updated'] = datetime.now().isoformat()
        fan_control['updated_by'] = session.get('username', 'unknown')
        
        if action == 'on':
            fan_control['fan_start_time'] = datetime.now().isoformat()
            if fan_control['mode'] == 'automatic':
                # Schedule prediction check for 10 minutes from now
                fan_control['auto_predict_time'] = (datetime.now() + timedelta(minutes=10)).isoformat()
                msg = f'Fan turned ON - will predict in 10 minutes'
            else:
                msg = f'Fan turned ON for {fan_control["manual_runtime_minutes"]} minutes'
        else:
            fan_control['fan_start_time'] = None
            fan_control['auto_predict_time'] = None
            msg = 'Fan turned OFF'
        
        print(f"[FAN] {msg}")
        
        return jsonify({
            'status': 'success',
            'message': msg,
            'fan_on': fan_control['fan_on'],
            'mode': fan_control['mode']
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/fan/status', methods=['GET'])
@require_login
def api_fan_status():
    """Get current fan status"""
    try:
        return jsonify({
            'status': 'success',
            'data': {
                'is_on': fan_control['fan_on'],
                'mode': fan_control['mode'],
                'manual_runtime_minutes': fan_control['manual_runtime_minutes'],
                'temperature_threshold': fan_control['temperature_threshold'],
                'last_updated': fan_control['last_updated'],
                'updated_by': fan_control['updated_by']
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/fan/control', methods=['POST'])
@require_admin
def api_fan_control():
    """Control fan manually (ON/OFF/Timer Stop)"""
    try:
        data = request.get_json()
        action = data.get('action', '').lower()
        mode = data.get('mode', 'manual')
        runtime_minutes = data.get('runtime_minutes', 30)
        
        global fan_control
        
        if action == 'manual_on':
            fan_control['fan_on'] = True
            fan_control['mode'] = 'manual'
            fan_control['manual_runtime_minutes'] = runtime_minutes
            fan_control['fan_start_time'] = datetime.now().isoformat()
            msg = f'Fan turned ON for {runtime_minutes} minutes'
        elif action == 'manual_off':
            fan_control['fan_on'] = False
            fan_control['fan_start_time'] = None
            msg = 'Fan turned OFF'
        elif action == 'stop_timer':
            fan_control['fan_start_time'] = None
            msg = 'Timer stopped'
        else:
            return jsonify({'status': 'error', 'message': 'Invalid action'}), 400
        
        fan_control['last_updated'] = datetime.now().isoformat()
        fan_control['updated_by'] = session.get('username', 'admin')
        
        print(f"[FAN] {msg} by {fan_control['updated_by']}")
        
        return jsonify({
            'status': 'success',
            'message': msg,
            'data': {
                'is_on': fan_control['fan_on'],
                'mode': fan_control['mode']
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/fan/settings', methods=['POST'])
@require_admin
def api_fan_settings():
    """Update fan automatic mode settings"""
    try:
        data = request.get_json()
        mode = data.get('mode', 'automatic')
        activation_threshold = data.get('activation_threshold', 25)
        deactivation_threshold = data.get('deactivation_threshold', 20)
        
        if activation_threshold <= deactivation_threshold:
            return jsonify({'status': 'error', 'message': 'Activation threshold must be higher than deactivation threshold'}), 400
        
        global fan_control
        fan_control['mode'] = mode
        fan_control['temperature_threshold'] = activation_threshold
        fan_control['deactivation_threshold'] = deactivation_threshold
        fan_control['last_updated'] = datetime.now().isoformat()
        fan_control['updated_by'] = session.get('username', 'admin')
        
        # Save to Firebase
        if firebase_db:
            settings_dict = {
                'fan_activation_threshold': float(activation_threshold),
                'fan_deactivation_threshold': float(deactivation_threshold),
                'fan_mode': mode,
                'temp_threshold': float(activation_threshold),  # Keep in sync with main threshold
                'updated_by': session.get('username', 'admin')
            }
            success, message = firebase_db.update_settings(settings_dict)
            print(f"[FAN] Firebase update: {success} - {message}")
        
        print(f"[FAN] Automatic settings updated: {activation_threshold}°C (activate) / {deactivation_threshold}°C (deactivate)")
        
        return jsonify({
            'status': 'success',
            'message': 'Automatic settings saved',
            'data': {
                'activation_threshold': activation_threshold,
                'deactivation_threshold': deactivation_threshold
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/users/update/<username>', methods=['POST'])
@require_admin
def api_user_update(username):
    """Update user information"""
    try:
        data = request.get_json()
        
        if not firebase_db:
            return jsonify({'status': 'error', 'message': 'Firebase not initialized'}), 500
        
        update_data = {}
        if 'email' in data:
            update_data['email'] = data['email']
        if 'password' in data and data['password']:
            # In production, hash the password
            update_data['password'] = data['password']
        if 'role' in data:
            update_data['role'] = data['role']
        
        # Update in Firebase
        success, message = firebase_db.update_user(username, update_data)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message
            })
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ================= API - SENSOR DATA & PREDICTIONS =================

@app.route('/api/sensor-data', methods=['POST'])
def api_receive_sensor_data():
    """Receive sensor data from ESP32"""
    try:
        data = request.get_json()
        
        # Extract sensor data
        temp = float(data.get('temp', 0))
        hum = float(data.get('hum', 0))
        pressure = float(data.get('pressure', 0))
        movement = int(data.get('movement', 0))
        
        # Get current occupancy
        occupancy = firebase_db.get_current_occupancy()
        
        # Add to history
        sensor_history.append({
            'temp': temp,
            'hum': hum,
            'pressure': pressure,
            'movement': movement,
            'timestamp': datetime.now()
        })
        
        # Keep only last 100 readings
        if len(sensor_history) > 100:
            sensor_history.pop(0)
        
        # Make prediction
        prediction = temp
        confidence = 0
        
        if model and scaler and features_list:
            try:
                # Engineer features
                features = engineer_features(temp, hum, pressure, movement, occupancy)
                
                # Prepare feature vector with proper column names to avoid sklearn warnings
                X_dict = {f: features.get(f, 0) for f in features_list}
                X_df = pd.DataFrame([X_dict])
                X_scaled = scaler.transform(X_df)
                
                # Convert scaled array back to DataFrame with feature names to avoid model warnings
                X_scaled_df = pd.DataFrame(X_scaled, columns=features_list)
                
                # Get prediction using DataFrame (preserves feature names)
                prediction = float(model.predict(X_scaled_df)[0])
                
                # Get confidence
                if hasattr(model, 'predict_proba'):
                    proba = model.predict_proba(X_scaled_df)[0]
                    confidence = float(np.max(proba) * 100)
                else:
                    confidence = 85.0
            except Exception as e:
                print(f"[ERROR] Prediction error: {e}")
                traceback.print_exc()
        
        # Check automatic fan trigger (if enabled and 10 minutes have passed)
        if fan_control['mode'] == 'automatic' and fan_control['fan_on']:
            if fan_control['auto_predict_time'] and datetime.fromisoformat(fan_control['auto_predict_time']) <= datetime.now():
                threshold = fan_control['temperature_threshold']
                if prediction >= threshold:
                    print(f"[FAN-AUTO] TRIGGER: Prediction {prediction:.2f}°C >= Threshold {threshold}°C")
                    # Prediction triggers the fan, no additional action needed (it's already ON)
                else:
                    print(f"[FAN-AUTO] NO TRIGGER: Prediction {prediction:.2f}°C < Threshold {threshold}°C")
                # Reset the prediction check time
                fan_control['auto_predict_time'] = (datetime.now() + timedelta(minutes=10)).isoformat()
        
        # Store in Firebase
        sensor_data_dict = {
            'temperature': temp,
            'humidity': hum,
            'pressure': pressure,
            'movement': movement,
            'occupancy': occupancy
        }
        firebase_db.store_sensor_data(sensor_data_dict)
        
        # Store prediction
        prediction_dict = {
            'temperature': temp,
            'humidity': hum,
            'pressure': pressure,
            'movement': movement,
            'prediction': prediction,
            'confidence': confidence
        }
        firebase_db.store_prediction(prediction_dict)
        
        # Update history
        predictions_history.append({
            'timestamp': datetime.now(),
            **prediction_dict
        })
        
        # Keep only last 1000
        if len(predictions_history) > 1000:
            predictions_history.pop(0)
        
        # Update last sensor data
        global last_sensor_data
        last_sensor_data = {
            'status': 'success',
            'temperature': temp,
            'humidity': hum,
            'pressure': pressure,
            'movement': movement,
            'prediction': prediction,
            'confidence': confidence,
            'occupancy': occupancy,
            'timestamp': datetime.now().isoformat()
        }
        
        # Emit real-time data to all connected WebSocket clients
        try:
            socketio.emit('sensor_update', last_sensor_data, broadcast=True)
        except Exception as e:
            print(f"[WARNING] WebSocket emit failed: {e}")
        
        return jsonify(last_sensor_data)
        
    except Exception as e:
        print(f"[ERROR] Sensor data error: {str(e)}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 400
# ================= MISSING ENDPOINTS (ESP32 COMPATIBILITY) =================

@app.route('/api/status', methods=['GET'])
def api_status():
    """Check server status (no authentication required for health checks)"""
    try:
        return jsonify({
            'status': 'success',
            'message': 'Server is running',
            'timestamp': datetime.now().isoformat(),
            'uptime': str(datetime.now() - server_start_time)
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/predict', methods=['POST', 'OPTIONS'])
def predict():
    """Handle prediction requests from ESP32 (simplified endpoint)"""
    try:
        data = request.get_json()
        
        # Extract sensor data
        temp = float(data.get('temp', 0))
        hum = float(data.get('hum', 0))
        pressure = float(data.get('pressure', 0))
        movement = int(data.get('movement', 0))
        
        # Get current occupancy (with fallback if Firebase unavailable)
        occupancy = 0
        if firebase_db:
            try:
                occupancy = firebase_db.get_current_occupancy()
            except:
                occupancy = 0
        
        # Add to history
        sensor_history.append({
            'temp': temp,
            'hum': hum,
            'pressure': pressure,
            'movement': movement,
            'timestamp': datetime.now()
        })
        
        # Keep only last 100 readings
        if len(sensor_history) > 100:
            sensor_history.pop(0)
        
        # Make prediction
        prediction = temp
        confidence = 0
        
        if model and scaler and features_list:
            try:
                # Engineer features
                features = engineer_features(temp, hum, pressure, movement, occupancy)
                
                # Prepare feature vector with proper column names to avoid sklearn warnings
                X_dict = {f: features.get(f, 0) for f in features_list}
                X_df = pd.DataFrame([X_dict])
                X_scaled = scaler.transform(X_df)
                
                # Convert scaled array back to DataFrame with feature names to avoid model warnings
                X_scaled_df = pd.DataFrame(X_scaled, columns=features_list)
                
                # Get prediction using DataFrame (preserves feature names)
                prediction = float(model.predict(X_scaled_df)[0])
                
                # Get confidence
                if hasattr(model, 'predict_proba'):
                    proba = model.predict_proba(X_scaled_df)[0]
                    confidence = float(np.max(proba) * 100)
                else:
                    confidence = 85.0
            except Exception as e:
                print(f"[WARNING] Prediction error: {e}")
                traceback.print_exc()
        
        # Store in Firebase (if available)
        if firebase_db:
            try:
                sensor_data_dict = {
                    'temperature': temp,
                    'humidity': hum,
                    'pressure': pressure,
                    'movement': movement,
                    'occupancy': occupancy
                }
                firebase_db.store_sensor_data(sensor_data_dict)
                
                prediction_dict = {
                    'temperature': temp,
                    'humidity': hum,
                    'pressure': pressure,
                    'movement': movement,
                    'prediction': prediction,
                    'confidence': confidence
                }
                firebase_db.store_prediction(prediction_dict)
            except Exception as e:
                print(f"[WARNING] Failed to store data in Firebase: {e}")
        
        # Update history
        predictions_history.append({
            'timestamp': datetime.now(),
            'temperature': temp,
            'humidity': hum,
            'pressure': pressure,
            'movement': movement,
            'prediction': prediction,
            'confidence': confidence
        })
        
        # Keep only last 1000
        if len(predictions_history) > 1000:
            predictions_history.pop(0)
        
        print(f"[PREDICTION] T:{temp}C, H:{hum}%, P:{prediction}C, Conf:{confidence}%")
        
        # Update last_sensor_data global for dashboard
        global last_sensor_data
        last_sensor_data = {
            'status': 'success',
            'temperature': temp,
            'humidity': hum,
            'pressure': pressure,
            'movement': movement,
            'prediction': prediction,
            'confidence': confidence,
            'occupancy': occupancy,
            'timestamp': datetime.now().isoformat()
        }
        
        # Emit real-time data to all connected WebSocket clients
        try:
            socketio.emit('sensor_update', last_sensor_data, broadcast=True)
        except Exception as e:
            print(f"[WARNING] WebSocket emit failed: {e}")
        
        # Determine fan state based on priority logic
        # Priority: Manual control > Automatic control
        actual_fan_state = False
        if fan_control['manual_mode']:
            # Manual mode takes priority
            actual_fan_state = fan_control['manual_state']
        elif fan_control['auto_enabled']:
            # Use automatic control based on temperature threshold
            settings = firebase_db.get_settings() if firebase_db else {}
            temp_threshold = settings.get('temp_threshold', 25.0)
            actual_fan_state = temp > temp_threshold
        
        # Update global fan state
        fan_control['fan_on'] = actual_fan_state
        
        return jsonify({
            'status': 'success',
            'prediction': prediction,
            'confidence': confidence,
            'occupancy': occupancy,
            'fan_on': actual_fan_state,
            'fan_control_mode': 'manual' if fan_control['manual_mode'] else 'automatic' if fan_control['auto_enabled'] else 'off'
        })
        
    except Exception as e:
        print(f"[ERROR] Prediction error: {str(e)}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/api/rfid/verify', methods=['POST', 'OPTIONS'])
def api_rfid_verify():
    """Verify RFID tag (for ESP32 compatibility)"""
    try:
        data = request.get_json()
        rfid_code = data.get('rfid_code', '').upper()
        
        if not rfid_code:
            return jsonify({'status': 'error', 'valid': False, 'message': 'No RFID code provided'}), 400
        
        # Check if RFID exists in database (with fallback if Firebase unavailable)
        rfid_valid = False
        person_name = 'Unknown'
        
        if firebase_db:
            try:
                rfid_info = firebase_db.get_rfid_device(rfid_code)
                if rfid_info:
                    rfid_valid = True
                    person_name = rfid_info.get('person_name', 'Unknown')
            except Exception as e:
                print(f"[WARNING] Could not verify RFID in Firebase: {e}")
        
        print(f"[RFID] Code: {rfid_code}, Valid: {rfid_valid}, Person: {person_name}")
        
        return jsonify({
            'status': 'success',
            'valid': rfid_valid,
            'person_name': person_name,
            'rfid_code': rfid_code
        })
        
    except Exception as e:
        print(f"[ERROR] RFID verification error: {str(e)}")
        return jsonify({'status': 'error', 'valid': False, 'message': str(e)}), 500
@app.route('/api/sensor/latest', methods=['GET'])
@require_login
def api_latest_sensor():
    """Get latest sensor data"""
    try:
        if last_sensor_data and len(last_sensor_data) > 0:
            return jsonify({'status': 'success', 'data': last_sensor_data})
        
        # Return default data if no readings yet
        return jsonify({
            'status': 'success',
            'data': {
                'temperature': 0,
                'humidity': 0,
                'pressure': 0,
                'movement': 0,
                'prediction': 0,
                'confidence': 0,
                'occupancy': 0,
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        print(f"[ERROR] Error fetching latest sensor data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/sensor-data', methods=['GET'])
@require_login
def api_get_sensor_data():
    """Get latest sensor data (alias for /api/sensor/latest for compatibility)"""
    try:
        if last_sensor_data and len(last_sensor_data) > 0:
            return jsonify(last_sensor_data)
        
        # Return default data if no readings yet
        return jsonify({
            'status': 'success',
            'temperature': 0,
            'humidity': 0,
            'pressure': 0,
            'movement': 0,
            'prediction': 0,
            'confidence': 0,
            'occupancy': 0,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"[ERROR] Error fetching sensor data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/predictions/latest', methods=['GET'])
@require_login
def api_latest_predictions():
    """Get latest predictions"""
    try:
        limit = request.args.get('limit', 10, type=int)
        predictions = firebase_db.get_latest_predictions(limit=limit)
        return jsonify({'status': 'success', 'predictions': predictions})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/occupancy', methods=['GET'])
@require_login
def api_get_occupancy():
    """Get current occupancy"""
    try:
        occupancy = firebase_db.get_current_occupancy()
        return jsonify({'status': 'success', 'occupancy': occupancy})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/attendance', methods=['GET'])
@require_admin
def api_get_attendance():
    """Get attendance log (admin only)"""
    try:
        attendance = firebase_db.get_attendance_log()
        return jsonify({'status': 'success', 'attendance': attendance})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/predictions/debug', methods=['GET'])
def api_debug_predictions():
    """Debug endpoint to check Firebase predictions (no auth required for debugging)"""
    try:
        if not firebase_db:
            return jsonify({'status': 'error', 'message': 'Firebase not initialized'}), 500
        
        # Get all predictions
        all_predictions = firebase_db.get_latest_predictions(limit=1000)
        memory_predictions = predictions_history[-100:] if predictions_history else []
        
        return jsonify({
            'status': 'success',
            'firebase_count': len(all_predictions),
            'memory_count': len(memory_predictions),
            'firebase_sample': all_predictions[:5] if all_predictions else [],
            'memory_sample': memory_predictions[-5:] if memory_predictions else [],
            'message': f'Firebase has {len(all_predictions)} predictions, Memory has {len(memory_predictions)}'
        })
    except Exception as e:
        print(f"[ERROR] Debug error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/predictions/test-data', methods=['GET', 'POST'])
def api_generate_test_data():
    """Generate test prediction data for debugging"""
    try:
        if not firebase_db:
            return jsonify({'status': 'error', 'message': 'Firebase not initialized'}), 500
        
        import random
        count = int(request.args.get('count', 50))
        
        # Generate 50 test predictions over the last 24 hours
        base_time = datetime.now() - timedelta(hours=24)
        
        for i in range(count):
            # Create records spaced throughout the last 24 hours
            timestamp = base_time + timedelta(minutes=i * (24 * 60 // count))
            
            # Generate realistic sensor data
            base_temp = 20 + random.gauss(2, 1)  # Temperature around 22°C with noise
            temp = base_temp + random.gauss(0, 0.5)
            humidity = 45 + random.gauss(5, 5)
            pressure = 1013 + random.gauss(0, 2)
            movement = random.randint(0, 5)
            
            # Prediction should be close to actual but with some error
            prediction = temp + random.gauss(0, 0.3)
            confidence = 80 + random.gauss(5, 5)
            
            prediction_data = {
                "timestamp": timestamp.isoformat(),
                "temperature": round(temp, 2),
                "humidity": round(max(0, min(100, humidity)), 1),
                "pressure": round(pressure, 1),
                "movement": movement,
                "occupancy": random.randint(0, 10),
                "prediction": round(prediction, 2),
                "confidence": round(max(0, min(100, confidence)), 1)
            }
            
            # Store in Firebase
            success, msg = firebase_db.store_prediction(prediction_data)
            if not success:
                print(f"[WARNING] Failed to store test prediction {i}: {msg}")
        
        print(f"[INFO] Generated {count} test predictions")
        return jsonify({
            'status': 'success',
            'message': f'Generated {count} test predictions',
            'count': count
        })
    except Exception as e:
        print(f"[ERROR] Test data generation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/predictions/history', methods=['GET'])
def api_get_predictions_history():
    """Get prediction history from Firebase with date and time"""
    try:
        limit = request.args.get('limit', 100, type=int)
        hours = request.args.get('hours', 24, type=int)
        
        history = []
        
        # Try to fetch from Firebase first
        if firebase_db:
            try:
                history = firebase_db.get_predictions_history(limit=limit, hours=hours)
                print(f"[DEBUG] Fetched {len(history)} records from Firebase")
            except Exception as e:
                print(f"[WARNING] Firebase fetch failed: {e}")
        
        # Fallback to in-memory predictions_history if Firebase empty
        if not history and predictions_history:
            print("[DEBUG] Using in-memory predictions_history as fallback")
            history = predictions_history[-limit:] if predictions_history else []
        
        if not history:
            print("[WARNING] No prediction data available from Firebase or memory")
            return jsonify({
                'status': 'success',
                'labels': [],
                'temperatures': [],
                'predictions': [],
                'errors': [],
                'confidences': [],
                'humidities': [],
                'records': [],
                'count': 0,
                'statistics': {
                    'mae': 0,
                    'rmse': 0,
                    'avg_confidence': 0,
                    'max_error': 0,
                    'min_error': 0
                }
            })
        
        # Format for charting and table display
        labels = []
        temperatures = []
        predictions_list = []
        errors = []
        confidences = []
        humidities = []
        full_records = []
        
        for record in history:
            try:
                # Handle both dict records and datetime objects
                if isinstance(record, dict):
                    timestamp_str = record.get('timestamp', '')
                    temp = float(record.get('temperature', 0))
                    pred = float(record.get('prediction', 0))
                    conf = float(record.get('confidence', 0))
                    hum = float(record.get('humidity', 0))
                else:
                    continue
                
                if not timestamp_str:
                    continue
                
                # Parse timestamp
                if isinstance(timestamp_str, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str)
                    except:
                        # Try alternative format
                        try:
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        except:
                            continue
                else:
                    timestamp = timestamp_str
                
                # Format: "YYYY-MM-DD HH:MM:SS"
                datetime_label = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                labels.append(datetime_label)
                
                temperatures.append(temp)
                predictions_list.append(pred)
                error = abs(temp - pred)
                errors.append(error)
                confidences.append(conf)
                humidities.append(hum)
                
                # Full record for table display
                full_records.append({
                    'datetime': datetime_label,
                    'temperature': temp,
                    'prediction': pred,
                    'error': error,
                    'confidence': conf,
                    'humidity': hum,
                    'timestamp': timestamp_str
                })
            except Exception as e:
                print(f"[WARNING] Error processing prediction record: {e}")
                continue
        
        # Calculate statistics
        mae = 0
        rmse = 0
        if errors:
            mae = sum(errors) / len(errors)
            rmse = (sum(e**2 for e in errors) / len(errors)) ** 0.5
        
        avg_confidence = 0
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
        
        print(f"[DEBUG] Returning {len(full_records)} formatted records")
        
        return jsonify({
            'status': 'success',
            'labels': labels,
            'temperatures': temperatures,
            'predictions': predictions_list,
            'errors': errors,
            'confidences': confidences,
            'humidities': humidities,
            'records': full_records,
            'count': len(history),
            'statistics': {
                'mae': round(mae, 2),
                'rmse': round(rmse, 2),
                'avg_confidence': round(avg_confidence, 2),
                'max_error': round(max(errors) if errors else 0, 2),
                'min_error': round(min(errors) if errors else 0, 2)
            }
        })
    except Exception as e:
        print(f"[ERROR] Error fetching predictions history: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ================= WEBSOCKET EVENTS =================

@socketio.on('connect', namespace='/')
def websocket_connect():
    """Handle WebSocket client connection"""
    print(f"[WEBSOCKET] Client connected: {request.sid}")
    # Send current sensor data to newly connected client
    if last_sensor_data:
        emit('sensor_update', last_sensor_data)

@socketio.on('disconnect', namespace='/')
def websocket_disconnect():
    """Handle WebSocket client disconnection"""
    print(f"[WEBSOCKET] Client disconnected: {request.sid}")

@socketio.on('request_data', namespace='/')
def handle_data_request():
    """Handle client request for current data"""
    if last_sensor_data:
        emit('sensor_update', last_sensor_data)
    else:
        emit('sensor_update', {
            'temperature': 0,
            'humidity': 0,
            'pressure': 0,
            'movement': 0,
            'prediction': 0,
            'confidence': 0,
            'occupancy': 0,
            'timestamp': datetime.now().isoformat()
        })

# ================= ERROR HANDLERS =================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not Found'}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    print(f"[ERROR] Internal server error: {error}")
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal Server Error'}), 500
    return render_template('500.html'), 500

# ================= STARTUP =================

if __name__ == '__main__':
    print("\n" + "="*70)
    print("[SYSTEM] RFID Temperature Prediction System with Firebase")
    print("="*70)
    print("[INFO] Database: Firebase Firestore")
    print("[INFO] Authentication: Enabled (Username/Password & RFID)")
    print("[INFO] Real-Time: WebSocket Support Enabled")
    print("[INFO] Starting Flask server with SocketIO...")
    print("[INFO] Open http://localhost:5000 in your browser")
    print("[INFO] Or use http://192.168.1.18:5000")
    print("="*70)

    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
