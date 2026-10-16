# FreshStock — Food Inventory Management System

College project starter based on the Food Inventory Management report.

## Features
- Dashboard with current stock, low-stock, near-expiry and expired-batch indicators
- Food item and category management
- Supplier directory
- Purchase and batch recording
- FIFO consumption (oldest eligible purchase batch first)
- Wastage recording and stock deduction
- Current stock, batch, transaction and wastage reports
- Print reports or save as PDF from the browser
- SQLite database created automatically

## Demo login
- Username: `admin`
- Password: `admin123`

This is a classroom prototype. The demo password is stored as plain text and must be replaced with secure password hashing before real-world use. Do not store real customer or business data in this demo deployment.

## Run on Windows
1. Install Python 3.11 or later from https://www.python.org/downloads/
2. Extract the ZIP.
3. Open the extracted folder in VS Code.
4. In VS Code, choose Terminal > New Terminal.
5. Run:
   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   python -m pip install -r requirements.txt
   python app.py
   ```
6. Visit http://127.0.0.1:5000 in your browser.
7. Sign in using the demo credentials above.
8. Click "Load demo data" to insert a sample Tomatoes item with two batches.

## FIFO test
The demo data creates 10 kg in older batch TOM-001 and 20 kg in newer batch TOM-002. Issue 15 kg from FIFO Consumption. The expected remaining quantities are 0 kg in TOM-001 and 15 kg in TOM-002.

## Render deployment
- Push the project files to a GitHub repository.
- In Render, create a Web Service connected to the repository.
- Runtime: Python.
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Add environment variable `SECRET_KEY` with a long random value.
- Important: this starter uses a local SQLite file. On many free hosted services the filesystem may be ephemeral, so database changes can be lost during redeploy/restart. For persistent hosted data, attach a persistent disk and store `inventory.db` on it, or migrate to a managed PostgreSQL/MySQL database. Do not assume a free service will preserve SQLite data.

## Important limitations
- Demo login is not production security: passwords are not hashed and there is no user registration/password reset.
- Report output is view/print based, not a generated Excel/PDF file.
- Purchases are recorded one item per purchase entry in this starter.
- Automatic supplier ordering, accounting/billing, barcode/QR and physical sensor integration are not implemented.
- This starter uses SQLite instead of the MySQL database proposed in the project report.
