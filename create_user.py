#!/usr/bin/env python
# Script to create a dummy user in the HMS database

from app import create_app, db, User, Hospital
import uuid

# Create app instance
app = create_app()

with app.app_context():
    # First, create a dummy hospital if it doesn't exist
    hospital = Hospital.query.first()
    
    if not hospital:
        print("Creating dummy hospital...")
        hospital = Hospital(
            id=str(uuid.uuid4()),
            name="Test Hospital",
            address="123 Test St, Test City",
            contact_details="+1-555-0100",
            license_number="TEST-LIC-001",
            admin_email="admin@testhospital.com",
            status="ACTIVE"
        )
        db.session.add(hospital)
        db.session.commit()
        print(f"Hospital created with ID: {hospital.id}")
    else:
        print(f"Using existing hospital: {hospital.name}")
    
    # Check if user already exists
    existing_user = User.query.filter_by(email="superadmin@test.com").first()
    
    if existing_user:
        print("User already exists. Updating password...")
        existing_user.set_password("Test@123")
        db.session.commit()
        print("✓ User password updated successfully!")
    else:
        print("Creating new user...")
        new_user = User(
            hospital_id=hospital.id,
            first_name="Super",
            last_name="Admin",
            email="superadmin@test.com"
        )
        new_user.set_password("Test@123")
        db.session.add(new_user)
        db.session.commit()
        print("✓ Dummy user created successfully!")
    
    print("\nUser Details:")
    print(f"  Email: superadmin@test.com")
    print(f"  Password: Test@123")
    print(f"\nYou can now login at http://127.0.0.1:5000/auth/login")
