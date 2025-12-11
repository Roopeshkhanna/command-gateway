#!/usr/bin/env python3
"""
Initialize the Command Gateway database with default admin user and seed rules.
"""

import os
from models import Database, User, Rule, AuditLog

def init_database():
    print("Initializing Command Gateway database...")
    
    # Initialize database and tables
    db = Database()
    print("✓ Database tables created")
    
    # Create default admin user
    admin_user = User.create("Default Admin", "admin", 1000)
    print(f"✓ Default admin created:")
    print(f"  Name: {admin_user['name']}")
    print(f"  Role: {admin_user['role']}")
    print(f"  API Key: {admin_user['api_key']}")
    print(f"  Credits: {admin_user['credits']}")
    print(f"  ⚠️  SAVE THIS API KEY - it won't be shown again!")
    
    # Seed dangerous command rules
    dangerous_rules = [
        (r'rm\s+-rf\s+/', 'AUTO_REJECT'),  # Dangerous rm commands
        (r'sudo\s+rm', 'AUTO_REJECT'),     # Sudo rm commands
        (r'dd\s+if=', 'AUTO_REJECT'),      # dd commands
        (r'mkfs\.|format\s+', 'AUTO_REJECT'),  # Format commands
        (r'shutdown|reboot', 'AUTO_REJECT'),   # System shutdown
        (r'curl.*\|\s*sh', 'AUTO_REJECT'), # Pipe to shell
        (r'wget.*\|\s*sh', 'AUTO_REJECT'), # Pipe to shell
    ]
    
    # Seed safe command rules
    safe_rules = [
        (r'^ls(\s|$)', 'AUTO_ACCEPT'),     # List files
        (r'^pwd(\s|$)', 'AUTO_ACCEPT'),    # Print working directory
        (r'^echo\s+', 'AUTO_ACCEPT'),      # Echo commands
        (r'^cat\s+[^|;&]+$', 'AUTO_ACCEPT'),  # Cat single files
        (r'^grep\s+', 'AUTO_ACCEPT'),      # Grep commands
        (r'^find\s+', 'AUTO_ACCEPT'),      # Find commands
        (r'^ps(\s|$)', 'AUTO_ACCEPT'),     # Process list
        (r'^whoami(\s|$)', 'AUTO_ACCEPT'), # Current user
        (r'^date(\s|$)', 'AUTO_ACCEPT'),   # Date command
    ]
    
    print("\n✓ Creating seed rules...")
    
    # Create dangerous rules first (higher priority)
    for pattern, action in dangerous_rules:
        Rule.create(pattern, action, admin_user['id'])
        print(f"  - {action}: {pattern}")
    
    # Create safe rules
    for pattern, action in safe_rules:
        Rule.create(pattern, action, admin_user['id'])
        print(f"  - {action}: {pattern}")
    
    print(f"\n✓ Created {len(dangerous_rules) + len(safe_rules)} seed rules")
    
    # Log initialization
    AuditLog.log(admin_user['id'], 'SYSTEM_INITIALIZED', 'Database initialized with default admin and seed rules')
    
    print("\n🚀 Command Gateway initialized successfully!")
    print("\nNext steps:")
    print("1. Save the admin API key above")
    print("2. Run: python app.py")
    print("3. Open http://localhost:5000 in your browser")
    print("4. Use the API key to authenticate")

if __name__ == '__main__':
    # Remove existing database for fresh start
    if os.path.exists('command_gateway.db'):
        os.remove('command_gateway.db')
        print("Removed existing database")
    
    init_database()