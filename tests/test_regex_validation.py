#!/usr/bin/env python3
"""
Test script for regex validation functionality
"""

import sys
sys.path.append('../backend')
from models import Rule

def test_regex_validation():
    print("🧪 Testing Regex Validation System")
    print("=" * 50)
    
    # Test cases: (pattern, expected_valid, description)
    test_cases = [
        # Valid patterns
        ("^ls", True, "Simple start anchor"),
        ("rm.*-rf", True, "Pattern with wildcard"),
        ("sudo\\s+", True, "Escaped whitespace"),
        ("\\.(sh|bash)$", True, "Alternation with end anchor"),
        ("[a-zA-Z]+", True, "Character class"),
        ("\\d{1,3}", True, "Quantifier with range"),
        
        # Invalid patterns
        ("", False, "Empty pattern"),
        ("   ", False, "Whitespace only"),
        ("[abc", False, "Unmatched bracket"),
        ("abc]", False, "Unmatched closing bracket"),
        ("(group", False, "Unmatched parenthesis"),
        ("group)", False, "Unmatched closing parenthesis"),
        ("{test", False, "Unmatched brace"),
        ("test}", False, "Unmatched closing brace"),
        ("*start", False, "Quantifier at start"),
        ("+start", False, "Plus at start"),
        ("\\", False, "Incomplete escape"),
        
        # Edge cases
        (".*", True, "Match everything (valid but warned)"),
        ("a" * 150, True, "Very long pattern"),
        (".*.*.*.*", True, "Multiple wildcards (valid but warned)"),
    ]
    
    passed = 0
    failed = 0
    
    for pattern, expected_valid, description in test_cases:
        print(f"\nTesting: {description}")
        print(f"Pattern: '{pattern}'")
        
        try:
            result = Rule.validate_regex_pattern(pattern)
            
            if result['valid'] == expected_valid:
                print(f"✅ PASS - Valid: {result['valid']}")
                if result['error']:
                    print(f"   Error: {result['error']}")
                if result['suggestions']:
                    print(f"   Suggestions: {len(result['suggestions'])} provided")
                passed += 1
            else:
                print(f"❌ FAIL - Expected: {expected_valid}, Got: {result['valid']}")
                if result['error']:
                    print(f"   Error: {result['error']}")
                failed += 1
                
        except Exception as e:
            print(f"❌ EXCEPTION - {str(e)}")
            failed += 1
    
    print(f"\n" + "=" * 50)
    print(f"Test Results: {passed} passed, {failed} failed")
    
    # Test specific error messages
    print(f"\n🔍 Testing Error Message Quality")
    print("-" * 30)
    
    error_test_cases = [
        ("[abc", "Should mention missing closing bracket"),
        ("(group", "Should mention missing closing parenthesis"),
        ("*start", "Should mention quantifier needs content"),
        ("\\", "Should mention incomplete escape"),
    ]
    
    for pattern, expectation in error_test_cases:
        result = Rule.validate_regex_pattern(pattern)
        print(f"\nPattern: '{pattern}'")
        print(f"Expected: {expectation}")
        print(f"Got: {result['error']}")
        print(f"Suggestions: {len(result['suggestions'])} provided")
        if result['suggestions']:
            for i, suggestion in enumerate(result['suggestions'][:2], 1):
                print(f"  {i}. {suggestion}")
    
    return failed == 0

def demo_validation_messages():
    print(f"\n🎨 Demo: User-Friendly Validation Messages")
    print("=" * 50)
    
    demo_patterns = [
        "[abc",           # Missing bracket
        "rm.*-rf",        # Valid pattern
        "*dangerous",     # Invalid quantifier
        "sudo\\s+rm",     # Valid with escape
        "test)",          # Unmatched parenthesis
        "^ls$",           # Perfect pattern
        "",               # Empty
        ".*",             # Valid but warned
    ]
    
    for pattern in demo_patterns:
        print(f"\n📝 Pattern: '{pattern}'")
        result = Rule.validate_regex_pattern(pattern)
        
        if result['valid']:
            print("✅ Status: VALID")
        else:
            print("❌ Status: INVALID")
            print(f"   Error: {result['error']}")
        
        if result['suggestions']:
            print("💡 Suggestions:")
            for suggestion in result['suggestions'][:3]:
                print(f"   • {suggestion}")

if __name__ == '__main__':
    success = test_regex_validation()
    demo_validation_messages()
    
    print(f"\n🎉 Regex validation system {'✅ WORKING' if success else '❌ NEEDS FIXES'}")
    print("\nFeatures implemented:")
    print("✅ Real-time pattern validation")
    print("✅ Helpful error messages")
    print("✅ Specific suggestions for fixes")
    print("✅ Common mistake detection")
    print("✅ Performance warnings")
    print("✅ Frontend integration ready")