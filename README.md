# RFID Temperature Prediction System

A comprehensive Flask-based system that integrates RFID entry/exit tracking with real-time temperature prediction using machine learning. The system features Firebase Firestore backend, WebSocket real-time updates, and ESP32 microcontroller integration.

## 🎯 Features

- **RFID Entry/Exit Tracking**: Automatic occupancy management via RFID cards
- **Temperature Prediction**: ML-based predictions using RandomForest algorithm
- **Real-Time Updates**: WebSocket support for live sensor data streaming
- **User Authentication**: Secure login with email verification and password reset
- **Role-Based Access Control**: Admin and user role management
- **Fan Control**: Manual and automatic temperature-based fan control
- **Firebase Integration**: Cloud-based data storage and user management
- **Dashboard**: Real-time visualization of sensor data and predictions
- **Admin Panel**: System configuration and user management
- **ESP32 Compatible**: Full support for ESP32 microcontroller communication

## 📋 Requirements

- Python 3.8+
- Flask
- Firebase Admin SDK
- scikit-learn (for ML model)
- pandas
- numpy
- Flask-CORS
- Flask-SocketIO
- joblib

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd Projet
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root based on `.env.example`:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
FLASK_SECRET_KEY=your-secure-secret-key-here
FIREBASE_CREDENTIALS=app/API/your-firebase-credentials.json
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-specific-password
```

### 5. Set Up Firebase

1. Create a Firebase project at [firebase.google.com](https://firebase.google.com)
2. Create a Firestore database
3. Generate a service account JSON key
4. Place the JSON file at `app/API/microcontrolleur-c05ca-firebase-adminsdk-fbsvc-319765e201.json`
5. Update the `FIREBASE_CREDENTIALS` path in `.env`

### 6. Prepare Models

Ensure the following model files exist in `app/models/`:
- `model_BEST_RandomForest_20260326_140710.pkl` - Trained ML model
- `scaler_20260326_140710.pkl` - Feature scaler
- `features_20260326_140710.pkl` - Feature list

## 🏃 Running the Application

### Development

```bash
cd app
python app.py
```

The server will start at `http://localhost:5000`

### Production

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## 📁 Project Structure

```
Projet/
├── app/
│   ├── app.py                 # Main Flask application
│   ├── static/                # CSS, JavaScript files
│   ├── templates/             # HTML templates
│   ├── models/                # ML models and scalers
│   ├── database/              # Database managers
│   │   ├── firebase_manager.py
│   │   ├── auth_manager.py
│   │   ├── email_manager.py
│   │   ├── scheduler_manager.py
│   │   └── db_manager.py
│   └── esp32_client/          # ESP32 Arduino code
├── training/                  # Model training scripts
├── dataset_collect/           # Data collection utilities
├── .env.example              # Environment variables template
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## 🔌 API Endpoints

### Authentication
- `POST /login` - User login
- `POST /signup` - User registration
- `GET /logout` - User logout
- `GET /verify-email` - Email verification
- `POST /resend-verification` - Resend verification email
- `POST /forgot-password` - Request password reset
- `POST /reset-password` - Reset password

### Main Routes
- `GET /` - Root (redirects to dashboard)
- `GET /dashboard` - Main dashboard
- `GET /stats` - Statistics page
- `GET /admin` - Admin panel
- `GET /system-info` - System information

### API - Sensor Data & Predictions
- `POST /api/sensor-data` - Receive sensor data from ESP32
- `POST /predict` - Make predictions
- `GET /api/sensor/latest` - Get latest sensor reading
- `GET /api/sensor-data` - Get sensor data
- `GET /api/predictions/latest` - Get latest predictions
- `GET /api/predictions/history` - Get prediction history
- `GET /api/occupancy` - Get current occupancy

### API - Fan Control
- `POST /api/fan/config` - Configure fan mode
- `POST /api/fan/command` - Turn fan ON/OFF
- `GET /api/fan/status` - Get fan status
- `POST /api/fan/control` - Manual fan control
- `POST /api/fan/settings` - Update fan automatic settings

### API - Admin Management
- `GET /api/admin/users/list` - List all users
- `POST /api/admin/users/create` - Create new user
- `POST /api/admin/users/delete/<username>` - Delete user
- `POST /api/admin/users/update/<username>` - Update user
- `POST /api/admin/rfid/register` - Register RFID device
- `GET /api/admin/rfid/list` - List RFID devices
- `POST /api/admin/rfid/remove/<rfid_code>` - Remove RFID
- `POST /api/admin/settings/update` - Update settings

### API - RFID
- `POST /api/rfid/verify` - Verify RFID tag

## 🤖 ESP32 Integration

### WiFi Configuration

Edit the SSID and password in `app/esp32_client/esp32_code.ino`:

```cpp
const char* ssid = "YOUR_SSID";
const char* password = "YOUR_PASSWORD";
const char* serverUrl = "http://192.168.1.18:5000";
```

### Uploading to ESP32

1. Install Arduino IDE
2. Install ESP32 board support
3. Open `app/esp32_client/esp32_code.ino`
4. Select your board and port
5. Upload the sketch

### Sensors

The ESP32 code reads from:
- Temperature/Humidity sensor (DHT22)
- Pressure sensor (BMP280)
- RFID reader (MFRC522)
- PIR motion sensor
- Optional: Light sensor (LDR)

## 🧠 Machine Learning Model

The temperature prediction model uses:
- **Algorithm**: RandomForest Classifier
- **Features**: 
  - Raw sensor values (temperature, humidity, pressure, movement)
  - Temporal features (hour, minute, time of day)
  - Lag features (previous readings)
  - Rolling statistics (mean, std, min, max)
  - Interaction features

### Training

To retrain the model:

```bash
cd training
python train_ultimate.py
```

Model files will be generated in `app/models/`

## 📊 Database Schema

### Firestore Collections

- **users**: User accounts and credentials
- **rfid_devices**: RFID card registrations
- **sensor_data**: Raw sensor readings
- **predictions**: Temperature predictions
- **attendance**: Entry/exit logs
- **settings**: System configuration

## 🔐 Security Features

- **Email Verification**: Confirm user email during signup
- **Password Hashing**: Secure password storage
- **CORS Support**: Cross-origin request handling
- **Authentication Decorators**: `@require_login`, `@require_admin`
- **Session Management**: 24-hour session timeout
- **Role-Based Access**: Admin-only endpoints protected

## 🛠️ Development

### Testing

```bash
# Test ESP32 communication
python test_esp32_communication.py

# Test fan modes
python test_fan_modes.py

# Verify fan implementation
python verify_fan_implementation.py
```

### Debugging

Enable debug mode in `app.py`:

```python
socketio.run(app, debug=True)
```

View logs in the terminal for request/response tracking.

## 📝 Environment Setup for GitHub

Before uploading to GitHub:

1. ✅ Remove API credentials: Firebase JSON deleted
2. ✅ Create `.env.example`: Template for environment variables
3. Create `.gitignore`: Exclude sensitive files

Example `.gitignore`:
```
.env
.env.local
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
app/API/*.json
app/models/*.pkl
venv/
.vscode/
.idea/
*.log
node_modules/
```

## 🚨 Common Issues

### Firebase Connection Error
- Verify `FIREBASE_CREDENTIALS` path in `.env`
- Check Firebase project ID matches configuration
- Ensure service account has Firestore permissions

### Model Loading Error
- Verify model files exist in `app/models/`
- Check Python version matches model training environment
- Ensure scikit-learn version compatibility

### ESP32 Not Connecting
- Verify WiFi credentials in Arduino sketch
- Check server IP address is correct
- Ensure firewall allows port 5000

## 📚 Documentation

Additional documentation:
- [Hardware Setup Guide](guide/README_NEW.md)
- [Email Verification Setup](guide/SETUP_EMAIL_VERIFICATION.md)
- [API Documentation](Backup/app/help/API_DOCUMENTATION.md)
- [Deployment Guide](Backup/app/help/DEPLOYMENT.md)

## 👥 Contributors

- Project Lead: [Your Name]
- Hardware Integration: ESP32 team
- ML Model Development: Data science team

## 📄 License

This project is licensed under the MIT License - see LICENSE file for details.

## 📞 Support

For issues or questions:
1. Check the documentation in `guide/` and `Backup/app/help/`
2. Review test files: `test_*.py`
3. Enable debug logging in Flask

## 🔄 Version History

### v1.0.0
- Initial release with RFID tracking
- Temperature prediction with RandomForest
- Firebase backend integration
- ESP32 support
- Web dashboard with real-time updates
