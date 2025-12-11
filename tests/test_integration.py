#!/usr/bin/env python3
"""
Integration tests using curl-like requests
"""

import requests
import json
import subprocess
import time
import os
import signal
from threading import Thread

class TestServer:
    def __init__(self):
        self.process = None
        self.base_url = 'http://localhost:5000'
    
    def start(self):
        """Start the Flask server in background"""
        # Initialize database first
        subprocess.run(['python', 'init_db.py'], check=True)
        
        # Start server
        self.process = subprocess.Popen(
            ['python', 'app.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for server to start
        time.sleep(3)
        
        # Verify server is running
        try:
            response = requests.get(f'{self.base_url}/')
            if response.status_code != 200:
                raise Exception("Server not responding")
        except requests.exceptions.ConnectionError:
            raise Exception("Could not connect to server")
    
    def stop(self):
        """Stop the Flask server"""
        if self.process:
            self.process.terminate()
            self.process.wait()

def get_admin_api_key():
    """Extract admin API key from init_db.py output"""
    result = subprocess.run(['python', 'init_db.py'], 
                          capture_output=True, text=True)
    
    # Parse output to find API key
    lines = result.stdout.split('\n')
    for line in lines:
        if 'API Key:' in line:
            return line.split('API Key: ')[1].strip()
    
    raise Exception("Could not find admin API key in init output")

def test_authentication():
    """Test API key authentication"""
    server = TestServer()
    
    try:
        server.start()
        admin_key = get_admin_api_key()
        
        # Test valid API key
        response = requests.get(
            f'{server.base_url}/api/auth/verify',
            headers={'X-API-Key': admin_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['user']['role'] == 'admin'
        print("✓ Valid API key authentication works")
        
        # Test invalid API key
        response = requests.get(
            f'{server.base_url}/api/auth/verify',
            headers={'X-API-Key': 'invalid-key'}
        )
        assert response.status_code == 401
        print("✓ Invalid API key properly rejected")
        
        # Test missing API key
        response = requests.get(f'{server.base_url}/api/auth/verify')
        assert response.status_code == 401
        print("✓ Missing API key properly rejected")
        
    finally:
        server.stop()

def test_user_management():
    """Test user creation and management"""
    server = TestServer()
    
    try:
        server.start()
        admin_key = get_admin_api_key()
        
        # Create a new member user
        response = requests.post(
            f'{server.base_url}/api/users',
            headers={
                'X-API-Key': admin_key,
                'Content-Type': 'application/json'
            },
            json={
                'name': 'Test Member',
                'role': 'member',
                'credits': 50
            }
        )
        
        assert response.status_code == 200
        user_data = response.json()
        assert user_data['name'] == 'Test Member'
        assert user_data['role'] == 'member'
        assert user_data['credits'] == 50
        assert 'api_key' in user_data
        print("✓ User creation works")
        
        # Test authentication with new user
        member_key = user_data['api_key']
        response = requests.get(
            f'{server.base_url}/api/auth/verify',
            headers={'X-API-Key': member_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['user']['name'] == 'Test Member'
        print("✓ New user authentication works")
        
    finally:
        server.stop()

def test_rule_management():
    """Test rule creation and management"""
    server = TestServer()
    
    try:
        server.start()
        admin_key = get_admin_api_key()
        
        # Get existing rules
        response = requests.get(
            f'{server.base_url}/api/rules',
            headers={'X-API-Key': admin_key}
        )
        assert response.status_code == 200
        initial_rules = response.json()
        print(f"✓ Found {len(initial_rules)} initial rules")
        
        # Create a new rule
        response = requests.post(
            f'{server.base_url}/api/rules',
            headers={
                'X-API-Key': admin_key,
                'Content-Type': 'application/json'
            },
            json={
                'pattern': r'test.*command',
                'action': 'AUTO_REJECT'
            }
        )
        
        assert response.status_code == 200
        print("✓ Rule creation works")
        
        # Verify rule was created
        response = requests.get(
            f'{server.base_url}/api/rules',
            headers={'X-API-Key': admin_key}
        )
        assert response.status_code == 200
        rules = response.json()
        assert len(rules) == len(initial_rules) + 1
        
        # Find our new rule
        new_rule = next((r for r in rules if r['pattern'] == r'test.*command'), None)
        assert new_rule is not None
        assert new_rule['action'] == 'AUTO_REJECT'
        print("✓ Rule creation verified")
        
    finally:
        server.stop()

def test_command_submission():
    """Test command submission and execution"""
    server = TestServer()
    
    try:
        server.start()
        admin_key = get_admin_api_key()
        
        # Create a test member
        response = requests.post(
            f'{server.base_url}/api/users',
            headers={
                'X-API-Key': admin_key,
                'Content-Type': 'application/json'
            },
            json={
                'name': 'Test Member',
                'role': 'member',
                'credits': 10
            }
        )
        member_key = response.json()['api_key']
        
        # Test safe command (should be executed)
        response = requests.post(
            f'{server.base_url}/api/commands',
            headers={
                'X-API-Key': member_key,
                'Content-Type': 'application/json'
            },
            json={'command': 'ls -la'}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'EXECUTED'
        assert result['credits_remaining'] == 9
        print("✓ Safe command executed successfully")
        
        # Test dangerous command (should be rejected)
        response = requests.post(
            f'{server.base_url}/api/commands',
            headers={
                'X-API-Key': member_key,
                'Content-Type': 'application/json'
            },
            json={'command': 'rm -rf /'}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'REJECTED'
        print("✓ Dangerous command rejected successfully")
        
        # Verify credits weren't deducted for rejected command
        response = requests.get(
            f'{server.base_url}/api/auth/verify',
            headers={'X-API-Key': member_key}
        )
        user_data = response.json()
        assert user_data['user']['credits'] == 9  # Still 9, not 8
        print("✓ Credits not deducted for rejected command")
        
        # Test command history
        response = requests.get(
            f'{server.base_url}/api/commands',
            headers={'X-API-Key': member_key}
        )
        
        assert response.status_code == 200
        commands = response.json()
        assert len(commands) == 2
        print("✓ Command history retrieval works")
        
    finally:
        server.stop()

def test_credit_system():
    """Test credit deduction and insufficient credits"""
    server = TestServer()
    
    try:
        server.start()
        admin_key = get_admin_api_key()
        
        # Create a member with only 1 credit
        response = requests.post(
            f'{server.base_url}/api/users',
            headers={
                'X-API-Key': admin_key,
                'Content-Type': 'application/json'
            },
            json={
                'name': 'Poor Member',
                'role': 'member',
                'credits': 1
            }
        )
        member_key = response.json()['api_key']
        
        # Execute one command (should work)
        response = requests.post(
            f'{server.base_url}/api/commands',
            headers={
                'X-API-Key': member_key,
                'Content-Type': 'application/json'
            },
            json={'command': 'echo hello'}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'EXECUTED'
        assert result['credits_remaining'] == 0
        print("✓ Command executed with 1 credit")
        
        # Try to execute another command (should fail)
        response = requests.post(
            f'{server.base_url}/api/commands',
            headers={
                'X-API-Key': member_key,
                'Content-Type': 'application/json'
            },
            json={'command': 'echo hello again'}
        )
        
        assert response.status_code == 400
        error_data = response.json()
        assert 'credit' in error_data['error'].lower()
        print("✓ Command rejected due to insufficient credits")
        
    finally:
        server.stop()

def test_audit_logs():
    """Test audit log functionality"""
    server = TestServer()
    
    try:
        server.start()
        admin_key = get_admin_api_key()
        
        # Get initial audit logs
        response = requests.get(
            f'{server.base_url}/api/audit-logs',
            headers={'X-API-Key': admin_key}
        )
        
        assert response.status_code == 200
        logs = response.json()
        assert len(logs) > 0  # Should have initialization logs
        print(f"✓ Found {len(logs)} audit log entries")
        
        # Verify log structure
        log = logs[0]
        required_fields = ['id', 'user_id', 'action', 'details', 'timestamp']
        for field in required_fields:
            assert field in log
        print("✓ Audit log structure is correct")
        
    finally:
        server.stop()

def run_all_tests():
    """Run all integration tests"""
    tests = [
        test_authentication,
        test_user_management,
        test_rule_management,
        test_command_submission,
        test_credit_system,
        test_audit_logs
    ]
    
    print("Running Command Gateway Integration Tests")
    print("=" * 50)
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            print(f"\nRunning {test.__name__}...")
            test()
            print(f"✅ {test.__name__} PASSED")
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Tests completed: {passed} passed, {failed} failed")
    
    if failed > 0:
        exit(1)

if __name__ == '__main__':
    run_all_tests()