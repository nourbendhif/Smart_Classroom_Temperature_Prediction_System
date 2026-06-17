# scheduler_manager.py - Schedule manager for minute-based data collection and predictions
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from typing import Callable, Optional
import logging
import atexit

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SchedulerManager:
    """Manages scheduled tasks for sensor data and predictions"""
    
    def __init__(self):
        """Initialize the scheduler"""
        self.scheduler = BackgroundScheduler()
        self.jobs = {}
        
        # Register scheduler cleanup on exit
        atexit.register(self.shutdown)
    
    def start(self):
        """Start the scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            print("[INFO] ✓ Scheduler started!")
        else:
            print("[INFO] Scheduler already running")
    
    def shutdown(self):
        """Shutdown the scheduler gracefully"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            print("[INFO] Scheduler shutdown complete")
    
    def add_minute_job(
        self,
        func: Callable,
        job_id: str,
        interval_minutes: int = 1,
        args: tuple = None,
        kwargs: dict = None
    ) -> bool:
        """
        Add a job that runs every N minutes
        
        Args:
            func: Function to run
            job_id: Unique identifier for the job
            interval_minutes: Interval in minutes (default 1)
            args: Positional arguments for function
            kwargs: Keyword arguments for function
        
        Returns:
            bool: Success status
        """
        try:
            if job_id in self.jobs:
                print(f"[WARNING] Job {job_id} already exists, removing old job")
                self.remove_job(job_id)
            
            job = self.scheduler.add_job(
                func,
                IntervalTrigger(minutes=interval_minutes),
                id=job_id,
                args=args or (),
                kwargs=kwargs or {},
                replace_existing=True,
                misfire_grace_time=60
            )
            
            self.jobs[job_id] = job
            print(f"[INFO] ✓ Job '{job_id}' scheduled every {interval_minutes} minute(s)")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to add job '{job_id}': {e}")
            return False
    
    def add_immediate_job(
        self,
        func: Callable,
        job_id: str,
        args: tuple = None,
        kwargs: dict = None
    ) -> bool:
        """
        Add a job that runs immediately
        
        Args:
            func: Function to run
            job_id: Unique identifier for the job
            args: Positional arguments
            kwargs: Keyword arguments
        
        Returns:
            bool: Success status
        """
        try:
            from apscheduler.triggers.date import DateTrigger
            from datetime import datetime
            
            job = self.scheduler.add_job(
                func,
                DateTrigger(run_date=datetime.now()),
                id=job_id,
                args=args or (),
                kwargs=kwargs or {},
                replace_existing=True
            )
            
            self.jobs[job_id] = job
            print(f"[INFO] ✓ Job '{job_id}' scheduled for immediate execution")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to add immediate job '{job_id}': {e}")
            return False
    
    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job"""
        try:
            self.scheduler.remove_job(job_id)
            if job_id in self.jobs:
                del self.jobs[job_id]
            print(f"[INFO] Job '{job_id}' removed")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to remove job '{job_id}': {e}")
            return False
    
    def pause_job(self, job_id: str) -> bool:
        """Pause a scheduled job"""
        try:
            job = self.scheduler.get_job(job_id)
            if job:
                job.pause()
                print(f"[INFO] Job '{job_id}' paused")
                return True
            return False
        except Exception as e:
            print(f"[ERROR] Failed to pause job '{job_id}': {e}")
            return False
    
    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job"""
        try:
            job = self.scheduler.get_job(job_id)
            if job:
                job.resume()
                print(f"[INFO] Job '{job_id}' resumed")
                return True
            return False
        except Exception as e:
            print(f"[ERROR] Failed to resume job '{job_id}': {e}")
            return False
    
    def get_job_info(self, job_id: str) -> dict:
        """Get information about a job"""
        try:
            job = self.scheduler.get_job(job_id)
            if job:
                return {
                    'id': job.id,
                    'name': job.name,
                    'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                    'paused': job.paused,
                    'trigger': str(job.trigger)
                }
            return {}
        except Exception as e:
            print(f"[ERROR] Failed to get job info: {e}")
            return {}
    
    def list_jobs(self) -> list:
        """List all scheduled jobs"""
        jobs_list = []
        for job in self.scheduler.get_jobs():
            jobs_list.append({
                'id': job.id,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'paused': job.paused
            })
        return jobs_list
    
    def is_running(self) -> bool:
        """Check if scheduler is running"""
        return self.scheduler.running


class SensorDataCollector:
    """Collects sensor data every minute and stores to database"""
    
    def __init__(self, db_manager, sensor_history_list: list):
        """
        Initialize collector
        
        Args:
            db_manager: MongoDB or Firebase manager instance
            sensor_history_list: Reference to sensor history list
        """
        self.db = db_manager
        self.sensor_history = sensor_history_list
        self.collection_count = 0
    
    def collect_minute_data(self):
        """Collect current sensor data and store to MongoDB"""
        if not self.sensor_history:
            print("[INFO] No sensor data to collect yet")
            return
        
        try:
            # Get latest sensor reading
            latest = self.sensor_history[-1]
            
            sensor_data = {
                "temperature": latest.get('temp', 0),
                "humidity": latest.get('hum', 0),
                "pressure": latest.get('pressure', 0),
                "movement": latest.get('movement', 0),
                "persons": 0,  # Will be updated from global_persons
            }
            
            success, data_id = self.db.store_sensor_data(sensor_data)
            
            if success:
                self.collection_count += 1
                print(f"[COLLECTOR] ✓ Sensor data stored (#{self.collection_count}) - "
                      f"Temp: {sensor_data['temperature']}°C, "
                      f"Humidity: {sensor_data['humidity']}%")
            else:
                print(f"[COLLECTOR] ✗ Failed to store sensor data: {data_id}")
        
        except Exception as e:
            print(f"[ERROR] Sensor data collection error: {e}")
            import traceback
            traceback.print_exc()


class PredictionScheduler:
    """Makes predictions every minute and stores with 10-minute delay"""
    
    def __init__(self, db_manager, app_predict_func, sensor_history_list: list):
        """
        Initialize predictor
        
        Args:
            db_manager: MongoDB or Firebase manager instance
            app_predict_func: Function to make predictions
            sensor_history_list: Reference to sensor history list
        """
        self.db = db_manager
        self.predict_func = app_predict_func
        self.sensor_history = sensor_history_list
        self.prediction_count = 0
        self.delayed_count = 0
    
    def make_minute_prediction(self):
        """Make prediction every minute and store with 10-minute delay"""
        if not self.sensor_history:
            print("[INFO] No sensor data for prediction yet")
            return
        
        try:
            # Get latest sensor reading
            latest = self.sensor_history[-1]
            
            # Call the prediction function (will update predictions_history)
            prediction_result = self.predict_func(
                temp=latest.get('temp', 0),
                hum=latest.get('hum', 0),
                pressure=latest.get('pressure', 0),
                movement=latest.get('movement', 0)
            )
            
            if prediction_result:
                # Store prediction with 10-minute delay
                success, pred_id = self.db.store_delayed_prediction(
                    prediction_data=prediction_result,
                    delay_minutes=10
                )
                
                if success:
                    self.prediction_count += 1
                    self.delayed_count += 1
                    print(f"[PREDICTOR] ✓ Prediction stored (#{self.prediction_count}) - "
                          f"Predicted Temp: {prediction_result.get('prediction', 0):.2f}°C "
                          f"(will display in 10 min)")
                else:
                    print(f"[PREDICTOR] ✗ Failed to store prediction: {pred_id}")
        
        except Exception as e:
            print(f"[ERROR] Prediction error: {e}")
            import traceback
            traceback.print_exc()


class DelayedPredictionDisplay:
    """Handles displaying predictions after 10-minute delay"""
    
    def __init__(self, db_manager):
        """
        Initialize delayed display handler
        
        Args:
            db_manager: MongoDB or Firebase manager instance
        """
        self.db = db_manager
        self.display_count = 0
        self.ready_predictions = []
    
    def check_ready_predictions(self):
        """Check for predictions ready to display"""
        try:
            ready = self.db.get_ready_delayed_predictions()
            
            if ready:
                self.display_count += len(ready)
                print(f"[DISPLAY] ✓ {len(ready)} prediction(s) ready to display!")
                
                for pred in ready:
                    print(f"  - Pred at {pred['timestamp']}: "
                          f"{pred['predicted_temperature']:.2f}°C "
                          f"(confidence: {pred['confidence']}%)")
                    
                    # Mark as displayed
                    self.db.mark_delayed_prediction_displayed(pred['_id'])
                
                self.ready_predictions = ready
            
            return ready
        
        except Exception as e:
            print(f"[ERROR] Failed to check delayed predictions: {e}")
            return []
    
    def get_latest_ready_predictions(self, limit: int = 5) -> list:
        """Get latest predictions ready for display"""
        return self.ready_predictions[-limit:] if self.ready_predictions else []
