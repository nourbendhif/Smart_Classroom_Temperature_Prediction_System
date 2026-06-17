# email_manager.py - Email verification and notification manager
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import secrets
import hashlib

load_dotenv()

class EmailManager:
    """Handle email verification and notifications"""
    
    def __init__(self):
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.sender_password = os.getenv('SENDER_PASSWORD')
        self.app_url = os.getenv('APP_URL', 'http://localhost:5000')
    
    def send_verification_email(self, recipient_email: str, username: str, 
                               verification_token: str) -> bool:
        """
        Send verification email to new user
        
        Args:
            recipient_email: User's email address
            username: Username of the new account
            verification_token: Unique verification token
            
        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.sender_email or not self.sender_password:
            print("[WARNING] Email credentials not configured. Skipping email verification.")
            return False
        
        try:
            # Create verification link
            verify_link = f"{self.app_url}/verify-email?token={verification_token}"
            
            # Prepare email content
            subject = "Email Verification - RFID Temperature Prediction System"
            
            html_body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <p>Hi <strong>{username}</strong>,</p>
                        
                        <p>Thank you for creating an account. To complete your registration and verify your email address, 
                        please click the button below:</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{verify_link}" style="display: inline-block; padding: 12px 30px; 
                            background-color: #4CAF50; color: white; text-decoration: none; border-radius: 5px; 
                            font-weight: bold;">Verify Email</a>
                        </div>
                        
                        <p style="color: #666;">Or copy and paste this link in your browser:</p>
                        <p style="background-color: #f5f5f5; padding: 10px; border-left: 4px solid #4CAF50; 
                        word-break: break-all; color: #666;">{verify_link}</p>
                        
                        <p style="color: #999; font-size: 12px; margin-top: 30px;">
                            This verification link will expire in 24 hours.<br>
                            If you did not create this account, please ignore this email.
                        </p>
                    </div>
                </body>
            </html>
            """
            
            # Create email message
            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = self.sender_email
            message['To'] = recipient_email
            
            # Attach plain text and HTML versions
            text_body = f"""
            Hi {username},
            
            Thank you for creating an account. To complete your registration and verify your email address, 
            please visit the following link:
            
            {verify_link}
            
            This verification link will expire in 24 hours.
            
            If you did not create this account, please ignore this email.
            """
            
            part1 = MIMEText(text_body, 'plain')
            part2 = MIMEText(html_body, 'html')
            
            message.attach(part1)
            message.attach(part2)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(message)
            
            print(f"[EMAIL] Verification email sent to {recipient_email}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to send verification email: {e}")
            return False
    
    def send_password_reset_email(self, recipient_email: str, username: str, 
                                  reset_token: str) -> bool:
        """Send password reset email"""
        if not self.sender_email or not self.sender_password:
            print("[WARNING] Email credentials not configured. Skipping password reset email.")
            return False
        
        try:
            reset_link = f"{self.app_url}/reset-password?token={reset_token}"
            
            subject = "Password Reset - RFID Temperature Prediction System"
            
            html_body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #FF9800;">Password Reset Request</h2>
                        
                        <p>Hi <strong>{username}</strong>,</p>
                        
                        <p>We received a request to reset your password. Click the button below to set a new password:</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{reset_link}" style="display: inline-block; padding: 12px 30px; 
                            background-color: #FF9800; color: white; text-decoration: none; border-radius: 5px; 
                            font-weight: bold;">Reset Password</a>
                        </div>
                        
                        <p style="color: #666;">Or copy and paste this link in your browser:</p>
                        <p style="background-color: #f5f5f5; padding: 10px; border-left: 4px solid #FF9800; 
                        word-break: break-all; color: #666;">{reset_link}</p>
                        
                        <p style="color: #999; font-size: 12px; margin-top: 30px;">
                            This reset link will expire in 1 hour.<br>
                            If you did not request this reset, please ignore this email.
                        </p>
                    </div>
                </body>
            </html>
            """
            
            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = self.sender_email
            message['To'] = recipient_email
            
            text_body = f"""
            Password Reset Request
            
            Hi {username},
            
            We received a request to reset your password. Visit the following link to set a new password:
            
            {reset_link}
            
            This reset link will expire in 1 hour.
            
            If you did not request this reset, please ignore this email.
            """
            
            part1 = MIMEText(text_body, 'plain')
            part2 = MIMEText(html_body, 'html')
            
            message.attach(part1)
            message.attach(part2)
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(message)
            
            print(f"[EMAIL] Password reset email sent to {recipient_email}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to send password reset email: {e}")
            return False
    
    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def hash_token(token: str) -> str:
        """Hash token for storage"""
        return hashlib.sha256(token.encode()).hexdigest()
