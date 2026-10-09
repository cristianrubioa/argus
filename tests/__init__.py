import os

from cryptography.fernet import Fernet

os.environ.setdefault("ARGUS_SESSION_SECRET", "test-secret-not-for-production")
os.environ.setdefault("ARGUS_SETUP_TOKEN", "test-setup-token-not-for-production")
os.environ.setdefault("ARGUS_MQTT_SECRET", Fernet.generate_key().decode())
