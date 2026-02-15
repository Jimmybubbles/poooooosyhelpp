"""
Artist Portfolio Website - Main Flask Application
"""
import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.utils import secure_filename
from PIL import Image
import config
import models

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Ensure upload directories exist
os.makedirs(config.ORIGINALS_FOLDER, exist_ok=True)
os.makedirs(config.THUMBNAILS_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in config.ALLOWED_EXTENSIONS

def generate_unique_filename(filename):
    """Generate a unique filename while preserving extension"""
    ext = filename.rsplit('.', 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    return unique_name

def create_thumbnail(original_path, thumbnail_path):
    """Create a thumbnail from the original image"""
    with Image.open(original_path) as img:
        # Convert to RGB if necessary (for PNG with transparency)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # Calculate thumbnail size maintaining aspect ratio
        img.thumbnail(config.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

        # Save optimized thumbnail
        img.save(thumbnail_path, 'JPEG', quality=85, optimize=True)

def is_logged_in():
    """Check if user is logged in as admin"""
    return session.get('logged_in', False)

# ============================================================
# PUBLIC ROUTES
# ============================================================

@app.route('/')
def gallery():
    """Main gallery page"""
    paintings = models.get_all_paintings()
    categories = models.get_all_categories()
    return render_template('gallery.html',
                         paintings=paintings,
                         categories=categories,
                         site_name=config.SITE_NAME,
                         artist_name=config.ARTIST_NAME)

@app.route('/category/<category>')
def gallery_by_category(category):
    """Gallery filtered by category"""
    paintings = models.get_paintings_by_category(category)
    categories = models.get_all_categories()
    return render_template('gallery.html',
                         paintings=paintings,
                         categories=categories,
                         current_category=category,
                         site_name=config.SITE_NAME,
                         artist_name=config.ARTIST_NAME)

@app.route('/painting/<int:painting_id>')
def view_painting(painting_id):
    """Single painting view (for sharing)"""
    painting = models.get_painting_by_id(painting_id)
    if not painting:
        flash('Painting not found', 'error')
        return redirect(url_for('gallery'))
    return render_template('painting.html',
                         painting=painting,
                         site_name=config.SITE_NAME,
                         artist_name=config.ARTIST_NAME)

# ============================================================
# ADMIN ROUTES
# ============================================================

@app.route('/admin')
def admin():
    """Admin panel"""
    if not is_logged_in():
        return redirect(url_for('login'))
    paintings = models.get_all_paintings()
    categories = models.get_all_categories()
    return render_template('admin.html',
                         paintings=paintings,
                         categories=categories,
                         site_name=config.SITE_NAME)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Welcome back!', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Invalid credentials', 'error')

    return render_template('login.html', site_name=config.SITE_NAME)

@app.route('/logout')
def logout():
    """Admin logout"""
    session.pop('logged_in', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('gallery'))

@app.route('/admin/upload', methods=['POST'])
def upload():
    """Handle image upload"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    # Get form data
    title = request.form.get('title', 'Untitled')
    description = request.form.get('description', '')
    category = request.form.get('category', 'Other')

    # Generate unique filename
    unique_filename = generate_unique_filename(file.filename)
    original_path = os.path.join(config.ORIGINALS_FOLDER, unique_filename)
    thumbnail_filename = f"thumb_{unique_filename.rsplit('.', 1)[0]}.jpg"
    thumbnail_path = os.path.join(config.THUMBNAILS_FOLDER, thumbnail_filename)

    try:
        # Save original
        file.save(original_path)

        # Create thumbnail
        create_thumbnail(original_path, thumbnail_path)

        # Add to database
        painting_id = models.add_painting(
            title=title,
            description=description,
            category=category,
            original_filename=unique_filename,
            thumbnail_filename=thumbnail_filename
        )

        return jsonify({
            'success': True,
            'id': painting_id,
            'title': title,
            'thumbnail': url_for('static', filename=f'uploads/thumbnails/{thumbnail_filename}')
        })

    except Exception as e:
        # Cleanup on error
        if os.path.exists(original_path):
            os.remove(original_path)
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/edit/<int:painting_id>', methods=['POST'])
def edit_painting(painting_id):
    """Edit painting details"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    title = request.form.get('title')
    description = request.form.get('description')
    category = request.form.get('category')

    models.update_painting(painting_id, title, description, category)
    return jsonify({'success': True})

@app.route('/admin/delete/<int:painting_id>', methods=['POST'])
def delete_painting(painting_id):
    """Delete a painting"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    painting = models.delete_painting(painting_id)

    if painting:
        # Delete files
        original_path = os.path.join(config.ORIGINALS_FOLDER, painting['original_filename'])
        thumbnail_path = os.path.join(config.THUMBNAILS_FOLDER, painting['thumbnail_filename'])

        if os.path.exists(original_path):
            os.remove(original_path)
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)

    return jsonify({'success': True})

@app.route('/admin/reorder', methods=['POST'])
def reorder_paintings():
    """Reorder paintings via drag and drop"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    painting_ids = data.get('order', [])

    if painting_ids:
        models.update_painting_order(painting_ids)

    return jsonify({'success': True})

# ============================================================
# API ROUTES (for AJAX)
# ============================================================

@app.route('/api/painting/<int:painting_id>')
def api_get_painting(painting_id):
    """Get painting data as JSON"""
    painting = models.get_painting_by_id(painting_id)
    if not painting:
        return jsonify({'error': 'Not found'}), 404

    return jsonify({
        'id': painting['id'],
        'title': painting['title'],
        'description': painting['description'],
        'category': painting['category'],
        'original': url_for('static', filename=f"uploads/originals/{painting['original_filename']}"),
        'thumbnail': url_for('static', filename=f"uploads/thumbnails/{painting['thumbnail_filename']}")
    })

# ============================================================
# INITIALIZE AND RUN
# ============================================================

if __name__ == '__main__':
    # Initialize database
    models.init_db()

    print("\n" + "=" * 60)
    print("ARTIST PORTFOLIO WEBSITE")
    print("=" * 60)
    print(f"\nGallery:  http://localhost:5000")
    print(f"Admin:    http://localhost:5000/admin")
    print(f"\nLogin:    {config.ADMIN_USERNAME} / {config.ADMIN_PASSWORD}")
    print("=" * 60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)
