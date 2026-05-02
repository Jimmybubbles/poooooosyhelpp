"""
Database models for the Artist Portfolio Website
"""
import sqlite3
from datetime import datetime
import config

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with tables"""
    conn = get_db()
    cursor = conn.cursor()

    # Create paintings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS paintings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT,
            original_filename TEXT NOT NULL,
            thumbnail_filename TEXT NOT NULL,
            display_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')

    # Insert default categories
    default_categories = ['Paintings', 'Drawings', 'Digital Art', 'Sculptures', 'Other']
    for cat in default_categories:
        cursor.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (cat,))

    conn.commit()
    conn.close()
    print("Database initialized successfully!")

# Painting CRUD operations
def get_all_paintings():
    """Get all paintings ordered by display_order"""
    conn = get_db()
    paintings = conn.execute(
        'SELECT * FROM paintings ORDER BY display_order ASC, created_at DESC'
    ).fetchall()
    conn.close()
    return paintings

def get_painting_by_id(painting_id):
    """Get a single painting by ID"""
    conn = get_db()
    painting = conn.execute(
        'SELECT * FROM paintings WHERE id = ?', (painting_id,)
    ).fetchone()
    conn.close()
    return painting

def add_painting(title, description, category, original_filename, thumbnail_filename):
    """Add a new painting"""
    conn = get_db()
    cursor = conn.cursor()

    # Get the next display order
    max_order = conn.execute('SELECT MAX(display_order) FROM paintings').fetchone()[0]
    display_order = (max_order or 0) + 1

    cursor.execute('''
        INSERT INTO paintings (title, description, category, original_filename, thumbnail_filename, display_order)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (title, description, category, original_filename, thumbnail_filename, display_order))

    painting_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return painting_id

def update_painting(painting_id, title, description, category):
    """Update painting details"""
    conn = get_db()
    conn.execute('''
        UPDATE paintings SET title = ?, description = ?, category = ?
        WHERE id = ?
    ''', (title, description, category, painting_id))
    conn.commit()
    conn.close()

def delete_painting(painting_id):
    """Delete a painting"""
    conn = get_db()
    # Get filenames first for cleanup
    painting = conn.execute('SELECT * FROM paintings WHERE id = ?', (painting_id,)).fetchone()
    conn.execute('DELETE FROM paintings WHERE id = ?', (painting_id,))
    conn.commit()
    conn.close()
    return painting

def update_painting_order(painting_ids):
    """Update display order of paintings"""
    conn = get_db()
    for order, painting_id in enumerate(painting_ids):
        conn.execute('UPDATE paintings SET display_order = ? WHERE id = ?', (order, painting_id))
    conn.commit()
    conn.close()

def get_all_categories():
    """Get all categories"""
    conn = get_db()
    categories = conn.execute('SELECT * FROM categories ORDER BY name').fetchall()
    conn.close()
    return categories

def get_paintings_by_category(category):
    """Get paintings filtered by category"""
    conn = get_db()
    paintings = conn.execute(
        'SELECT * FROM paintings WHERE category = ? ORDER BY display_order ASC',
        (category,)
    ).fetchall()
    conn.close()
    return paintings

if __name__ == '__main__':
    init_db()
