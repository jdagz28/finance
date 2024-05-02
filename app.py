import os
import datetime

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]
    transactions_db = db.execute(
        "SELECT symbol, SUM(shares) AS shares, AVG(price) AS price_per_share, SUM(shares * price) AS total FROM transactions WHERE user_id = ? GROUP BY symbol",
        user_id,
    )
    cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash = cash_db[0]["cash"]
    if transactions_db is not None and len(transactions_db) > 0:
        total_cash = cash + transactions_db[0]["total"]
    else:
        total_cash = cash
    for row in transactions_db:
        row["price_per_share"] = usd(row["price_per_share"])
        row["total"] = usd(row["total"])
    cash_formatted = usd(cash)
    total_cash_formatted = usd(total_cash)

    return render_template(
        "index.html",
        database=transactions_db,
        cash=cash_formatted,
        total_cash=total_cash_formatted,
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol = request.form.get("symbol")
        shares_str = request.form.get("shares")
        if not symbol:
            return apology("Must enter a valid stock symbol")
        elif not shares_str or not shares_str.isdigit() or int(shares_str) <= 0:
            return apology("Invalid number of shares")
        shares = int(shares_str)
        stock = lookup(symbol.upper())
        if stock == None:
            return apology("Stock symbol does not exist")
        transaction_value = shares * stock["price"]
        user_id = session["user_id"]
        user_cash_db = db.execute("SELECT cash FROM users WHERE id = :id", id=user_id)
        user_cash = user_cash_db[0]["cash"]
        if transaction_value > user_cash:
            return apology("User does not have enough cash for the transaction")
        update_cash = user_cash - transaction_value
        db.execute("UPDATE users SET cash = ? WHERE id = ?", update_cash, user_id)
        date = datetime.datetime.now()
        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price, date, action) VALUES (?, ?, ?, ?, ?, ?)",
            user_id,
            stock["symbol"],
            shares,
            stock["price"],
            date,
            "BUY",
        )

        flash(f"Bought {shares} of {symbol} for {usd(transaction_value)}")
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]
    user_transactions_db = db.execute(
        "SELECT * FROM transactions WHERE user_id = :id", id=user_id
    )
    return render_template("history.html", transactions=user_transactions_db)


@app.route("/addcash", methods=["GET", "POST"])
@login_required
def addcash():
    """User can add cash"""
    user_id = session["user_id"]
    if request.method == "GET":
        return render_template("add.html")
    else:
        new_cash = int(request.form.get("cash"))
        if not new_cash:
            return apology("must deposit at least $1")
        user_cash_db = db.execute("SELECT cash FROM users WHERE id = :id", id=user_id)
        user_cash = user_cash_db[0]["cash"]
        update_cash = user_cash + new_cash
        db.execute("UPDATE users SET cash = ? WHERE id = ?", update_cash, user_id)
        return redirect("/")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Must enter a valid stock symbol")
        stock = lookup(symbol.upper())
        if stock == None:
            return apology("Stock symbol does not exist")
        else:
            return render_template(
                "quoted.html",
                name=stock["name"],
                price=usd(stock["price"]),
                symbol=stock["symbol"],
            )


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if not username:
            return apology("Blank username")
        if not password:
            return apology("Blank password")
        if not confirmation:
            return apology("Blank confirmation")
        if password != confirmation:
            return apology("Password and confirmation does not match")
        hash = generate_password_hash(password)
        try:
            new_user = db.execute(
                "INSERT INTO users(username, hash) VALUES (?, ?)", username, hash
            )
        except:
            return apology("Username already exists")

        session["user_id"] = new_user
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        user_id = session["user_id"]
        symbols_user = db.execute(
            "SELECT symbol FROM transactions WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0",
            user_id,
        )
        return render_template(
            "sell.html",
            symbols=[row["symbol"] for row in symbols_user],
            shares=symbols_user,
        )
    else:
        user_id = session["user_id"]
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        if not symbol:
            return apology("Must enter a valid stock symbol")
        stock = lookup(symbol.upper())
        if stock == None:
            return apology("Stock symbol does not exist")
        if shares < 1:
            return apology("Invalid number of shares")
        user_shares = db.execute(
            "SELECT SUM(shares) as total_shares FROM transactions WHERE user_id = ? AND symbol = ? GROUP BY symbol",
            user_id,
            symbol,
        )
        user_shares_actual = user_shares[0]["total_shares"]
        if shares > user_shares_actual:
            return apology("Insufficient number of shares")
        transaction_value = shares * stock["price"]
        user_cash_db = db.execute("SELECT cash FROM users WHERE id = :id", id=user_id)
        user_cash = user_cash_db[0]["cash"]
        update_cash = user_cash + transaction_value
        db.execute("UPDATE users SET cash = ? WHERE id = ?", update_cash, user_id)
        date = datetime.datetime.now()
        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price, date, action) VALUES (?, ?, ?, ?, ?, ?)",
            user_id,
            stock["symbol"],
            (-1) * shares,
            stock["price"],
            date,
            "SELL",
        )

        flash("Sold!")

        return redirect("/")
