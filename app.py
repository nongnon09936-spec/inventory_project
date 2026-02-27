import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
# ต้องมี Secret Key สำหรับใช้งาน flash messages
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-key-psru")

from routes.dashboard import dashboard_bp
from routes.inventory import inventory_bp
from routes.manage import manage_bp

# Register routes
app.register_blueprint(dashboard_bp)
app.register_blueprint(inventory_bp)
app.register_blueprint(manage_bp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)