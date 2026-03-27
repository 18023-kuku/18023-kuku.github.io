from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_cors import CORS
import os
from dotenv import load_dotenv
from db import db

# 加载环境变量
load_dotenv()

# 创建应用实例
app = Flask(__name__)

# 配置数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///todo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your-secret-key')

# 初始化扩展
db.init_app(app)
jwt = JWTManager(app)
CORS(app)

# 导入模型和路由
from models import User, Todo
from routes import auth_bp, todo_bp

# 注册蓝图
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(todo_bp, url_prefix='/todos')

# 应用启动时创建数据库表
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)