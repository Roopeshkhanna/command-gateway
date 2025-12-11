import os

class Config:
    DATABASE_PATH = 'command_gateway.db'
    DEFAULT_CREDITS = 100
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Command validation
    MAX_COMMAND_LENGTH = 1000
    ALLOWED_COMMAND_CHARS = r'^[a-zA-Z0-9\s\-_./\\:@#$%^&*()+=\[\]{}|;,<>?~`"\']+$'