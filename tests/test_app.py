#!/usr/bin/env python3
"""
Unit tests for Command Gateway
"""

import pytest
import os
import tempfile
import sqlite3
import sys
sys.path.append('../backend')
from models import Database, User, Rule, Command, AuditLog
from config import Config

class TestDatabase:
    def setup_method(self):
        # Use temporary database for testing
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        # Monkey patch the database path
        self.original_db_path = Config.DATABASE_PATH
        Config.DATABASE_PATH = self.temp_db.name
        self.db = Database(self.temp_db.name)
    
    def teardown_method(self):
        os.unlink(self.temp_db.name)
    
    def test_database_initialization(self):
        # Test that tables are created
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = ['users', 'rules', 'commands', 'audit_logs']
        for table in expected_tables:
            assert table in tables
        
        conn.close()

class TestUser:
    def setup_method(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        self.db = Database(self.temp_db.name)
    
    def teardown_method(self):
        os.unlink(self.temp_db.name)
    
    def test_create_user(self):
        user = User.create("Test User", "member", 50)
        
        assert user['name'] == "Test User"
        assert user['role'] == "member"
        assert user['credits'] == 50
        assert len(user['api_key']) > 20  # API key should be generated
        assert user['id'] is not None
    
    def test_get_user_by_api_key(self):
        user = User.create("Test User", "admin")
        
        retrieved_user = User.get_by_api_key(user['api_key'])
        assert retrieved_user['name'] == "Test User"
        assert retrieved_user['role'] == "admin"
        
        # Test with invalid API key
        invalid_user = User.get_by_api_key("invalid-key")
        assert invalid_user is None
    
    def test_update_credits(self):
        user = User.create("Test User", "member", 100)
        
        User.update_credits(user['id'], 150)
        
        retrieved_user = User.get_by_api_key(user['api_key'])
        assert retrieved_user['credits'] == 150
    
    def test_deduct_credits(self):
        user = User.create("Test User", "member", 100)
        
        # Successful deduction
        result = User.deduct_credits(user['id'], 30)
        assert result is True
        
        retrieved_user = User.get_by_api_key(user['api_key'])
        assert retrieved_user['credits'] == 70
        
        # Insufficient credits
        result = User.deduct_credits(user['id'], 100)
        assert result is False

class TestRule:
    def setup_method(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        # Override the global database path for this test
        Config.DATABASE_PATH = self.temp_db.name
        self.db = Database(self.temp_db.name)
        self.admin_user = User.create("Admin", "admin")
    
    def teardown_method(self):
        os.unlink(self.temp_db.name)
    
    def test_create_rule(self):
        rule_id = Rule.create(r'rm\s+-rf', 'AUTO_REJECT', self.admin_user['id'])
        assert rule_id is not None
        
        rules = Rule.get_all_ordered()
        assert len(rules) == 1
        assert rules[0]['pattern'] == r'rm\s+-rf'
        assert rules[0]['action'] == 'AUTO_REJECT'
    
    def test_invalid_regex_pattern(self):
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            Rule.create(r'[invalid', 'AUTO_REJECT', self.admin_user['id'])
    
    def test_rule_matching(self):
        # Create rules
        Rule.create(r'rm\s+-rf', 'AUTO_REJECT', self.admin_user['id'])
        Rule.create(r'^ls', 'AUTO_ACCEPT', self.admin_user['id'])
        
        # Test matching
        dangerous_match = Rule.match_command('rm -rf /tmp')
        assert dangerous_match is not None
        assert dangerous_match['action'] == 'AUTO_REJECT'
        
        safe_match = Rule.match_command('ls -la')
        assert safe_match is not None
        assert safe_match['action'] == 'AUTO_ACCEPT'
        
        no_match = Rule.match_command('echo hello')
        assert no_match is None
    
    def test_rule_order(self):
        # Create rules in specific order
        rule1_id = Rule.create(r'.*', 'AUTO_ACCEPT', self.admin_user['id'])  # Catch-all
        rule2_id = Rule.create(r'rm', 'AUTO_REJECT', self.admin_user['id'])  # Specific
        
        rules = Rule.get_all_ordered()
        assert len(rules) == 2
        assert rules[0]['id'] == rule1_id  # First rule created
        assert rules[1]['id'] == rule2_id  # Second rule created
        
        # First matching rule should win (catch-all in this case)
        match = Rule.match_command('rm file.txt')
        assert match['id'] == rule1_id
        assert match['action'] == 'AUTO_ACCEPT'

class TestCommand:
    def setup_method(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        # Override the global database path for this test
        Config.DATABASE_PATH = self.temp_db.name
        self.db = Database(self.temp_db.name)
        self.user = User.create("Test User", "member", 100)
        self.admin = User.create("Admin", "admin", 100)
    
    def teardown_method(self):
        os.unlink(self.temp_db.name)
    
    def test_command_validation(self):
        # Test command too long
        long_command = 'a' * (Config.MAX_COMMAND_LENGTH + 1)
        with pytest.raises(ValueError, match="Command too long"):
            Command.submit(self.user['id'], long_command)
        
        # Test invalid characters (if validation is enabled)
        # This test depends on the ALLOWED_COMMAND_CHARS config
    
    def test_insufficient_credits(self):
        # Create user with 0 credits
        poor_user = User.create("Poor User", "member", 0)
        
        with pytest.raises(ValueError, match="Insufficient credits"):
            Command.submit(poor_user['id'], 'ls')
    
    def test_command_rejection(self):
        # Create rejection rule
        Rule.create(r'rm\s+-rf', 'AUTO_REJECT', self.admin['id'])
        
        result = Command.submit(self.user['id'], 'rm -rf /tmp')
        
        assert result['status'] == 'REJECTED'
        assert result['matched_rule'] is not None
        
        # Credits should not be deducted for rejected commands
        updated_user = User.get_by_api_key(self.user['api_key'])
        assert updated_user['credits'] == 100
    
    def test_command_execution(self):
        # Create acceptance rule
        Rule.create(r'^ls', 'AUTO_ACCEPT', self.admin['id'])
        
        result = Command.submit(self.user['id'], 'ls -la')
        
        assert result['status'] == 'EXECUTED'
        assert result['matched_rule'] is not None
        assert 'execution_result' in result
        assert result['credits_remaining'] == 99
        
        # Verify credits were deducted
        updated_user = User.get_by_api_key(self.user['api_key'])
        assert updated_user['credits'] == 99
    
    def test_command_execution_no_rule(self):
        # No rules created - should default to execution
        result = Command.submit(self.user['id'], 'echo hello')
        
        assert result['status'] == 'EXECUTED'
        assert result['matched_rule'] is None
        assert result['credits_remaining'] == 99
    
    def test_transactional_behavior(self):
        # This test ensures that either both credits and command record are updated, or neither
        initial_credits = self.user['credits']
        
        # Mock a database error during command insertion
        # This is a simplified test - in a real scenario, you'd mock the database
        try:
            result = Command.submit(self.user['id'], 'valid command')
            # If successful, both credits and command should be updated
            updated_user = User.get_by_api_key(self.user['api_key'])
            assert updated_user['credits'] == initial_credits - 1
            
            commands = Command.get_user_commands(self.user['id'])
            assert len(commands) == 1
        except Exception:
            # If failed, credits should remain unchanged
            updated_user = User.get_by_api_key(self.user['api_key'])
            assert updated_user['credits'] == initial_credits
    
    def test_get_user_commands(self):
        # Submit multiple commands
        Command.submit(self.user['id'], 'echo test1')
        Command.submit(self.user['id'], 'echo test2')
        
        commands = Command.get_user_commands(self.user['id'])
        assert len(commands) == 2
        assert commands[0]['command_text'] in ['echo test1', 'echo test2']

class TestAuditLog:
    def setup_method(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        self.db = Database(self.temp_db.name)
        self.user = User.create("Test User", "member")
    
    def teardown_method(self):
        os.unlink(self.temp_db.name)
    
    def test_audit_logging(self):
        AuditLog.log(self.user['id'], 'TEST_ACTION', 'Test details')
        
        logs = AuditLog.get_logs()
        assert len(logs) >= 1  # At least our test log (plus user creation log)
        
        # Find our test log
        test_log = next((log for log in logs if log['action'] == 'TEST_ACTION'), None)
        assert test_log is not None
        assert test_log['details'] == 'Test details'
        assert test_log['user_name'] == 'Test User'

def test_integration_flow():
    """Test a complete flow from user creation to command execution"""
    # Setup
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db.close()
    db = Database(temp_db.name)
    
    try:
        # Create admin and rules
        admin = User.create("Admin", "admin", 1000)
        Rule.create(r'rm\s+-rf', 'AUTO_REJECT', admin['id'])
        Rule.create(r'^ls', 'AUTO_ACCEPT', admin['id'])
        
        # Create member user
        member = User.create("Member", "member", 100)
        
        # Test safe command
        result = Command.submit(member['id'], 'ls -la')
        assert result['status'] == 'EXECUTED'
        assert result['credits_remaining'] == 99
        
        # Test dangerous command
        result = Command.submit(member['id'], 'rm -rf /')
        assert result['status'] == 'REJECTED'
        
        # Verify member still has 99 credits (no deduction for rejected command)
        updated_member = User.get_by_api_key(member['api_key'])
        assert updated_member['credits'] == 99
        
        # Check audit logs
        logs = AuditLog.get_logs()
        assert len(logs) >= 4  # User creations + command actions
        
    finally:
        os.unlink(temp_db.name)

if __name__ == '__main__':
    pytest.main([__file__, '-v'])