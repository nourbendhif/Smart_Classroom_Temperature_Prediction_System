# firebase_manager.py - Enhanced Firebase Realtime Database Manager with Authentication & RFID Tracking
import firebase_admin
from firebase_admin import credentials, db, auth as fb_auth
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import os
import hashlib
import secrets
import json
from database.email_manager import EmailManager

class EnhancedFirebaseManager:
    """
    Enhanced Firebase Realtime Database manager for:
    - User authentication (Admin/User roles)
    - RFID management and entry/exit tracking
    - Sensor data storage
    - Configuration management
    """
    
    def __init__(self, credentials_path: str = None):
        """
        Initialize Firebase connection
        
        Args:
            credentials_path: Path to Firebase service account JSON
        """
        self.credentials_path = credentials_path or os.getenv(
            'FIREBASE_CREDENTIALS', 
            'firebase-credentials.json'
        )
        
        # Convert to absolute path if relative
        if not os.path.isabs(self.credentials_path):
            self.credentials_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), '..', self.credentials_path
            ))
        
        print(f"[INFO] Firebase credentials path: {self.credentials_path}")
        print(f"[INFO] Credentials file exists: {os.path.exists(self.credentials_path)}")
        
        self.database_url = None
        self.email_manager = EmailManager()
        self.connect()
    
    def connect(self):
        """Establish Firebase Realtime Database connection"""
        try:
            if not os.path.exists(self.credentials_path):
                raise FileNotFoundError(f"Firebase credentials file not found: {self.credentials_path}")
            
            if not firebase_admin._apps:
                cred = credentials.Certificate(self.credentials_path)
                # Extract database URL from credentials
                with open(self.credentials_path, 'r') as f:
                    creds_dict = json.load(f)
                    project_id = creds_dict.get('project_id')
                    self.database_url = f"https://{project_id}-default-rtdb.firebaseio.com"
                
                firebase_admin.initialize_app(cred, {
                    'databaseURL': self.database_url
                })
            
            print("[INFO] [OK] Firebase Realtime Database connected successfully!")
            print(f"[INFO] Database URL: {self.database_url}")
            self._init_collections()
            return True
        except FileNotFoundError as e:
            print(f"[ERROR] {e}")
            return False
        except Exception as e:
            print(f"[ERROR] Firebase connection failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _init_collections(self):
        """Initialize Realtime Database root nodes"""
        root_nodes = ['users', 'rfid_devices', 'rfid_scans', 'sensor_data', 
                      'predictions', 'settings', 'attendance_log']
        
        # Create root nodes if they don't exist
        for node in root_nodes:
            try:
                ref = db.reference(node)
                snapshot = ref.get()
                if snapshot is not None and snapshot.val() is None:
                    ref.set({})
            except:
                pass
        
        print("[INFO] [OK] Firebase Realtime Database nodes initialized")
    
    def _check_connection(self) -> bool:
        """Check if Firebase is connected"""
        try:
            db.reference().get()
            return True
        except Exception as e:
            print("[ERROR] Firebase is not connected. Check your credentials file and configuration.")
            return False
    
    def _get_snapshot_value(self, snapshot):
        """Safely extract value from snapshot, handling both DataSnapshot objects and dict returns"""
        if snapshot is None:
            return None
        elif isinstance(snapshot, dict):
            return snapshot
        else:
            # It's a DataSnapshot object, call .val()
            return snapshot.val()
    
    # ==================== USER MANAGEMENT ====================
    
    def hash_password(self, password: str) -> str:
        """Hash password with salt"""
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return f"{salt}${pwd_hash.hex()}"
    
    def verify_password(self, password: str, hash_pwd: str) -> bool:
        """Verify password against hash"""
        try:
            salt = hash_pwd.split('$')[0]
            stored_hash = hash_pwd.split('$')[1]
            pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
            return pwd_hash.hex() == stored_hash
        except:
            return False
    
    def create_user(self, username: str, password: str, role: str = 'user', 
                   email: str = None) -> Tuple[bool, str]:
        """Create new user account with email verification"""
        if not self._check_connection():
            return False, "Database connection error. Please try again later."
        
        try:
            # Check if user exists
            user_snapshot = db.reference(f'users/{username}').get()
            if user_snapshot is not None and user_snapshot.val() is not None:
                return False, f"Username '{username}' already exists"
            
            # Generate verification token
            verification_token = self.email_manager.generate_token()
            verification_token_hash = self.email_manager.hash_token(verification_token)
            verification_expires = (datetime.now() + timedelta(hours=24)).isoformat()
            
            user_data = {
                'username': username,
                'password_hash': self.hash_password(password),
                'role': role,  # 'admin' or 'user'
                'email': email,
                'created_at': datetime.now().isoformat(),
                'is_active': True,
                'email_verified': False,
                'verification_token_hash': verification_token_hash,
                'verification_token_expires_at': verification_expires,
                'rfid_assigned': None,
                'login_attempts': 0,
                'last_login': None
            }
            
            db.reference(f'users/{username}').set(user_data)
            
            # Send verification email
            if email:
                self.email_manager.send_verification_email(email, username, verification_token)
            
            print(f"[USER] Created new user: {username} ({role}) - Verification email sent")
            return True, f"User '{username}' created successfully. Please check your email to verify your account."
            
        except Exception as e:
            print(f"[ERROR] Failed to create user: {e}")
            return False, str(e)
    
    def authenticate_user(self, username: str, password: str) -> Tuple[bool, Dict]:
        """Authenticate user with username and password"""
        if not self._check_connection():
            return False, {'error': 'Database connection error. Please try again later.'}
        
        try:
            user_snapshot = db.reference(f'users/{username}').get()
            user_data = self._get_snapshot_value(user_snapshot)
            
            if user_data is None:
                return False, {'error': 'User not found'}
            
            if not user_data.get('is_active'):
                return False, {'error': 'User account is inactive'}
            
            # Check if email is verified
            if not user_data.get('email_verified', False):
                return False, {'error': 'Please verify your email first. Check your email for verification link.'}
            
            if not self.verify_password(password, user_data.get('password_hash', '')):
                # Increment login attempts
                login_attempts = user_data.get('login_attempts', 0) + 1
                db.reference(f'users/{username}').update({
                    'login_attempts': login_attempts
                })
                return False, {'error': 'Invalid password'}
            
            # Reset login attempts and update last login
            db.reference(f'users/{username}').update({
                'login_attempts': 0,
                'last_login': datetime.now().isoformat()
            })
            
            print(f"[AUTH] User authenticated: {username}")
            return True, {
                'username': username,
                'role': user_data.get('role'),
                'email': user_data.get('email'),
                'rfid_assigned': user_data.get('rfid_assigned')
            }
            
        except Exception as e:
            print(f"[ERROR] Authentication failed: {e}")
            return False, {'error': str(e)}
    
    def verify_email(self, verification_token: str) -> Tuple[bool, str]:
        """Verify email using verification token"""
        if not self._check_connection():
            return False, "Database connection error. Please try again later."
        
        try:
            # Hash the token to compare with stored hash
            token_hash = self.email_manager.hash_token(verification_token)
            
            # Find user with matching token
            users_snapshot = db.reference('users').get()
            users_data = self._get_snapshot_value(users_snapshot)
            
            if users_data is None:
                return False, "Invalid verification token"
            
            found_user = None
            found_username = None
            
            for username, user_data in users_data.items():
                if isinstance(user_data, dict):
                    if user_data.get('verification_token_hash') == token_hash:
                        found_user = user_data
                        found_username = username
                        break
            
            if found_user is None:
                return False, "Invalid verification token"
            
            # Check if token has expired
            token_expires_str = found_user.get('verification_token_expires_at')
            if token_expires_str:
                token_expires = datetime.fromisoformat(token_expires_str)
                if datetime.now() > token_expires:
                    return False, "Verification token has expired. Please request a new one."
            
            # Mark email as verified
            db.reference(f'users/{found_username}').update({
                'email_verified': True,
                'verification_token_hash': None,
                'verification_token_expires_at': None,
                'email_verified_at': datetime.now().isoformat()
            })
            
            print(f"[EMAIL] Email verified for user: {found_username}")
            return True, f"Email verified successfully! You can now login."
            
        except Exception as e:
            print(f"[ERROR] Email verification failed: {e}")
            return False, str(e)
    
    def resend_verification_email(self, username: str) -> Tuple[bool, str]:
        """Resend verification email to user"""
        if not self._check_connection():
            return False, "Database connection error. Please try again later."
        
        try:
            user_snapshot = db.reference(f'users/{username}').get()
            # Handle both DataSnapshot objects and direct dict returns
            user_data = self._get_snapshot_value(user_snapshot)
            
            if user_data is None:
                return False, "User not found"
            
            if user_data.get('email_verified'):
                return False, "Email is already verified"
            
            email = user_data.get('email')
            if not email:
                return False, "No email address on file"
            
            # Generate new verification token
            verification_token = self.email_manager.generate_token()
            verification_token_hash = self.email_manager.hash_token(verification_token)
            verification_expires = (datetime.now() + timedelta(hours=24)).isoformat()
            
            # Update user with new token
            db.reference(f'users/{username}').update({
                'verification_token_hash': verification_token_hash,
                'verification_token_expires_at': verification_expires
            })
            
            # Send verification email
            self.email_manager.send_verification_email(email, username, verification_token)
            
            print(f"[EMAIL] Verification email resent to: {username}")
            return True, "Verification email sent successfully"
            
        except Exception as e:
            print(f"[ERROR] Failed to resend verification email: {e}")
            return False, str(e)
    
    def request_password_reset(self, username: str) -> Tuple[bool, str]:
        """Request password reset - sends email with reset link"""
        if not self._check_connection():
            return False, "Database connection error. Please try again later."
        
        try:
            user_snapshot = db.reference(f'users/{username}').get()
            user_data = self._get_snapshot_value(user_snapshot)
            
            if user_data is None:
                # Don't reveal if user exists for security
                return True, "If the username exists, a password reset link will be sent to the registered email."
            
            email = user_data.get('email')
            if not email:
                return True, "If the username exists, a password reset link will be sent to the registered email."
            
            # Generate password reset token
            reset_token = self.email_manager.generate_token()
            reset_token_hash = self.email_manager.hash_token(reset_token)
            reset_expires = (datetime.now() + timedelta(hours=1)).isoformat()
            
            # Update user with reset token
            db.reference(f'users/{username}').update({
                'password_reset_token_hash': reset_token_hash,
                'password_reset_token_expires_at': reset_expires
            })
            
            # Send password reset email
            self.email_manager.send_password_reset_email(email, username, reset_token)
            
            print(f"[EMAIL] Password reset email sent to: {username}")
            return True, "If the username exists, a password reset link will be sent to the registered email."
            
        except Exception as e:
            print(f"[ERROR] Failed to request password reset: {e}")
            return False, str(e)
    
    def reset_password(self, reset_token: str, new_password: str) -> Tuple[bool, str]:
        """Reset password using reset token"""
        if not self._check_connection():
            return False, "Database connection error. Please try again later."
        
        try:
            # Hash the token to compare with stored hash
            token_hash = self.email_manager.hash_token(reset_token)
            
            # Find user with matching reset token
            users_snapshot = db.reference('users').get()
            users_data = self._get_snapshot_value(users_snapshot)
            
            if users_data is None:
                return False, "Invalid password reset link"
            
            found_user = None
            found_username = None
            
            for username, user_data in users_data.items():
                if isinstance(user_data, dict):
                    if user_data.get('password_reset_token_hash') == token_hash:
                        found_user = user_data
                        found_username = username
                        break
            
            if found_user is None:
                return False, "Invalid password reset link"
            
            # Check if token has expired
            token_expires_str = found_user.get('password_reset_token_expires_at')
            if token_expires_str:
                token_expires = datetime.fromisoformat(token_expires_str)
                if datetime.now() > token_expires:
                    return False, "Password reset link has expired. Please request a new one."
            
            # Validate new password
            if len(new_password) < 6:
                return False, "Password must be at least 6 characters"
            
            # Update password and clear reset token
            db.reference(f'users/{found_username}').update({
                'password_hash': self.hash_password(new_password),
                'password_reset_token_hash': None,
                'password_reset_token_expires_at': None,
                'password_reset_at': datetime.now().isoformat()
            })
            
            print(f"[AUTH] Password reset successfully for user: {found_username}")
            return True, "Password has been reset successfully! You can now login with your new password."
            
        except Exception as e:
            print(f"[ERROR] Password reset failed: {e}")
            return False, str(e)
    
    def get_user(self, username: str) -> Optional[Dict]:
        """Get user details"""
        try:
            user_snapshot = db.reference(f'users/{username}').get()
            user_data = self._get_snapshot_value(user_snapshot)
            if user_data is not None:
                return user_data
            return None
        except Exception as e:
            print(f"[ERROR] Failed to get user: {e}")
            return None
    
    def list_users(self) -> List[Dict]:
        """List all users"""
        try:
            users = []
            users_snapshot = db.reference('users').get()
            users_data = self._get_snapshot_value(users_snapshot)
            
            if users_data is None:
                return []
            
            for username, user_data in users_data.items():
                if isinstance(user_data, dict):
                    # Don't expose password hashes
                    user_data_copy = user_data.copy()
                    user_data_copy.pop('password_hash', None)
                    user_data_copy['username'] = username
                    users.append(user_data_copy)
            
            return users
        except Exception as e:
            print(f"[ERROR] Failed to list users: {e}")
            return []
    
    def delete_user(self, username: str) -> Tuple[bool, str]:
        """Delete user account"""
        try:
            db.reference(f'users/{username}').delete()
            return True, f"User '{username}' deleted"
        except Exception as e:
            return False, str(e)
    
    def update_user_role(self, username: str, new_role: str) -> Tuple[bool, str]:
        """Update user role"""
        try:
            db.reference(f'users/{username}').update({
                'role': new_role,
                'updated_at': datetime.now().isoformat()
            })
            return True, f"User role updated to '{new_role}'"
        except Exception as e:
            return False, str(e)
    
    def update_user(self, username: str, update_data: Dict) -> Tuple[bool, str]:
        """Update user information (email, password, role, etc.)"""
        if not self._check_connection():
            return False, "Database connection error. Please try again later."
        
        try:
            # Check if user exists
            user_snapshot = db.reference(f'users/{username}').get()
            user_data = self._get_snapshot_value(user_snapshot)
            
            if user_data is None:
                return False, f"User '{username}' not found"
            
            # Prepare update dictionary
            updates = {}
            
            # Update email if provided
            if 'email' in update_data and update_data['email']:
                updates['email'] = update_data['email']
            
            # Update password if provided (hash it first)
            if 'password' in update_data and update_data['password']:
                updates['password_hash'] = self.hash_password(update_data['password'])
            
            # Update role if provided
            if 'role' in update_data and update_data['role']:
                updates['role'] = update_data['role']
            
            # Add timestamp
            updates['updated_at'] = datetime.now().isoformat()
            
            # Perform update
            db.reference(f'users/{username}').update(updates)
            
            print(f"[USER] Updated user: {username} - Fields: {list(updates.keys())}")
            return True, f"User '{username}' updated successfully"
            
        except Exception as e:
            print(f"[ERROR] Failed to update user: {e}")
            return False, str(e)
    
    # ==================== RFID MANAGEMENT ====================
    
    def register_rfid(self, rfid_code: str, person_name: str, 
                     assigned_user: str = None) -> Tuple[bool, str]:
        """Register new RFID device"""
        try:
            rfid_data = {
                'rfid_code': rfid_code,
                'person_name': person_name,
                'assigned_user': assigned_user,
                'registered_at': datetime.now().isoformat(),
                'last_scan': None,
                'is_active': True,
                'entry_count': 0,
                'total_scans': 0
            }
            
            db.reference(f'rfid_devices/{rfid_code}').set(rfid_data)
            
            # Update user if assigned
            if assigned_user:
                db.reference(f'users/{assigned_user}').update({
                    'rfid_assigned': rfid_code
                })
            
            print(f"[RFID] Registered: {person_name} ({rfid_code})")
            return True, f"RFID '{rfid_code}' registered successfully"
            
        except Exception as e:
            print(f"[ERROR] Failed to register RFID: {e}")
            return False, str(e)
    
    def handle_rfid_scan(self, rfid_code: str) -> Tuple[bool, Dict]:
        """
        Handle RFID scan with entry/exit tracking
        Entry: First scan of the day marks entry
        Exit: Second scan marks exit (ends current session)
        """
        try:
            rfid_snapshot = db.reference(f'rfid_devices/{rfid_code}').get()
            rfid_data = self._get_snapshot_value(rfid_snapshot)
            
            if rfid_data is None:
                return False, {'error': 'RFID not registered'}
            
            if not rfid_data.get('is_active'):
                return False, {'error': 'RFID is inactive'}
            
            person_name = rfid_data.get('person_name')
            assigned_user = rfid_data.get('assigned_user')
            
            # Get today's date
            today = datetime.now().date()
            log_date_str = today.isoformat()
            log_key = f"{rfid_code}_{log_date_str}"
            
            # Check today's attendance
            today_log_snapshot = db.reference(f'attendance_log/{log_key}').get()
            today_log_data = self._get_snapshot_value(today_log_snapshot)
            
            if today_log_data is not None:
                if today_log_data.get('exit_time') is None:
                    # Already entered, this is an exit
                    db.reference(f'attendance_log/{log_key}').update({
                        'exit_time': datetime.now().isoformat(),
                        'status': 'exited'
                    })
                    
                    # Decrement entry count
                    new_entry_count = max(0, rfid_data.get('entry_count', 0) - 1)
                    db.reference(f'rfid_devices/{rfid_code}').update({
                        'last_scan': datetime.now().isoformat(),
                        'total_scans': rfid_data.get('total_scans', 0) + 1,
                        'entry_count': new_entry_count
                    })
                    
                    result = {
                        'status': 'exit',
                        'person_name': person_name,
                        'message': f'Goodbye {person_name}! You have exited.',
                        'current_occupancy': new_entry_count
                    }
                else:
                    # Already exited today
                    return False, {'error': f'{person_name} already exited today'}
            else:
                # New entry
                db.reference(f'attendance_log/{log_key}').set({
                    'rfid_code': rfid_code,
                    'person_name': person_name,
                    'assigned_user': assigned_user,
                    'date': log_date_str,
                    'entry_time': datetime.now().isoformat(),
                    'exit_time': None,
                    'status': 'entered'
                })
                
                # Increment entry count
                new_entry_count = rfid_data.get('entry_count', 0) + 1
                db.reference(f'rfid_devices/{rfid_code}').update({
                    'last_scan': datetime.now().isoformat(),
                    'total_scans': rfid_data.get('total_scans', 0) + 1,
                    'entry_count': new_entry_count
                })
                
                result = {
                    'status': 'entry',
                    'person_name': person_name,
                    'message': f'Welcome {person_name}!',
                    'current_occupancy': new_entry_count
                }
            
            # Log scan
            scan_ref = db.reference('rfid_scans').push({
                'rfid_code': rfid_code,
                'person_name': person_name,
                'scan_time': datetime.now().isoformat(),
                'status': result.get('status'),
                'result': result
            })
            
            return True, result
            
        except Exception as e:
            print(f"[ERROR] RFID scan failed: {e}")
            return False, {'error': str(e)}
    
    def get_rfid_device(self, rfid_code: str) -> Optional[Dict]:
        """Get RFID device details"""
        try:
            rfid_snapshot = db.reference(f'rfid_devices/{rfid_code}').get()
            rfid_data = self._get_snapshot_value(rfid_snapshot)
            if rfid_data is not None:
                return rfid_data
            return None
        except Exception as e:
            print(f"[ERROR] Failed to get RFID device: {e}")
            return None
    
    def list_rfid_devices(self) -> List[Dict]:
        """List all registered RFID devices"""
        try:
            devices = []
            devices_snapshot = db.reference('rfid_devices').get()
            devices_data = self._get_snapshot_value(devices_snapshot)
            
            if devices_data is None:
                return []
            
            for rfid_code, device_data in devices_data.items():
                if isinstance(device_data, dict):
                    devices.append(device_data)
            
            return devices
        except Exception as e:
            print(f"[ERROR] Failed to list RFID devices: {e}")
            return []
    
    def remove_rfid(self, rfid_code: str) -> Tuple[bool, str]:
        """Remove RFID device"""
        try:
            db.reference(f'rfid_devices/{rfid_code}').delete()
            return True, f"RFID '{rfid_code}' removed"
        except Exception as e:
            return False, str(e)
    
    def get_current_occupancy(self) -> int:
        """Get current number of people in building"""
        try:
            count = 0
            devices_snapshot = db.reference('rfid_devices').get()
            devices_data = self._get_snapshot_value(devices_snapshot)
            
            if devices_data is None:
                return 0
            
            for rfid_code, device in devices_data.items():
                if isinstance(device, dict):
                    if device.get('is_active') and device.get('entry_count', 0) > 0:
                        count += device.get('entry_count', 0)
            
            return count
        except Exception as e:
            print(f"[ERROR] Failed to get occupancy: {e}")
            return 0
    
    # ==================== SENSOR DATA ====================
    
    def store_sensor_data(self, sensor_data: Dict) -> Tuple[bool, str]:
        """Store sensor data in Firebase"""
        try:
            data = {
                "timestamp": datetime.now().isoformat(),
                "temperature": sensor_data.get("temperature", 0),
                "humidity": sensor_data.get("humidity", 0),
                "pressure": sensor_data.get("pressure", 0),
                "movement": sensor_data.get("movement", 0),
                "occupancy": self.get_current_occupancy(),
            }
            
            new_record = db.reference('sensor_data').push(data)
            return True, new_record.key
        except Exception as e:
            print(f"[ERROR] Failed to store sensor data: {e}")
            return False, str(e)
    
    def get_latest_sensor_data(self, limit: int = 1) -> List[Dict]:
        """Get latest sensor readings"""
        try:
            data = []
            sensors_snapshot = db.reference('sensor_data').get()
            sensors_data = self._get_snapshot_value(sensors_snapshot)
            
            if sensors_data is None:
                return []
            
            # Convert to list and sort by timestamp descending
            sensor_list = []
            for key, sensor in sensors_data.items():
                if isinstance(sensor, dict):
                    sensor['_id'] = key
                    sensor_list.append(sensor)
            
            # Sort by timestamp (most recent first)
            sensor_list.sort(
                key=lambda x: x.get('timestamp', ''), 
                reverse=True
            )
            
            return sensor_list[:limit]
        except Exception as e:
            print(f"[ERROR] Failed to fetch sensor data: {e}")
            return []
    
    def get_sensor_data_range(self, minutes: int = 60) -> List[Dict]:
        """Get sensor data from last N minutes"""
        try:
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            data = []
            
            sensors_snapshot = db.reference('sensor_data').get()
            sensors_data = self._get_snapshot_value(sensors_snapshot)
            
            if sensors_data is None:
                return []
            
            # Convert to list and filter
            sensor_list = []
            for key, sensor in sensors_data.items():
                if isinstance(sensor, dict):
                    try:
                        sensor_time = datetime.fromisoformat(sensor.get('timestamp', ''))
                        if sensor_time >= cutoff_time:
                            sensor['_id'] = key
                            sensor_list.append(sensor)
                    except:
                        pass
            
            # Sort by timestamp (most recent first)
            sensor_list.sort(
                key=lambda x: x.get('timestamp', ''),
                reverse=True
            )
            
            return sensor_list
        except Exception as e:
            print(f"[ERROR] Failed to fetch sensor data range: {e}")
            return []
    
    # ==================== PREDICTIONS ====================
    
    def store_prediction(self, prediction_data: Dict) -> Tuple[bool, str]:
        """Store prediction result"""
        try:
            data = {
                "timestamp": datetime.now().isoformat(),
                "temperature": prediction_data.get("temperature", 0),
                "humidity": prediction_data.get("humidity", 0),
                "pressure": prediction_data.get("pressure", 0),
                "movement": prediction_data.get("movement", 0),
                "occupancy": self.get_current_occupancy(),
                "prediction": prediction_data.get("prediction", 0),
                "confidence": prediction_data.get("confidence", 0)
            }
            
            new_record = db.reference('predictions').push(data)
            return True, new_record.key
        except Exception as e:
            print(f"[ERROR] Failed to store prediction: {e}")
            return False, str(e)
    
    def get_latest_predictions(self, limit: int = 10) -> List[Dict]:
        """Get latest predictions"""
        try:
            data = []
            predictions_snapshot = db.reference('predictions').get()
            predictions_data = self._get_snapshot_value(predictions_snapshot)
            
            if predictions_data is None:
                return []
            
            # Convert to list and sort by timestamp descending
            prediction_list = []
            for key, prediction in predictions_data.items():
                if isinstance(prediction, dict):
                    prediction['_id'] = key
                    prediction_list.append(prediction)
            
            # Sort by timestamp (most recent first)
            prediction_list.sort(
                key=lambda x: x.get('timestamp', ''),
                reverse=True
            )
            
            return prediction_list[:limit]
        except Exception as e:
            print(f"[ERROR] Failed to fetch predictions: {e}")
            return []
    
    def get_predictions_history(self, limit: int = 100, hours: int = 24) -> List[Dict]:
        """Get prediction history with date and time for the last N hours"""
        try:
            data = []
            predictions_snapshot = db.reference('predictions').get()
            predictions_data = self._get_snapshot_value(predictions_snapshot)
            
            if predictions_data is None:
                return []
            
            # Convert to list
            prediction_list = []
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            for key, prediction in predictions_data.items():
                if isinstance(prediction, dict):
                    try:
                        timestamp_str = prediction.get('timestamp', '')
                        if timestamp_str:
                            timestamp = datetime.fromisoformat(timestamp_str)
                            # Only include recent predictions
                            if timestamp >= cutoff_time:
                                prediction['_id'] = key
                                prediction_list.append(prediction)
                    except:
                        pass
            
            # Sort by timestamp (oldest first for chart display)
            prediction_list.sort(
                key=lambda x: x.get('timestamp', ''),
                reverse=False
            )
            
            return prediction_list[-limit:] if len(prediction_list) > limit else prediction_list
        except Exception as e:
            print(f"[ERROR] Failed to fetch prediction history: {e}")
            return []
    
    # ==================== SETTINGS ====================
    
    def update_settings(self, settings_dict: Dict) -> Tuple[bool, str]:
        """Update system settings"""
        try:
            settings_dict['updated_at'] = datetime.now().isoformat()
            db.reference('settings/config').update(settings_dict)
            return True, "Settings updated"
        except Exception as e:
            return False, str(e)
    
    def get_settings(self) -> Dict:
        """Get system settings"""
        try:
            settings_snapshot = db.reference('settings/config').get()
            settings_data = self._get_snapshot_value(settings_snapshot)
            
            if settings_data is not None and isinstance(settings_data, dict):
                return settings_data
            else:
                # Return defaults
                return {
                    'fan_runtime_minutes': 30,
                    'temp_threshold': 25.0,
                    'vent_status': False,
                    'updated_at': datetime.now().isoformat()
                }
        except Exception as e:
            print(f"[ERROR] Failed to get settings: {e}")
            return {}
    
    def get_attendance_log(self, dated: datetime = None) -> List[Dict]:
        """Get attendance log for a specific date"""
        try:
            target_date = (dated or datetime.now()).date()
            target_date_str = target_date.isoformat()
            logs = []
            
            attendance_snapshot = db.reference('attendance_log').get()
            attendance_data = self._get_snapshot_value(attendance_snapshot)
            
            if attendance_data is None:
                return []
            
            # Filter by date
            for key, log_entry in attendance_data.items():
                if isinstance(log_entry, dict):
                    # Check if this log entry is for the target date
                    if log_entry.get('date') == target_date_str:
                        logs.append(log_entry)
            
            return logs
        except Exception as e:
            print(f"[ERROR] Failed to get attendance log: {e}")
            return []
