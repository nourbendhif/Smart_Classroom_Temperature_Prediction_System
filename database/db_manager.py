# db_manager.py - SQLite Database Manager for RFID IDs
import sqlite3
import os
from datetime import datetime
from typing import List, Tuple, Optional, Dict

class RFIDDatabase:
    """Database manager for storing and managing RFID IDs"""
    
    def __init__(self, db_path="rfid_database.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create RFID IDs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rfid_ids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfid_code TEXT UNIQUE NOT NULL,
                person_name TEXT NOT NULL,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Create scan history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scan_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfid_code TEXT NOT NULL,
                person_name TEXT,
                scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                scan_status TEXT DEFAULT 'success',
                FOREIGN KEY (rfid_code) REFERENCES rfid_ids(rfid_code)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_rfid(self, rfid_code: str, person_name: str) -> Tuple[bool, str]:
        """Add new RFID ID to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO rfid_ids (rfid_code, person_name)
                VALUES (?, ?)
            ''', (rfid_code.strip(), person_name.strip()))
            
            conn.commit()
            conn.close()
            return True, f"RFID {rfid_code} added successfully"
        except sqlite3.IntegrityError:
            return False, f"RFID {rfid_code} already exists"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def remove_rfid(self, rfid_code: str) -> Tuple[bool, str]:
        """Remove RFID ID from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM rfid_ids WHERE rfid_code = ?', (rfid_code,))
            
            if cursor.rowcount == 0:
                conn.close()
                return False, f"RFID {rfid_code} not found"
            
            conn.commit()
            conn.close()
            return True, f"RFID {rfid_code} removed successfully"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def update_rfid(self, rfid_code: str, person_name: str) -> Tuple[bool, str]:
        """Update RFID person name"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE rfid_ids SET person_name = ? WHERE rfid_code = ?
            ''', (person_name.strip(), rfid_code.strip()))
            
            if cursor.rowcount == 0:
                conn.close()
                return False, f"RFID {rfid_code} not found"
            
            conn.commit()
            conn.close()
            return True, f"RFID {rfid_code} updated successfully"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def verify_rfid(self, rfid_code: str) -> Tuple[bool, Optional[str]]:
        """Verify if RFID exists and is active"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT person_name FROM rfid_ids 
                WHERE rfid_code = ? AND is_active = 1
            ''', (rfid_code,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return True, result[0]
            return False, None
        except Exception as e:
            print(f"Error verifying RFID: {str(e)}")
            return False, None
    
    def get_all_rfids(self) -> List[Dict]:
        """Get all RFID IDs from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, rfid_code, person_name, added_date, is_active 
                FROM rfid_ids ORDER BY added_date DESC
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            return [
                {
                    'id': row[0],
                    'rfid_code': row[1],
                    'person_name': row[2],
                    'added_date': row[3],
                    'is_active': bool(row[4])
                }
                for row in results
            ]
        except Exception as e:
            print(f"Error fetching RFIDs: {str(e)}")
            return []
    
    def toggle_rfid_status(self, rfid_code: str) -> Tuple[bool, str]:
        """Toggle RFID active/inactive status"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE rfid_ids SET is_active = NOT is_active 
                WHERE rfid_code = ?
            ''', (rfid_code,))
            
            if cursor.rowcount == 0:
                conn.close()
                return False, f"RFID {rfid_code} not found"
            
            conn.commit()
            conn.close()
            return True, f"RFID {rfid_code} status toggled"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def add_scan_history(self, rfid_code: str, scan_status: str = "success") -> None:
        """Log RFID scan to history"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get person name
            cursor.execute('SELECT person_name FROM rfid_ids WHERE rfid_code = ?', (rfid_code,))
            result = cursor.fetchone()
            person_name = result[0] if result else "Unknown"
            
            cursor.execute('''
                INSERT INTO scan_history (rfid_code, person_name, scan_status)
                VALUES (?, ?, ?)
            ''', (rfid_code, person_name, scan_status))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error adding scan history: {str(e)}")
    
    def get_scan_history(self, limit: int = 100) -> List[Dict]:
        """Get recent scan history"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT rfid_code, person_name, scan_time, scan_status 
                FROM scan_history ORDER BY scan_time DESC LIMIT ?
            ''', (limit,))
            
            results = cursor.fetchall()
            conn.close()
            
            return [
                {
                    'rfid_code': row[0],
                    'person_name': row[1],
                    'scan_time': row[2],
                    'scan_status': row[3]
                }
                for row in results
            ]
        except Exception as e:
            print(f"Error fetching scan history: {str(e)}")
            return []

# Global database instance
db = RFIDDatabase()
