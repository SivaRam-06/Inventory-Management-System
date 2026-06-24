import os
import csv
import io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, IntegerField, DecimalField, SelectField, FileField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'images')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'inventory.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

############# Models #############

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text)
    products = db.relationship('Product', backref='category', lazy=True)

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_name = db.Column(db.String(200), nullable=False)
    contact_person = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(200))
    address = db.Column(db.Text)
    products = db.relationship('Product', backref='supplier', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=True)
    sku = db.Column(db.String(120), unique=True, nullable=False)
    brand = db.Column(db.String(120))
    description = db.Column(db.Text)
    purchase_price = db.Column(db.Float, default=0.0)
    selling_price = db.Column(db.Float, default=0.0)
    quantity = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=0)
    image = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    logs = db.relationship('InventoryLog', backref='product', lazy=True)

class InventoryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)  # IN, OUT, ADJUST
    quantity = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.Column(db.String(120))

############# Forms #############

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class CategoryForm(FlaskForm):
    name = StringField('Category Name', validators=[DataRequired(), Length(max=120)])
    description = TextAreaField('Description', validators=[Optional()])
    submit = SubmitField('Save')

class SupplierForm(FlaskForm):
    supplier_name = StringField('Supplier Name', validators=[DataRequired()])
    contact_person = StringField('Contact Person', validators=[Optional()])
    phone = StringField('Phone', validators=[Optional()])
    email = StringField('Email', validators=[Optional()])
    address = TextAreaField('Address', validators=[Optional()])
    submit = SubmitField('Save')

def validate_non_negative(form, field):
    if field.data is not None and field.data < 0:
        raise ValidationError('Value cannot be negative')

class ProductForm(FlaskForm):
    name = StringField('Product Name', validators=[DataRequired()])
    category_id = SelectField('Category', coerce=int, validators=[Optional()])
    supplier_id = SelectField('Supplier', coerce=int, validators=[Optional()])
    sku = StringField('SKU', validators=[DataRequired(), Length(max=120)])
    brand = StringField('Brand', validators=[Optional()])
    description = TextAreaField('Description', validators=[Optional()])
    purchase_price = DecimalField('Purchase Price', validators=[NumberRange(min=0)], default=0)
    selling_price = DecimalField('Selling Price', validators=[NumberRange(min=0)], default=0)
    quantity = IntegerField('Quantity', validators=[NumberRange(min=0)], default=0)
    reorder_level = IntegerField('Reorder Level', validators=[NumberRange(min=0)], default=0)
    image = FileField('Product Image', validators=[Optional()])
    submit = SubmitField('Save')

class StockForm(FlaskForm):
    product_id = SelectField('Product', coerce=int, validators=[DataRequired()])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Apply')

############# Auth #############

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def create_default_admin():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        pw = generate_password_hash('admin123')
        admin = User(username='admin', password=pw)
        db.session.add(admin)
        db.session.commit()

############# Helpers #############

def save_image(file_storage):
    if not file_storage:
        return None
    filename = secure_filename(file_storage.filename)
    if filename == '':
        return None
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file_storage.save(path)
    return filename

def generate_product_id():
    base = 'P' + datetime.utcnow().strftime('%Y%m%d%H%M%S')
    return base

############# Routes #############

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            flash('Logged in successfully', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    total_products = Product.query.count()
    total_categories = Category.query.count()
    total_stock = db.session.query(db.func.sum(Product.quantity)).scalar() or 0
    low_stock = Product.query.filter(Product.quantity <= Product.reorder_level).count()
    out_of_stock = Product.query.filter(Product.quantity <= 0).count()
    recent_products = Product.query.order_by(Product.created_at.desc()).limit(6).all()
    return render_template('dashboard.html', total_products=total_products, total_categories=total_categories,
                           total_stock=total_stock, low_stock=low_stock, out_of_stock=out_of_stock,
                           recent_products=recent_products)

### Category CRUD
@app.route('/categories')
@login_required
def categories():
    q = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    query = Category.query
    if q:
        query = query.filter(Category.name.ilike(f'%{q}%'))
    pagination = query.order_by(Category.name).paginate(page=page, per_page=10)
    return render_template('categories.html', pagination=pagination, q=q)

@app.route('/category/add', methods=['GET', 'POST'])
@login_required
def add_category():
    form = CategoryForm()
    if form.validate_on_submit():
        existing = Category.query.filter_by(name=form.name.data.strip()).first()
        if existing:
            flash('Category already exists', 'danger')
        else:
            cat = Category(name=form.name.data.strip(), description=form.description.data)
            db.session.add(cat)
            db.session.commit()
            flash('Category added', 'success')
            return redirect(url_for('categories'))
    return render_template('category_form.html', form=form)

@app.route('/category/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_category(id):
    cat = Category.query.get_or_404(id)
    form = CategoryForm(obj=cat)
    if form.validate_on_submit():
        cat.name = form.name.data.strip()
        cat.description = form.description.data
        db.session.commit()
        flash('Category updated', 'success')
        return redirect(url_for('categories'))
    return render_template('category_form.html', form=form, edit=True)

@app.route('/category/<int:id>/delete', methods=['POST'])
@login_required
def delete_category(id):
    cat = Category.query.get_or_404(id)
    try:
        db.session.delete(cat)
        db.session.commit()
        flash('Category deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting category', 'danger')
    return redirect(url_for('categories'))

### Supplier CRUD
@app.route('/suppliers')
@login_required
def suppliers():
    q = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    query = Supplier.query
    if q:
        query = query.filter(Supplier.supplier_name.ilike(f'%{q}%'))
    pagination = query.order_by(Supplier.supplier_name).paginate(page=page, per_page=10)
    return render_template('suppliers.html', pagination=pagination, q=q)

@app.route('/supplier/add', methods=['GET', 'POST'])
@login_required
def add_supplier():
    form = SupplierForm()
    if form.validate_on_submit():
        s = Supplier(supplier_name=form.supplier_name.data.strip(), contact_person=form.contact_person.data,
                     phone=form.phone.data, email=form.email.data, address=form.address.data)
        db.session.add(s)
        db.session.commit()
        flash('Supplier added', 'success')
        return redirect(url_for('suppliers'))
    return render_template('supplier_form.html', form=form)

@app.route('/supplier/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_supplier(id):
    s = Supplier.query.get_or_404(id)
    form = SupplierForm(obj=s)
    if form.validate_on_submit():
        s.supplier_name = form.supplier_name.data.strip()
        s.contact_person = form.contact_person.data
        s.phone = form.phone.data
        s.email = form.email.data
        s.address = form.address.data
        db.session.commit()
        flash('Supplier updated', 'success')
        return redirect(url_for('suppliers'))
    return render_template('supplier_form.html', form=form, edit=True)

@app.route('/supplier/<int:id>/delete', methods=['POST'])
@login_required
def delete_supplier(id):
    s = Supplier.query.get_or_404(id)
    try:
        db.session.delete(s)
        db.session.commit()
        flash('Supplier deleted', 'success')
    except Exception:
        db.session.rollback()
        flash('Error deleting supplier', 'danger')
    return redirect(url_for('suppliers'))

### Product CRUD
@app.route('/products')
@login_required
def products():
    q = request.args.get('q', '')
    category = request.args.get('category', type=int)
    supplier = request.args.get('supplier', type=int)
    status = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    query = Product.query
    if q:
        query = query.filter((Product.name.ilike(f'%{q}%')) | (Product.sku.ilike(f'%{q}%')) | (Product.brand.ilike(f'%{q}%')))
    if category:
        query = query.filter_by(category_id=category)
    if supplier:
        query = query.filter_by(supplier_id=supplier)
    if status == 'low':
        query = query.filter(Product.quantity <= Product.reorder_level)
    if status == 'out':
        query = query.filter(Product.quantity <= 0)
    pagination = query.order_by(Product.name).paginate(page=page, per_page=12)
    categories = Category.query.order_by(Category.name).all()
    suppliers = Supplier.query.order_by(Supplier.supplier_name).all()
    return render_template('products.html', pagination=pagination, categories=categories, suppliers=suppliers, q=q)

@app.route('/product/add', methods=['GET', 'POST'])
@login_required
def add_product():
    form = ProductForm()
    form.category_id.choices = [(0, '---')] + [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    form.supplier_id.choices = [(0, '---')] + [(s.id, s.supplier_name) for s in Supplier.query.order_by(Supplier.supplier_name).all()]
    if form.validate_on_submit():
        if Product.query.filter_by(sku=form.sku.data.strip()).first():
            flash('SKU already exists', 'danger')
            return render_template('product_form.html', form=form)
        pid = generate_product_id()
        filename = None
        if form.image.data:
            filename = save_image(form.image.data)
        prod = Product(product_id=pid, name=form.name.data.strip(), category_id=(form.category_id.data or None) or None,
                       supplier_id=(form.supplier_id.data or None) or None,
                       sku=form.sku.data.strip(), brand=form.brand.data, description=form.description.data,
                       purchase_price=float(form.purchase_price.data or 0), selling_price=float(form.selling_price.data or 0),
                       quantity=int(form.quantity.data or 0), reorder_level=int(form.reorder_level.data or 0), image=filename)
        db.session.add(prod)
        db.session.commit()
        # log initial stock
        if prod.quantity and prod.quantity > 0:
            log = InventoryLog(product_id=prod.id, action_type='IN', quantity=prod.quantity, notes='Initial stock', user=current_user.username)
            db.session.add(log)
            db.session.commit()
        flash('Product added', 'success')
        return redirect(url_for('products'))
    return render_template('product_form.html', form=form)

@app.route('/product/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    prod = Product.query.get_or_404(id)
    form = ProductForm(obj=prod)
    form.category_id.choices = [(0, '---')] + [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    form.supplier_id.choices = [(0, '---')] + [(s.id, s.supplier_name) for s in Supplier.query.order_by(Supplier.supplier_name).all()]
    if form.validate_on_submit():
        if prod.sku != form.sku.data.strip() and Product.query.filter_by(sku=form.sku.data.strip()).first():
            flash('SKU already exists', 'danger')
            return render_template('product_form.html', form=form, edit=True)
        prod.name = form.name.data.strip()
        prod.category_id = (form.category_id.data or None) or None
        prod.supplier_id = (form.supplier_id.data or None) or None
        prod.sku = form.sku.data.strip()
        prod.brand = form.brand.data
        prod.description = form.description.data
        prod.purchase_price = float(form.purchase_price.data or 0)
        prod.selling_price = float(form.selling_price.data or 0)
        # quantity change -> log
        new_q = int(form.quantity.data or 0)
        if new_q != prod.quantity:
            diff = new_q - prod.quantity
            action = 'IN' if diff > 0 else 'OUT'
            log = InventoryLog(product_id=prod.id, action_type=action, quantity=abs(diff), notes='Manual edit', user=current_user.username)
            db.session.add(log)
        prod.quantity = new_q
        prod.reorder_level = int(form.reorder_level.data or 0)
        if form.image.data:
            filename = save_image(form.image.data)
            prod.image = filename
        db.session.commit()
        flash('Product updated', 'success')
        return redirect(url_for('products'))
    # populate select fields
    form.category_id.data = prod.category_id or 0
    form.supplier_id.data = prod.supplier_id or 0
    return render_template('product_form.html', form=form, edit=True, product=prod)

@app.route('/product/<int:id>/delete', methods=['POST'])
@login_required
def delete_product(id):
    p = Product.query.get_or_404(id)
    try:
        db.session.delete(p)
        db.session.commit()
        flash('Product deleted', 'success')
    except Exception:
        db.session.rollback()
        flash('Error deleting product', 'danger')
    return redirect(url_for('products'))

@app.route('/product/<int:id>')
@login_required
def product_view(id):
    p = Product.query.get_or_404(id)
    logs = InventoryLog.query.filter_by(product_id=p.id).order_by(InventoryLog.created_at.desc()).all()
    return render_template('product_view.html', product=p, logs=logs)

### Stock management
@app.route('/stock/in', methods=['GET', 'POST'])
@login_required
def stock_in():
    form = StockForm()
    form.product_id.choices = [(p.id, f'{p.name} ({p.sku})') for p in Product.query.order_by(Product.name).all()]
    if form.validate_on_submit():
        p = Product.query.get_or_404(form.product_id.data)
        p.quantity += int(form.quantity.data)
        log = InventoryLog(product_id=p.id, action_type='IN', quantity=form.quantity.data, notes=form.notes.data, user=current_user.username)
        db.session.add(log)
        db.session.commit()
        flash('Stock updated (IN)', 'success')
        return redirect(url_for('products'))
    return render_template('stock_in.html', form=form)

@app.route('/stock/out', methods=['GET', 'POST'])
@login_required
def stock_out():
    form = StockForm()
    form.product_id.choices = [(p.id, f'{p.name} ({p.sku})') for p in Product.query.order_by(Product.name).all()]
    if form.validate_on_submit():
        p = Product.query.get_or_404(form.product_id.data)
        qty = int(form.quantity.data)
        if qty > p.quantity:
            flash('Cannot remove more than available stock', 'danger')
            return render_template('stock_out.html', form=form)
        p.quantity -= qty
        log = InventoryLog(product_id=p.id, action_type='OUT', quantity=qty, notes=form.notes.data, user=current_user.username)
        db.session.add(log)
        db.session.commit()
        flash('Stock updated (OUT)', 'success')
        return redirect(url_for('products'))
    return render_template('stock_out.html', form=form)

@app.route('/logs')
@login_required
def logs():
    page = request.args.get('page', 1, type=int)
    pagination = InventoryLog.query.order_by(InventoryLog.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('logs.html', pagination=pagination)

### Reports & Exports
@app.route('/export/csv')
@login_required
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Product ID', 'Name', 'SKU', 'Category', 'Supplier', 'Quantity', 'Reorder Level'])
    for p in Product.query.order_by(Product.name).all():
        writer.writerow([p.product_id, p.name, p.sku, p.category.name if p.category else '', p.supplier.supplier_name if p.supplier else '', p.quantity, p.reorder_level])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()), mimetype='text/csv', as_attachment=True, download_name='inventory.csv')

@app.route('/backup')
@login_required
def backup_db():
    path = os.path.join(BASE_DIR, 'inventory.db')
    if not os.path.exists(path):
        flash('Database not found', 'danger')
        return redirect(url_for('dashboard'))
    return send_file(path, as_attachment=True, download_name='inventory_backup.db')

@app.route('/restore', methods=['GET', 'POST'])
@login_required
def restore_db():
    if request.method == 'POST':
        file = request.files.get('db')
        if not file:
            flash('No file', 'danger')
            return redirect(url_for('restore_db'))
        fname = secure_filename(file.filename)
        target = os.path.join(BASE_DIR, fname)
        file.save(target)
        # replace current db
        try:
            db.session.close()
            os.replace(target, os.path.join(BASE_DIR, 'inventory.db'))
            flash('Database restored. Restart app to apply.', 'success')
        except Exception as e:
            flash('Restore failed', 'danger')
        return redirect(url_for('dashboard'))
    return render_template('restore.html')

### Error handlers
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

############# App init #############
if __name__ == '__main__':
    # Ensure DB and default admin are created within app context
    with app.app_context():
        db.create_all()
        create_default_admin()
        # copy a default image if not exists
        default_img = os.path.join(app.config['UPLOAD_FOLDER'], 'default.png')
        if not os.path.exists(default_img):
            with open(default_img, 'wb') as f:
                f.write(b'')
    app.run(debug=True)
