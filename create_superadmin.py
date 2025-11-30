#!/usr/bin/env python
"""
Script to create a super admin user in the HMS database
This runs automatically on app startup and can also be run manually.
Usage: python create_superadmin.py
"""

from app import create_app, db, User, Hospital
import uuid
import sys

def init_superadmin(app=None, verbose=True):
    """
    Initialize super admin user with test credentials.
    
    Args:
        app: Flask app instance (optional, creates one if not provided)
        verbose: Print status messages (default: True)
    
    Returns:
        bool: True if successful, False otherwise
    """
    if app is None:
        app = create_app()
    
    with app.app_context():
        try:
            # Create all tables
            db.create_all()
            if verbose:
                print("✓ Database tables created/verified")
            
            # Check if hospital exists
            hospital = Hospital.query.first()
            
            if not hospital:
                if verbose:
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
                if verbose:
                    print(f"✓ Hospital created: {hospital.name} (ID: {hospital.id})")
            else:
                if verbose:
                    print(f"✓ Using existing hospital: {hospital.name}")
            
            # Check if user already exists
            existing_user = User.query.filter_by(email="superadmin@test.com").first()
            
            if existing_user:
                if verbose:
                    print("✓ User 'superadmin@test.com' already exists. Skipping insertion.")
                return True
            else:
                if verbose:
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
                if verbose:
                    print("✓ Super admin user created successfully")
            
            # Print credentials only if verbose
            if verbose:
                print("\n" + "="*50)
                print("LOGIN CREDENTIALS")
                print("="*50)
                print(f"Email:    superadmin@test.com")
                print(f"Password: Test@123")
                print("="*50 + "\n")
            
            return True
            
        except Exception as e:
            if verbose:
                print(f"✗ Error: {str(e)}", file=sys.stderr)
            db.session.rollback()
            return False

if __name__ == '__main__':
    success = init_superadmin()
    sys.exit(0 if success else 1)
