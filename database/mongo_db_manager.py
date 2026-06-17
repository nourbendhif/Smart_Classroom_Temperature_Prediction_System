# mongo_db_manager.py - MongoDB Manager for Sensor Data and Predictions
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import os

class MongoDBManager:
    """MongoDB manager for storing sensor data and predictions"""
    
    def __init__(self, connection_string: str = None, db_name: str = "rfid_system"):
        """
        Initialize MongoDB connection
        
        Args:
            connection_string: MongoDB connection string (e.g., "mongodb://localhost:27017")
            db_name: Database name
        """
        self.connection_string = connection_string or os.getenv(
            "MONGODB_URI", 
            "mongodb://localhost:27017"
        )
        self.db_name = db_name
        self.client = None
        self.db = None
        self.connect()
    
    def connect(self):
        """Establish MongoDB connection"""
        try:
            self.client = MongoClient(self.connection_string, serverSelectionTimeoutMS=5000)
            # Verify connection
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            self._init_collections()
            print("[INFO] ✓ MongoDB connected successfully!")
            return True
        except ServerSelectionTimeoutError:
            print("[ERROR] MongoDB connection failed. Make sure MongoDB is running.")
            return False
        except Exception as e:
            print(f"[ERROR] MongoDB connection error: {e}")
            return False
    
    def _init_collections(self):
        """Initialize collections and indexes"""
        try:
            # Create collections if they don't exist
            if "sensor_data" not in self.db.list_collection_names():
                self.db.create_collection("sensor_data")
            
            if "predictions" not in self.db.list_collection_names():
                self.db.create_collection("predictions")
            
            if "delayed_predictions" not in self.db.list_collection_names():
                self.db.create_collection("delayed_predictions")
            
            # Create indexes for better query performance
            self.db.sensor_data.create_index("timestamp")
            self.db.predictions.create_index("timestamp")
            self.db.predictions.create_index("prediction_time")
            self.db.delayed_predictions.create_index("timestamp")
            self.db.delayed_predictions.create_index("display_after")
            
            # Create TTL index (auto-delete data older than 30 days)
            try:
                self.db.sensor_data.create_index(
                    "timestamp", 
                    expireAfterSeconds=2592000  # 30 days
                )
                self.db.predictions.create_index(
                    "timestamp", 
                    expireAfterSeconds=2592000
                )
            except:
                pass  # TTL index may already exist
                
            print("[INFO] ✓ MongoDB collections and indexes initialized")
        except Exception as e:
            print(f"[ERROR] Failed to initialize collections: {e}")
    
    # ==================== SENSOR DATA ====================
    
    def store_sensor_data(self, sensor_data: Dict) -> Tuple[bool, str]:
        """Store sensor data in MongoDB"""
        try:
            data = {
                "timestamp": datetime.now(),
                "temperature": sensor_data.get("temperature", 0),
                "humidity": sensor_data.get("humidity", 0),
                "pressure": sensor_data.get("pressure", 0),
                "movement": sensor_data.get("movement", 0),
                "persons": sensor_data.get("persons", 0),
            }
            
            result = self.db.sensor_data.insert_one(data)
            return True, str(result.inserted_id)
        except Exception as e:
            print(f"[ERROR] Failed to store sensor data: {e}")
            return False, str(e)
    
    def get_latest_sensor_data(self, limit: int = 1) -> List[Dict]:
        """Get latest sensor readings"""
        try:
            data = list(self.db.sensor_data.find().sort("timestamp", -1).limit(limit))
            
            # Convert ObjectId to string for JSON serialization
            for doc in data:
                doc['_id'] = str(doc['_id'])
                doc['timestamp'] = doc['timestamp'].isoformat()
            
            return data
        except Exception as e:
            print(f"[ERROR] Failed to fetch sensor data: {e}")
            return []
    
    def get_sensor_data_range(self, minutes: int = 60) -> List[Dict]:
        """Get sensor data from last N minutes"""
        try:
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            data = list(self.db.sensor_data.find({
                "timestamp": {"$gte": cutoff_time}
            }).sort("timestamp", -1))
            
            for doc in data:
                doc['_id'] = str(doc['_id'])
                doc['timestamp'] = doc['timestamp'].isoformat()
            
            return data
        except Exception as e:
            print(f"[ERROR] Failed to fetch sensor data range: {e}")
            return []
    
    def get_sensor_data_stats(self, minutes: int = 60) -> Dict:
        """Get statistical summary of sensor data"""
        try:
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            data = list(self.db.sensor_data.find({
                "timestamp": {"$gte": cutoff_time}
            }))
            
            if not data:
                return {}
            
            temps = [d['temperature'] for d in data]
            hums = [d['humidity'] for d in data]
            pressures = [d['pressure'] for d in data]
            
            import statistics
            
            return {
                "temperature": {
                    "avg": statistics.mean(temps),
                    "min": min(temps),
                    "max": max(temps),
                    "std": statistics.stdev(temps) if len(temps) > 1 else 0
                },
                "humidity": {
                    "avg": statistics.mean(hums),
                    "min": min(hums),
                    "max": max(hums),
                    "std": statistics.stdev(hums) if len(hums) > 1 else 0
                },
                "pressure": {
                    "avg": statistics.mean(pressures),
                    "min": min(pressures),
                    "max": max(pressures),
                    "std": statistics.stdev(pressures) if len(pressures) > 1 else 0
                },
                "data_points": len(data)
            }
        except Exception as e:
            print(f"[ERROR] Failed to calculate stats: {e}")
            return {}
    
    # ==================== PREDICTIONS ====================
    
    def store_prediction(self, prediction_data: Dict) -> Tuple[bool, str]:
        """Store prediction with current timestamp"""
        try:
            data = {
                "timestamp": datetime.now(),
                "prediction_time": datetime.now(),
                "temperature": prediction_data.get("temperature", 0),
                "humidity": prediction_data.get("humidity", 0),
                "pressure": prediction_data.get("pressure", 0),
                "movement": prediction_data.get("movement", 0),
                "predicted_temperature": prediction_data.get("prediction", 0),
                "confidence": prediction_data.get("confidence", 0),
                "is_delayed_displayed": False,  # Not yet displayed with delay
            }
            
            result = self.db.predictions.insert_one(data)
            return True, str(result.inserted_id)
        except Exception as e:
            print(f"[ERROR] Failed to store prediction: {e}")
            return False, str(e)
    
    # ==================== DELAYED PREDICTIONS (10-minute delay) ====================
    
    def store_delayed_prediction(self, prediction_data: Dict, delay_minutes: int = 10) -> Tuple[bool, str]:
        """Store prediction for delayed display (10 minutes)"""
        try:
            display_time = datetime.now() + timedelta(minutes=delay_minutes)
            
            data = {
                "timestamp": datetime.now(),
                "display_after": display_time,
                "temperature": prediction_data.get("temperature", 0),
                "humidity": prediction_data.get("humidity", 0),
                "pressure": prediction_data.get("pressure", 0),
                "movement": prediction_data.get("movement", 0),
                "predicted_temperature": prediction_data.get("prediction", 0),
                "confidence": prediction_data.get("confidence", 0),
                "displayed": False,
                "display_time": None,
            }
            
            result = self.db.delayed_predictions.insert_one(data)
            return True, str(result.inserted_id)
        except Exception as e:
            print(f"[ERROR] Failed to store delayed prediction: {e}")
            return False, str(e)
    
    def get_ready_delayed_predictions(self) -> List[Dict]:
        """Get predictions that are ready to be displayed (10 minutes passed)"""
        try:
            now = datetime.now()
            predictions = list(self.db.delayed_predictions.find({
                "display_after": {"$lte": now},
                "displayed": False
            }).sort("display_after", -1))
            
            for doc in predictions:
                doc['_id'] = str(doc['_id'])
                doc['timestamp'] = doc['timestamp'].isoformat()
                doc['display_after'] = doc['display_after'].isoformat()
            
            return predictions
        except Exception as e:
            print(f"[ERROR] Failed to fetch delayed predictions: {e}")
            return []
    
    def mark_delayed_prediction_displayed(self, prediction_id: str) -> bool:
        """Mark a delayed prediction as displayed"""
        try:
            from bson import ObjectId
            result = self.db.delayed_predictions.update_one(
                {"_id": ObjectId(prediction_id)},
                {
                    "$set": {
                        "displayed": True,
                        "display_time": datetime.now()
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"[ERROR] Failed to mark prediction as displayed: {e}")
            return False
    
    def get_latest_predictions(self, limit: int = 10) -> List[Dict]:
        """Get latest predictions"""
        try:
            data = list(self.db.predictions.find().sort("timestamp", -1).limit(limit))
            
            for doc in data:
                doc['_id'] = str(doc['_id'])
                doc['timestamp'] = doc['timestamp'].isoformat()
                doc['prediction_time'] = doc['prediction_time'].isoformat()
            
            return data
        except Exception as e:
            print(f"[ERROR] Failed to fetch predictions: {e}")
            return []
    
    def get_predictions_range(self, minutes: int = 60) -> List[Dict]:
        """Get predictions from last N minutes"""
        try:
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            data = list(self.db.predictions.find({
                "timestamp": {"$gte": cutoff_time}
            }).sort("timestamp", -1))
            
            for doc in data:
                doc['_id'] = str(doc['_id'])
                doc['timestamp'] = doc['timestamp'].isoformat()
                doc['prediction_time'] = doc['prediction_time'].isoformat()
            
            return data
        except Exception as e:
            print(f"[ERROR] Failed to fetch predictions range: {e}")
            return []
    
    # ==================== CLEANUP ====================
    
    def cleanup_old_data(self, days: int = 30) -> bool:
        """Delete sensor data older than N days"""
        try:
            cutoff_time = datetime.now() - timedelta(days=days)
            
            sensor_result = self.db.sensor_data.delete_many({
                "timestamp": {"$lt": cutoff_time}
            })
            
            pred_result = self.db.predictions.delete_many({
                "timestamp": {"$lt": cutoff_time}
            })
            
            print(f"[INFO] Cleaned up {sensor_result.deleted_count} sensor records and {pred_result.deleted_count} predictions")
            return True
        except Exception as e:
            print(f"[ERROR] Cleanup failed: {e}")
            return False
    
    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            print("[INFO] MongoDB connection closed")


# Firebase Firestore alternative
class FirebaseManager:
    """Firebase Firestore manager for sensor data and predictions"""
    
    def __init__(self, credentials_path: str = None):
        """
        Initialize Firebase connection
        
        Args:
            credentials_path: Path to Firebase service account JSON
        """
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError:
            print("[ERROR] firebase-admin not installed. Install with: pip install firebase-admin")
            self.db = None
            return
        
        try:
            if credentials_path is None:
                credentials_path = os.getenv("FIREBASE_CREDENTIALS", "firebase-credentials.json")
            
            if not os.path.exists(credentials_path):
                print(f"[ERROR] Firebase credentials not found at {credentials_path}")
                self.db = None
                return
            
            cred = credentials.Certificate("API/microcontrolleur-c05ca-firebase-adminsdk-fbsvc-319765e201.json")
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            print("[INFO] ✓ Firebase Firestore connected successfully!")
        except Exception as e:
            print(f"[ERROR] Firebase connection error: {e}")
            self.db = None
    
    def store_sensor_data(self, sensor_data: Dict) -> Tuple[bool, str]:
        """Store sensor data in Firebase"""
        if not self.db:
            return False, "Firebase not connected"
        
        try:
            data = {
                "timestamp": datetime.now(),
                "temperature": sensor_data.get("temperature", 0),
                "humidity": sensor_data.get("humidity", 0),
                "pressure": sensor_data.get("pressure", 0),
                "movement": sensor_data.get("movement", 0),
                "persons": sensor_data.get("persons", 0),
            }
            
            ref = self.db.collection("sensor_data").document()
            ref.set(data)
            return True, ref.id
        except Exception as e:
            print(f"[ERROR] Failed to store sensor data: {e}")
            return False, str(e)
    
    def store_delayed_prediction(self, prediction_data: Dict, delay_minutes: int = 10) -> Tuple[bool, str]:
        """Store prediction for delayed display"""
        if not self.db:
            return False, "Firebase not connected"
        
        try:
            display_time = datetime.now() + timedelta(minutes=delay_minutes)
            
            data = {
                "timestamp": datetime.now(),
                "display_after": display_time,
                "temperature": prediction_data.get("temperature", 0),
                "humidity": prediction_data.get("humidity", 0),
                "pressure": prediction_data.get("pressure", 0),
                "movement": prediction_data.get("movement", 0),
                "predicted_temperature": prediction_data.get("prediction", 0),
                "confidence": prediction_data.get("confidence", 0),
                "displayed": False,
                "display_time": None,
            }
            
            ref = self.db.collection("delayed_predictions").document()
            ref.set(data)
            return True, ref.id
        except Exception as e:
            print(f"[ERROR] Failed to store delayed prediction: {e}")
            return False, str(e)
    
    def get_ready_delayed_predictions(self) -> List[Dict]:
        """Get predictions ready to display"""
        if not self.db:
            return []
        
        try:
            now = datetime.now()
            docs = self.db.collection("delayed_predictions").where(
                "display_after", "<=", now
            ).where(
                "displayed", "==", False
            ).stream()
            
            predictions = []
            for doc in docs:
                data = doc.to_dict()
                data['_id'] = doc.id
                predictions.append(data)
            
            return predictions
        except Exception as e:
            print(f"[ERROR] Failed to fetch delayed predictions: {e}")
            return []
    
    def mark_delayed_prediction_displayed(self, prediction_id: str) -> bool:
        """Mark prediction as displayed"""
        if not self.db:
            return False
        
        try:
            self.db.collection("delayed_predictions").document(prediction_id).update({
                "displayed": True,
                "display_time": datetime.now()
            })
            return True
        except Exception as e:
            print(f"[ERROR] Failed to mark prediction as displayed: {e}")
            return False
