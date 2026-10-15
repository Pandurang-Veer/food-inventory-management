import os, sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "inventory.db")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-demo-secret-key")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
 username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'admin'
);
CREATE TABLE IF NOT EXISTS categories (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS suppliers (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
 phone TEXT, email TEXT, address TEXT
);
CREATE TABLE IF NOT EXISTS items (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
 category_id INTEGER, unit TEXT NOT NULL DEFAULT 'kg',
 min_stock REAL NOT NULL DEFAULT 0,
 FOREIGN KEY(category_id) REFERENCES categories(id)
);
CREATE TABLE IF NOT EXISTS purchases (
 id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_id INTEGER,
 user_id INTEGER, purchase_date TEXT NOT NULL, total_amount REAL NOT NULL DEFAULT 0,
 FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
);
CREATE TABLE IF NOT EXISTS batches (
 id INTEGER PRIMARY KEY AUTOINCREMENT, purchase_id INTEGER,
 item_id INTEGER NOT NULL, batch_no TEXT NOT NULL,
 quantity REAL NOT NULL, remaining_qty REAL NOT NULL,
 purchase_date TEXT NOT NULL, expiry_date TEXT,
 FOREIGN KEY(purchase_id) REFERENCES purchases(id),
 FOREIGN KEY(item_id) REFERENCES items(id)
);
CREATE TABLE IF NOT EXISTS transactions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER, item_id INTEGER NOT NULL,
 type TEXT NOT NULL, quantity REAL NOT NULL, transaction_date TEXT NOT NULL,
 user_id INTEGER, notes TEXT,
 FOREIGN KEY(batch_id) REFERENCES batches(id),
 FOREIGN KEY(item_id) REFERENCES items(id)
);
CREATE TABLE IF NOT EXISTS wastage (
 id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL, batch_id INTEGER,
 quantity REAL NOT NULL, reason TEXT NOT NULL, wastage_date TEXT NOT NULL,
 FOREIGN KEY(item_id) REFERENCES items(id), FOREIGN KEY(batch_id) REFERENCES batches(id)
);
"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO users(name, username, password, role) VALUES(?,?,?,?)",
                 ("Project Administrator", "admin", "admin123", "admin"))
    conn.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", ("Grains",))
    conn.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", ("Vegetables",))
    conn.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", ("Dairy",))
    conn.commit()
    conn.close()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def stock_for(item_id):
    row = db().execute("SELECT COALESCE(SUM(remaining_qty),0) n FROM batches WHERE item_id=?", (item_id,)).fetchone()
    return float(row["n"] or 0)

@app.route("/")
def home():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    conn = db()
    items = conn.execute("""
      SELECT i.*, c.name category,
      COALESCE((SELECT SUM(b.remaining_qty) FROM batches b WHERE b.item_id=i.id),0) stock
      FROM items i LEFT JOIN categories c ON c.id=i.category_id ORDER BY i.name
    """).fetchall()
    low = [i for i in items if float(i["stock"]) <= float(i["min_stock"])]
    today = date.today().isoformat()
    soon = (date.today() + timedelta(days=7)).isoformat()
    near = conn.execute("""SELECT b.*, i.name item_name, i.unit FROM batches b JOIN items i ON i.id=b.item_id
      WHERE b.remaining_qty>0 AND b.expiry_date IS NOT NULL AND b.expiry_date BETWEEN ? AND ?
      ORDER BY b.expiry_date""", (today, soon)).fetchall()
    expired = conn.execute("""SELECT b.*, i.name item_name, i.unit FROM batches b JOIN items i ON i.id=b.item_id
      WHERE b.remaining_qty>0 AND b.expiry_date IS NOT NULL AND b.expiry_date < ? ORDER BY b.expiry_date""", (today,)).fetchall()
    wastage_total = conn.execute("SELECT COALESCE(SUM(quantity),0) n FROM wastage").fetchone()["n"]
    return render_template("dashboard.html", items=items, low=low, near=near, expired=expired,
                           wastage_total=wastage_total, total_items=len(items))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user = db().execute("SELECT * FROM users WHERE username=? AND password=?",
                            (request.form.get("username","").strip(), request.form.get("password",""))).fetchone()
        if user:
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            return redirect(url_for("home"))
        flash("Incorrect username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/items", methods=["GET","POST"])
@login_required
def items_page():
    conn = db()
    if request.method == "POST":
        name = request.form.get("name","").strip()
        unit = request.form.get("unit","kg").strip()
        category_id = request.form.get("category_id") or None
        min_stock = request.form.get("min_stock") or 0
        if not name:
            flash("Item name is required.", "error")
        else:
            conn.execute("INSERT INTO items(name,category_id,unit,min_stock) VALUES(?,?,?,?)",
                         (name, category_id, unit, float(min_stock)))
            conn.commit()
            flash("Food item added.", "success")
        return redirect(url_for("items_page"))
    items = conn.execute("""SELECT i.*, c.name category,
      COALESCE((SELECT SUM(b.remaining_qty) FROM batches b WHERE b.item_id=i.id),0) stock
      FROM items i LEFT JOIN categories c ON c.id=i.category_id ORDER BY i.name""").fetchall()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    return render_template("items.html", items=items, categories=categories)

@app.route("/categories", methods=["POST"])
@login_required
def add_category():
    name = request.form.get("name","").strip()
    if name:
        try:
            db().execute("INSERT INTO categories(name) VALUES(?)", (name,))
            db().commit()
            flash("Category added.", "success")
        except sqlite3.IntegrityError:
            flash("That category already exists.", "error")
    return redirect(url_for("items_page"))

@app.route("/suppliers", methods=["GET","POST"])
@login_required
def suppliers_page():
    conn = db()
    if request.method == "POST":
        name = request.form.get("name","").strip()
        if name:
            conn.execute("INSERT INTO suppliers(name,phone,email,address) VALUES(?,?,?,?)",
                (name, request.form.get("phone",""), request.form.get("email",""), request.form.get("address","")))
            conn.commit()
            flash("Supplier added.", "success")
        else:
            flash("Supplier name is required.", "error")
        return redirect(url_for("suppliers_page"))
    suppliers = conn.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    return render_template("suppliers.html", suppliers=suppliers)

@app.route("/purchases", methods=["GET","POST"])
@login_required
def purchases_page():
    conn = db()
    if request.method == "POST":
        try:
            item_id = int(request.form["item_id"])
            qty = float(request.form["quantity"])
            amount = float(request.form.get("total_amount") or 0)
            if qty <= 0 or amount < 0:
                raise ValueError()
            purchase_date = request.form.get("purchase_date") or date.today().isoformat()
            expiry_date = request.form.get("expiry_date") or None
            supplier_id = request.form.get("supplier_id") or None
            batch_no = request.form.get("batch_no","").strip() or "B-" + datetime.now().strftime("%Y%m%d%H%M%S")
            cur = conn.execute("INSERT INTO purchases(supplier_id,user_id,purchase_date,total_amount) VALUES(?,?,?,?)",
                               (supplier_id, session["user_id"], purchase_date, amount))
            purchase_id = cur.lastrowid
            cur = conn.execute("""INSERT INTO batches(purchase_id,item_id,batch_no,quantity,remaining_qty,purchase_date,expiry_date)
                                  VALUES(?,?,?,?,?,?,?)""",
                               (purchase_id,item_id,batch_no,qty,qty,purchase_date,expiry_date))
            conn.execute("""INSERT INTO transactions(batch_id,item_id,type,quantity,transaction_date,user_id,notes)
                            VALUES(?,?,?,?,?,?,?)""",
                         (cur.lastrowid,item_id,"PURCHASE",qty,purchase_date,session["user_id"],"Stock received"))
            conn.commit()
            flash("Purchase recorded and batch stock updated.", "success")
        except (ValueError, KeyError):
            conn.rollback()
            flash("Enter a valid item, positive quantity and valid amount.", "error")
        return redirect(url_for("purchases_page"))
    items = conn.execute("SELECT * FROM items ORDER BY name").fetchall()
    suppliers = conn.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    purchases = conn.execute("""SELECT p.*, s.name supplier FROM purchases p LEFT JOIN suppliers s ON s.id=p.supplier_id
                                ORDER BY p.id DESC LIMIT 50""").fetchall()
    return render_template("purchases.html", items=items, suppliers=suppliers, purchases=purchases, today=date.today().isoformat())

@app.route("/consume", methods=["GET","POST"])
@login_required
def consume_page():
    conn = db()
    if request.method == "POST":
        try:
            item_id = int(request.form["item_id"])
            requested = float(request.form["quantity"])
            if requested <= 0:
                raise ValueError()
            batches = conn.execute("""SELECT * FROM batches WHERE item_id=? AND remaining_qty>0
              AND (expiry_date IS NULL OR expiry_date>=?) ORDER BY purchase_date ASC, id ASC""",
              (item_id, date.today().isoformat())).fetchall()
            available = sum(float(b["remaining_qty"]) for b in batches)
            if requested > available:
                flash(f"Insufficient non-expired stock. Available: {available:g}.", "error")
                return redirect(url_for("consume_page"))
            remaining = requested
            for batch in batches:
                if remaining <= 0:
                    break
                take = min(float(batch["remaining_qty"]), remaining)
                conn.execute("UPDATE batches SET remaining_qty=remaining_qty-? WHERE id=?", (take,batch["id"]))
                conn.execute("""INSERT INTO transactions(batch_id,item_id,type,quantity,transaction_date,user_id,notes)
                                VALUES(?,?,?,?,?,?,?)""",
                             (batch["id"],item_id,"CONSUMPTION",take,date.today().isoformat(),session["user_id"],"FIFO issue"))
                remaining -= take
            conn.commit()
            flash("Stock consumed using FIFO (oldest purchase batch first).", "success")
        except (ValueError, KeyError):
            conn.rollback()
            flash("Enter a valid item and positive quantity.", "error")
        return redirect(url_for("consume_page"))
    items = conn.execute("""SELECT i.*, COALESCE((SELECT SUM(b.remaining_qty) FROM batches b WHERE b.item_id=i.id),0) stock
                            FROM items i ORDER BY i.name""").fetchall()
    transactions = conn.execute("""SELECT t.*, i.name item_name, i.unit, b.batch_no FROM transactions t
      JOIN items i ON i.id=t.item_id LEFT JOIN batches b ON b.id=t.batch_id
      ORDER BY t.id DESC LIMIT 40""").fetchall()
    return render_template("consume.html", items=items, transactions=transactions)

@app.route("/wastage", methods=["GET","POST"])
@login_required
def wastage_page():
    conn = db()
    if request.method == "POST":
        try:
            item_id = int(request.form["item_id"])
            qty = float(request.form["quantity"])
            reason = request.form.get("reason","").strip()
            if qty <= 0 or not reason:
                raise ValueError()
            batches = conn.execute("""SELECT * FROM batches WHERE item_id=? AND remaining_qty>0
              AND (expiry_date IS NULL OR expiry_date>=?) ORDER BY purchase_date ASC, id ASC""",
              (item_id, date.today().isoformat())).fetchall()
            available = sum(float(b["remaining_qty"]) for b in batches)
            if qty > available:
                flash(f"Insufficient non-expired stock. Available: {available:g}.", "error")
                return redirect(url_for("wastage_page"))
            remaining = qty
            for batch in batches:
                if remaining <= 0: break
                take = min(float(batch["remaining_qty"]), remaining)
                conn.execute("UPDATE batches SET remaining_qty=remaining_qty-? WHERE id=?", (take,batch["id"]))
                conn.execute("INSERT INTO wastage(item_id,batch_id,quantity,reason,wastage_date) VALUES(?,?,?,?,?)",
                             (item_id,batch["id"],take,reason,date.today().isoformat()))
                conn.execute("""INSERT INTO transactions(batch_id,item_id,type,quantity,transaction_date,user_id,notes)
                                VALUES(?,?,?,?,?,?,?)""",
                             (batch["id"],item_id,"WASTAGE",take,date.today().isoformat(),session["user_id"],reason))
                remaining -= take
            conn.commit()
            flash("Wastage recorded and stock updated.", "success")
        except (ValueError, KeyError):
            conn.rollback()
            flash("Enter a valid quantity and wastage reason.", "error")
        return redirect(url_for("wastage_page"))
    items = conn.execute("""SELECT i.*, COALESCE((SELECT SUM(b.remaining_qty) FROM batches b WHERE b.item_id=i.id),0) stock
                            FROM items i ORDER BY i.name""").fetchall()
    records = conn.execute("""SELECT w.*, i.name item_name, i.unit, b.batch_no FROM wastage w
      JOIN items i ON i.id=w.item_id LEFT JOIN batches b ON b.id=w.batch_id ORDER BY w.id DESC LIMIT 100""").fetchall()
    return render_template("wastage.html", items=items, records=records)

@app.route("/reports")
@login_required
def reports_page():
    conn = db()
    items = conn.execute("""SELECT i.*, c.name category,
      COALESCE((SELECT SUM(b.remaining_qty) FROM batches b WHERE b.item_id=i.id),0) stock
      FROM items i LEFT JOIN categories c ON c.id=i.category_id ORDER BY i.name""").fetchall()
    batches = conn.execute("""SELECT b.*, i.name item_name, i.unit FROM batches b JOIN items i ON i.id=b.item_id
                              ORDER BY b.purchase_date, b.id""").fetchall()
    transactions = conn.execute("""SELECT t.*, i.name item_name, i.unit, b.batch_no FROM transactions t
      JOIN items i ON i.id=t.item_id LEFT JOIN batches b ON b.id=t.batch_id ORDER BY t.id DESC""").fetchall()
    wastage = conn.execute("""SELECT w.*, i.name item_name, i.unit FROM wastage w JOIN items i ON i.id=w.item_id
                              ORDER BY w.id DESC""").fetchall()
    return render_template("reports.html", items=items, batches=batches, transactions=transactions, wastage=wastage)

@app.route("/seed-demo")
@login_required
def seed_demo():
    conn = db()
    if conn.execute("SELECT COUNT(*) n FROM items").fetchone()["n"] == 0:
        cat = conn.execute("SELECT id FROM categories WHERE name='Vegetables'").fetchone()
        conn.execute("INSERT INTO items(name,category_id,unit,min_stock) VALUES(?,?,?,?)", ("Tomatoes",cat["id"],"kg",5))
        item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO suppliers(name,phone,email,address) VALUES(?,?,?,?)", ("Fresh Farm Supplies","9876543210","demo@example.com","Pune"))
        supplier_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        today = date.today()
        for idx, (qty, days, bno) in enumerate([(10,14,"TOM-001"),(20,30,"TOM-002")]):
            pd = (today - timedelta(days=idx*3)).isoformat()
            exp = (today + timedelta(days=days)).isoformat()
            p = conn.execute("INSERT INTO purchases(supplier_id,user_id,purchase_date,total_amount) VALUES(?,?,?,?)",
                             (supplier_id,session["user_id"],pd,qty*30))
            b = conn.execute("INSERT INTO batches(purchase_id,item_id,batch_no,quantity,remaining_qty,purchase_date,expiry_date) VALUES(?,?,?,?,?,?,?)",
                             (p.lastrowid,item_id,bno,qty,qty,pd,exp))
            conn.execute("INSERT INTO transactions(batch_id,item_id,type,quantity,transaction_date,user_id,notes) VALUES(?,?,?,?,?,?,?)",
                         (b.lastrowid,item_id,"PURCHASE",qty,pd,session["user_id"],"Demo stock"))
        conn.commit()
        flash("Demo data added: Tomatoes with two batches and a supplier.", "success")
    else:
        flash("Demo data skipped because items already exist.", "error")
    return redirect(url_for("home"))

@app.route("/health")
def health():
    return {"status": "ok"}

init_db()

if __name__ == "__main__":
    app.run(debug=True)
