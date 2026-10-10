# Voucher Distribution Management System

A Django 5-based voucher management platform for tracking voucher distributions, payments, balances, and reporting.

## Features
- Authentication with login, logout, password change, and profile management
- Selling point CRUD and detail views
- Voucher type management
- Voucher distribution entries and payment entry flow
- Dashboard metrics and audit logs
- CSV export for reports

## Setup
1. Create and activate a virtual environment
2. Install dependencies: `pip install -r requirements.txt`
3. Run migrations: `python manage.py migrate`
4. Seed sample data: `python manage.py seed_data`
5. Start the server: `python manage.py runserver`

## Default Admin
- Username: `admin`
- Password: `admin123`
