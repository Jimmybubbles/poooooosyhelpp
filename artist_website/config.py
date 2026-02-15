"""
Configuration settings for the Artist Portfolio Website
"""
import os

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database
DATABASE = os.path.join(BASE_DIR, 'paintings.db')

# Upload folders
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ORIGINALS_FOLDER = os.path.join(UPLOAD_FOLDER, 'originals')
THUMBNAILS_FOLDER = os.path.join(UPLOAD_FOLDER, 'thumbnails')

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

# Thumbnail size (width, height) - maintains aspect ratio
THUMBNAIL_SIZE = (300, 300)

# Secret key for sessions (change this in production!)
SECRET_KEY = 'your-secret-key-change-in-production'

# Admin credentials (change these!)
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'artgallery123'

# Site settings
SITE_NAME = "Art Gallery"
ARTIST_NAME = "Artist Name"
