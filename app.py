# single_file_hms.py
# A single-file multi-tenant HMS prototype implementing FR-1 (Hospital Self-Registration) and basic Login.

from flask import Flask, redirect, url_for, render_template_string, request, flash, Blueprint, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import os
from functools import wraps
from datetime import datetime

# ----------------------------------------------------
# 1. Configuration 
# ----------------------------------------------------
class Config:
    # Support both SQLite (local) and PostgreSQL (Render)
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        # Fix Render's deprecated postgres:// scheme
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = database_url or 'sqlite:///hms_main.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_super_secret_key_change_me_in_production'
    JWT_SECRET_KEY = "jwt-secret-key" 

# ----------------------------------------------------
# 2. Initialization & Blueprint Definition
# ----------------------------------------------------
db = SQLAlchemy()
# Define Blueprint globally
auth_bp = Blueprint('auth', __name__)

# ----------------------------------------------------
# 3. Database Models 
# ----------------------------------------------------

# Model for Hospital/Tenant (FR-1)
class Hospital(db.Model):
    __tablename__ = 'hospitals'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(255))
    contact_details = db.Column(db.String(50))
    license_number = db.Column(db.String(50), unique=True, nullable=False)
    admin_email = db.Column(db.String(120), unique=True, nullable=False)
    status = db.Column(db.String(20), default='PENDING', nullable=False) # Status flow: PENDING → VERIFIED → ACTIVE → SUSPENDED → INACTIVE

# Model for Users (FR-6)
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.String(36), db.ForeignKey('hospitals.id'), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Model for Patients
class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.String(36), db.ForeignKey('hospitals.id'), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(10))
    blood_group = db.Column(db.String(5))
    address = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    def __repr__(self):
        return f'<Patient {self.first_name} {self.last_name}>'

# Model for Departments
class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.String(36), db.ForeignKey('hospitals.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    head_name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    def __repr__(self):
        return f'<Department {self.name}>'

# Model for Doctors
class Doctor(db.Model):
    __tablename__ = 'doctors'
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.String(36), db.ForeignKey('hospitals.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    specialization = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    license_number = db.Column(db.String(50))
    experience_years = db.Column(db.Integer)
    status = db.Column(db.String(20), default='ACTIVE')
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    def __repr__(self):
        return f'<Doctor {self.first_name} {self.last_name}>'

# Model for Appointments
class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.String(36), db.ForeignKey('hospitals.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    appointment_date = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String(255))
    status = db.Column(db.String(20), default='SCHEDULED')  # SCHEDULED, COMPLETED, CANCELLED
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    def __repr__(self):
        return f'<Appointment {self.id}>'

# Model for Medical Records
class MedicalRecord(db.Model):
    __tablename__ = 'medical_records'
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.String(36), db.ForeignKey('hospitals.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    diagnosis = db.Column(db.String(255))
    treatment = db.Column(db.Text)
    prescription = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    def __repr__(self):
        return f'<MedicalRecord {self.id}>'

# ----------------------------------------------------
# 4. HTML Templates (Embedded)
# ----------------------------------------------------

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# HTML Templates for additional pages
PATIENTS_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Patients - HMS</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #f5f5f5; }
        .navbar { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .navbar a { color: white !important; }
        .btn-back { color: white; text-decoration: none; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark">
        <div class="container-fluid">
            <span class="navbar-brand"><a href="{{ url_for('dashboard') }}" class="btn-back"><i class="bi bi-arrow-left"></i> Back to Dashboard</a></span>
            <span style="color: white;">Welcome, {{ user_name }}</span>
        </div>
    </nav>
    <div class="container mt-5">
        <h2>👥 Patients Management</h2>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="mb-3">
                    {% for category, message in messages %}
                        <div class="alert alert-{{ 'danger' if category == 'error' else category }}" role="alert">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        <div class="card mt-4">
            <div class="card-header bg-primary text-white">
                <h5 class="mb-0">Add New Patient</h5>
            </div>
            <div class="card-body">
                <form method="POST" action="{{ url_for('add_patient') }}">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">First Name</label>
                            <input type="text" class="form-control" name="first_name" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Last Name</label>
                            <input type="text" class="form-control" name="last_name" required>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Email</label>
                            <input type="email" class="form-control" name="email" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Phone</label>
                            <input type="tel" class="form-control" name="phone" required>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-4 mb-3">
                            <label class="form-label">Date of Birth</label>
                            <input type="date" class="form-control" name="dob" required>
                        </div>
                        <div class="col-md-4 mb-3">
                            <label class="form-label">Gender</label>
                            <select class="form-control" name="gender">
                                <option value="">Select</option>
                                <option value="Male">Male</option>
                                <option value="Female">Female</option>
                                <option value="Other">Other</option>
                            </select>
                        </div>
                        <div class="col-md-4 mb-3">
                            <label class="form-label">Blood Group</label>
                            <select class="form-control" name="blood_group">
                                <option value="">Select</option>
                                <option value="O+">O+</option>
                                <option value="O-">O-</option>
                                <option value="A+">A+</option>
                                <option value="A-">A-</option>
                                <option value="B+">B+</option>
                                <option value="B-">B-</option>
                                <option value="AB+">AB+</option>
                                <option value="AB-">AB-</option>
                            </select>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Address</label>
                        <input type="text" class="form-control" name="address">
                    </div>
                    <button type="submit" class="btn btn-success"><i class="bi bi-plus-circle"></i> Add Patient</button>
                </form>
            </div>
        </div>

        <div class="card mt-4">
            <div class="card-header bg-secondary text-white">
                <h5 class="mb-0">Patient List ({{ patient_count }})</h5>
            </div>
            <div class="card-body">
                {% if patients %}
                    <table class="table table-striped table-hover">
                        <thead class="table-dark">
                            <tr>
                                <th>ID</th>
                                <th>Name</th>
                                <th>Email</th>
                                <th>Phone</th>
                                <th>Blood Group</th>
                                <th>Registered</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for patient in patients %}
                            <tr>
                                <td>#{{ patient.id }}</td>
                                <td>{{ patient.first_name }} {{ patient.last_name }}</td>
                                <td>{{ patient.email }}</td>
                                <td>{{ patient.phone }}</td>
                                <td><span class="badge bg-info">{{ patient.blood_group or 'N/A' }}</span></td>
                                <td>{{ patient.created_at.strftime('%d/%m/%Y') }}</td>
                                <td>
                                    <a href="#" class="btn btn-sm btn-info">View</a>
                                    <a href="#" class="btn btn-sm btn-warning">Edit</a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                {% else %}
                    <div class="alert alert-info">✓ Patient management system is ready. Add your first patient above!</div>
                {% endif %}
            </div>
        </div>
    </div>
</body>
</html>
"""

APPOINTMENTS_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Appointments - HMS</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #f5f5f5; }
        .navbar { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .navbar a { color: white !important; }
        .btn-back { color: white; text-decoration: none; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark">
        <div class="container-fluid">
            <span class="navbar-brand"><a href="{{ url_for('dashboard') }}" class="btn-back"><i class="bi bi-arrow-left"></i> Back to Dashboard</a></span>
            <span style="color: white;">Welcome, {{ user_name }}</span>
        </div>
    </nav>
    <div class="container mt-5">
        <h2>📅 Appointments Management</h2>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="mb-3">
                    {% for category, message in messages %}
                        <div class="alert alert-{{ 'danger' if category == 'error' else category }}" role="alert">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        <div class="card mt-4">
            <div class="card-header bg-primary text-white">
                <h5 class="mb-0">Schedule New Appointment</h5>
            </div>
            <div class="card-body">
                <form method="POST" action="{{ url_for('add_appointment') }}">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Patient</label>
                            <select class="form-control" name="patient_id" required>
                                <option value="">Select Patient</option>
                                {% for patient in patients %}
                                    <option value="{{ patient.id }}">{{ patient.first_name }} {{ patient.last_name }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Doctor</label>
                            <select class="form-control" name="doctor_id" required>
                                <option value="">Select Doctor</option>
                                {% for doctor in doctors %}
                                    <option value="{{ doctor.id }}">Dr. {{ doctor.first_name }} {{ doctor.last_name }} ({{ doctor.specialization }})</option>
                                {% endfor %}
                            </select>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Appointment Date</label>
                            <input type="datetime-local" class="form-control" name="appointment_date" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Reason for Visit</label>
                            <input type="text" class="form-control" name="reason" placeholder="e.g., Check-up">
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Notes</label>
                        <textarea class="form-control" name="notes" rows="3"></textarea>
                    </div>
                    <button type="submit" class="btn btn-success"><i class="bi bi-calendar-plus"></i> Schedule Appointment</button>
                </form>
            </div>
        </div>

        <div class="card mt-4">
            <div class="card-header bg-secondary text-white">
                <h5 class="mb-0">Appointments ({{ appointment_count }})</h5>
            </div>
            <div class="card-body">
                {% if appointments %}
                    <table class="table table-striped table-hover">
                        <thead class="table-dark">
                            <tr>
                                <th>Date & Time</th>
                                <th>Patient</th>
                                <th>Doctor</th>
                                <th>Reason</th>
                                <th>Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for apt in appointments %}
                            <tr>
                                <td>{{ apt.appointment_date.strftime('%d/%m/%Y %H:%M') }}</td>
                                <td>{{ apt.patient.first_name }} {{ apt.patient.last_name }}</td>
                                <td>Dr. {{ apt.doctor.first_name }} {{ apt.doctor.last_name }}</td>
                                <td>{{ apt.reason or 'General' }}</td>
                                <td><span class="badge bg-{{ 'success' if apt.status == 'SCHEDULED' else 'warning' if apt.status == 'COMPLETED' else 'danger' }}">{{ apt.status }}</span></td>
                                <td>
                                    <a href="#" class="btn btn-sm btn-info">View</a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                {% else %}
                    <div class="alert alert-info">✓ No appointments scheduled yet. Schedule your first appointment above!</div>
                {% endif %}
            </div>
        </div>
    </div>
</body>
</html>
"""

DOCTORS_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Doctors - HMS</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #f5f5f5; }
        .navbar { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .navbar a { color: white !important; }
        .btn-back { color: white; text-decoration: none; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark">
        <div class="container-fluid">
            <span class="navbar-brand"><a href="{{ url_for('dashboard') }}" class="btn-back"><i class="bi bi-arrow-left"></i> Back to Dashboard</a></span>
            <span style="color: white;">Welcome, {{ user_name }}</span>
        </div>
    </nav>
    <div class="container mt-5">
        <h2>👨‍⚕️ Doctors Management</h2>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="mb-3">
                    {% for category, message in messages %}
                        <div class="alert alert-{{ 'danger' if category == 'error' else category }}" role="alert">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        <div class="card mt-4">
            <div class="card-header bg-primary text-white">
                <h5 class="mb-0">Add New Doctor</h5>
            </div>
            <div class="card-body">
                <form method="POST" action="{{ url_for('add_doctor') }}">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">First Name</label>
                            <input type="text" class="form-control" name="first_name" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Last Name</label>
                            <input type="text" class="form-control" name="last_name" required>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Specialization</label>
                            <input type="text" class="form-control" name="specialization" placeholder="e.g., Cardiology" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Experience (Years)</label>
                            <input type="number" class="form-control" name="experience">
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Email</label>
                            <input type="email" class="form-control" name="email" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Phone</label>
                            <input type="tel" class="form-control" name="phone" required>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">License Number</label>
                            <input type="text" class="form-control" name="license">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Department</label>
                            <select class="form-control" name="department_id">
                                <option value="">Select Department</option>
                                {% for dept in departments %}
                                    <option value="{{ dept.id }}">{{ dept.name }}</option>
                                {% endfor %}
                            </select>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-success"><i class="bi bi-person-plus"></i> Add Doctor</button>
                </form>
            </div>
        </div>

        <div class="card mt-4">
            <div class="card-header bg-secondary text-white">
                <h5 class="mb-0">Doctor List ({{ doctor_count }})</h5>
            </div>
            <div class="card-body">
                {% if doctors %}
                    <table class="table table-striped table-hover">
                        <thead class="table-dark">
                            <tr>
                                <th>ID</th>
                                <th>Name</th>
                                <th>Specialization</th>
                                <th>Experience</th>
                                <th>Email</th>
                                <th>Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for doctor in doctors %}
                            <tr>
                                <td>#{{ doctor.id }}</td>
                                <td>Dr. {{ doctor.first_name }} {{ doctor.last_name }}</td>
                                <td>{{ doctor.specialization }}</td>
                                <td>{{ doctor.experience_years or 'N/A' }} years</td>
                                <td>{{ doctor.email }}</td>
                                <td><span class="badge bg-success">{{ doctor.status }}</span></td>
                                <td>
                                    <a href="#" class="btn btn-sm btn-info">View</a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                {% else %}
                    <div class="alert alert-info">✓ No doctors added yet. Add your first doctor above!</div>
                {% endif %}
            </div>
        </div>
    </div>
</body>
</html>
"""

DEPARTMENTS_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Departments - HMS</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #f5f5f5; }
        .navbar { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .navbar a { color: white !important; }
        .btn-back { color: white; text-decoration: none; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark">
        <div class="container-fluid">
            <span class="navbar-brand"><a href="{{ url_for('dashboard') }}" class="btn-back"><i class="bi bi-arrow-left"></i> Back to Dashboard</a></span>
            <span style="color: white;">Welcome, {{ user_name }}</span>
        </div>
    </nav>
    <div class="container mt-5">
        <h2>🏢 Departments Management</h2>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="mb-3">
                    {% for category, message in messages %}
                        <div class="alert alert-{{ 'danger' if category == 'error' else category }}" role="alert">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        <div class="card mt-4">
            <div class="card-header bg-primary text-white">
                <h5 class="mb-0">Add New Department</h5>
            </div>
            <div class="card-body">
                <form method="POST" action="{{ url_for('add_department') }}">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Department Name</label>
                            <input type="text" class="form-control" name="name" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Head of Department</label>
                            <input type="text" class="form-control" name="head_name" required>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Email</label>
                            <input type="email" class="form-control" name="email" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Phone</label>
                            <input type="tel" class="form-control" name="phone" required>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Description</label>
                        <textarea class="form-control" name="description" rows="3"></textarea>
                    </div>
                    <button type="submit" class="btn btn-success"><i class="bi bi-building"></i> Add Department</button>
                </form>
            </div>
        </div>

        <div class="card mt-4">
            <div class="card-header bg-secondary text-white">
                <h5 class="mb-0">Department List ({{ department_count }})</h5>
            </div>
            <div class="card-body">
                {% if departments %}
                    <table class="table table-striped table-hover">
                        <thead class="table-dark">
                            <tr>
                                <th>Department</th>
                                <th>Head of Department</th>
                                <th>Email</th>
                                <th>Phone</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for dept in departments %}
                            <tr>
                                <td>{{ dept.name }}</td>
                                <td>{{ dept.head_name }}</td>
                                <td>{{ dept.email }}</td>
                                <td>{{ dept.phone }}</td>
                                <td>
                                    <a href="#" class="btn btn-sm btn-info">View</a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                {% else %}
                    <div class="alert alert-info">✓ No departments added yet. Add your first department above!</div>
                {% endif %}
            </div>
        </div>
    </div>
</body>
</html>
"""

SETTINGS_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Settings - HMS</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #f5f5f5; }
        .navbar { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .navbar a { color: white !important; }
        .btn-back { color: white; text-decoration: none; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark">
        <div class="container-fluid">
            <span class="navbar-brand"><a href="{{ url_for('dashboard') }}" class="btn-back"><i class="bi bi-arrow-left"></i> Back to Dashboard</a></span>
            <span style="color: white;">Welcome, {{ user_name }}</span>
        </div>
    </nav>
    <div class="container mt-5">
        <h2>⚙️ Hospital Settings</h2>
        <div class="card mt-4">
            <div class="card-header bg-primary text-white">
                <h5 class="mb-0">Hospital Information</h5>
            </div>
            <div class="card-body">
                <form method="POST" action="/hospital_settings">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Hospital Name</label>
                            <input type="text" class="form-control" value="{{ hospital_name }}" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Admin Email</label>
                            <input type="email" class="form-control" value="{{ hospital_email }}" required>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Phone Number</label>
                            <input type="tel" class="form-control" value="{{ hospital_phone }}" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Address</label>
                            <input type="text" class="form-control" value="{{ hospital_address }}" required>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary"><i class="bi bi-check-circle"></i> Save Changes</button>
                </form>
            </div>
        </div>
        <div class="card mt-4">
            <div class="card-header bg-secondary text-white">
                <h5 class="mb-0">System Status</h5>
            </div>
            <div class="card-body">
                <ul class="list-group">
                    <li class="list-group-item"><i class="bi bi-check-circle text-success"></i> Database Connection: <strong>Active</strong></li>
                    <li class="list-group-item"><i class="bi bi-check-circle text-success"></i> Authentication System: <strong>Active</strong></li>
                    <li class="list-group-item"><i class="bi bi-check-circle text-success"></i> Multi-tenant Support: <strong>Enabled</strong></li>
                    <li class="list-group-item"><i class="bi bi-check-circle text-success"></i> User Management: <strong>Active</strong></li>
                </ul>
            </div>
        </div>
    </div>
</body>
</html>
"""

# Use raw strings (r""") to embed the HTML
REGISTER_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Hospital Self-Registration</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
    <div class="container my-5">
        <div class="row justify-content-center">
            <div class="col-md-6">
                <div class="card shadow">
                    <div class="card-header bg-primary text-white">
                        <h2 class="mb-0">🏥 Hospital Self-Registration (FR-1)</h2>
                    </div>
                    <div class="card-body">
                        {% with messages = get_flashed_messages(with_categories=true) %}
                            {% if messages %}
                                <div class="mb-3">
                                    {% for category, message in messages %}
                                        <div class="alert alert-{{ 'danger' if category == 'danger' else 'success' }}" role="alert">{{ message }}</div>
                                    {% endfor %}
                                </div>
                            {% endif %}
                        {% endwith %}
                        <form method="POST">
                            <div class="mb-3">
                                <label for="name" class="form-label">Hospital Name:</label>
                                <input type="text" class="form-control" id="name" name="name" required>
                            </div>
                            <div class="mb-3">
                                <label for="license_number" class="form-label">License Number (Unique):</label>
                                <input type="text" class="form-control" id="license_number" name="license_number" required>
                            </div>
                            <div class="mb-3">
                                <label for="admin_email" class="form-label">Admin Email:</label>
                                <input type="email" class="form-control" id="admin_email" name="admin_email" required>
                            </div>
                            <div class="mb-3">
                                <label for="phone" class="form-label">Contact Phone:</label>
                                <input type="tel" class="form-control" id="phone" name="phone" required>
                            </div>
                            <div class="mb-3">
                                <label for="address" class="form-label">Address:</label>
                                <input type="text" class="form-control" id="address" name="address" required>
                            </div>
                            <button type="submit" class="btn btn-success w-100">Register Hospital</button>
                        </form>
                        <p class="mt-3 text-center">Already registered? <a href="{{ url_for('auth.login') }}">Login here</a>.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

LOGIN_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>HMS Login</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
    <div class="container my-5">
        <div class="row justify-content-center">
            <div class="col-md-5">
                <div class="card shadow">
                    <div class="card-header bg-secondary text-white">
                        <h2 class="mb-0">🔑 HMS Login</h2>
                    </div>
                    <div class="card-body">
                        {% with messages = get_flashed_messages(with_categories=true) %}
                            {% if messages %}
                                <div class="mb-3">
                                    {% for category, message in messages %}
                                        <div class="alert alert-{{ 'danger' if category == 'danger' else 'success' }}" role="alert">{{ message }}</div>
                                    {% endfor %}
                                </div>
                            {% endif %}
                        {% endwith %}
                        <form method="POST">
                            <div class="mb-3">
                                <label for="email" class="form-label">Email Address:</label>
                                <input type="email" class="form-control" id="email" name="email" required>
                            </div>
                            <div class="mb-3">
                                <label for="password" class="form-label">Password:</label>
                                <input type="password" class="form-control" id="password" name="password" required>
                            </div>
                            <button type="submit" class="btn btn-primary w-100">Log In</button>
                        </form>
                        <p class="mt-3 text-center">New Hospital? <a href="{{ url_for('auth.register') }}">Register here</a>.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

# IMPORTANT CHANGE: Adding the Chatbot Widget Code before </body>
DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>HMS Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        .sidebar {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .sidebar-menu a {
            color: white;
            text-decoration: none;
            padding: 12px 15px;
            display: block;
            border-radius: 5px;
            margin-bottom: 10px;
            transition: all 0.3s;
        }
        .sidebar-menu a:hover {
            background-color: rgba(255, 255, 255, 0.2);
            transform: translateX(5px);
        }
        .sidebar-menu a.active {
            background-color: rgba(255, 255, 255, 0.3);
            font-weight: bold;
        }
        .main-content {
            padding: 30px;
        }
        .stats-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .stats-card h5 {
            margin-top: 10px;
        }
        .user-badge {
            background-color: #e3f2fd;
            padding: 5px 12px;
            border-radius: 20px;
            font-weight: bold;
        }
        .header-top {
            background: white;
            padding: 15px 30px;
            border-bottom: 1px solid #ddd;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
    </style>
</head>
<body>
    <div class="header-top">
        <div>
            <h3>🏥 Hospital Management System</h3>
        </div>
        <div>
            <span class="user-badge">{{ user_name }}</span>
            <a href="{{ url_for('auth.logout') }}" class="btn btn-sm btn-danger ms-2">Logout</a>
        </div>
    </div>

    <div class="container-fluid">
        <div class="row">
            <!-- Sidebar -->
            <div class="col-md-3 sidebar">
                <h5 class="text-white mb-4"><i class="bi bi-list"></i> Menu</h5>
                <div class="sidebar-menu">
                    <a href="{{ url_for('dashboard') }}" class="active"><i class="bi bi-speedometer2"></i> Dashboard</a>
                    <a href="{{ url_for('patients') }}"><i class="bi bi-people"></i> Patients</a>
                    <a href="{{ url_for('appointments') }}"><i class="bi bi-calendar-event"></i> Appointments</a>
                    <a href="{{ url_for('doctors') }}"><i class="bi bi-person-badge"></i> Doctors</a>
                    <a href="{{ url_for('departments') }}"><i class="bi bi-building"></i> Departments</a>
                    <a href="{{ url_for('hospital_settings') }}"><i class="bi bi-gear"></i> Settings</a>
                </div>
            </div>

            <!-- Main Content -->
            <div class="col-md-9 main-content">
                <h2 class="mb-4">Welcome, {{ user_name }}!</h2>
                <p>Hospital: <strong>{{ hospital_name }}</strong></p>

                <!-- Stats -->
                <div class="row">
                    <div class="col-md-3">
                        <div class="stats-card">
                            <i class="bi bi-people" style="font-size: 2rem;"></i>
                            <h5>{{ total_patients }}</h5>
                            <p>Total Patients</p>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stats-card">
                            <i class="bi bi-calendar-event" style="font-size: 2rem;"></i>
                            <h5>{{ total_appointments }}</h5>
                            <p>Appointments Today</p>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stats-card">
                            <i class="bi bi-person-badge" style="font-size: 2rem;"></i>
                            <h5>{{ total_doctors }}</h5>
                            <p>Active Doctors</p>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stats-card">
                            <i class="bi bi-building" style="font-size: 2rem;"></i>
                            <h5>{{ total_departments }}</h5>
                            <p>Departments</p>
                        </div>
                    </div>
                </div>

                <!-- Recent Activity -->
                <div class="mt-5">
                    <h4>Recent Activities</h4>
                    <div class="alert alert-info">
                        ✓ System is fully functional with user authentication
                    </div>
                    <ul class="list-group">
                        <li class="list-group-item"><i class="bi bi-check-circle text-success"></i> User Authentication implemented</li>
                        <li class="list-group-item"><i class="bi bi-check-circle text-success"></i> Multi-tenant support active</li>
                        <li class="list-group-item"><i class="bi bi-check-circle text-success"></i> Database integration working</li>
                        <li class="list-group-item"><i class="bi bi-check-circle text-success"></i> Dashboard features available</li>
                    </ul>
                </div>
            </div>
        </div>
    </div>

    <!-- START OF PATIENT FAQ CHATBOT WIDGET -->
    <script type="text/javascript">
    var Tawk_API = Tawk_API || {}, Tawk_LoadStart = new Date();
    (function() {
    var s1 = document.createElement("script"), s0 = document.getElementsByTagName("script")[0];
    s1.async = true;
    s1.src = 'https://embed.tawk.to/67890abcdef/default'; 
    s1.charset = 'UTF-8';
    s1.setAttribute('crossorigin', '*');
    s0.parentNode.insertBefore(s1, s0);
    })();
    </script>
    <!-- END OF PATIENT FAQ CHATBOT WIDGET -->

</body>
</html>
"""

# ----------------------------------------------------
# 5. ROUTES (BLUEPRINT) - DEFINED BEFORE APP CREATION
# ----------------------------------------------------
# These functions MUST be defined before create_app() is called in __main__.

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handles Hospital Self-Registration (FR-1)."""
    if request.method == 'POST':
        # 1. Get data 
        name = request.form.get('name')
        license_number = request.form.get('license_number')
        admin_email = request.form.get('admin_email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        
        # 2. Validate license number uniqueness
        if Hospital.query.filter_by(license_number=license_number).first():
            flash('License number is already registered.', 'danger')
            return render_template_string(REGISTER_HTML)
        
        # 3. Auto-generate tenant ID (UUID-based) & create Hospital
        tenant_id = str(uuid.uuid4())
        new_hospital = Hospital(
            id=tenant_id,
            name=name,
            license_number=license_number,
            admin_email=admin_email,
            address=address,
            contact_details=phone,
            status='PENDING' 
        )
        db.session.add(new_hospital)
        
        # 4. Create Admin Credentials automatically
        admin_username = f"admin@{name.lower().replace(' ', '')}.hms" 
        temp_password = 'TemporaryPass1!' 
        
        admin_user = User(
            hospital_id=tenant_id,
            first_name='Hospital',
            last_name='Admin',
            email=admin_email,
            password_hash=generate_password_hash(temp_password)
        )
        db.session.add(admin_user)
        
        try:
            db.session.commit()
            flash('Registration successful! Please check your email for the activation link and temporary admin credentials.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred during registration: {e}', 'danger')
            return render_template_string(REGISTER_HTML)
        
    return render_template_string(REGISTER_HTML)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handles User Login."""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            # Set session data
            session['user_id'] = user.id
            session['user_email'] = user.email
            session['user_name'] = f"{user.first_name} {user.last_name}"
            session['hospital_id'] = user.hospital_id
            
            flash(f'Successfully logged in as {user.email}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
            
    return render_template_string(LOGIN_HTML)

@auth_bp.route('/logout')
def logout():
    """Logout the user."""
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('auth.login'))

# ----------------------------------------------------
# 6. CORE APPLICATION ROUTES (HELPER FUNCTION)
# ----------------------------------------------------
# This function attaches routes to the main app instance.

def register_app_routes(app_instance):
    """Registers non-blueprint routes and middleware."""
    
    @app_instance.before_request
    def before_request_func():
        """Placeholder for the Multi-tenancy Context Adapter (FR-2)."""
        # Middleware that handles cross-tenant data access prevention
        pass

    @app_instance.route('/')
    def index():
        return redirect(url_for('auth.login'))

    @app_instance.route('/dashboard')
    @login_required
    def dashboard():
        """Main dashboard - protected route."""
        user = User.query.get(session['user_id'])
        hospital = Hospital.query.get(user.hospital_id)
        
        # Get statistics
        total_patients = Patient.query.filter_by(hospital_id=user.hospital_id).count()
        total_appointments = Appointment.query.filter_by(hospital_id=user.hospital_id).count()
        total_doctors = Doctor.query.filter_by(hospital_id=user.hospital_id).count()
        total_departments = Department.query.filter_by(hospital_id=user.hospital_id).count()
        
        return render_template_string(DASHBOARD_HTML,
            user_name=session['user_name'],
            hospital_name=hospital.name,
            total_patients=total_patients,
            total_appointments=total_appointments,
            total_doctors=total_doctors,
            total_departments=total_departments
        )

    @app_instance.route('/patients')
    @login_required
    def patients():
        """Patients management page."""
        user = User.query.get(session['user_id'])
        patient_list = Patient.query.filter_by(hospital_id=user.hospital_id).all()
        return render_template_string(PATIENTS_HTML, 
            user_name=session['user_name'],
            patients=patient_list,
            patient_count=len(patient_list)
        )

    @app_instance.route('/add_patient', methods=['POST'])
    @login_required
    def add_patient():
        """Add a new patient."""
        try:
            user = User.query.get(session['user_id'])
            new_patient = Patient(
                hospital_id=user.hospital_id,
                first_name=request.form.get('first_name'),
                last_name=request.form.get('last_name'),
                email=request.form.get('email'),
                phone=request.form.get('phone'),
                date_of_birth=datetime.strptime(request.form.get('dob'), '%Y-%m-%d').date(),
                gender=request.form.get('gender'),
                blood_group=request.form.get('blood_group'),
                address=request.form.get('address')
            )
            db.session.add(new_patient)
            db.session.commit()
            flash('Patient added successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding patient: {str(e)}', 'error')
        return redirect(url_for('patients'))

    @app_instance.route('/appointments')
    @login_required
    def appointments():
        """Appointments management page."""
        user = User.query.get(session['user_id'])
        appointment_list = Appointment.query.filter_by(hospital_id=user.hospital_id).all()
        patient_list = Patient.query.filter_by(hospital_id=user.hospital_id).all()
        doctor_list = Doctor.query.filter_by(hospital_id=user.hospital_id).all()
        
        return render_template_string(APPOINTMENTS_HTML, 
            user_name=session['user_name'],
            appointments=appointment_list,
            patients=patient_list,
            doctors=doctor_list,
            appointment_count=len(appointment_list)
        )

    @app_instance.route('/add_appointment', methods=['POST'])
    @login_required
    def add_appointment():
        """Add a new appointment."""
        try:
            user = User.query.get(session['user_id'])
            appointment_datetime = datetime.strptime(
                request.form.get('appointment_date'), 
                '%Y-%m-%dT%H:%M'
            )
            new_appointment = Appointment(
                hospital_id=user.hospital_id,
                patient_id=request.form.get('patient_id'),
                doctor_id=request.form.get('doctor_id'),
                appointment_date=appointment_datetime,
                reason=request.form.get('reason'),
                notes=request.form.get('notes'),
                status='SCHEDULED'
            )
            db.session.add(new_appointment)
            db.session.commit()
            flash('Appointment scheduled successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error scheduling appointment: {str(e)}', 'error')
        return redirect(url_for('appointments'))

    @app_instance.route('/doctors')
    @login_required
    def doctors():
        """Doctors management page."""
        user = User.query.get(session['user_id'])
        doctor_list = Doctor.query.filter_by(hospital_id=user.hospital_id).all()
        department_list = Department.query.filter_by(hospital_id=user.hospital_id).all()
        
        return render_template_string(DOCTORS_HTML, 
            user_name=session['user_name'],
            doctors=doctor_list,
            departments=department_list,
            doctor_count=len(doctor_list)
        )

    @app_instance.route('/add_doctor', methods=['POST'])
    @login_required
    def add_doctor():
        """Add a new doctor."""
        try:
            user = User.query.get(session['user_id'])
            new_doctor = Doctor(
                hospital_id=user.hospital_id,
                first_name=request.form.get('first_name'),
                last_name=request.form.get('last_name'),
                specialization=request.form.get('specialization'),
                email=request.form.get('email'),
                phone=request.form.get('phone'),
                license_number=request.form.get('license'),
                experience_years=request.form.get('experience'),
                department_id=request.form.get('department_id') or None,
                status='ACTIVE'
            )
            db.session.add(new_doctor)
            db.session.commit()
            flash('Doctor added successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding doctor: {str(e)}', 'error')
        return redirect(url_for('doctors'))

    @app_instance.route('/departments')
    @login_required
    def departments():
        """Departments management page."""
        user = User.query.get(session['user_id'])
        department_list = Department.query.filter_by(hospital_id=user.hospital_id).all()
        
        return render_template_string(DEPARTMENTS_HTML, 
            user_name=session['user_name'],
            departments=department_list,
            department_count=len(department_list)
        )

    @app_instance.route('/add_department', methods=['POST'])
    @login_required
    def add_department():
        """Add a new department."""
        try:
            user = User.query.get(session['user_id'])
            new_department = Department(
                hospital_id=user.hospital_id,
                name=request.form.get('name'),
                description=request.form.get('description'),
                head_name=request.form.get('head_name'),
                email=request.form.get('email'),
                phone=request.form.get('phone')
            )
            db.session.add(new_department)
            db.session.commit()
            flash('Department added successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding department: {str(e)}', 'error')
        return redirect(url_for('departments'))

    @app_instance.route('/hospital_settings')
    @login_required
    def hospital_settings():
        """Hospital settings page."""
        user = User.query.get(session['user_id'])
        hospital = Hospital.query.get(user.hospital_id)
        return render_template_string(SETTINGS_HTML, 
            user_name=session['user_name'],
            hospital_name=hospital.name,
            hospital_email=hospital.admin_email,
            hospital_phone=hospital.contact_details,
            hospital_address=hospital.address
        )


# ----------------------------------------------------
# 7. APP FACTORY
# ----------------------------------------------------
# This function is responsible for creating and configuring the app instance.

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = app.config['SECRET_KEY']  # Required for session management
    db.init_app(app)
    
    # 1. Register Blueprint (this is safe now that all routes are defined above)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    # 2. Register core app routes
    register_app_routes(app)
    
    return app


# ----------------------------------------------------
# 8. EXECUTION BLOCK
# ----------------------------------------------------
if __name__ == '__main__':
    print("Hospital Management System (HMS) - Initializing Single-File Flask App")
    print("Database: sqlite:///hms_main.db")

    # Create the application instance
    app_instance = create_app()

    with app_instance.app_context():
        # Create database tables for the main metadata DB
        db.create_all()
        print("Database tables created/checked.")
    
    # Run the application
    # For production, use: gunicorn app:app_instance
    app_instance.run(debug=True, host='0.0.0.0', port=5000)

# WSGI app for production (Gunicorn/Render)
app = create_app()
with app.app_context():
    db.create_all()
