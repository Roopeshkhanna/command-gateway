class CommandGateway {
    constructor() {
        this.apiKey = localStorage.getItem('apiKey') || '';
        this.currentUser = null;
        this.socket = null;
        this.stats = {
            commandsToday: 0,
            activeUsers: 0,
            blockedCommands: 0
        };
        this.init();
    }

    init() {
        this.bindEvents();
        if (this.apiKey) {
            this.verifyAuth();
        }
    }

    bindEvents() {
        // Auth
        document.getElementById('auth-btn').addEventListener('click', () => this.authenticate());
        document.getElementById('logout-btn').addEventListener('click', () => this.logout());
        
        // Member actions
        document.getElementById('submit-command').addEventListener('click', () => this.submitCommand());
        
        // Admin actions
        document.getElementById('create-user').addEventListener('click', () => this.createUser());
        document.getElementById('create-rule').addEventListener('click', () => this.createRule());
        document.getElementById('check-conflicts').addEventListener('click', () => this.checkRuleConflicts());
        
        // Real-time regex validation
        document.getElementById('new-rule-pattern').addEventListener('input', (e) => {
            this.validateRegexPattern(e.target.value);
        });
        
        // Check conflicts when action changes
        document.getElementById('new-rule-action').addEventListener('change', () => {
            const pattern = document.getElementById('new-rule-pattern').value.trim();
            if (pattern) {
                this.validateRegexPattern(pattern);
            }
        });
        
        // History search and export
        document.getElementById('history-search').addEventListener('input', (e) => this.filterHistory(e.target.value));
        document.getElementById('export-history').addEventListener('click', () => this.exportHistory());
        
        // Tabs
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
        });

        // Enter key for command submission
        document.getElementById('command-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                this.submitCommand();
            }
        });

        // Enter key for auth
        document.getElementById('api-key').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.authenticate();
            }
        });

        // Template buttons
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('template-btn')) {
                const command = e.target.dataset.command;
                document.getElementById('command-input').value = command;
                document.getElementById('command-input').focus();
            }
        });
    }

    async authenticate() {
        const apiKey = document.getElementById('api-key').value.trim();
        if (!apiKey) {
            this.showMessage('Please enter an API key', 'error');
            return;
        }

        try {
            const response = await fetch('/api/auth/verify', {
                headers: { 'X-API-Key': apiKey }
            });

            if (response.ok) {
                const data = await response.json();
                this.apiKey = apiKey;
                this.currentUser = data.user;
                localStorage.setItem('apiKey', apiKey);
                this.showDashboard();
                this.showMessage('Authentication successful', 'success');
            } else {
                this.showMessage('Invalid API key', 'error');
            }
        } catch (error) {
            this.showMessage('Authentication failed', 'error');
        }
    }

    async verifyAuth() {
        try {
            const response = await fetch('/api/auth/verify', {
                headers: { 'X-API-Key': this.apiKey }
            });

            if (response.ok) {
                const data = await response.json();
                this.currentUser = data.user;
                this.showDashboard();
            } else {
                this.logout();
            }
        } catch (error) {
            this.logout();
        }
    }

    logout() {
        this.apiKey = '';
        this.currentUser = null;
        localStorage.removeItem('apiKey');
        document.getElementById('auth-section').style.display = 'block';
        document.getElementById('member-dashboard').style.display = 'none';
        document.getElementById('admin-dashboard').style.display = 'none';
        document.getElementById('user-info').style.display = 'none';
        document.getElementById('api-key').value = '';
    }

    showDashboard() {
        document.getElementById('auth-section').style.display = 'none';
        document.getElementById('user-info').style.display = 'flex';
        
        // Update user info
        document.getElementById('user-name').textContent = `${this.currentUser.name} (${this.currentUser.role})`;
        document.getElementById('user-credits').textContent = `Credits: ${this.currentUser.credits}`;

        // Initialize WebSocket connection
        this.initWebSocket();

        if (this.currentUser.role === 'admin') {
            document.getElementById('admin-dashboard').style.display = 'block';
            document.getElementById('member-dashboard').style.display = 'none';
            this.loadRules();
            this.loadAuditLogs();
            this.loadRealtimeStats();
        } else {
            document.getElementById('member-dashboard').style.display = 'block';
            document.getElementById('admin-dashboard').style.display = 'none';
            this.loadCommandHistory();
        }
    }

    initWebSocket() {
        this.socket = io();
        
        // Join appropriate room
        if (this.currentUser.role === 'admin') {
            this.socket.emit('join_admin_room', { api_key: this.apiKey });
        }
        this.socket.emit('join_user_room', { api_key: this.apiKey });

        // Listen for real-time events
        this.socket.on('command_executed', (data) => {
            this.handleRealtimeCommand(data);
        });

        this.socket.on('credit_update', (data) => {
            this.currentUser.credits = data.credits;
            document.getElementById('user-credits').textContent = `Credits: ${this.currentUser.credits}`;
        });

        this.socket.on('approval_update', (data) => {
            this.handleApprovalUpdate(data);
        });
    }

    handleRealtimeCommand(data) {
        if (this.currentUser.role !== 'admin') return;

        // Update stats
        this.stats.commandsToday++;
        if (data.status === 'REJECTED') {
            this.stats.blockedCommands++;
        }

        // Update display
        this.updateRealtimeStats();
        this.addLiveActivity(data);
    }

    updateRealtimeStats() {
        document.getElementById('commands-today').textContent = this.stats.commandsToday;
        document.getElementById('active-users').textContent = this.stats.activeUsers;
        document.getElementById('blocked-commands').textContent = this.stats.blockedCommands;
    }

    addLiveActivity(data) {
        const container = document.getElementById('live-activity');
        if (!container) return;

        const activityItem = document.createElement('div');
        activityItem.className = `activity-item ${data.status.toLowerCase()}`;
        
        const statusIcon = data.status === 'EXECUTED' ? '✅' : '❌';
        const statusColor = data.status === 'EXECUTED' ? '#27ae60' : '#e74c3c';
        
        activityItem.innerHTML = `
            <div class="activity-header">
                <span class="activity-status" style="color: ${statusColor}">${statusIcon} ${data.status}</span>
                <span class="activity-time">${new Date(data.timestamp).toLocaleTimeString()}</span>
            </div>
            <div class="activity-user">👤 ${data.user_name}</div>
            <div class="activity-command">${this.escapeHtml(data.command)}</div>
        `;

        container.insertBefore(activityItem, container.firstChild);

        // Keep only last 10 activities
        while (container.children.length > 10) {
            container.removeChild(container.lastChild);
        }

        // Animate new item
        activityItem.style.opacity = '0';
        activityItem.style.transform = 'translateY(-20px)';
        setTimeout(() => {
            activityItem.style.transition = 'all 0.3s ease';
            activityItem.style.opacity = '1';
            activityItem.style.transform = 'translateY(0)';
        }, 10);
    }

    async loadRealtimeStats() {
        try {
            const response = await fetch('/api/analytics', {
                headers: { 'X-API-Key': this.apiKey }
            });

            if (response.ok) {
                const analytics = await response.json();
                
                // Update stats from analytics
                this.stats.commandsToday = analytics.daily_stats.total_commands || 0;
                this.stats.blockedCommands = analytics.daily_stats.rejected_commands || 0;
                this.stats.activeUsers = analytics.user_activity.filter(u => u.command_count > 0).length || 1;
                
                this.updateRealtimeStats();
                this.renderAnalytics(analytics);
            }
        } catch (error) {
            console.error('Failed to load analytics:', error);
            // Fallback to basic stats
            this.stats.activeUsers = 1;
            this.updateRealtimeStats();
        }
    }

    renderAnalytics(analytics) {
        const container = document.getElementById('live-activity');
        if (!container) return;

        // Add analytics summary
        const analyticsHtml = `
            <div class="analytics-summary">
                <h4>📊 Today's Analytics</h4>
                <div class="analytics-grid">
                    <div class="analytics-item">
                        <strong>Total Commands:</strong> ${analytics.daily_stats.total_commands || 0}
                    </div>
                    <div class="analytics-item">
                        <strong>Success Rate:</strong> ${this.calculateSuccessRate(analytics.daily_stats)}%
                    </div>
                    <div class="analytics-item">
                        <strong>Credits Used:</strong> ${analytics.daily_stats.total_credits_used || 0}
                    </div>
                </div>
            </div>
            <div class="top-commands">
                <h4>🔥 Most Used Commands</h4>
                ${analytics.top_commands.slice(0, 5).map(cmd => `
                    <div class="command-stat">
                        <code>${this.escapeHtml(cmd.command_text)}</code>
                        <span class="command-count">${cmd.count}x</span>
                        <span class="command-status ${cmd.status.toLowerCase()}">${cmd.status}</span>
                    </div>
                `).join('')}
            </div>
        `;

        container.innerHTML = analyticsHtml;
    }

    calculateSuccessRate(stats) {
        const total = stats.total_commands || 0;
        const executed = stats.executed_commands || 0;
        return total > 0 ? Math.round((executed / total) * 100) : 100;
    }

    filterHistory(searchTerm) {
        const historyItems = document.querySelectorAll('.history-item');
        const term = searchTerm.toLowerCase();

        historyItems.forEach(item => {
            const commandText = item.querySelector('.command-text').textContent.toLowerCase();
            const isVisible = commandText.includes(term) || term === '';
            item.style.display = isVisible ? 'block' : 'none';
        });
    }

    exportHistory() {
        if (!this.allCommands) return;

        const csvContent = [
            ['Timestamp', 'Command', 'Status', 'Credits Used', 'Rule Pattern'].join(','),
            ...this.allCommands.map(cmd => [
                new Date(cmd.created_at).toISOString(),
                `"${cmd.command_text.replace(/"/g, '""')}"`,
                cmd.status,
                cmd.credits_deducted || 0,
                cmd.rule_pattern || ''
            ].join(','))
        ].join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `command-history-${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        this.showMessage('📥 Command history exported successfully!', 'success');
    }

    async validateRegexPattern(pattern) {
        const validationDiv = document.getElementById('pattern-validation');
        const createButton = document.getElementById('create-rule');
        const conflictButton = document.getElementById('check-conflicts');
        
        if (!pattern.trim()) {
            validationDiv.innerHTML = '';
            createButton.disabled = true;
            conflictButton.disabled = true;
            return;
        }

        // Enable conflict button immediately if there's any pattern
        // (conflict checking doesn't require valid regex)
        conflictButton.disabled = false;

        try {
            const response = await fetch('/api/rules/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': this.apiKey
                },
                body: JSON.stringify({ pattern: pattern.trim() })
            });

            const validation = await response.json();

            if (validation.valid) {
                validationDiv.innerHTML = `
                    <div class="validation-success">
                        ✅ Valid regex pattern
                        ${validation.suggestions.length > 0 ? 
                            `<div class="validation-suggestions">
                                <strong>💡 Suggestions:</strong>
                                <ul>${validation.suggestions.map(s => `<li>${s}</li>`).join('')}</ul>
                            </div>` : ''
                        }
                    </div>
                `;
                createButton.disabled = false;
                conflictButton.disabled = false;
            } else {
                validationDiv.innerHTML = `
                    <div class="validation-error">
                        ❌ ${validation.error}
                        ${validation.suggestions.length > 0 ? 
                            `<div class="validation-suggestions">
                                <strong>💡 Try these fixes:</strong>
                                <ul>${validation.suggestions.map(s => `<li>${s}</li>`).join('')}</ul>
                            </div>` : ''
                        }
                    </div>
                `;
                createButton.disabled = true;
                conflictButton.disabled = true;
            }
        } catch (error) {
            validationDiv.innerHTML = `
                <div class="validation-error">
                    ❌ Unable to validate pattern
                </div>
            `;
            createButton.disabled = true;
            conflictButton.disabled = true;
        }
    }

    async checkRuleConflicts() {
        console.log('🔍 Check conflicts button clicked!'); // Debug log
        
        const pattern = document.getElementById('new-rule-pattern').value.trim();
        const action = document.getElementById('new-rule-action').value;
        const conflictDiv = document.getElementById('conflict-analysis');

        console.log('Pattern:', pattern, 'Action:', action); // Debug log

        if (!pattern) {
            this.showMessage('Please enter a pattern first', 'error');
            return;
        }

        // Show loading message
        conflictDiv.innerHTML = '<div class="conflict-result"><h4>🔍 Checking for conflicts...</h4></div>';
        conflictDiv.style.display = 'block';

        try {
            const response = await fetch('/api/rules/check-conflicts', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': this.apiKey
                },
                body: JSON.stringify({ pattern, action })
            });

            const result = await response.json();
            console.log('Conflict check result:', result); // Debug log

            if (response.ok) {
                this.renderConflictAnalysis(result);
                conflictDiv.style.display = 'block';
            } else {
                this.showMessage(result.error || 'Failed to check conflicts', 'error');
                conflictDiv.innerHTML = `<div class="conflict-result"><h4>❌ Error: ${result.error}</h4></div>`;
            }
        } catch (error) {
            console.error('Conflict check error:', error); // Debug log
            this.showMessage('Failed to check conflicts', 'error');
            conflictDiv.innerHTML = `<div class="conflict-result"><h4>❌ Error: ${error.message}</h4></div>`;
        }
    }

    renderConflictAnalysis(result) {
        const conflictDiv = document.getElementById('conflict-analysis');
        
        if (!result.has_conflicts) {
            conflictDiv.innerHTML = `
                <div class="conflict-result no-conflicts">
                    <h4>✅ No Conflicts Detected</h4>
                    <p>This rule doesn't conflict with existing rules.</p>
                </div>
            `;
            return;
        }

        const highSeverity = result.conflicts.filter(c => c.severity === 'HIGH');
        const mediumSeverity = result.conflicts.filter(c => c.severity === 'MEDIUM');
        const lowSeverity = result.conflicts.filter(c => c.severity === 'LOW');

        let html = `
            <div class="conflict-result has-conflicts">
                <h4>⚠️ Rule Conflicts Detected</h4>
                <div class="conflict-summary">
                    ${highSeverity.length > 0 ? `<span class="severity-high">${highSeverity.length} High</span>` : ''}
                    ${mediumSeverity.length > 0 ? `<span class="severity-medium">${mediumSeverity.length} Medium</span>` : ''}
                    ${lowSeverity.length > 0 ? `<span class="severity-low">${lowSeverity.length} Low</span>` : ''}
                </div>
        `;

        // Show warnings
        if (result.warnings.length > 0) {
            html += `
                <div class="conflict-warnings">
                    <h5>⚠️ Warnings:</h5>
                    <ul>
                        ${result.warnings.map(w => `<li>${w}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        // Show detailed conflicts
        if (result.conflicts.length > 0) {
            html += `<div class="conflict-details">`;
            
            [...highSeverity, ...mediumSeverity, ...lowSeverity].forEach(conflict => {
                html += `
                    <div class="conflict-item severity-${conflict.severity.toLowerCase()}">
                        <div class="conflict-header">
                            <span class="conflict-type">${conflict.conflict_type.replace('_', ' ')}</span>
                            <span class="severity-badge ${conflict.severity.toLowerCase()}">${conflict.severity}</span>
                        </div>
                        <div class="conflict-description">${conflict.description}</div>
                        <div class="conflict-rule">
                            <strong>Conflicts with Rule #${conflict.rule_id}:</strong> 
                            <code>${conflict.existing_pattern}</code> → ${conflict.existing_action}
                        </div>
                        ${conflict.examples.length > 0 ? `
                            <div class="conflict-examples">
                                <strong>Example overlapping commands:</strong>
                                <div class="example-commands">
                                    ${conflict.examples.map(ex => `<code>${ex}</code>`).join(' ')}
                                </div>
                            </div>
                        ` : ''}
                    </div>
                `;
            });
            
            html += `</div>`;
        }

        // Show suggestions
        if (result.suggestions.length > 0) {
            html += `
                <div class="conflict-suggestions">
                    <h5>💡 Suggestions:</h5>
                    <ul>
                        ${result.suggestions.map(s => `<li>${s}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        html += `</div>`;
        conflictDiv.innerHTML = html;
    }

    async loadPendingApprovals() {
        try {
            const response = await fetch('/api/pending-approvals', {
                headers: { 'X-API-Key': this.apiKey }
            });

            if (response.ok) {
                const approvals = await response.json();
                this.renderPendingApprovals(approvals);
            }
        } catch (error) {
            console.error('Failed to load pending approvals:', error);
        }
    }

    renderPendingApprovals(approvals) {
        const container = document.getElementById('pending-approvals');
        
        if (approvals.length === 0) {
            container.innerHTML = '<p>✅ No commands pending approval.</p>';
            return;
        }

        container.innerHTML = approvals.map(cmd => `
            <div class="approval-item" data-command-id="${cmd.id}">
                <div class="approval-header">
                    <div class="approval-user">👤 ${cmd.user_name}</div>
                    <div class="approval-time">${new Date(cmd.created_at).toLocaleString()}</div>
                </div>
                <div class="approval-command">${this.escapeHtml(cmd.command_text)}</div>
                <div class="ai-analysis-full">
                    <strong>🤖 AI Analysis:</strong> ${cmd.ai_analysis}
                </div>
                <div class="risk-indicator">
                    <span class="risk-score-badge risk-${this.getRiskLevel(cmd.ai_risk_score)}">
                        Risk Score: ${cmd.ai_risk_score}/10
                    </span>
                </div>
                <div class="approval-status">
                    Approvals: ${cmd.approval_count}/${cmd.required_approvals}
                </div>
                <div class="approval-actions">
                    <button class="btn btn-success approve-btn" data-command-id="${cmd.id}">
                        ✅ Approve
                    </button>
                    <button class="btn btn-danger reject-btn" data-command-id="${cmd.id}">
                        ❌ Reject
                    </button>
                </div>
            </div>
        `).join('');

        // Add event listeners for approval buttons
        container.querySelectorAll('.approve-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const commandId = parseInt(e.target.dataset.commandId);
                this.handleApproval(commandId, true);
            });
        });

        container.querySelectorAll('.reject-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const commandId = parseInt(e.target.dataset.commandId);
                this.handleApproval(commandId, false);
            });
        });
    }

    getRiskLevel(score) {
        if (score >= 8) return 'high';
        if (score >= 5) return 'medium';
        return 'low';
    }

    async handleApproval(commandId, approved) {
        const reason = approved ? 
            prompt('Optional reason for approval:') : 
            prompt('Reason for rejection (required):');
        
        if (!approved && !reason) {
            this.showMessage('Rejection reason is required', 'error');
            return;
        }

        try {
            const response = await fetch(`/api/commands/${commandId}/approve`, {
                method: 'POST',
                headers: {
                    'X-API-Key': this.apiKey,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    approved: approved,
                    reason: reason || ''
                })
            });

            const result = await response.json();

            if (response.ok) {
                const action = approved ? 'approved' : 'rejected';
                this.showMessage(`✅ Command ${action} successfully`, 'success');
                this.loadPendingApprovals(); // Refresh the list
            } else {
                this.showMessage(result.error || 'Failed to process approval', 'error');
            }
        } catch (error) {
            this.showMessage('Failed to process approval', 'error');
        }
    }

    handleApprovalUpdate(data) {
        // Handle real-time approval updates
        this.showMessage(`🔐 Admin ${data.admin_name} ${data.approved ? 'approved' : 'rejected'} a command`, 'info');
        
        // Refresh approvals if we're on that tab
        const activeTab = document.querySelector('.tab-content.active');
        if (activeTab && activeTab.id === 'approvals-tab') {
            this.loadPendingApprovals();
        }
    }

    async submitCommand() {
        const commandText = document.getElementById('command-input').value.trim();
        if (!commandText) {
            this.showMessage('Please enter a command', 'error');
            return;
        }

        try {
            const response = await fetch('/api/commands', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': this.apiKey
                },
                body: JSON.stringify({ command: commandText })
            });

            const data = await response.json();

            if (response.ok) {
                document.getElementById('command-input').value = '';
                
                // Show user-friendly messages based on command status
                let message = '';
                let messageType = '';
                
                if (data.status === 'EXECUTED') {
                    message = '✅ Command accepted and executed successfully!';
                    messageType = 'success';
                } else if (data.status === 'REJECTED') {
                    message = '❌ You don\'t have access to execute this command';
                    messageType = 'error';
                } else if (data.status === 'ACCEPTED') {
                    message = '✅ Command accepted';
                    messageType = 'success';
                } else if (data.status === 'PENDING_APPROVAL') {
                    message = '🤖 Command flagged by AI - awaiting admin approval';
                    messageType = 'info';
                } else {
                    message = `Command ${data.status.toLowerCase()}`;
                    messageType = 'info';
                }
                
                this.showMessage(message, messageType);
                
                // Update credits display
                if (data.credits_remaining !== undefined) {
                    this.currentUser.credits = data.credits_remaining;
                    document.getElementById('user-credits').textContent = `Credits: ${this.currentUser.credits}`;
                }
                
                this.loadCommandHistory();
            } else {
                // Handle different error types with user-friendly messages
                let errorMessage = '';
                if (data.error && data.error.toLowerCase().includes('credit')) {
                    errorMessage = '❌ Insufficient credits to execute command';
                } else if (data.error && data.error.toLowerCase().includes('invalid')) {
                    errorMessage = '❌ Invalid command format';
                } else {
                    errorMessage = data.error || 'Command submission failed';
                }
                this.showMessage(errorMessage, 'error');
            }
        } catch (error) {
            this.showMessage('Command submission failed', 'error');
        }
    }

    async loadCommandHistory() {
        try {
            const response = await fetch('/api/commands', {
                headers: { 'X-API-Key': this.apiKey }
            });

            if (response.ok) {
                const commands = await response.json();
                this.allCommands = commands; // Store for export
                this.renderCommandHistory(commands);
            }
        } catch (error) {
            console.error('Failed to load command history:', error);
        }
    }

    renderCommandHistory(commands) {
        const container = document.getElementById('command-history');
        
        if (commands.length === 0) {
            container.innerHTML = '<p>No commands submitted yet.</p>';
            return;
        }

        container.innerHTML = commands.map(cmd => {
            let statusText = '';
            let statusIcon = '';
            
            if (cmd.status === 'EXECUTED') {
                statusText = 'Executed Successfully';
                statusIcon = '✅';
            } else if (cmd.status === 'REJECTED') {
                statusText = 'Access Denied';
                statusIcon = '❌';
            } else if (cmd.status === 'ACCEPTED') {
                statusText = 'Accepted';
                statusIcon = '✅';
            } else if (cmd.status === 'PENDING_APPROVAL') {
                statusText = 'Awaiting Approval';
                statusIcon = '🤖';
            } else {
                statusText = cmd.status;
                statusIcon = '⏳';
            }
            
            return `
                <div class="history-item ${cmd.status.toLowerCase()}">
                    <div class="item-header">
                        <span class="status ${cmd.status.toLowerCase()}">${statusIcon} ${statusText}</span>
                        <span class="timestamp">${new Date(cmd.created_at).toLocaleString()}</span>
                    </div>
                    <div class="command-text">${this.escapeHtml(cmd.command_text)}</div>
                    ${cmd.status === 'REJECTED' ? '<div class="rejection-reason">⚠️ Command blocked by security rules</div>' : ''}
                    ${cmd.status === 'PENDING_APPROVAL' ? '<div class="ai-analysis">🤖 AI flagged as potentially dangerous - awaiting admin approval</div>' : ''}
                    ${cmd.ai_analysis ? `<div class="ai-info">AI Analysis: ${cmd.ai_analysis}</div>` : ''}
                    ${cmd.ai_risk_score ? `<div class="risk-score">Risk Score: ${cmd.ai_risk_score}/10</div>` : ''}
                    ${cmd.rule_pattern ? `<div class="rule-info">Security rule: ${cmd.rule_pattern}</div>` : ''}
                    ${cmd.credits_deducted ? `<div class="credits-info">Credits used: ${cmd.credits_deducted}</div>` : ''}
                </div>
            `;
        }).join('');
    }

    async createUser() {
        const name = document.getElementById('new-user-name').value.trim();
        const role = document.getElementById('new-user-role').value;
        const credits = parseInt(document.getElementById('new-user-credits').value) || 100;

        if (!name) {
            this.showMessage('Please enter a user name', 'error');
            return;
        }

        try {
            const response = await fetch('/api/users', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': this.apiKey
                },
                body: JSON.stringify({ name, role, credits })
            });

            const data = await response.json();

            if (response.ok) {
                document.getElementById('new-user-name').value = '';
                document.getElementById('new-user-credits').value = '100';
                
                document.getElementById('new-user-result').innerHTML = `
                    <h4>User Created Successfully</h4>
                    <p><strong>Name:</strong> ${data.name}</p>
                    <p><strong>Role:</strong> ${data.role}</p>
                    <p><strong>Credits:</strong> ${data.credits}</p>
                    <p><strong>API Key:</strong></p>
                    <div class="api-key-display">${data.api_key}</div>
                    <p><em>⚠️ Save this API key - it won't be shown again!</em></p>
                `;
                
                this.showMessage('User created successfully', 'success');
            } else {
                this.showMessage(data.error || 'Failed to create user', 'error');
            }
        } catch (error) {
            this.showMessage('Failed to create user', 'error');
        }
    }

    async validateRegexPattern(pattern) {
        const validationDiv = document.getElementById('pattern-validation');
        const createButton = document.getElementById('create-rule');
        
        if (!pattern.trim()) {
            validationDiv.innerHTML = '';
            createButton.disabled = true;
            return;
        }

        try {
            const response = await fetch('/api/rules/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': this.apiKey
                },
                body: JSON.stringify({ pattern: pattern.trim() })
            });

            const validation = await response.json();

            if (validation.valid) {
                validationDiv.innerHTML = `
                    <div class="validation-success">
                        ✅ Valid regex pattern
                        ${validation.suggestions.length > 0 ? 
                            `<div class="validation-suggestions">
                                <strong>💡 Suggestions:</strong>
                                <ul>${validation.suggestions.map(s => `<li>${s}</li>`).join('')}</ul>
                            </div>` : ''
                        }
                    </div>
                `;
                createButton.disabled = false;
            } else {
                validationDiv.innerHTML = `
                    <div class="validation-error">
                        ❌ ${validation.error}
                        ${validation.suggestions.length > 0 ? 
                            `<div class="validation-suggestions">
                                <strong>💡 Try these fixes:</strong>
                                <ul>${validation.suggestions.map(s => `<li>${s}</li>`).join('')}</ul>
                            </div>` : ''
                        }
                    </div>
                `;
                createButton.disabled = true;
            }
        } catch (error) {
            validationDiv.innerHTML = `
                <div class="validation-error">
                    ❌ Unable to validate pattern
                </div>
            `;
            createButton.disabled = true;
        }
    }

    async createRule() {
        const pattern = document.getElementById('new-rule-pattern').value.trim();
        const action = document.getElementById('new-rule-action').value;

        if (!pattern) {
            this.showMessage('Please enter a regex pattern', 'error');
            return;
        }

        try {
            const response = await fetch('/api/rules', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': this.apiKey
                },
                body: JSON.stringify({ pattern, action })
            });

            const data = await response.json();

            if (response.ok) {
                document.getElementById('new-rule-pattern').value = '';
                document.getElementById('pattern-validation').innerHTML = '';
                document.getElementById('create-rule').disabled = true;
                this.showMessage('✅ Rule created successfully', 'success');
                this.loadRules();
            } else {
                this.showMessage(`❌ ${data.error}`, 'error');
            }
        } catch (error) {
            this.showMessage('Failed to create rule', 'error');
        }
    }

    async loadRules() {
        try {
            const response = await fetch('/api/rules', {
                headers: { 'X-API-Key': this.apiKey }
            });

            if (response.ok) {
                const rules = await response.json();
                this.renderRules(rules);
            }
        } catch (error) {
            console.error('Failed to load rules:', error);
        }
    }

    renderRules(rules) {
        const container = document.getElementById('rules-list');
        
        if (rules.length === 0) {
            container.innerHTML = '<p>No rules configured.</p>';
            return;
        }

        container.innerHTML = rules.map(rule => `
            <div class="rule-item ${rule.action.toLowerCase().replace('_', '-')}">
                <div class="item-header">
                    <span class="status ${rule.action.toLowerCase().replace('_', '-')}">${rule.action.replace('_', ' ')}</span>
                    <span class="timestamp">Order: ${rule.order_index}</span>
                </div>
                <div class="command-text">${this.escapeHtml(rule.pattern)}</div>
                <div class="timestamp">Created: ${new Date(rule.created_at).toLocaleString()}</div>
            </div>
        `).join('');
    }

    async loadAuditLogs() {
        try {
            const response = await fetch('/api/audit-logs', {
                headers: { 'X-API-Key': this.apiKey }
            });

            if (response.ok) {
                const logs = await response.json();
                this.renderAuditLogs(logs);
            }
        } catch (error) {
            console.error('Failed to load audit logs:', error);
        }
    }

    renderAuditLogs(logs) {
        const container = document.getElementById('audit-logs');
        
        if (logs.length === 0) {
            container.innerHTML = '<p>No audit logs available.</p>';
            return;
        }

        container.innerHTML = logs.map(log => `
            <div class="audit-item">
                <div class="item-header">
                    <span class="status info">${log.action}</span>
                    <span class="timestamp">${new Date(log.timestamp).toLocaleString()}</span>
                </div>
                <div><strong>User:</strong> ${log.user_name || 'System'}</div>
                <div><strong>Details:</strong> ${this.escapeHtml(log.details)}</div>
            </div>
        `).join('');
    }

    switchTab(tabName) {
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(`${tabName}-tab`).classList.add('active');

        // Load data for specific tabs
        if (tabName === 'rules') {
            this.loadRules();
        } else if (tabName === 'audit') {
            this.loadAuditLogs();
        } else if (tabName === 'realtime') {
            this.loadRealtimeStats();
        } else if (tabName === 'approvals') {
            this.loadPendingApprovals();
        }
    }

    showMessage(text, type = 'info') {
        const messageEl = document.getElementById('message');
        messageEl.textContent = text;
        messageEl.className = `message ${type}`;
        messageEl.classList.add('show');

        setTimeout(() => {
            messageEl.classList.remove('show');
        }, 3000);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    new CommandGateway();
});