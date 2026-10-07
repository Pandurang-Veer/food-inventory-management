from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3, os
from datetime import datetime, date

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, 'inventory.db')
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'food-inventory-demo-secret')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, username TEXT UNIQUE, password TEXT, role TEXT);
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT, email TEXT, address TEXT);
CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category_id INTEGER, unit TEXT, min_stock REAL DEFAULT 0, FOREIGN KEY(category_id) REFERENCES categories(id));
CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, supplier_id INTEGER, batch_no TEXT, quantity REAL, remaining_qty REAL, purchase_date TEXT, expiry_date TEXT, cost REAL DEFAULT 0, FOREIGN KEY(item_id) REFERENCES items(id), FOREIGN KEY(supplier_id) REFERENCES suppliers(id));
CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, batch_id INTEGER, type TEXT, quantity REAL, note TEXT, created_at TEXT, user_id INTEGER);
CREATE TABLE IF NOT EXISTS wastage(id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, batch_id INTEGER, quantity REAL, reason TEXT, created_at TEXT, user_id INTEGER);
'''

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c=db(); c.executescript(SCHEMA)
    if c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        c.execute('INSERT INTO users(name,username,password,role) VALUES(?,?,?,?)',('Demo Admin','admin','admin123','Admin'))
    if c.execute('SELECT COUNT(*) FROM categories').fetchone()[0] == 0:
        c.executemany('INSERT INTO categories(name) VALUES(?)',[('Vegetables',),('Dairy',),('Grains',),('Spices',),('Beverages',)])
    if c.execute('SELECT COUNT(*) FROM suppliers').fetchone()[0] == 0:
        c.executemany('INSERT INTO suppliers(name,phone,email,address) VALUES(?,?,?,?)',[
            ('Fresh Farm Foods','9876543210','fresh@example.com','Pune'),('Daily Dairy Co.','9876501234','dairy@example.com','Pimpri'),('Grain House','9822001122','grain@example.com','Pune')])
    if c.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 0:
        cats={r['name']:r['id'] for r in c.execute('SELECT * FROM categories')}
        items=[('Tomato',cats['Vegetables'],'kg',10),('Potato',cats['Vegetables'],'kg',15),('Milk',cats['Dairy'],'L',20),('Rice',cats['Grains'],'kg',25),('Turmeric',cats['Spices'],'kg',3)]
        c.executemany('INSERT INTO items(name,category_id,unit,min_stock) VALUES(?,?,?,?)',items)
        ids={r['name']:r['id'] for r in c.execute('SELECT * FROM items')}
        sids=[r['id'] for r in c.execute('SELECT * FROM suppliers')]
        today=date.today()
        demo=[
            (ids['Tomato'],sids[0],'TOM-001',25,20,(today.replace(day=max(1,today.day-3))).isoformat(),(today.replace(day=min(28,today.day+4))).isoformat(),40),
            (ids['Tomato'],sids[0],'TOM-002',30,30,today.isoformat(),(today.replace(day=min(28,today.day+10))).isoformat(),42),
            (ids['Potato'],sids[0],'POT-001',40,40,today.isoformat(),(today.replace(day=min(28,today.day+18))).isoformat(),30),
            (ids['Milk'],sids[1],'MLK-001',50,35,today.isoformat(),(today.replace(day=min(28,today.day+2))).isoformat(),55),
            (ids['Rice'],sids[2],'RIC-001',60,60,today.isoformat(),(today.replace(day=min(28,today.day+90))).isoformat(),48),
            (ids['Turmeric'],sids[2],'TUR-001',5,2,today.isoformat(),(today.replace(day=min(28,today.day+60))).isoformat(),120)]
        c.executemany('INSERT INTO batches(item_id,supplier_id,batch_no,quantity,remaining_qty,purchase_date,expiry_date,cost) VALUES(?,?,?,?,?,?,?,?)',demo)
    c.commit(); c.close()

init_db()

def require_login():
    return 'user_id' in session

def rows(sql,args=()):
    c=db(); r=c.execute(sql,args).fetchall(); c.close(); return [dict(x) for x in r]

def one(sql,args=()):
    c=db(); r=c.execute(sql,args).fetchone(); c.close(); return dict(r) if r else None

@app.route('/')
def index():
    return render_template('index.html', logged=bool(session.get('user_id')), user=session.get('name'))

@app.route('/login', methods=['POST'])
def login():
    data=request.get_json() or request.form
    u=data.get('username',''); p=data.get('password','')
    user=one('SELECT * FROM users WHERE username=? AND password=?',(u,p))
    if not user: return jsonify(ok=False,error='Invalid username or password'),401
    session['user_id']=user['id']; session['name']=user['name']; session['role']=user['role']
    return jsonify(ok=True)

@app.route('/logout')
def logout():
    session.clear(); return redirect('/')

@app.route('/api/dashboard')
def dashboard():
    items=rows('''SELECT i.id,i.name,i.unit,i.min_stock,COALESCE(SUM(b.remaining_qty),0) stock FROM items i LEFT JOIN batches b ON i.id=b.item_id GROUP BY i.id ORDER BY i.name''')
    total=sum(x['stock'] for x in items)
    low=[x for x in items if x['stock'] <= x['min_stock']]
    exp=rows('''SELECT b.*,i.name item_name,i.unit FROM batches b JOIN items i ON i.id=b.item_id WHERE b.remaining_qty>0 AND date(b.expiry_date)<=date('now','+7 day') ORDER BY date(b.expiry_date)''')
    waste=one("SELECT COALESCE(SUM(quantity),0) q FROM wastage")['q']
    return jsonify(items=items,total_stock=total,low_stock=low,expiry=exp,wastage=waste)

@app.route('/api/items', methods=['GET','POST'])
def items_api():
    if request.method=='GET':
        return jsonify(items=rows('''SELECT i.*,c.name category,COALESCE(SUM(b.remaining_qty),0) stock FROM items i LEFT JOIN categories c ON c.id=i.category_id LEFT JOIN batches b ON b.item_id=i.id GROUP BY i.id ORDER BY i.name'''), categories=rows('SELECT * FROM categories ORDER BY name'))
    data=request.get_json(); c=db(); c.execute('INSERT INTO items(name,category_id,unit,min_stock) VALUES(?,?,?,?)',(data['name'],data['category_id'],data['unit'],float(data.get('min_stock',0)))); c.commit(); c.close(); return jsonify(ok=True)

@app.route('/api/suppliers', methods=['GET','POST'])
def suppliers_api():
    if request.method=='GET': return jsonify(suppliers=rows('SELECT * FROM suppliers ORDER BY name'))
    d=request.get_json(); c=db(); c.execute('INSERT INTO suppliers(name,phone,email,address) VALUES(?,?,?,?)',(d['name'],d.get('phone',''),d.get('email',''),d.get('address',''))); c.commit(); c.close(); return jsonify(ok=True)

@app.route('/api/batches', methods=['GET','POST'])
def batches_api():
    if request.method=='GET':
        return jsonify(batches=rows('''SELECT b.*,i.name item_name,i.unit,s.name supplier_name FROM batches b JOIN items i ON i.id=b.item_id LEFT JOIN suppliers s ON s.id=b.supplier_id ORDER BY date(b.expiry_date),date(b.purchase_date)'''))
    d=request.get_json(); qty=float(d['quantity']); c=db(); c.execute('''INSERT INTO batches(item_id,supplier_id,batch_no,quantity,remaining_qty,purchase_date,expiry_date,cost) VALUES(?,?,?,?,?,?,?,?,?)''',(d['item_id'],d.get('supplier_id'),d['batch_no'],qty,qty,d['purchase_date'],d['expiry_date'],float(d.get('cost',0)))); c.commit(); c.close(); return jsonify(ok=True)

@app.route('/api/consume', methods=['POST'])
def consume():
    if not require_login(): return jsonify(error='Login required'),401
    d=request.get_json(); item_id=int(d['item_id']); required=float(d['quantity']); c=db()
    batches=c.execute('''SELECT * FROM batches WHERE item_id=? AND remaining_qty>0 ORDER BY date(purchase_date),id''',(item_id,)).fetchall()
    remaining=required; used=[]
    for b in batches:
        take=min(remaining,b['remaining_qty'])
        if take>0:
            c.execute('UPDATE batches SET remaining_qty=remaining_qty-? WHERE id=?',(take,b['id']))
            c.execute('INSERT INTO transactions(item_id,batch_id,type,quantity,note,created_at,user_id) VALUES(?,?,?,?,?,?,?)',(item_id,b['id'],'CONSUMPTION',take,'FIFO issue',datetime.now().isoformat(),session['user_id']))
            used.append({'batch_no':b['batch_no'],'quantity':take}); remaining-=take
        if remaining<=0: break
    if remaining>0:
        c.rollback(); c.close(); return jsonify(error='Insufficient stock',used=used),400
    c.commit(); c.close(); return jsonify(ok=True,used=used)

@app.route('/api/wastage', methods=['POST'])
def wastage_api():
    if not require_login(): return jsonify(error='Login required'),401
    d=request.get_json(); item_id=int(d['item_id']); qty=float(d['quantity']); c=db();
    # wastage also follows oldest-batch-first for traceability
    batches=c.execute('SELECT * FROM batches WHERE item_id=? AND remaining_qty>0 ORDER BY date(purchase_date),id',(item_id,)).fetchall(); rem=qty
    for b in batches:
        take=min(rem,b['remaining_qty']); c.execute('UPDATE batches SET remaining_qty=remaining_qty-? WHERE id=?',(take,b['id'])); c.execute('INSERT INTO wastage(item_id,batch_id,quantity,reason,created_at,user_id) VALUES(?,?,?,?,?,?)',(item_id,b['id'],take,d.get('reason',''),datetime.now().isoformat(),session['user_id'])); rem-=take
        if rem<=0: break
    if rem>0: c.rollback(); c.close(); return jsonify(error='Insufficient stock'),400
    c.commit(); c.close(); return jsonify(ok=True)

@app.route('/api/reports')
def reports():
    stock=rows('''SELECT i.name,i.unit,i.min_stock,COALESCE(SUM(b.remaining_qty),0) stock FROM items i LEFT JOIN batches b ON b.item_id=i.id GROUP BY i.id ORDER BY i.name''')
    purchases=rows('''SELECT date(purchase_date) date, COUNT(*) batches, ROUND(SUM(quantity*cost),2) value FROM batches GROUP BY date(purchase_date) ORDER BY date DESC''')
    waste=rows('''SELECT date(w.created_at) date, i.name, SUM(w.quantity) quantity, w.reason FROM wastage w JOIN items i ON i.id=w.item_id GROUP BY date(w.created_at),i.id,w.reason ORDER BY date DESC''')
    return jsonify(stock=stock,purchases=purchases,wastage=waste)

@app.route('/api/transactions')
def transactions():
    return jsonify(rows=rows('''SELECT t.*,i.name item_name,b.batch_no FROM transactions t JOIN items i ON i.id=t.item_id JOIN batches b ON b.id=t.batch_id ORDER BY t.id DESC LIMIT 100'''))

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=False)
