# auth_manager.py - Authentication helper module
from functools import wraps
from flask import session, redirect, url_for, request, jsonify
from datetime import datetime, timedelta
import os

def require_login(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def require_admin(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login', next=request.url))
        
        if session.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

def require_role(role):
    """Decorator to require specific role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                return redirect(url_for('login', next=request.url))
            
            if session.get('role') != role and session.get('role') != 'admin':
                return jsonify({'error': f'{role} access required'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def login_user(session_obj, username, role, email=None):
    """Set user session after login"""
    session_obj['username'] = username
    session_obj['role'] = role
    session_obj['email'] = email
    session_obj['login_time'] = datetime.now().isoformat()
    session_obj.permanent = True

def logout_user(session_obj):
    """Clear user session"""
    session_obj.clear()

def is_authenticated(session_obj) -> bool:
    """Check if user is authenticated"""
    return 'username' in session_obj

def get_current_user(session_obj) -> dict:
    """Get current user info"""
    if 'username' not in session_obj:
        return None
    
    return {
        'username': session_obj.get('username'),
        'role': session_obj.get('role'),
        'email': session_obj.get('email'),
        'login_time': session_obj.get('login_time')
    }
