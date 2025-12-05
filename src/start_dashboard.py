#!/usr/bin/env python3
"""
Start dashboard service on port 8001
"""
import os
import sys

# Set environment defaults without overriding caller choices
os.environ.setdefault('PORT', '8001')
os.environ.setdefault('SYNC_SERVICE_URL', 'http://localhost:8000')

# Change to dashboard app directory
sys.path.insert(0, os.path.dirname(__file__))

try:
    from app import app
    port = int(os.environ.get('PORT', '8001'))
    sync_url = os.environ.get('SYNC_SERVICE_URL', 'http://localhost:8000')
    print(f"✅ Starting Dashboard Service on port {port}")
    print(f"✅ Sync Service URL: {sync_url}")
    app.run(host='0.0.0.0', port=port, debug=False)
except Exception as e:
    print(f"❌ Error starting dashboard: {e}")
    import traceback
    traceback.print_exc()
