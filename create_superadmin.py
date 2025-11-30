#!/usr/bin/env python
"""
Script to create a super admin user in the HMS database
Usage: python create_superadmin.py
"""

from app import create_app, db, User, Hospital
import uuid
import sys

def create_superadmin():
    """Create a super admin user with test credentials"""
    app = create_app()
    
    with app.app_context():
        try:
            # Create all tables
            db.create_all()
            print("✓ Database tables created/verified")
            
            # Check if hospital exists
            hospital = Hospital.query.first()
            
            if not hospital:
                print("Creating Test Hospital...")
                hospital = Hospital(
                    id=str(uuid.uuid4()),
                    name="Test Hospital",
                    address="123 Test Street, Test City",
                    contact_details="+1-555-0100",
                    license_number="TEST-LIC-001",
                    admin_email="admin@testhospital.com",
                    status="ACTIVE"
                )
                db.session.add(hospital)
                db.session.commit()
                print(f"✓ Hospital created: {hospital.name} (ID: {hospital.id})")
            else:
                print(f"✓ Using existing hospital: {hospital.name}")
            
            # Check if user already exists
            existing_user = User.query.filter_by(email="superadmin@test.com").first()
            
            if existing_user:
                print("User already exists. Updating password...")
                existing_user.set_password("Test@123")
                db.session.commit()
                print("✓ Password updated successfully")
            else:
                print("Creating super admin user...")
                super_admin = User(
                    hospital_id=hospital.id,
                    first_name="Super",
                    last_name="Admin",
                    email="superadmin@test.com"
                )
                super_admin.set_password("Test@123")
                db.session.add(super_admin)
                db.session.commit()
                print("✓ Super admin user created successfully")
            
            # Print credentials
            print("\n" + "="*50)
            print("LOGIN CREDENTIALS")
            print("="*50)
            print(f"Email:    superadmin@test.com")
            print(f"Password: Test@123")
            print("="*50)
            print("\nYou can now login at: http://127.0.0.1:5000/auth/login")
            print("="*50 + "\n")
            
            return True
            
        except Exception as e:
            print(f"✗ Error: {str(e)}", file=sys.stderr)
            db.session.rollback()
            return False

if __name__ == '__main__':
    success = create_superadmin()
    sys.exit(0 if success else 1)
