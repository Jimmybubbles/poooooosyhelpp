/* ============================================================
   ARTIST PORTFOLIO - GALLERY JAVASCRIPT
   ============================================================ */

// Lightbox functionality
const lightbox = document.getElementById('lightbox');
const lightboxImage = document.getElementById('lightbox-image');
const lightboxTitle = document.getElementById('lightbox-title');
const lightboxDescription = document.getElementById('lightbox-description');
const lightboxCategory = document.getElementById('lightbox-category');

let currentLightboxIndex = 0;

// Open lightbox
async function openLightbox(paintingId) {
    try {
        const response = await fetch(`/api/painting/${paintingId}`);
        const painting = await response.json();

        if (painting.error) {
            console.error('Painting not found');
            return;
        }

        // Set content
        lightboxImage.src = painting.original;
        lightboxImage.alt = painting.title;
        lightboxTitle.textContent = painting.title;
        lightboxDescription.textContent = painting.description || '';
        lightboxCategory.textContent = painting.category || '';

        // Update current index
        if (typeof paintingIds !== 'undefined') {
            currentLightboxIndex = paintingIds.indexOf(paintingId);
        }

        // Show lightbox
        lightbox.classList.add('active');
        document.body.style.overflow = 'hidden';

    } catch (error) {
        console.error('Error loading painting:', error);
    }
}

// Close lightbox
function closeLightbox(event) {
    if (event && event.target !== lightbox) return;

    lightbox.classList.remove('active');
    document.body.style.overflow = '';
    lightboxImage.src = '';
}

// Navigate lightbox
function navigateLightbox(direction) {
    if (typeof paintingIds === 'undefined' || paintingIds.length === 0) return;

    currentLightboxIndex += direction;

    // Loop around
    if (currentLightboxIndex < 0) {
        currentLightboxIndex = paintingIds.length - 1;
    } else if (currentLightboxIndex >= paintingIds.length) {
        currentLightboxIndex = 0;
    }

    openLightbox(paintingIds[currentLightboxIndex]);
}

// Keyboard navigation
document.addEventListener('keydown', (e) => {
    if (!lightbox || !lightbox.classList.contains('active')) return;

    switch (e.key) {
        case 'Escape':
            closeLightbox();
            break;
        case 'ArrowLeft':
            navigateLightbox(-1);
            break;
        case 'ArrowRight':
            navigateLightbox(1);
            break;
    }
});

/* ============================================================
   SOCIAL SHARING
   ============================================================ */

function getShareUrl(paintingId) {
    return `${window.location.origin}/painting/${paintingId}`;
}

function shareOnFacebook(paintingId, title) {
    const url = encodeURIComponent(getShareUrl(paintingId));
    window.open(
        `https://www.facebook.com/sharer/sharer.php?u=${url}`,
        'facebook-share',
        'width=580,height=400'
    );
}

function shareOnTwitter(paintingId, title) {
    const url = encodeURIComponent(getShareUrl(paintingId));
    const text = encodeURIComponent(`Check out "${title}" by ${document.querySelector('.artist-name')?.textContent || 'this artist'}`);
    window.open(
        `https://twitter.com/intent/tweet?url=${url}&text=${text}`,
        'twitter-share',
        'width=580,height=400'
    );
}

function shareOnPinterest(paintingId, title) {
    const url = encodeURIComponent(getShareUrl(paintingId));
    const description = encodeURIComponent(title);

    // Get image URL from the painting card
    const card = document.querySelector(`.painting-card[data-id="${paintingId}"]`);
    let imageUrl = '';
    if (card) {
        const img = card.querySelector('.painting-image img');
        if (img) {
            // Convert thumbnail URL to original URL for Pinterest
            imageUrl = encodeURIComponent(img.src.replace('/thumbnails/thumb_', '/originals/').replace('.jpg', ''));
        }
    }

    window.open(
        `https://pinterest.com/pin/create/button/?url=${url}&description=${description}&media=${imageUrl}`,
        'pinterest-share',
        'width=750,height=550'
    );
}

async function copyLink(paintingId) {
    const url = getShareUrl(paintingId);

    try {
        await navigator.clipboard.writeText(url);
        showToast('Link copied to clipboard!');
    } catch (err) {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = url;
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        showToast('Link copied to clipboard!');
    }
}

// Toast notification
function showToast(message) {
    // Remove existing toast
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }

    // Create toast
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: #333;
        color: white;
        padding: 1rem 2rem;
        border-radius: 8px;
        z-index: 10000;
        animation: fadeInUp 0.3s ease;
    `;

    document.body.appendChild(toast);

    // Remove after 3 seconds
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Add toast animations
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translate(-50%, 20px);
        }
        to {
            opacity: 1;
            transform: translate(-50%, 0);
        }
    }
    @keyframes fadeOut {
        from { opacity: 1; }
        to { opacity: 0; }
    }
`;
document.head.appendChild(style);

/* ============================================================
   LAZY LOADING (Intersection Observer)
   ============================================================ */

// Lazy load images as they come into view
document.addEventListener('DOMContentLoaded', () => {
    const lazyImages = document.querySelectorAll('img[loading="lazy"]');

    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.classList.add('loaded');
                    observer.unobserve(img);
                }
            });
        });

        lazyImages.forEach(img => imageObserver.observe(img));
    }
});
