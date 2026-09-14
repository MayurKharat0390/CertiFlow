"""CertiFlow Settings Package"""
import os

# Auto-detect Render or production environment
if os.getenv('RENDER') or os.getenv('DJANGO_ENV') == 'production' or os.getenv('ENVIRONMENT') == 'production':
    from .production import *  # noqa: F401, F403
else:
    from .development import *  # noqa: F401, F403
