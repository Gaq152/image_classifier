"""Build-time product channel embedded into the executable.

The tracked value stays ``standard``. ``build.py --edition ai`` temporarily
rewrites this module while PyInstaller analyzes the application, then restores
the source file after the build.
"""

APP_EDITION = "standard"
