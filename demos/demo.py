#!/usr/bin/env python3
"""
Demo script to showcase Command Gateway functionality
"""

import requests
import json
import time

def demo_command_gateway():
    base_url = 'http://localhost:5000'
    
    # Admin API key from init_db.py output
    admin_key = "ir4TjlqMzo3k2BeVk09UqoRVLdqLhLsNUhU-zuf-3dQ"
    
    print("🚀 Command Gateway Demo")
    print("=" * 50)
    
    # 1. Verify admin authentication
    print("\n1. Testing admin authentication...")
    response = requests.get(f'{base_url}/api/auth/verify', 
                          headers={'X-API-Key': admin_key})
    if response.status_code == 200:
        user = response.json()['user']
        print(f"✓ Admin authenticated: {user['name']} ({user['role']}) - {user['credits']} credits")
    else:
        print("❌ Admin authentication failed")
        return
    
    # 2. Create a member user
    print("\n2. Creating a member user...")
    response = requests.post(f'{base_url}/api/users',
                           headers={'X-API-Key': admin_key, 'Content-Type': 'application/json'},
                           json={'name': 'Demo Member', 'role': 'member', 'credits': 5})
    
    if response.status_code == 200:
        member = response.json()
        member_key = member['api_key']
        print(f"✓ Member created: {member['name']} - API Key: {member_key[:20]}...")
    else:
        print("❌ Member creation failed")
        return
    
    # 3. Test safe commands
    print("\n3. Testing safe commands...")
    safe_commands = ['ls -la', 'pwd', 'echo "Hello World"', 'date']
    
    for cmd in safe_commands:
        response = requests.post(f'{base_url}/api/commands',
                               headers={'X-API-Key': member_key, 'Content-Type': 'application/json'},
                               json={'command': cmd})
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ '{cmd}' -> {result['status']} (Credits: {result.get('credits_remaining', 'N/A')})")
        else:
            print(f"❌ '{cmd}' -> Failed")
    
    # 4. Test dangerous commands
    print("\n4. Testing dangerous commands...")
    dangerous_commands = ['rm -rf /', 'sudo rm -rf /tmp', 'dd if=/dev/zero of=/dev/sda']
    
    for cmd in dangerous_commands:
        response = requests.post(f'{base_url}/api/commands',
                               headers={'X-API-Key': member_key, 'Content-Type': 'application/json'},
                               json={'command': cmd})
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ '{cmd}' -> {result['status']} (Rule: {result['matched_rule']['pattern']})")
        else:
            print(f"❌ '{cmd}' -> Failed")
    
    # 5. Test credit exhaustion
    print("\n5. Testing credit exhaustion...")
    # Execute commands until credits run out
    credits_left = 2  # Should have 2 credits left after safe commands
    
    while credits_left > 0:
        response = requests.post(f'{base_url}/api/commands',
                               headers={'X-API-Key': member_key, 'Content-Type': 'application/json'},
                               json={'command': 'echo test'})
        
        if response.status_code == 200:
            result = response.json()
            credits_left = result.get('credits_remaining', 0)
            print(f"✓ Command executed - Credits remaining: {credits_left}")
        else:
            break
    
    # Try one more command (should fail)
    response = requests.post(f'{base_url}/api/commands',
                           headers={'X-API-Key': member_key, 'Content-Type': 'application/json'},
                           json={'command': 'echo should fail'})
    
    if response.status_code == 400:
        error = response.json()
        print(f"✓ Command rejected due to insufficient credits: {error['error']}")
    else:
        print("❌ Expected credit exhaustion failure")
    
    # 6. View command history
    print("\n6. Viewing command history...")
    response = requests.get(f'{base_url}/api/commands',
                          headers={'X-API-Key': member_key})
    
    if response.status_code == 200:
        commands = response.json()
        print(f"✓ Found {len(commands)} commands in history")
        for i, cmd in enumerate(commands[:3]):  # Show first 3
            print(f"   {i+1}. '{cmd['command_text']}' -> {cmd['status']}")
    
    # 7. View rules (admin only)
    print("\n7. Viewing rules (admin)...")
    response = requests.get(f'{base_url}/api/rules',
                          headers={'X-API-Key': admin_key})
    
    if response.status_code == 200:
        rules = response.json()
        print(f"✓ Found {len(rules)} rules configured")
        print("   Top 5 rules:")
        for i, rule in enumerate(rules[:5]):
            print(f"   {i+1}. {rule['pattern']} -> {rule['action']}")
    
    # 8. View audit logs (admin only)
    print("\n8. Viewing audit logs (admin)...")
    response = requests.get(f'{base_url}/api/audit-logs',
                          headers={'X-API-Key': admin_key})
    
    if response.status_code == 200:
        logs = response.json()
        print(f"✓ Found {len(logs)} audit log entries")
        print("   Recent activities:")
        for i, log in enumerate(logs[:3]):
            print(f"   {i+1}. {log['action']}: {log['details'][:50]}...")
    
    print("\n" + "=" * 50)
    print("🎉 Demo completed successfully!")
    print("\nNext steps:")
    print("1. Open http://localhost:5000 in your browser")
    print("2. Use the admin API key to access the web interface")
    print("3. Create users, manage rules, and view audit logs")
    print(f"4. Admin API Key: {admin_key}")
    print(f"5. Member API Key: {member_key}")

if __name__ == '__main__':
    print("Make sure the Flask server is running (python app.py)")
    print("Press Enter to start demo...")
    input()
    
    try:
        demo_command_gateway()
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Make sure Flask app is running on localhost:5000")
    except Exception as e:
        print(f"❌ Demo failed: {e}")