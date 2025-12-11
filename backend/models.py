import sqlite3
import secrets
import re
import json
from datetime import datetime
from config import Config
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("Warning: Ollama not available. AI analysis will be skipped.")

class Database:
    def __init__(self, db_path=Config.DATABASE_PATH):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
                api_key TEXT UNIQUE NOT NULL,
                credits INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Rules table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL,
                action TEXT NOT NULL CHECK (action IN ('AUTO_ACCEPT', 'AUTO_REJECT')),
                order_index INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        ''')
        
        # Commands table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                command_text TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('ACCEPTED', 'REJECTED', 'EXECUTED', 'PENDING', 'PENDING_APPROVAL')),
                matched_rule_id INTEGER,
                credits_deducted INTEGER DEFAULT 0,
                ai_analysis TEXT,
                ai_risk_score INTEGER DEFAULT 0,
                approval_count INTEGER DEFAULT 0,
                required_approvals INTEGER DEFAULT 2,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (matched_rule_id) REFERENCES rules (id)
            )
        ''')
        
        # Audit logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Command approvals table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS command_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                approved BOOLEAN NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (command_id) REFERENCES commands (id),
                FOREIGN KEY (admin_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()

class User:
    @staticmethod
    def generate_api_key():
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def create(name, role, credits=Config.DEFAULT_CREDITS, db_path=None):
        db = Database(db_path) if db_path else Database()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        api_key = User.generate_api_key()
        cursor.execute(
            'INSERT INTO users (name, role, api_key, credits) VALUES (?, ?, ?, ?)',
            (name, role, api_key, credits)
        )
        user_id = cursor.lastrowid
        conn.commit()
        
        # Log user creation
        AuditLog.log(user_id, 'USER_CREATED', f'User {name} created with role {role}')
        
        conn.close()
        return {'id': user_id, 'name': name, 'role': role, 'api_key': api_key, 'credits': credits}
    
    @staticmethod
    def get_by_api_key(api_key):
        conn = Database().get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE api_key = ?', (api_key,))
        user = cursor.fetchone()
        conn.close()
        return dict(user) if user else None
    
    @staticmethod
    def update_credits(user_id, new_credits):
        conn = Database().get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET credits = ? WHERE id = ?', (new_credits, user_id))
        conn.commit()
        conn.close()
    
    @staticmethod
    def deduct_credits(user_id, amount):
        conn = Database().get_connection()
        cursor = conn.cursor()
        
        # Get current credits
        cursor.execute('SELECT credits FROM users WHERE id = ?', (user_id,))
        result = cursor.fetchone()
        if not result or result['credits'] < amount:
            conn.close()
            return False
        
        # Deduct credits
        new_credits = result['credits'] - amount
        cursor.execute('UPDATE users SET credits = ? WHERE id = ?', (new_credits, user_id))
        conn.commit()
        conn.close()
        return True

class Rule:
    @staticmethod
    def create(pattern, action, created_by):
        # Validate regex pattern with detailed error messages
        validation_result = Rule.validate_regex_pattern(pattern)
        if not validation_result['valid']:
            raise ValueError(validation_result['error'])
        
        # Check for rule conflicts
        conflict_result = Rule.detect_rule_conflicts(pattern, action)
        if conflict_result['has_conflicts']:
            # For now, we'll warn but still allow creation
            # In production, you might want to block creation or require confirmation
            AuditLog.log(created_by, 'RULE_CONFLICT_WARNING', 
                        f'Rule created with conflicts: {pattern} -> {action}. Conflicts: {len(conflict_result["conflicts"])}')
        
        conn = Database().get_connection()
        cursor = conn.cursor()
        
        # Get next order index
        cursor.execute('SELECT MAX(order_index) FROM rules')
        max_order = cursor.fetchone()[0] or 0
        
        cursor.execute(
            'INSERT INTO rules (pattern, action, order_index, created_by) VALUES (?, ?, ?, ?)',
            (pattern, action, max_order + 1, created_by)
        )
        rule_id = cursor.lastrowid
        conn.commit()
        
        AuditLog.log(created_by, 'RULE_CREATED', f'Rule created: {pattern} -> {action}')
        
        conn.close()
        return {'id': rule_id, 'conflicts': conflict_result}
    
    @staticmethod
    def validate_regex_pattern(pattern):
        """
        Validate regex pattern and provide helpful error messages
        Returns: {'valid': bool, 'error': str, 'suggestions': list}
        """
        if not pattern or not pattern.strip():
            return {
                'valid': False,
                'error': 'Pattern cannot be empty',
                'suggestions': ['Try: ^ls', '^echo', 'rm.*-rf']
            }
        
        pattern = pattern.strip()
        
        # Check for common mistakes
        common_issues = []
        suggestions = []
        
        # Check for unescaped special characters that might be mistakes
        if '(' in pattern and ')' not in pattern:
            common_issues.append('Unmatched opening parenthesis')
            suggestions.append('Add closing ) or escape with \\(')
        
        if ')' in pattern and '(' not in pattern:
            common_issues.append('Unmatched closing parenthesis')
            suggestions.append('Add opening ( or escape with \\)')
        
        if '[' in pattern and ']' not in pattern:
            common_issues.append('Unmatched opening bracket')
            suggestions.append('Add closing ] or escape with \\[')
        
        if ']' in pattern and '[' not in pattern:
            common_issues.append('Unmatched closing bracket')
            suggestions.append('Add opening [ or escape with \\]')
        
        # Check for unmatched braces (only if they're not part of quantifiers)
        if '{' in pattern and '}' not in pattern and not re.search(r'\{\d+,?\d*\}', pattern):
            common_issues.append('Unmatched opening brace')
            suggestions.append('Add closing } or escape with \\{')
        
        if '}' in pattern and '{' not in pattern and not re.search(r'\{\d+,?\d*\}', pattern):
            common_issues.append('Unmatched closing brace')
            suggestions.append('Add opening { or escape with \\}')
        
        # Check for potentially problematic patterns
        if pattern == '.*':
            suggestions.append('Warning: .* matches everything - consider being more specific')
        
        if pattern.startswith('*') or pattern.startswith('+'):
            common_issues.append('Pattern starts with quantifier')
            suggestions.append('Quantifiers need something to quantify - try: .* or .+')
        
        # Try to compile the regex
        try:
            compiled_pattern = re.compile(pattern)
            
            # Test with some sample strings to catch potential issues
            test_strings = ['ls', 'rm -rf /', 'echo hello', 'sudo command', '']
            for test_str in test_strings:
                try:
                    compiled_pattern.search(test_str)
                except Exception as e:
                    return {
                        'valid': False,
                        'error': f'Pattern causes runtime error: {str(e)}',
                        'suggestions': ['Simplify the pattern', 'Check for complex lookaheads/lookbehinds']
                    }
            
            # Pattern is valid
            result = {
                'valid': True,
                'error': None,
                'suggestions': []
            }
            
            # Add helpful suggestions even for valid patterns
            if common_issues:
                result['suggestions'].extend(suggestions)
            
            # Add performance suggestions
            if len(pattern) > 100:
                result['suggestions'].append('Consider shorter patterns for better performance')
            
            if pattern.count('.*') > 3:
                result['suggestions'].append('Multiple .* can be slow - consider more specific patterns')
            
            return result
            
        except re.error as e:
            # Parse the regex error and provide helpful message
            error_msg = str(e)
            helpful_error = Rule._get_helpful_regex_error(error_msg, pattern)
            
            return {
                'valid': False,
                'error': helpful_error,
                'suggestions': suggestions + Rule._get_regex_suggestions(error_msg, pattern)
            }
    
    @staticmethod
    def _get_helpful_regex_error(error_msg, pattern):
        """Convert technical regex errors to user-friendly messages"""
        error_lower = error_msg.lower()
        
        if 'unterminated character set' in error_lower:
            return f'Unterminated character set in pattern "{pattern}". Missing closing bracket ]?'
        
        if 'unbalanced parenthesis' in error_lower or 'missing )' in error_lower:
            return f'Unbalanced parentheses in pattern "{pattern}". Check for missing ( or )'
        
        if 'nothing to repeat' in error_lower:
            return f'Invalid quantifier in pattern "{pattern}". Quantifiers like *, +, ? need something to repeat'
        
        if 'bad escape' in error_lower:
            return f'Invalid escape sequence in pattern "{pattern}". Use \\\\ for literal backslash'
        
        if 'bad character range' in error_lower:
            return f'Invalid character range in pattern "{pattern}". Check ranges like [a-z]'
        
        if 'incomplete escape' in error_lower:
            return f'Incomplete escape sequence in pattern "{pattern}". Complete the escape or use \\\\'
        
        # Default message with original error
        return f'Invalid regex pattern "{pattern}": {error_msg}'
    
    @staticmethod
    def _get_regex_suggestions(error_msg, pattern):
        """Provide specific suggestions based on the error type"""
        suggestions = []
        error_lower = error_msg.lower()
        
        if 'unterminated character set' in error_lower:
            suggestions.extend([
                'Add closing bracket: [abc] instead of [abc',
                'Escape literal bracket: \\[ instead of ['
            ])
        
        if 'unbalanced parenthesis' in error_lower:
            suggestions.extend([
                'Match parentheses: (group) instead of (group',
                'Escape literal parenthesis: \\( instead of ('
            ])
        
        if 'nothing to repeat' in error_lower:
            suggestions.extend([
                'Add content before quantifier: .* instead of *',
                'Escape literal quantifier: \\* instead of *'
            ])
        
        if 'bad escape' in error_lower:
            suggestions.extend([
                'Use double backslash: \\\\d instead of \\d',
                'Common escapes: \\s (space), \\d (digit), \\w (word)'
            ])
        
        # General suggestions
        suggestions.extend([
            'Test your pattern at regex101.com',
            'Common patterns: ^start, end$, .* (any), \\s+ (spaces)'
        ])
        
        return suggestions
    
    @staticmethod
    def detect_rule_conflicts(new_pattern, new_action):
        """
        Detect conflicts between a new rule and existing rules
        Returns: {
            'has_conflicts': bool,
            'conflicts': [list of conflict details],
            'warnings': [list of warnings],
            'suggestions': [list of suggestions]
        }
        """
        existing_rules = Rule.get_all_ordered()
        conflicts = []
        warnings = []
        suggestions = []
        
        try:
            new_regex = re.compile(new_pattern)
        except re.error:
            return {
                'has_conflicts': False,
                'conflicts': [],
                'warnings': ['Cannot check conflicts - invalid regex pattern'],
                'suggestions': []
            }
        
        # Test strings to check pattern overlaps
        test_commands = [
            'ls -la', 'rm -rf /', 'sudo rm file', 'echo hello', 'cat file.txt',
            'grep pattern', 'find /home', 'ps aux', 'whoami', 'date',
            'git status', 'docker run', 'curl http://example.com',
            'wget file.zip', 'chmod 755', 'chown user:group', 'mv file1 file2',
            'cp file1 file2', 'mkdir directory', 'rmdir directory',
            'ssh user@host', 'scp file user@host:', 'rsync -av',
            'tar -xzf', 'zip -r', 'unzip file.zip', 'python script.py',
            'node app.js', 'npm install', 'pip install package'
        ]
        
        for existing_rule in existing_rules:
            try:
                existing_regex = re.compile(existing_rule['pattern'])
                conflict_info = Rule._analyze_pattern_conflict(
                    new_pattern, new_action, new_regex,
                    existing_rule['pattern'], existing_rule['action'], existing_regex,
                    test_commands
                )
                
                if conflict_info:
                    conflicts.append({
                        'rule_id': existing_rule['id'],
                        'existing_pattern': existing_rule['pattern'],
                        'existing_action': existing_rule['action'],
                        'conflict_type': conflict_info['type'],
                        'description': conflict_info['description'],
                        'severity': conflict_info['severity'],
                        'examples': conflict_info['examples'],
                        'order_index': existing_rule['order_index']
                    })
                    
            except re.error:
                # Skip invalid existing rules
                continue
        
        # Generate warnings and suggestions based on conflicts
        if conflicts:
            warnings, suggestions = Rule._generate_conflict_warnings_and_suggestions(
                new_pattern, new_action, conflicts
            )
        
        return {
            'has_conflicts': len(conflicts) > 0,
            'conflicts': conflicts,
            'warnings': warnings,
            'suggestions': suggestions
        }
    
    @staticmethod
    def _analyze_pattern_conflict(new_pattern, new_action, new_regex, 
                                existing_pattern, existing_action, existing_regex, 
                                test_commands):
        """Analyze if two patterns conflict and how"""
        
        # Check for exact duplicates
        if new_pattern == existing_pattern:
            if new_action == existing_action:
                return {
                    'type': 'EXACT_DUPLICATE',
                    'description': 'Identical pattern and action already exists',
                    'severity': 'HIGH',
                    'examples': []
                }
            else:
                return {
                    'type': 'SAME_PATTERN_DIFFERENT_ACTION',
                    'description': f'Same pattern exists with different action ({existing_action})',
                    'severity': 'HIGH',
                    'examples': []
                }
        
        # Check for pattern containment
        if Rule._is_pattern_subset(new_pattern, existing_pattern):
            return {
                'type': 'NEW_IS_SUBSET',
                'description': f'New pattern is more specific than existing pattern',
                'severity': 'MEDIUM',
                'examples': []
            }
        
        if Rule._is_pattern_subset(existing_pattern, new_pattern):
            return {
                'type': 'EXISTING_IS_SUBSET',
                'description': f'Existing pattern is more specific than new pattern',
                'severity': 'MEDIUM',
                'examples': []
            }
        
        # Check for overlapping matches using test commands
        overlapping_commands = []
        for cmd in test_commands:
            new_matches = bool(new_regex.search(cmd))
            existing_matches = bool(existing_regex.search(cmd))
            
            if new_matches and existing_matches:
                overlapping_commands.append(cmd)
        
        if overlapping_commands:
            # Determine conflict severity
            overlap_ratio = len(overlapping_commands) / len(test_commands)
            
            if overlap_ratio > 0.5:
                severity = 'HIGH'
                description = 'Patterns overlap significantly'
            elif overlap_ratio > 0.2:
                severity = 'MEDIUM'
                description = 'Patterns have moderate overlap'
            else:
                severity = 'LOW'
                description = 'Patterns have minor overlap'
            
            # Check if actions differ
            if new_action != existing_action:
                severity = 'HIGH' if severity != 'LOW' else 'MEDIUM'
                description += f' with conflicting actions ({new_action} vs {existing_action})'
            
            return {
                'type': 'OVERLAPPING_PATTERNS',
                'description': description,
                'severity': severity,
                'examples': overlapping_commands[:5]  # Show first 5 examples
            }
        
        return None
    
    @staticmethod
    def _is_pattern_subset(pattern1, pattern2):
        """Check if pattern1 is a subset of pattern2 (simplified heuristic)"""
        # This is a simplified check - in practice, this is computationally complex
        # We use heuristics to detect common subset patterns
        
        # Check if pattern1 is more specific (has more constraints)
        specificity_indicators = ['^', '$', '\\s+', '\\d+', '\\w+', '[', '{']
        
        pattern1_specificity = sum(1 for indicator in specificity_indicators if indicator in pattern1)
        pattern2_specificity = sum(1 for indicator in specificity_indicators if indicator in pattern2)
        
        # If pattern1 has more specificity indicators and contains pattern2's core
        if pattern1_specificity > pattern2_specificity:
            # Remove anchors and quantifiers for core comparison
            core1 = re.sub(r'[\^$]', '', pattern1)
            core2 = re.sub(r'[\^$]', '', pattern2)
            
            if core2 in core1 or core1 in core2:
                return True
        
        return False
    
    @staticmethod
    def _generate_conflict_warnings_and_suggestions(new_pattern, new_action, conflicts):
        """Generate user-friendly warnings and suggestions based on conflicts"""
        warnings = []
        suggestions = []
        
        high_severity_conflicts = [c for c in conflicts if c['severity'] == 'HIGH']
        medium_severity_conflicts = [c for c in conflicts if c['severity'] == 'MEDIUM']
        
        if high_severity_conflicts:
            warnings.append(f"⚠️ {len(high_severity_conflicts)} high-severity conflicts detected")
            
            for conflict in high_severity_conflicts:
                if conflict['conflict_type'] == 'EXACT_DUPLICATE':
                    warnings.append(f"Rule already exists: '{conflict['existing_pattern']}'")
                    suggestions.append("Consider if this rule is really needed")
                    
                elif conflict['conflict_type'] == 'SAME_PATTERN_DIFFERENT_ACTION':
                    warnings.append(f"Same pattern exists with {conflict['existing_action']} action")
                    suggestions.append(f"Consider modifying existing rule instead of creating new one")
                    
                elif conflict['conflict_type'] == 'OVERLAPPING_PATTERNS':
                    warnings.append(f"Significant overlap with rule #{conflict['rule_id']}")
                    if conflict['examples']:
                        warnings.append(f"Overlapping commands: {', '.join(conflict['examples'][:3])}")
        
        if medium_severity_conflicts:
            warnings.append(f"ℹ️ {len(medium_severity_conflicts)} medium-severity conflicts detected")
            
            for conflict in medium_severity_conflicts:
                if conflict['conflict_type'] == 'NEW_IS_SUBSET':
                    suggestions.append(f"New rule is more specific than rule #{conflict['rule_id']} - consider rule order")
                elif conflict['conflict_type'] == 'EXISTING_IS_SUBSET':
                    suggestions.append(f"Rule #{conflict['rule_id']} is more specific - may never be reached")
        
        # General suggestions
        if conflicts:
            suggestions.extend([
                "Review rule order - first matching rule wins",
                "Consider combining similar rules",
                "Test with sample commands to verify behavior"
            ])
        
        return warnings, suggestions
    
    @staticmethod
    def get_all_ordered():
        conn = Database().get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM rules ORDER BY order_index ASC')
        rules = cursor.fetchall()
        conn.close()
        return [dict(rule) for rule in rules]
    
    @staticmethod
    def match_command(command_text):
        rules = Rule.get_all_ordered()
        for rule in rules:
            if re.search(rule['pattern'], command_text):
                return rule
        return None

class AIAnalyzer:
    @staticmethod
    def analyze_command(command_text):
        """Analyze command using Ollama Qwen model for security risks"""
        if not OLLAMA_AVAILABLE:
            return {
                'is_dangerous': False,
                'risk_score': 0,
                'analysis': 'AI analysis unavailable - Ollama not installed',
                'confidence': 0
            }
        
        try:
            prompt = f"""
Analyze this Linux/Unix command for security risks and potential dangers:

Command: {command_text}

Please evaluate:
1. Is this command potentially dangerous or harmful?
2. What are the specific risks?
3. Rate the risk level from 0-10 (0=safe, 10=extremely dangerous)
4. Should this command require admin approval?

Respond in JSON format:
{{
    "is_dangerous": true/false,
    "risk_score": 0-10,
    "analysis": "detailed explanation",
    "requires_approval": true/false,
    "confidence": 0-100
}}

Consider dangerous: file deletion, system modification, network attacks, privilege escalation, data exfiltration.
Consider safe: file listing, reading files, basic system info, simple calculations.
"""

            response = ollama.chat(model='qwen2.5', messages=[
                {'role': 'user', 'content': prompt}
            ])
            
            # Parse JSON response
            try:
                result = json.loads(response['message']['content'])
                return {
                    'is_dangerous': result.get('is_dangerous', False),
                    'risk_score': min(10, max(0, result.get('risk_score', 0))),
                    'analysis': result.get('analysis', 'No analysis provided'),
                    'requires_approval': result.get('requires_approval', False),
                    'confidence': min(100, max(0, result.get('confidence', 50)))
                }
            except json.JSONDecodeError:
                # Fallback parsing if JSON is malformed
                content = response['message']['content'].lower()
                is_dangerous = any(word in content for word in ['dangerous', 'harmful', 'risky', 'approval'])
                risk_score = 5 if is_dangerous else 2
                
                return {
                    'is_dangerous': is_dangerous,
                    'risk_score': risk_score,
                    'analysis': response['message']['content'],
                    'requires_approval': is_dangerous,
                    'confidence': 70
                }
                
        except Exception as e:
            print(f"AI Analysis error: {e}")
            return {
                'is_dangerous': True,  # Fail safe - assume dangerous if analysis fails
                'risk_score': 8,
                'analysis': f'AI analysis failed: {str(e)}. Defaulting to requiring approval for safety.',
                'requires_approval': True,
                'confidence': 0
            }

class Command:
    @staticmethod
    def submit(user_id, command_text):
        # Validate command
        if len(command_text) > Config.MAX_COMMAND_LENGTH:
            raise ValueError("Command too long")
        
        if not re.match(Config.ALLOWED_COMMAND_CHARS, command_text):
            raise ValueError("Command contains invalid characters")
        
        # Check user credits
        conn = Database().get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT credits FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user or user['credits'] <= 0:
            conn.close()
            raise ValueError("Insufficient credits")
        
        # Match against rules
        matched_rule = Rule.match_command(command_text)
        
        if matched_rule and matched_rule['action'] == 'AUTO_REJECT':
            # Reject command
            cursor.execute(
                'INSERT INTO commands (user_id, command_text, status, matched_rule_id) VALUES (?, ?, ?, ?)',
                (user_id, command_text, 'REJECTED', matched_rule['id'])
            )
            command_id = cursor.lastrowid
            conn.commit()
            
            AuditLog.log(user_id, 'COMMAND_REJECTED', f'Command rejected by rule {matched_rule["id"]}: {command_text}')
            
            conn.close()
            return {'id': command_id, 'status': 'REJECTED', 'matched_rule': matched_rule}
        
        # Auto-accept or no matching rule - perform AI analysis
        ai_analysis = AIAnalyzer.analyze_command(command_text)
        
        try:
            # Start transaction
            cursor.execute('BEGIN TRANSACTION')
            
            if ai_analysis['requires_approval'] and ai_analysis['risk_score'] >= 6:
                # Command needs admin approval
                cursor.execute(
                    '''INSERT INTO commands (user_id, command_text, status, matched_rule_id, 
                       ai_analysis, ai_risk_score, required_approvals) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (user_id, command_text, 'PENDING_APPROVAL', 
                     matched_rule['id'] if matched_rule else None,
                     ai_analysis['analysis'], ai_analysis['risk_score'], 2)
                )
                command_id = cursor.lastrowid
                conn.commit()
                
                AuditLog.log(user_id, 'COMMAND_PENDING_APPROVAL', 
                           f'Command requires approval (AI risk score: {ai_analysis["risk_score"]}): {command_text}')
                
                conn.close()
                return {
                    'id': command_id,
                    'status': 'PENDING_APPROVAL',
                    'matched_rule': matched_rule,
                    'ai_analysis': ai_analysis,
                    'message': 'Command flagged by AI security analysis. Awaiting admin approval.',
                    'credits_remaining': user['credits']  # No credits deducted yet
                }
            else:
                # Command is safe - execute immediately
                new_credits = user['credits'] - 1
                cursor.execute('UPDATE users SET credits = ? WHERE id = ?', (new_credits, user_id))
                
                cursor.execute(
                    '''INSERT INTO commands (user_id, command_text, status, matched_rule_id, 
                       credits_deducted, ai_analysis, ai_risk_score) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (user_id, command_text, 'EXECUTED', 
                     matched_rule['id'] if matched_rule else None, 1,
                     ai_analysis['analysis'], ai_analysis['risk_score'])
                )
                command_id = cursor.lastrowid
                
                # Simulate command execution (mock)
                execution_result = f"Mock execution of: {command_text}"
                
                conn.commit()
                
                AuditLog.log(user_id, 'COMMAND_EXECUTED', 
                           f'Command executed (AI approved, risk score: {ai_analysis["risk_score"]}): {command_text}')
                
                conn.close()
                return {
                    'id': command_id, 
                    'status': 'EXECUTED', 
                    'matched_rule': matched_rule,
                    'ai_analysis': ai_analysis,
                    'execution_result': execution_result,
                    'credits_remaining': new_credits
                }
            
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e
    
    @staticmethod
    def get_user_commands(user_id, limit=50):
        conn = Database().get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, r.pattern as rule_pattern, r.action as rule_action 
            FROM commands c 
            LEFT JOIN rules r ON c.matched_rule_id = r.id 
            WHERE c.user_id = ? 
            ORDER BY c.created_at DESC 
            LIMIT ?
        ''', (user_id, limit))
        commands = cursor.fetchall()
        conn.close()
        return [dict(cmd) for cmd in commands]
    
    @staticmethod
    def get_pending_approvals():
        """Get all commands pending admin approval"""
        conn = Database().get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, u.name as user_name, r.pattern as rule_pattern, r.action as rule_action
            FROM commands c 
            LEFT JOIN users u ON c.user_id = u.id
            LEFT JOIN rules r ON c.matched_rule_id = r.id 
            WHERE c.status = 'PENDING_APPROVAL'
            ORDER BY c.created_at ASC
        ''')
        commands = cursor.fetchall()
        conn.close()
        return [dict(cmd) for cmd in commands]
    
    @staticmethod
    def approve_command(command_id, admin_id, approved, reason=None):
        """Admin approves or rejects a pending command"""
        conn = Database().get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('BEGIN TRANSACTION')
            
            # Get command details
            cursor.execute('SELECT * FROM commands WHERE id = ? AND status = ?', 
                         (command_id, 'PENDING_APPROVAL'))
            command = cursor.fetchone()
            
            if not command:
                conn.rollback()
                conn.close()
                return {'error': 'Command not found or not pending approval'}
            
            # Record the approval/rejection
            cursor.execute('''
                INSERT INTO command_approvals (command_id, admin_id, approved, reason)
                VALUES (?, ?, ?, ?)
            ''', (command_id, admin_id, approved, reason))
            
            # Count current approvals
            cursor.execute('''
                SELECT COUNT(*) as approval_count
                FROM command_approvals 
                WHERE command_id = ? AND approved = 1
            ''', (command_id,))
            approval_count = cursor.fetchone()['approval_count']
            
            # Update command approval count
            cursor.execute('UPDATE commands SET approval_count = ? WHERE id = ?', 
                         (approval_count, command_id))
            
            if not approved:
                # Command rejected
                cursor.execute('UPDATE commands SET status = ? WHERE id = ?', 
                             ('REJECTED', command_id))
                conn.commit()
                
                AuditLog.log(admin_id, 'COMMAND_REJECTED_BY_ADMIN', 
                           f'Admin rejected command {command_id}: {reason or "No reason provided"}')
                
                conn.close()
                return {
                    'status': 'REJECTED',
                    'message': 'Command rejected by admin',
                    'reason': reason
                }
            
            elif approval_count >= command['required_approvals']:
                # Sufficient approvals - execute command
                cursor.execute('SELECT credits FROM users WHERE id = ?', (command['user_id'],))
                user = cursor.fetchone()
                
                if user['credits'] <= 0:
                    cursor.execute('UPDATE commands SET status = ? WHERE id = ?', 
                                 ('REJECTED', command_id))
                    conn.commit()
                    conn.close()
                    return {'error': 'User has insufficient credits'}
                
                # Deduct credits and execute
                new_credits = user['credits'] - 1
                cursor.execute('UPDATE users SET credits = ? WHERE id = ?', 
                             (new_credits, command['user_id']))
                cursor.execute('UPDATE commands SET status = ?, credits_deducted = ? WHERE id = ?', 
                             ('EXECUTED', 1, command_id))
                
                conn.commit()
                
                AuditLog.log(admin_id, 'COMMAND_APPROVED_EXECUTED', 
                           f'Command {command_id} approved and executed after {approval_count} approvals')
                
                conn.close()
                return {
                    'status': 'EXECUTED',
                    'message': f'Command approved by {approval_count} admins and executed',
                    'execution_result': f"Mock execution of: {command['command_text']}",
                    'credits_remaining': new_credits
                }
            else:
                # Need more approvals
                conn.commit()
                
                AuditLog.log(admin_id, 'COMMAND_PARTIALLY_APPROVED', 
                           f'Command {command_id} approved by admin ({approval_count}/{command["required_approvals"]} approvals)')
                
                conn.close()
                return {
                    'status': 'PENDING_APPROVAL',
                    'message': f'Command approved ({approval_count}/{command["required_approvals"]} approvals needed)',
                    'approvals_needed': command['required_approvals'] - approval_count
                }
                
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

class AuditLog:
    @staticmethod
    def log(user_id, action, details):
        conn = Database().get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO audit_logs (user_id, action, details) VALUES (?, ?, ?)',
            (user_id, action, details)
        )
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_logs(limit=100):
        conn = Database().get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT a.*, u.name as user_name 
            FROM audit_logs a 
            LEFT JOIN users u ON a.user_id = u.id 
            ORDER BY a.timestamp DESC 
            LIMIT ?
        ''', (limit,))
        logs = cursor.fetchall()
        conn.close()
        return [dict(log) for log in logs]