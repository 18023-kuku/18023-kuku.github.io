from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from db import db
from models import User, Todo

# 创建蓝图
auth_bp = Blueprint('auth', __name__)
todo_bp = Blueprint('todo', __name__)

# 注册路由
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    # 检查用户名是否已存在
    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Username already exists'}), 400
    
    # 创建新用户
    new_user = User(username=username, password=password)
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({'message': 'User created successfully'}), 201

# 登录路由
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    # 查找用户
    user = User.query.filter_by(username=username).first()
    if not user or user.password != password:
        return jsonify({'message': 'Invalid username or password'}), 401
    
    # 创建访问令牌（将用户 ID 转换为字符串）
    access_token = create_access_token(identity=str(user.id))
    return jsonify({'access_token': access_token}), 200

# 创建待办事项路由
@todo_bp.route('', methods=['POST'])
@jwt_required()
def create_todo():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    title = data.get('title')
    content = data.get('content', '')
    
    if not title:
        return jsonify({'message': 'Title is required'}), 400
    
    new_todo = Todo(title=title, content=content, user_id=user_id)
    db.session.add(new_todo)
    db.session.commit()
    
    return jsonify({
        'id': new_todo.id,
        'title': new_todo.title,
        'content': new_todo.content,
        'completed': new_todo.completed,
        'user_id': new_todo.user_id
    }), 201

# 获取待办事项列表路由
@todo_bp.route('', methods=['GET'])
@jwt_required()
def get_todos():
    user_id = int(get_jwt_identity())
    todos = Todo.query.filter_by(user_id=user_id).all()
    
    todo_list = []
    for todo in todos:
        todo_list.append({
            'id': todo.id,
            'title': todo.title,
            'content': todo.content,
            'completed': todo.completed,
            'user_id': todo.user_id
        })
    
    return jsonify(todo_list), 200

# 更新待办事项状态路由
@todo_bp.route('/<int:todo_id>', methods=['PUT'])
@jwt_required()
def update_todo(todo_id):
    user_id = int(get_jwt_identity())
    todo = Todo.query.filter_by(id=todo_id, user_id=user_id).first()
    
    if not todo:
        return jsonify({'message': 'Todo not found'}), 404
    
    data = request.get_json()
    todo.completed = data.get('completed', todo.completed)
    
    db.session.commit()
    
    return jsonify({
        'id': todo.id,
        'title': todo.title,
        'content': todo.content,
        'completed': todo.completed,
        'user_id': todo.user_id
    }), 200

# 删除待办事项路由
@todo_bp.route('/<int:todo_id>', methods=['DELETE'])
@jwt_required()
def delete_todo(todo_id):
    user_id = int(get_jwt_identity())
    todo = Todo.query.filter_by(id=todo_id, user_id=user_id).first()
    
    if not todo:
        return jsonify({'message': 'Todo not found'}), 404
    
    db.session.delete(todo)
    db.session.commit()
    
    return jsonify({'message': 'Todo deleted successfully'}), 200