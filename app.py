#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sqlite3
from functools import wraps
from flask import Flask, render_template_string, request, redirect, url_for, session, flash

# 修正：去掉 @ 符号
app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'


# ==================== 数据库初始化 ====================
def init_db():
    """初始化 SQLite 数据库"""
    conn = sqlite3.connect('library.db')
    cursor = conn.cursor()

    # 创建用户表
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS users
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       username
                       TEXT
                       UNIQUE
                       NOT
                       NULL,
                       password
                       TEXT
                       NOT
                       NULL,
                       created_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    # 创建图书表
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS books
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       title
                       TEXT
                       NOT
                       NULL,
                       author
                       TEXT
                       NOT
                       NULL,
                       isbn
                       TEXT
                       UNIQUE,
                       created_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    # 创建借阅记录表
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS borrow_records
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       book_id
                       INTEGER
                       NOT
                       NULL,
                       user_id
                       INTEGER
                       NOT
                       NULL,
                       borrow_date
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP,
                       return_date
                       TIMESTAMP,
                       status
                       TEXT
                       DEFAULT
                       'borrowed',
                       FOREIGN
                       KEY
                   (
                       book_id
                   ) REFERENCES books
                   (
                       id
                   ),
                       FOREIGN KEY
                   (
                       user_id
                   ) REFERENCES users
                   (
                       id
                   )
                       )
                   ''')

    conn.commit()
    conn.close()
    print("数据库初始化完成！")


# 初始化数据库
init_db()


# ==================== 辅助函数 ====================
def simple_encrypt(password):
    """简单的密码加密"""
    return ''.join(chr(ord(c) + 1) for c in password)


def simple_decrypt(encrypted_password):
    """简单的密码解密"""
    return ''.join(chr(ord(c) - 1) for c in encrypted_password)


def login_required(f):
    """登录验证装饰器"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect('library.db')
    conn.row_factory = sqlite3.Row
    return conn


# ==================== 路由 ====================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, page='index')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('用户名和密码不能为空', 'danger')
            return redirect(url_for('register'))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            flash('用户名已存在', 'danger')
            conn.close()
            return redirect(url_for('register'))

        encrypted_password = simple_encrypt(password)
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                       (username, encrypted_password))
        conn.commit()
        conn.close()

        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))

    return render_template_string(HTML_TEMPLATE, page='register')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, password FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()

        if user and simple_decrypt(user['password']) == password:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('登录成功', 'success')
            return redirect(url_for('books_list'))
        else:
            flash('用户名或密码错误', 'danger')
            return redirect(url_for('login'))

    return render_template_string(HTML_TEMPLATE, page='login')


@app.route('/logout')
def logout():
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('index'))


@app.route('/books')
def books_list():
    search_keyword = request.args.get('search', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    if search_keyword:
        search_pattern = f'%{search_keyword}%'
        cursor.execute('''
                       SELECT b.*,
                              CASE WHEN br.id IS NOT NULL AND br.status = 'borrowed' THEN 1 ELSE 0 END as is_borrowed,
                              br.user_id                                                               as borrowed_by
                       FROM books b
                                LEFT JOIN borrow_records br ON b.id = br.book_id AND br.status = 'borrowed'
                       WHERE b.title LIKE ?
                          OR b.author LIKE ?
                       ORDER BY b.id DESC
                       ''', (search_pattern, search_pattern))
    else:
        cursor.execute('''
                       SELECT b.*,
                              CASE WHEN br.id IS NOT NULL AND br.status = 'borrowed' THEN 1 ELSE 0 END as is_borrowed,
                              br.user_id                                                               as borrowed_by
                       FROM books b
                                LEFT JOIN borrow_records br ON b.id = br.book_id AND br.status = 'borrowed'
                       ORDER BY b.id DESC
                       ''')

    books = cursor.fetchall()
    conn.close()

    return render_template_string(HTML_TEMPLATE, page='books_list', books=books, search=search_keyword)


@app.route('/books/add', methods=['GET', 'POST'])
@login_required
def add_book():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        isbn = request.form.get('isbn', '').strip()

        if not title or not author:
            flash('书名和作者不能为空', 'danger')
            return redirect(url_for('add_book'))

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('INSERT INTO books (title, author, isbn) VALUES (?, ?, ?)',
                           (title, author, isbn if isbn else None))
            conn.commit()
            flash('图书添加成功', 'success')
        except sqlite3.IntegrityError:
            flash('ISBN已存在', 'danger')
        finally:
            conn.close()

        return redirect(url_for('books_list'))

    return render_template_string(HTML_TEMPLATE, page='add_book')


@app.route('/books/edit/<int:book_id>', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        isbn = request.form.get('isbn', '').strip()

        if not title or not author:
            flash('书名和作者不能为空', 'danger')
            return redirect(url_for('edit_book', book_id=book_id))

        cursor.execute('''
                       UPDATE books
                       SET title  = ?,
                           author = ?,
                           isbn   = ?
                       WHERE id = ?
                       ''', (title, author, isbn if isbn else None, book_id))
        conn.commit()
        conn.close()

        flash('图书信息更新成功', 'success')
        return redirect(url_for('books_list'))

    cursor.execute('SELECT * FROM books WHERE id = ?', (book_id,))
    book = cursor.fetchone()
    conn.close()

    if not book:
        flash('图书不存在', 'danger')
        return redirect(url_for('books_list'))

    return render_template_string(HTML_TEMPLATE, page='edit_book', book=book)


@app.route('/books/delete/<int:book_id>')
@login_required
def delete_book(book_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM borrow_records WHERE book_id = ? AND status = "borrowed"', (book_id,))
    if cursor.fetchone():
        flash('该图书尚有未归还的借阅记录，无法删除', 'danger')
        conn.close()
        return redirect(url_for('books_list'))

    cursor.execute('DELETE FROM borrow_records WHERE book_id = ?', (book_id,))
    cursor.execute('DELETE FROM books WHERE id = ?', (book_id,))
    conn.commit()
    conn.close()

    flash('图书删除成功', 'success')
    return redirect(url_for('books_list'))


@app.route('/borrow/<int:book_id>')
@login_required
def borrow_book(book_id):
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM books WHERE id = ?', (book_id,))
    if not cursor.fetchone():
        flash('图书不存在', 'danger')
        conn.close()
        return redirect(url_for('books_list'))

    cursor.execute('SELECT id FROM borrow_records WHERE book_id = ? AND status = "borrowed"', (book_id,))
    if cursor.fetchone():
        flash('该书已被借出', 'danger')
        conn.close()
        return redirect(url_for('books_list'))

    cursor.execute('''
                   INSERT INTO borrow_records (book_id, user_id, borrow_date, status)
                   VALUES (?, ?, datetime('now', 'localtime'), 'borrowed')
                   ''', (book_id, user_id))
    conn.commit()
    conn.close()

    flash('借书成功', 'success')
    return redirect(url_for('books_list'))


@app.route('/return/<int:book_id>')
@login_required
def return_book(book_id):
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
                   SELECT id
                   FROM borrow_records
                   WHERE book_id = ?
                     AND user_id = ?
                     AND status = 'borrowed'
                   ''', (book_id, user_id))
    record = cursor.fetchone()

    if not record:
        flash('您没有借阅该书', 'danger')
        conn.close()
        return redirect(url_for('books_list'))

    cursor.execute('''
                   UPDATE borrow_records
                   SET return_date = datetime('now', 'localtime'),
                       status      = 'returned'
                   WHERE id = ?
                   ''', (record['id'],))
    conn.commit()
    conn.close()

    flash('还书成功', 'success')
    return redirect(url_for('books_list'))


@app.route('/my_borrows')
@login_required
def my_borrows():
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
                   SELECT br.*,
                          b.title,
                          b.author,
                          b.isbn,
                          strftime('%Y-%m-%d %H:%M', br.borrow_date) as borrow_date_fmt,
                          CASE
                              WHEN br.return_date IS NOT NULL
                                  THEN strftime('%Y-%m-%d %H:%M', br.return_date)
                              ELSE NULL END                          as return_date_fmt
                   FROM borrow_records br
                            JOIN books b ON br.book_id = b.id
                   WHERE br.user_id = ?
                   ORDER BY br.borrow_date DESC
                   ''', (user_id,))

    records = cursor.fetchall()
    conn.close()

    return render_template_string(HTML_TEMPLATE, page='my_borrows', records=records)


# ==================== HTML 模板 ====================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>图书管理系统</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        .navbar {
            background: white;
            border-radius: 10px;
            padding: 15px 30px;
            margin-bottom: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }

        .navbar h1 {
            color: #667eea;
            font-size: 24px;
        }

        .nav-links {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }

        .nav-links a {
            text-decoration: none;
            color: #555;
            padding: 5px 10px;
            transition: color 0.3s;
        }

        .nav-links a:hover {
            color: #667eea;
        }

        .nav-links .user-info {
            color: #667eea;
            font-weight: bold;
        }

        .card {
            background: white;
            border-radius: 10px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        .card h2 {
            margin-bottom: 20px;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
        }

        .form-group input {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
        }

        .btn {
            display: inline-block;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            text-decoration: none;
        }

        .btn-primary {
            background: #667eea;
            color: white;
        }

        .btn-danger {
            background: #e74c3c;
            color: white;
        }

        .btn-success {
            background: #27ae60;
            color: white;
        }

        .btn-warning {
            background: #f39c12;
            color: white;
        }

        .btn-secondary {
            background: #95a5a6;
            color: white;
        }

        .table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }

        .table th, .table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }

        .table th {
            background: #f8f9fa;
        }

        .search-bar {
            margin-bottom: 20px;
            display: flex;
            gap: 10px;
        }

        .search-bar input {
            flex: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }

        .alert {
            padding: 12px 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }

        .alert-success {
            background: #d4edda;
            color: #155724;
        }

        .alert-danger {
            background: #f8d7da;
            color: #721c24;
        }

        .status-borrowed {
            color: #e74c3c;
            font-weight: bold;
        }

        .status-returned {
            color: #27ae60;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="navbar">
            <h1>📚 图书管理系统</h1>
            <div class="nav-links">
                <a href="{{ url_for('index') }}">首页</a>
                {% if session.user_id %}
                    <a href="{{ url_for('books_list') }}">图书列表</a>
                    <a href="{{ url_for('add_book') }}">添加图书</a>
                    <a href="{{ url_for('my_borrows') }}">我的借阅</a>
                    <span>欢迎, {{ session.username }}</span>
                    <a href="{{ url_for('logout') }}">退出登录</a>
                {% else %}
                    <a href="{{ url_for('login') }}">登录</a>
                    <a href="{{ url_for('register') }}">注册</a>
                {% endif %}
            </div>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% if page == 'index' %}
            <div class="card" style="text-align: center;">
                <h2>欢迎使用图书管理系统</h2>
                <p style="margin: 20px 0;">轻松管理您的图书借阅，享受阅读的乐趣</p>
            </div>

        {% elif page == 'register' %}
            <div class="card" style="max-width: 500px; margin: 0 auto;">
                <h2>用户注册</h2>
                <form method="POST">
                    <div class="form-group">
                        <label>用户名</label>
                        <input type="text" name="username" required>
                    </div>
                    <div class="form-group">
                        <label>密码</label>
                        <input type="password" name="password" required>
                    </div>
                    <button type="submit" class="btn btn-primary">注册</button>
                    <a href="{{ url_for('login') }}">已有账号？登录</a>
                </form>
            </div>

        {% elif page == 'login' %}
            <div class="card" style="max-width: 500px; margin: 0 auto;">
                <h2>用户登录</h2>
                <form method="POST">
                    <div class="form-group">
                        <label>用户名</label>
                        <input type="text" name="username" required>
                    </div>
                    <div class="form-group">
                        <label>密码</label>
                        <input type="password" name="password" required>
                    </div>
                    <button type="submit" class="btn btn-primary">登录</button>
                    <a href="{{ url_for('register') }}">没有账号？注册</a>
                </form>
            </div>

        {% elif page == 'books_list' %}
            <div class="card">
                <h2>图书列表</h2>
                <div class="search-bar">
                    <form method="GET" style="display: flex; gap: 10px; width: 100%;">
                        <input type="text" name="search" placeholder="按书名或作者搜索..." value="{{ search or '' }}">
                        <button type="submit" class="btn btn-primary">搜索</button>
                    </form>
                </div>
                <a href="{{ url_for('add_book') }}" class="btn btn-success">添加新书</a>
                {% if books %}
                    <table class="table">
                        <thead>
                            <tr><th>书名</th><th>作者</th><th>ISBN</th><th>状态</th><th>操作</th></tr>
                        </thead>
                        <tbody>
                            {% for book in books %}
                            <tr>
                                <td>{{ book.title }}</td>
                                <td>{{ book.author }}</td>
                                <td>{{ book.isbn or '-' }}</td>
                                <td>{% if book.is_borrowed %}已借出{% else %}可借{% endif %}</td>
                                <td>
                                    <a href="{{ url_for('edit_book', book_id=book.id) }}">编辑</a>
                                    {% if not book.is_borrowed %}
                                        <a href="{{ url_for('borrow_book', book_id=book.id) }}">借书</a>
                                    {% elif book.borrowed_by == session.user_id %}
                                        <a href="{{ url_for('return_book', book_id=book.id) }}">还书</a>
                                    {% endif %}
                                    <a href="{{ url_for('delete_book', book_id=book.id) }}" onclick="return confirm('确定删除？')">删除</a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                {% else %}
                    <p>暂无图书</p>
                {% endif %}
            </div>

        {% elif page == 'add_book' %}
            <div class="card" style="max-width: 600px; margin: 0 auto;">
                <h2>添加图书</h2>
                <form method="POST">
                    <div class="form-group">
                        <label>书名 *</label>
                        <input type="text" name="title" required>
                    </div>
                    <div class="form-group">
                        <label>作者 *</label>
                        <input type="text" name="author" required>
                    </div>
                    <div class="form-group">
                        <label>ISBN</label>
                        <input type="text" name="isbn">
                    </div>
                    <button type="submit" class="btn btn-primary">添加</button>
                    <a href="{{ url_for('books_list') }}">返回</a>
                </form>
            </div>

        {% elif page == 'edit_book' %}
            <div class="card" style="max-width: 600px; margin: 0 auto;">
                <h2>编辑图书</h2>
                <form method="POST">
                    <div class="form-group">
                        <label>书名 *</label>
                        <input type="text" name="title" value="{{ book.title }}" required>
                    </div>
                    <div class="form-group">
                        <label>作者 *</label>
                        <input type="text" name="author" value="{{ book.author }}" required>
                    </div>
                    <div class="form-group">
                        <label>ISBN</label>
                        <input type="text" name="isbn" value="{{ book.isbn or '' }}">
                    </div>
                    <button type="submit" class="btn btn-primary">保存</button>
                    <a href="{{ url_for('books_list') }}">取消</a>
                </form>
            </div>

        {% elif page == 'my_borrows' %}
            <div class="card">
                <h2>我的借阅记录</h2>
                {% if records %}
                    <table class="table">
                        <thead><tr><th>书名</th><th>作者</th><th>借阅时间</th><th>归还时间</th><th>状态</th></tr></thead>
                        <tbody>
                            {% for record in records %}
                            <tr>
                                <td>{{ record.title }}</td>
                                <td>{{ record.author }}</td>
                                <td>{{ record.borrow_date_fmt }}</td>
                                <td>{{ record.return_date_fmt or '-' }}</td>
                                <td>{% if record.status == 'borrowed' %}借阅中{% else %}已归还{% endif %}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                {% else %}
                    <p>暂无借阅记录</p>
                {% endif %}
            </div>
        {% endif %}
    </div>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)