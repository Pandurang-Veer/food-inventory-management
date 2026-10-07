# FoodStock Pro — Food Inventory Management System

A professional T.Y.B.Sc. Computer Science project demo built with Flask, SQLite, HTML, CSS and JavaScript.

## Features
- Dashboard with current stock, low-stock and expiry alerts
- Batch-wise inventory
- FIFO stock consumption (oldest batch first)
- Wastage recording with batch traceability
- Automatic stock, purchase and wastage reports
- Food item/category/supplier data APIs
- Demo login and protected inventory operations
- Responsive presentation-ready frontend

## Run locally
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Then open http://127.0.0.1:5000

Demo login: `admin` / `admin123`

## Deploy
This project is ready for a Python WSGI host. Create a web service from this folder, install from `requirements.txt`, and use the Procfile command `gunicorn app:app`.

For a public college demo, set `SECRET_KEY` in the hosting service. SQLite is suitable for a demo; for production, move the database to PostgreSQL/MySQL.
