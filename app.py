#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件上传服务 - 基于 Flask
包含用户认证、文件上传、文件管理、图片预览等功能
"""

import os
import uuid
import sqlite3
import hashlib
from functools import wraps
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, send_from_directory

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制上传文件大小为 16MB

# 配置上传文件夹
UPLOAD_FOLDER = Path(__file__).parent / 'uploads'
UPLOAD_FOLDER.mkdir(exist_ok=True)  # 创建上传文件夹（如果不存在）

ALLOWED_EXTENSIONS = {
    'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp',  # 图片格式
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',  # 文档格式
    'txt', 'md', 'csv',  # 文本格式
    'zip', 'rar', '7z'  # 压缩包
}

# ==================== 数据库初始化 ====================
def init_db():
    """初始化 SQLite 数据库"""
    conn = sqlite3.connect('file_upload.db')
    cursor = conn.cursor()

    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 创建文件记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            file_type TEXT,
            mime_type TEXT,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users (id)
        )
    ''')

    conn.commit()
    conn.close()
    print("数据库初始化完成！")

init_db()

# ==================== 辅助函数 ====================
def simple_encrypt(password):
    """简单的密码加密"""
    return hashlib.md5(password.encode()).hexdigest()

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
    conn = sqlite3.connect('file_upload.db')
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_image_file(filename):
    """判断是否为图片文件"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext in {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def generate_filename(original_filename):
    """生成唯一的文件名"""
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
    # 使用 UUID + 时间戳生成唯一文件名
    unique_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    if ext:
        unique_name = f"{unique_name}.{ext}"
    return unique_name

def format_file_size(size):
    """格式化文件大小"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    else:
        return f"{size / (1024 * 1024):.2f} MB"

# ==================== 路由 ====================
@app.route('/')
def index():
    """首页"""
    return render_template_string(HTML_TEMPLATE, page='index')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('用户名和密码不能为空', 'danger')
            return redirect(url_for('register'))

        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查用户名是否已存在
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            flash('用户名已存在', 'danger')
            conn.close()
            return redirect(url_for('register'))

        # 加密密码并保存
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
    """用户登录"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, password FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()

        if user and user['password'] == simple_encrypt(password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('登录成功', 'success')
            return redirect(url_for('my_files'))
        else:
            flash('用户名或密码错误', 'danger')
            return redirect(url_for('login'))

    return render_template_string(HTML_TEMPLATE, page='login')

@app.route('/logout')
def logout():
    """用户登出"""
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('index'))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    """上传文件"""
    if request.method == 'POST':
        # 检查是否有文件被上传
        if 'file' not in request.files:
            flash('请选择要上传的文件', 'danger')
            return redirect(url_for('upload_file'))

        file = request.files['file']

        # 检查是否选择了文件
        if file.filename == '':
            flash('请选择要上传的文件', 'danger')
            return redirect(url_for('upload_file'))

        # 检查文件类型是否允许
        if not allowed_file(file.filename):
            flash(f'不支持的文件类型，允许的类型：{", ".join(ALLOWED_EXTENSIONS)}', 'danger')
            return redirect(url_for('upload_file'))

        try:
            # 生成唯一文件名
            stored_filename = generate_filename(file.filename)
            file_path = UPLOAD_FOLDER / stored_filename

            # 获取文件大小
            file.seek(0, 2)  # 移动到文件末尾
            file_size = file.tell()  # 获取当前位置（文件大小）
            file.seek(0)  # 重置文件指针

            # 保存文件
            file.save(file_path)

            # 判断文件类型
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            mime_type = file.content_type or f'application/{file_ext}'

            # 记录到数据库
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO files (user_id, original_filename, stored_filename, file_path, file_size, file_type, mime_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (session['user_id'], file.filename, stored_filename, str(file_path), file_size, file_ext, mime_type))
            conn.commit()
            conn.close()

            flash('文件上传成功！', 'success')
            return redirect(url_for('my_files'))

        except Exception as e:
            flash(f'上传失败：{str(e)}', 'danger')
            return redirect(url_for('upload_file'))

    return render_template_string(HTML_TEMPLATE, page='upload')

@app.route('/my_files')
@login_required
def my_files():
    """我的文件列表"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM files 
        WHERE user_id = ? 
        ORDER BY upload_time DESC
    ''', (session['user_id'],))

    files = cursor.fetchall()
    conn.close()

    # 格式化文件大小
    for file in files:
        file['formatted_size'] = format_file_size(file['file_size'])
        file['is_image'] = is_image_file(file['stored_filename'])

    return render_template_string(HTML_TEMPLATE, page='my_files', files=files)

@app.route('/preview/<int:file_id>')
@login_required
def preview_file(file_id):
    """预览文件（图片显示缩略图，其他文件显示下载链接）"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM files WHERE id = ? AND user_id = ?',
                  (file_id, session['user_id']))
    file = cursor.fetchone()
    conn.close()

    if not file:
        flash('文件不存在或无权限访问', 'danger')
        return redirect(url_for('my_files'))

    return render_template_string(HTML_TEMPLATE, page='preview', file=file)

@app.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    """下载文件"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM files WHERE id = ? AND user_id = ?',
                  (file_id, session['user_id']))
    file = cursor.fetchone()
    conn.close()

    if not file:
        flash('文件不存在或无权限访问', 'danger')
        return redirect(url_for('my_files'))

    # 发送文件
    upload_dir = UPLOAD_FOLDER
    return send_from_directory(
        upload_dir,
        file['stored_filename'],
        as_attachment=True,
        download_name=file['original_filename']
    )

@app.route('/delete/<int:file_id>')
@login_required
def delete_file(file_id):
    """删除文件"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取文件信息
    cursor.execute('SELECT * FROM files WHERE id = ? AND user_id = ?',
                  (file_id, session['user_id']))
    file = cursor.fetchone()

    if not file:
        flash('文件不存在或无权限访问', 'danger')
        conn.close()
        return redirect(url_for('my_files'))

    try:
        # 删除物理文件
        file_path = Path(file['file_path'])
        if file_path.exists():
            file_path.unlink()

        # 删除数据库记录
        cursor.execute('DELETE FROM files WHERE id = ?', (file_id,))
        conn.commit()

        flash('文件删除成功', 'success')
    except Exception as e:
        flash(f'删除失败：{str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('my_files'))

# ==================== HTML 模板 ====================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>文件上传服务</title>
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
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
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
            gap: 15px;
        }

        .navbar h1 {
            color: #667eea;
            font-size: 24px;
        }

        .nav-links {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            align-items: center;
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

        .form-group input[type="text"],
        .form-group input[type="password"],
        .form-group input[type="file"] {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
        }

        .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }

        .btn {
            display: inline-block;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            text-decoration: none;
            transition: transform 0.2s, opacity 0.2s;
        }

        .btn:hover {
            transform: translateY(-2px);
            opacity: 0.9;
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

        .btn-secondary {
            background: #95a5a6;
            color: white;
        }

        .btn-info {
            background: #3498db;
            color: white;
        }

        .alert {
            padding: 12px 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }

        .alert-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }

        .alert-danger {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }

        .alert-warning {
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
        }

        .alert-info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }

        .file-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }

        .file-card {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .file-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
        }

        .file-icon {
            text-align: center;
            font-size: 48px;
            margin-bottom: 10px;
        }

        .file-info {
            text-align: center;
        }

        .file-name {
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
            word-break: break-all;
        }

        .file-meta {
            font-size: 12px;
            color: #777;
            margin-bottom: 10px;
        }

        .file-actions {
            display: flex;
            gap: 10px;
            justify-content: center;
            margin-top: 10px;
        }

        .file-actions a {
            padding: 5px 12px;
            font-size: 12px;
        }

        .preview-container {
            text-align: center;
        }

        .preview-image {
            max-width: 100%;
            max-height: 500px;
            border-radius: 8px;
            margin: 20px 0;
        }

        @media (max-width: 768px) {
            .navbar {
                flex-direction: column;
            }

            .file-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="navbar">
            <h1>📁 文件上传服务</h1>
            <div class="nav-links">
                <a href="{{ url_for('index') }}">首页</a>
                {% if session.user_id %}
                    <a href="{{ url_for('upload_file') }}">上传文件</a>
                    <a href="{{ url_for('my_files') }}">我的文件</a>
                    <span class="user-info">欢迎, {{ session.username }}</span>
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
                <h2>欢迎使用文件上传服务</h2>
                <p style="margin: 20px 0; font-size: 18px; color: #666;">
                    安全、便捷的文件管理工具
                </p>
                <p style="margin: 10px 0; color: #888;">
                    支持图片、文档、压缩包等多种格式
                </p>
                {% if not session.user_id %}
                    <div style="margin-top: 30px;">
                        <a href="{{ url_for('login') }}" class="btn btn-primary">登录</a>
                        <a href="{{ url_for('register') }}" class="btn btn-success">注册</a>
                    </div>
                {% else %}
                    <div style="margin-top: 30px;">
                        <a href="{{ url_for('upload_file') }}" class="btn btn-primary">立即上传文件</a>
                    </div>
                {% endif %}
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

        {% elif page == 'upload' %}
            <div class="card">
                <h2>上传文件</h2>
                <form method="POST" enctype="multipart/form-data">
                    <div class="form-group">
                        <label>选择文件</label>
                        <input type="file" name="file" required>
                        <small style="color: #777; display: block; margin-top: 5px;">
                            支持格式：图片、文档、压缩包等（最大 16MB）
                        </small>
                    </div>
                    <button type="submit" class="btn btn-primary">上传</button>
                    <a href="{{ url_for('my_files') }}" class="btn btn-secondary">取消</a>
                </form>
            </div>

        {% elif page == 'my_files' %}
            <div class="card">
                <h2>我的文件</h2>
                {% if files %}
                    <div class="file-grid">
                        {% for file in files %}
                            <div class="file-card">
                                <div class="file-icon">
                                    {% if file.is_image %}
                                        🖼️
                                    {% elif file.file_type in ['pdf'] %}
                                        📄
                                    {% elif file.file_type in ['doc', 'docx'] %}
                                        📝
                                    {% elif file.file_type in ['xls', 'xlsx'] %}
                                        📊
                                    {% elif file.file_type in ['zip', 'rar', '7z'] %}
                                        📦
                                    {% else %}
                                        📎
                                    {% endif %}
                                </div>
                                <div class="file-info">
                                    <div class="file-name">{{ file.original_filename }}</div>
                                    <div class="file-meta">{{ file.formatted_size }} • {{ file.upload_time[:10] }}</div>
                                    <div class="file-actions">
                                        <a href="{{ url_for('preview_file', file_id=file.id) }}" class="btn btn-info">预览</a>
                                        <a href="{{ url_for('download_file', file_id=file.id) }}" class="btn btn-success">下载</a>
                                        <a href="{{ url_for('delete_file', file_id=file.id) }}" class="btn btn-danger" onclick="return confirm('确定删除？')">删除</a>
                                    </div>
                                </div>
                            </div>
                        {% endfor %}
                    </div>
                {% else %}
                    <p style="text-align: center; padding: 40px; color: #999;">暂无文件，<a href="{{ url_for('upload_file') }}">点击上传</a></p>
                {% endif %}
            </div>

        {% elif page == 'preview' %}
            <div class="card">
                <h2>文件预览</h2>
                <div class="preview-container">
                    {% if file.is_image %}
                        <img src="{{ url_for('download_file', file_id=file.id) }}" class="preview-image" alt="{{ file.original_filename }}">
                    {% else %}
                        <div style="padding: 40px;">
                            <div style="font-size: 64px; margin-bottom: 20px;">📄</div>
                            <p>暂不支持在线预览此类型文件</p>
                            <p>文件名：{{ file.original_filename }}</p>
                            <p>大小：{{ file.formatted_size }}</p>
                            <a href="{{ url_for('download_file', file_id=file.id) }}" class="btn btn-primary">下载文件</a>
                        </div>
                    {% endif %}
                </div>
                <div style="margin-top: 20px; text-align: center;">
                    <a href="{{ url_for('my_files') }}" class="btn btn-secondary">返回列表</a>
                </div>
            </div>
        {% endif %}
    </div>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)