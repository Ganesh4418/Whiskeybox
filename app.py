from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from pathlib import Path
import os
import hmac
import json
import secrets
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
DB_PATH = os.path.join("/tmp", "whiskeybox.db")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
# SMS credentials are configured as environment variables on the hosting provider.
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")
VENDOR_SMS_NUMBER = os.getenv("VENDOR_SMS_NUMBER")

PRODUCTS = [
    # Change these details to your own single product.
    {"id": 1, "name": "Royal Stag", "description": "A standard full bottle of Royal Stag whisky 750 ml", "price": 40, "emoji": "📦", "image": "static/rs2022_pouring_shot_06_ratio4x5_0.jpg.avif", "category": "Product"},
]
PRODUCT_BY_ID = {p["id"]: p for p in PRODUCTS}


def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    # The orders table intentionally has no delivery_fee column.
    # If an older project database still has that column, rebuild the table
    # and copy the existing order data into the fee-free schema.
    with connect_db() as conn:
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='orders'"
        ).fetchone()
        if existing:
            old_columns = [row[1] for row in conn.execute("PRAGMA table_info(orders)")]
        else:
            old_columns = []

        create_sql = """CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            address TEXT NOT NULL,
            notes TEXT,
            items_json TEXT NOT NULL,
            subtotal REAL NOT NULL,
            total REAL NOT NULL,
            payment_method TEXT NOT NULL,
            fulfilled INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""

        if "delivery_fee" in old_columns:
            conn.execute("DROP TABLE IF EXISTS orders_migrating")
            conn.execute(create_sql.format(table_name="orders_migrating"))
            allowed = [
                "id", "customer_name", "phone", "email", "address", "notes",
                "items_json", "subtotal", "total", "payment_method", "created_at"
            ]
            common = [column for column in allowed if column in old_columns]
            columns_sql = ", ".join(common)
            conn.execute(
                f"INSERT INTO orders_migrating ({columns_sql}) "
                f"SELECT {columns_sql} FROM orders"
            )
            conn.execute("DROP TABLE orders")
            conn.execute("ALTER TABLE orders_migrating RENAME TO orders")
        else:
            conn.execute(create_sql.format(table_name="orders"))

        # Add fulfillment status to existing databases without losing orders.
        columns = [row[1] for row in conn.execute("PRAGMA table_info(orders)")]
        if "fulfilled" not in columns:
            conn.execute("ALTER TABLE orders ADD COLUMN fulfilled INTEGER NOT NULL DEFAULT 0")


# Ensure the database exists when the app is imported by Gunicorn/production server.
init_db()


def cart_items():
    cart = session.get("cart", {})
    items = []
    subtotal = 0
    for product_id, quantity in cart.items():
        product = PRODUCT_BY_ID.get(int(product_id))
        quantity = int(quantity)
        if product and quantity > 0:
            line_total = product["price"] * quantity
            items.append({**product, "quantity": quantity, "line_total": line_total})
            subtotal += line_total
    return items, subtotal


@app.context_processor
def inject_cart_count():
    return {"cart_count": sum(int(q) for q in session.get("cart", {}).values())}


@app.context_processor
def inject_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return {"csrf_token": token}


def valid_csrf():
    return bool(session.get("_csrf_token")) and hmac.compare_digest(
        request.form.get("csrf_token", ""), session.get("_csrf_token", "")
    )


@app.route("/")
def home():
    # Single-product site: show the product details immediately when the link opens.
    return render_template("index.html", product=PRODUCTS[0])


@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = PRODUCT_BY_ID.get(product_id)
    if not product:
        return redirect(url_for("home"))
    return render_template("product.html", product=product)


@app.post("/order-now/<int:product_id>")
def order_now(product_id):
    product = PRODUCT_BY_ID.get(product_id)
    if not product:
        flash("That item is not available.", "error")
        return redirect(url_for("home"))
    try:
        quantity = max(1, min(int(request.form.get("quantity", "1")), 99))
    except (TypeError, ValueError):
        quantity = 1
    cart = session.get("cart", {})
    cart[str(product_id)] = quantity
    session["cart"] = cart
    return redirect(url_for("checkout"))


@app.post("/cart/add/<int:product_id>")
def add_to_cart(product_id):
    if product_id not in PRODUCT_BY_ID:
        flash("That item is not available.", "error")
        return redirect(url_for("home"))
    cart = session.get("cart", {})
    key = str(product_id)
    cart[key] = min(int(cart.get(key, 0)) + 1, 99)
    session["cart"] = cart
    flash(f'{PRODUCT_BY_ID[product_id]["name"]} added to your cart.', "success")
    return redirect(request.referrer or url_for("home"))


@app.route("/cart", methods=["GET", "POST"])
def cart():
    if request.method == "POST":
        cart = session.get("cart", {})
        for product_id in list(cart.keys()):
            raw = request.form.get(f"qty_{product_id}", "0")
            try:
                qty = max(0, min(int(raw), 99))
            except ValueError:
                qty = int(cart[product_id])
            if qty == 0:
                cart.pop(product_id, None)
            else:
                cart[product_id] = qty
        session["cart"] = cart
        flash("Cart updated.", "success")
        return redirect(url_for("cart"))
    items, subtotal = cart_items()
    return render_template("cart.html", items=items, subtotal=subtotal, total=subtotal)


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items, subtotal = cart_items()
    if not items:
        flash("Your cart is empty. Add something delicious first!", "error")
        return redirect(url_for("home"))
    total = subtotal

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()
        notes = request.form.get("notes", "").strip()
        payment_method = request.form.get("payment_method", "Cash on delivery")
        if not name or not phone or not address:
            flash("Please enter your name, phone number and delivery address.", "error")
            return render_template("checkout.html", items=items, subtotal=subtotal, total=total)
        if request.form.get("age_confirmed") != "yes":
            flash("Please confirm legal-age and local-law eligibility before ordering.", "error")
            return render_template("checkout.html", items=items, subtotal=subtotal, total=total)
        if payment_method not in ("Cash on delivery", "UPI on delivery"):
            payment_method = "Cash on delivery"

        import json
        order_items = [{"id": i["id"], "name": i["name"], "quantity": i["quantity"], "price": i["price"]} for i in items]
        with connect_db() as conn:
            cursor = conn.execute("""INSERT INTO orders
                (customer_name, phone, email, address, notes, items_json, subtotal, total, payment_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, phone, email, address, notes, json.dumps(order_items), subtotal, total, payment_method))
            order_id = cursor.lastrowid
        # Optional automatic vendor SMS. The customer is never redirected to WhatsApp.
        message_lines = [
            f"NEW ORDER #{order_id}",
            f"Customer: {name}",
            f"Phone: {phone}",
            f"Address: {address}",
            f"Email: {email or '-'}",
            f"Notes: {notes or '-'}",
            "Items:",
        ]
        message_lines.extend(
            f"- {item['quantity']} x {item['name']} (AED {item['line_total']:.2f})"
            for item in items
        )
        message_lines.extend([
            f"TOTAL: AED {total:.2f}",
            f"Payment: {payment_method}",
            "Customer confirmed legal-age/local-law eligibility: Yes",
        ])
        sms_body = "\n".join(message_lines)

        if all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, VENDOR_SMS_NUMBER]):
            try:
                from twilio.rest import Client
                sms_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                sms_client.messages.create(body=sms_body, from_=TWILIO_FROM_NUMBER, to=VENDOR_SMS_NUMBER)
            except Exception:
                app.logger.exception("Vendor SMS failed for order %s", order_id)
        else:
            app.logger.info("Order %s saved; vendor SMS settings are not configured", order_id)

        session["cart"] = {}
        flash("Your order has been submitted successfully.", "success")
        return redirect(url_for("confirmation", order_id=order_id))

    return render_template("checkout.html", items=items, subtotal=subtotal, total=total)


@app.route("/order/<int:order_id>")
def confirmation(order_id):
    with connect_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return redirect(url_for("home"))
    return render_template("confirmation.html", order=order)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_authenticated"):
        return redirect(url_for("admin_orders"))
    if request.method == "POST":
        submitted = request.form.get("password", "")
        print("ADMIN_PASSWORD configured:", bool(ADMIN_PASSWORD))
        print("CSRF valid:", valid_csrf())
        print("Password matches:", bool(ADMIN_PASSWORD) and hmac.compare_digest(submitted, ADMIN_PASSWORD))
        
        if valid_csrf() and ADMIN_PASSWORD and hmac.compare_digest(submitted, ADMIN_PASSWORD):
            session.clear()
            session["_csrf_token"] = secrets.token_urlsafe(32)
            session["admin_authenticated"] = True
            flash("Admin login successful.", "success")
            next_url = request.args.get("next", "")
            if not next_url.startswith("/admin") or next_url.startswith("//"):
                next_url = url_for("admin_orders")
            return redirect(next_url)
        flash("Incorrect password or admin password is not configured.", "error")
    return render_template("admin_login.html")


@app.post("/admin/logout")
@admin_required
def admin_logout():
    if not valid_csrf():
        flash("Security token expired. Please try again.", "error")
        return redirect(url_for("admin_orders"))
    session.pop("admin_authenticated", None)
    flash("Admin logged out.", "success")
    return redirect(url_for("admin_login"))


@app.route("/admin")
@app.route("/admin/orders")
@admin_required
def admin_orders():
    with connect_db() as conn:
        orders = conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC, id DESC"
        ).fetchall()

    parsed_orders = []

    for order in orders:
        data = dict(order)

        try:
            data["order_lines"] = json.loads(data["items_json"])
        except (TypeError, ValueError):
            data["order_lines"] = []

        parsed_orders.append(data)

    pending_count = sum(
        1 for order in parsed_orders
        if not order["fulfilled"]
    )

    return render_template(
        "admin_orders.html",
        orders=parsed_orders,
        pending_count=pending_count
    )

@app.route("/admin/revenue")
@admin_required
def admin_revenue():
    with connect_db() as conn:
        stats = conn.execute("""SELECT
            COALESCE(SUM(CASE WHEN fulfilled = 1 THEN total ELSE 0 END), 0) AS collected_total,
            COALESCE(SUM(CASE WHEN fulfilled = 1 THEN 1 ELSE 0 END), 0) AS fulfilled_count,
            COALESCE(SUM(CASE WHEN fulfilled = 0 THEN total ELSE 0 END), 0) AS pending_total,
            COUNT(*) AS order_count
            FROM orders""").fetchone()
    return render_template("admin_revenue.html", stats=stats)


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")
