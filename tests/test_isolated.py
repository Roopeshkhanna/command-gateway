#!/usr/bin/env python3
"""
Isolated unit tests for Command Gateway that don't interfere with existing database
"""

import pytest
import os
import tempfile
import sqlite3
import sys
sys.path.append('../backend')
from models import Database, User, Rule, Command, AuditLog
from config import Config

def test_rule_matching_isolated():
    """Test rule matching with a clean database"""
    # Create temporary database
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db.close()
    
    try:
        # Create isolated database
        db = Database(temp_db.name)
        admin_user = User.create("Admin", "admin")
        
        # Create specific rules
        Rule.create(r'rm\s+-rf', 'AUTO_REJECT', admin_user['id'])
        Rule.create(r'^ls', 'AUTO_ACCEPT', admin_user['id'])
        
        # Test matching
        dangerous_match = Rule.match_command('rm -rf /tmp')
        assert dangerous_match is not None
        assert dangerous_match['action'] == 'AUTO_REJECT'
        
        safe_match = Rule.match_command('ls -la')
        assert safe_match is not None
        assert safe_match['action'] == 'AUTO_ACCEPT'
        
        no_match = Rule.match_command('echo hello')
        assert no_match is None
        
        print("✓ Rule matching test passed")
        
    finally:
        os.unlink(temp_db.name)

def test_command_execution_isolated():
    """Test command execution with clean database"""
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db.close()
    
    try:
        # Create isolated database
        db = Database(temp_db.name)
        user = User.create("Test User", "member", 100)
        admin = User.create("Admin", "admin", 100)
        
        # Test execution without rules (should execute)
        result = Command.submit(user['id'], 'echo hello')
        assert result['status'] == 'EXECUTED'
        assert result['matched_rule'] is None
        assert result['credits_remaining'] == 99
        
        # Create rejection rule
        Rule.create(r'rm\s+-rf', 'AUTO_REJECT', admin['id'])
        
        # Test rejection
        result = Command.submit(user['id'], 'rm -rf /tmp')
        assert result['status'] == 'REJECTED'
        assert result['matched_rule'] is not None
        
        # Credits should not be deducted for rejected commands
        updated_user = User.get_by_api_key(user['api_key'])
        assert updated_user['credits'] == 99
        
        print("✓ Command execution test passed")
        
    finally:
        os.unlink(temp_db.name)

def test_credit_system_isolated():
    """Test credit deduction system"""
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db.close()
    
    try:
        db = Database(temp_db.name)
        user = User.create("Test User", "member", 2)
        
        # Execute first command
        result = Command.submit(user['id'], 'echo test1')
        assert result['status'] == 'EXECUTED'
        assert result['credits_remaining'] == 1
        
        # Execute second command
        result = Command.submit(user['id'], 'echo test2')
        assert result['status'] == 'EXECUTED'
        assert result['credits_remaining'] == 0
        
        # Try third command (should fail)
        try:
            Command.submit(user['id'], 'echo test3')
            assert False, "Should have failed due to insufficient credits"
        except ValueError as e:
            assert "credit" in str(e).lower()
        
        print("✓ Credit system test passed")
        
    finally:
        os.unlink(temp_db.name)

def test_rule_order_isolated():
    """Test rule precedence"""
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db.close()
    
    try:
        db = Database(temp_db.name)
        admin = User.create("Admin", "admin")
        
        # Create rules in specific order
        rule1_id = Rule.create(r'.*', 'AUTO_ACCEPT', admin['id'])  # Catch-all first
        rule2_id = Rule.create(r'rm', 'AUTO_REJECT', admin['id'])  # Specific second
        
        # First matching rule should win (catch-all in this case)
        match = Rule.match_command('rm file.txt')
        assert match['id'] == rule1_id
        assert match['action'] == 'AUTO_ACCEPT'
        
        print("✓ Rule order test passed")
        
    finally:
        os.unlink(temp_db.name)

def run_isolated_tests():
    """Run all isolated tests"""
    tests = [
        test_rule_matching_isolated,
        test_command_execution_isolated,
        test_credit_system_isolated,
        test_rule_order_isolated
    ]
    
    print("Running isolated unit tests...")
    print("=" * 40)
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 40)
    print(f"Isolated tests: {passed} passed, {failed} failed")
    
    return failed == 0

if __name__ == '__main__':
    success = run_isolated_tests()
    exit(0 if success else 1)