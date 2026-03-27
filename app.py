import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'lms_secret' 

ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

def init_db():
    with sqlite3.connect("library.db") as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            isbn TEXT,
            quantity INTEGER NOT NULL,
            category TEXT DEFAULT 'Uncategorized'
        )''')

        # Run schema alters if needed (fails silently if column exists)
        try:
            conn.execute("ALTER TABLE books ADD COLUMN category TEXT DEFAULT 'Uncategorized'")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE issues ADD COLUMN fine INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        conn.execute('''CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL,
            password TEXT NOT NULL
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER,
            book_id INTEGER,
            issue_date TEXT,
            return_date TEXT,
            status TEXT DEFAULT 'Issued', 
            fine INTEGER DEFAULT 0,
            FOREIGN KEY(member_id) REFERENCES members(id),
            FOREIGN KEY(book_id) REFERENCES books(id)
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER,
            amount INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            FOREIGN KEY(member_id) REFERENCES members(id)
        )''')

# ---------------- MIDDLEWARE ------------------
@app.context_processor
def inject_globals():
    return {
        'now': datetime.now(),
        'timedelta': timedelta
    }

@app.template_filter('to_datetime')
def to_datetime_filter(value):
    if not value: return None
    return datetime.strptime(value, "%Y-%m-%d")

# ---------------- ROUTES ------------------

@app.route('/')
def home(): 
    return render_template("home.html")

@app.route('/admin')
def admin_redirect():
    return redirect(url_for('admin_login'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USER and password == ADMIN_PASS:
            session['admin_logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid credentials. Please try again."
    return render_template('login.html', error=error)

@app.route('/admin/dashboard')
def dashboard():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    return render_template('dashboard.html')

@app.route('/admin/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

# ---------------- BOOK MANAGEMENT ------------------

@app.route('/admin/books')
def manage_books():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    with sqlite3.connect("library.db") as conn:
        books = conn.execute("SELECT id, title, author, isbn, quantity, category FROM books").fetchall()
    return render_template("manage_books.html", books=books)

@app.route('/admin/book/add', methods=["POST"])
def add_book():
    title = request.form['title']
    author = request.form['author']
    isbn = request.form['isbn']
    quantity = request.form['quantity']
    category = request.form.get('category', 'Uncategorized')
    with sqlite3.connect("library.db") as conn:
        conn.execute("INSERT INTO books (title, author, isbn, quantity, category) VALUES (?, ?, ?, ?, ?)",
                     (title, author, isbn, quantity, category))
    return redirect(url_for('manage_books'))

@app.route('/admin/book/delete/<int:book_id>')
def delete_book(book_id):
    with sqlite3.connect("library.db") as conn:
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    return redirect(url_for('manage_books'))

@app.route('/admin/book/update/<int:book_id>', methods=["POST"])
def update_book(book_id):
    title = request.form['title']
    author = request.form['author']
    isbn = request.form['isbn']
    quantity = request.form['quantity']
    category = request.form.get('category', 'Uncategorized')
    with sqlite3.connect("library.db") as conn:
        conn.execute("UPDATE books SET title=?, author=?, isbn=?, quantity=?, category=? WHERE id=?",
                     (title, author, isbn, quantity, category, book_id))
    return redirect(url_for('manage_books'))

# ----------- MEMBER SIGNUP & LOGIN ----------

@app.route('/member/signup', methods=["GET", "POST"])
def member_signup():
    error = None
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        try:
            with sqlite3.connect("library.db") as conn:
                conn.execute("INSERT INTO members (name, email, phone, password) VALUES (?, ?, ?, ?)",
                             (name, email, phone, password))
            return redirect(url_for('member_login'))
        except sqlite3.IntegrityError:
            error = "Email already registered!"
    return render_template("member_signup.html", error=error)

@app.route('/member/login', methods=["GET", "POST"])
def member_login():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        with sqlite3.connect("library.db") as conn:
            user = conn.execute("SELECT * FROM members WHERE email = ? AND password = ?", 
                                (email, password)).fetchone()
        if user:
            session['member_logged_in'] = True
            session['member_id'] = user[0]
            session['member_name'] = user[1]
            return redirect(url_for('member_dashboard'))
        else:
            error = "Invalid credentials!"
    return render_template("member_login.html", error=error)

@app.route('/member/logout')
def member_logout():
    session.pop('member_logged_in', None)
    session.pop('member_id', None)
    session.pop('member_name', None)
    return redirect(url_for('home'))

# ----------- MEMBER ADVANCED: BROWSE & RESERVATIONS ----------

@app.route('/member/browse')
def browse_books():
    if not session.get('member_logged_in'): return redirect(url_for('member_login'))
    
    query = request.args.get('q', '')
    category = request.args.get('category', '')

    sql = "SELECT id, title, author, category, quantity FROM books WHERE quantity > 0"
    params = []

    if query:
        sql += " AND (title LIKE ? OR author LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])
    if category:
        sql += " AND category = ?"
        params.append(category)

    with sqlite3.connect("library.db") as conn:
        books = conn.execute(sql, params).fetchall()
        categories = conn.execute("SELECT DISTINCT category FROM books").fetchall()

    return render_template("member_browse.html", books=books, categories=[c[0] for c in categories], q=query, sel_cat=category)

@app.route('/member/reserve/<int:book_id>')
def reserve_book(book_id):
    if not session.get('member_logged_in'): return redirect(url_for('member_login'))
    member_id = session['member_id']
    issue_date = datetime.now().strftime("%Y-%m-%d")
    
    with sqlite3.connect("library.db") as conn:
        conn.execute("INSERT INTO issues (member_id, book_id, issue_date, status) VALUES (?, ?, ?, 'Reserved')",
                     (member_id, book_id, issue_date))
        conn.execute("UPDATE books SET quantity = quantity - 1 WHERE id = ?", (book_id,))
    
    return redirect(url_for('member_dashboard'))

# ----------- MEMBER DASHBOARD & FEES ----------

def calculate_member_fines(member_id):
    total_fines = 0
    with sqlite3.connect("library.db") as conn:
        # Calculate dynamic fines logic
        issues = conn.execute("SELECT issue_date, return_date, status, fine FROM issues WHERE member_id = ?", (member_id,)).fetchall()
        for issue_date, return_date, status, saved_fine in issues:
            if status == 'Issued' or status == 'Reserved':
                end_dt = datetime.today()
            else:
                end_dt = datetime.strptime(return_date, "%Y-%m-%d") if return_date else datetime.today()
            
            start_dt = datetime.strptime(issue_date, "%Y-%m-%d")
            days_late = max(0, (end_dt - start_dt).days - 14)
            total_fines += (days_late * 1) # $1 per day

        # Subtract payments
        payments = conn.execute("SELECT SUM(amount) FROM payments WHERE member_id = ?", (member_id,)).fetchone()[0]
        if not payments: payments = 0

    return max(0, total_fines - payments)

@app.route('/member/dashboard')
def member_dashboard():
    if not session.get('member_logged_in'): return redirect(url_for('member_login'))
    member_id = session['member_id']
    
    with sqlite3.connect("library.db") as conn:
        issued_books = conn.execute('''
            SELECT books.title, issues.issue_date, issues.return_date, issues.status, issues.id
            FROM issues JOIN books ON issues.book_id = books.id
            WHERE issues.member_id = ?
        ''', (member_id,)).fetchall()
    
    total_owed = calculate_member_fines(member_id)

    return render_template("member_dashboard.html", name=session['member_name'], issued_books=issued_books, total_owed=total_owed)


@app.route('/member/pay_fine')
def pay_fine():
    if not session.get('member_logged_in'): return redirect(url_for('member_login'))
    member_id = session['member_id']
    total_owed = calculate_member_fines(member_id)
    if total_owed <= 0:
        return redirect(url_for('member_dashboard'))
    return render_template("payment_gateway.html", total_owed=total_owed)

@app.route('/member/process_payment', methods=["POST"])
def process_payment():
    if not session.get('member_logged_in'): return redirect(url_for('member_login'))
    member_id = session['member_id']
    amount = int(request.form['amount'])
    pay_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect("library.db") as conn:
        conn.execute("INSERT INTO payments (member_id, amount, payment_date) VALUES (?, ?, ?)", (member_id, amount, pay_date))
    
    return redirect(url_for('member_dashboard'))


# ----------- ADMIN ADVANCED MGMT ----------
@app.route('/admin/members')
def manage_members():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    with sqlite3.connect("library.db") as conn:
        members = conn.execute("SELECT * FROM members").fetchall()
    return render_template("admin_manage_members.html", members=members)

@app.route('/admin/member/delete/<int:member_id>')
def delete_member(member_id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    with sqlite3.connect("library.db") as conn:
        conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
    return redirect(url_for('manage_members'))

@app.route('/admin/issue', methods=["GET", "POST"])
def issue_book():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    success = session.pop('issue_success', None)

    with sqlite3.connect("library.db") as conn:
        members = conn.execute("SELECT id, name FROM members").fetchall()
        books = conn.execute("SELECT id, title, quantity FROM books WHERE quantity > 0").fetchall()
        reservations = conn.execute('''
            SELECT issues.id, members.name, books.title, issues.issue_date
            FROM issues JOIN members ON issues.member_id = members.id
            JOIN books ON issues.book_id = books.id WHERE issues.status = 'Reserved'
        ''').fetchall()

    if request.method == "POST":
        member_id = request.form['member_id']
        book_id = request.form['book_id']
        issue_date = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect("library.db") as conn:
            conn.execute("INSERT INTO issues (member_id, book_id, issue_date) VALUES (?, ?, ?)",
                         (member_id, book_id, issue_date))
            conn.execute("UPDATE books SET quantity = quantity - 1 WHERE id = ?", (book_id,))
        session['issue_success'] = "Book issued successfully!"
        return redirect(url_for('issue_book'))

    return render_template("admin_issue_book.html", members=members, books=books, reservations=reservations, success=success)

@app.route('/admin/approve_reservation/<int:issue_id>')
def approve_reservation(issue_id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    with sqlite3.connect("library.db") as conn:
        conn.execute("UPDATE issues SET status = 'Issued' WHERE id = ?", (issue_id,))
    return redirect(url_for('issue_book'))

@app.route('/admin/return', methods=["GET", "POST"])
def return_book():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    success = session.pop('return_success', None)

    with sqlite3.connect("library.db") as conn:
        issued = conn.execute('''SELECT issues.id, members.name, books.title, issues.issue_date
                          FROM issues JOIN members ON issues.member_id = members.id
                          JOIN books ON issues.book_id = books.id
                          WHERE issues.status = 'Issued' ''').fetchall()

    if request.method == "POST":
        issue_id = request.form['issue_id']
        return_date = datetime.today().strftime("%Y-%m-%d")

        with sqlite3.connect("library.db") as conn:
            issue = conn.execute("SELECT issue_date FROM issues WHERE id = ?", (issue_id,)).fetchone()
            issue_dt = datetime.strptime(issue[0], "%Y-%m-%d")
            days_late = max(0, (datetime.today() - issue_dt).days - 14)
            fine = days_late * 1
            
            conn.execute("UPDATE issues SET return_date = ?, status = 'Returned', fine = ? WHERE id = ?",
                         (return_date, fine, issue_id))
        session['return_success'] = "Book returned. Assessed Fine: $" + str(fine)
        return redirect(url_for('return_book'))

    return render_template("admin_return_book.html", issued=issued, success=success)

@app.route('/admin/transactions')
def view_transactions():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    with sqlite3.connect("library.db") as conn:
        transactions = conn.execute('''
            SELECT members.name, books.title, issues.issue_date, issues.return_date, issues.status
            FROM issues JOIN members ON issues.member_id = members.id
            JOIN books ON issues.book_id = books.id ORDER BY issues.id DESC
        ''').fetchall()
    return render_template("admin_transactions.html", transactions=transactions)

@app.route('/admin/reports')
def reports():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    today = datetime.today().strftime('%Y-%m-%d')
    week_ago = (datetime.today() - timedelta(days=7)).strftime('%Y-%m-%d')
    month_start = datetime.today().replace(day=1).strftime('%Y-%m-%d')

    with sqlite3.connect("library.db") as conn:
        daily = conn.execute('''SELECT books.title, members.name, issues.issue_date, issues.status
            FROM issues JOIN books ON books.id = issues.book_id JOIN members ON members.id = issues.member_id
            WHERE issue_date = ?''', (today,)).fetchall()
        weekly = conn.execute('''SELECT books.title, members.name, issues.issue_date, issues.status
            FROM issues JOIN books ON books.id = issues.book_id JOIN members ON members.id = issues.member_id
            WHERE issue_date BETWEEN ? AND ?''', (week_ago, today)).fetchall()
        monthly = conn.execute('''SELECT books.title, members.name, issues.issue_date, issues.status
            FROM issues JOIN books ON books.id = issues.book_id JOIN members ON members.id = issues.member_id
            WHERE issue_date >= ?''', (month_start,)).fetchall()

    return render_template("admin_reports.html", daily=daily, weekly=weekly, monthly=monthly)

@app.route('/admin/fines')
def track_fines():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    with sqlite3.connect("library.db") as conn:
        payments = conn.execute("SELECT members.name, payments.amount, payments.payment_date FROM payments JOIN members ON members.id = payments.member_id ORDER BY payments.id DESC").fetchall()
        total_collected = conn.execute("SELECT SUM(amount) FROM payments").fetchone()[0] or 0
    return render_template("admin_fines.html", payments=payments, total_collected=total_collected)

@app.route('/admin/send_reminders')
def send_reminders():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    # Simulate email notifications
    emails_sent = 0
    with sqlite3.connect("library.db") as conn:
        overdue = conn.execute('''SELECT members.name, members.email, books.title, issues.issue_date 
            FROM issues JOIN members ON issues.member_id = members.id JOIN books ON issues.book_id = books.id
            WHERE issues.status = 'Issued' ''').fetchall()
        for name, email, title, idate in overdue:
            diff = (datetime.today() - datetime.strptime(idate, "%Y-%m-%d")).days
            if diff > 14:
                # Simulate terminal email log
                print(f"[MAIL SIMULATOR] Sent overdue reminder to {name} ({email}) for '{title}'.")
                emails_sent += 1
    session['issue_success'] = f"Success! Dispatched {emails_sent} overdue email reminders."
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000)) 
    app.run(host='0.0.0.0', port=port)
