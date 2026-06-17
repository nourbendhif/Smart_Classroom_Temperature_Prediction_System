// admin.js - Admin panel functionality

// Add new RFID
async function addRFID() {
    const rfidCode = document.getElementById('rfidCodeInput')?.value;
    const personName = document.getElementById('personNameInput')?.value;
    
    if (!rfidCode || !personName) {
        showAlert('Please fill all fields', 'warning');
        return;
    }
    
    try {
        const response = await fetch('/api/admin/rfid/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                rfid_code: rfidCode,
                person_name: personName
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showAlert('RFID added successfully!', 'success');
            document.getElementById('rfidCodeInput').value = '';
            document.getElementById('personNameInput').value = '';
            loadRFIDList();
        } else {
            showAlert(data.message || 'Error adding RFID', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error adding RFID', 'error');
    }
}

// Remove RFID
async function removeRFID(rfidCode) {
    if (!confirm(`Remove RFID ${rfidCode}?`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/admin/rfid/remove', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                rfid_code: rfidCode
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showAlert('RFID removed successfully!', 'success');
            loadRFIDList();
        } else {
            showAlert(data.message || 'Error removing RFID', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error removing RFID', 'error');
    }
}

// Update RFID
async function updateRFID(rfidCode) {
    const newName = prompt('Enter new person name:', rfidCode);
    
    if (newName === null) {
        return;
    }
    
    if (!newName.trim()) {
        showAlert('Person name cannot be empty', 'warning');
        return;
    }
    
    // Note: Update via remove and re-add
    if (confirm(`Remove ${rfidCode} and re-add with new name?`)) {
        await removeRFID(rfidCode);
    }
}

// Toggle RFID status (placeholder)
async function toggleRFIDStatus(rfidCode) {
    showAlert('Toggle feature not yet available', 'info');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error toggling RFID', 'error');
    }
}

// Load RFID list
async function loadRFIDList() {
    try {
        const response = await fetch('/api/admin/rfid/list');
        const data = await response.json();
        
        if (data.status === 'success') {
            const tableBody = document.getElementById('rfidTableBody');
            
            if (!tableBody) return;
            
            tableBody.innerHTML = '';
            
            if (data.rfids.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="5" style="text-align: center;">No RFIDs found</td></tr>';
                return;
            }
            
            data.rfids.forEach(rfid => {
                const row = document.createElement('tr');
                const statusBadge = rfid.is_active ? 
                    '<span style="background: #28a745; color: white; padding: 0.25rem 0.75rem; border-radius: 4px;">Active</span>' :
                    '<span style="background: #dc3545; color: white; padding: 0.25rem 0.75rem; border-radius: 4px;">Inactive</span>';
                
                row.innerHTML = `
                    <td>${rfid.rfid_code}</td>
                    <td>${rfid.person_name}</td>
                    <td>${formatDate(rfid.added_date)}</td>
                    <td>${statusBadge}</td>
                    <td>
                        <button class="btn btn-small btn-info" onclick="updateRFID('${rfid.rfid_code}')">Edit</button>
                        <button class="btn btn-small btn-secondary" onclick="toggleRFIDStatus('${rfid.rfid_code}')">Toggle</button>
                        <button class="btn btn-small btn-danger" onclick="removeRFID('${rfid.rfid_code}')">Delete</button>
                    </td>
                `;
                tableBody.appendChild(row);
            });
        }
    } catch (error) {
        console.error('Error loading RFID list:', error);
        showAlert('Error loading RFID list', 'error');
    }
}

// Load scan history (Attendance log)
async function loadScanHistory() {
    try {
        const response = await fetch('/api/attendance');
        const data = await response.json();
        
        if (data.status === 'success') {
            const tableBody = document.getElementById('scanHistoryBody');
            
            if (!tableBody) return;
            
            tableBody.innerHTML = '';
            
            const attendance = data.attendance || [];
            if (attendance.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="4" style="text-align: center;">No records available</td></tr>';
                return;
            }
            
            attendance.forEach(record => {
                const row = document.createElement('tr');
                const action = record.action || 'Entry';
                const actionBadge = action === 'Entry' ?
                    '<span style="background: #28a745; color: white; padding: 0.25rem 0.75rem; border-radius: 4px;">📥 Entry</span>' :
                    '<span style="background: #dc3545; color: white; padding: 0.25rem 0.75rem; border-radius: 4px;">📤 Exit</span>';
                
                row.innerHTML = `
                    <td><code>${record.rfid_code || 'N/A'}</code></td>
                    <td>${record.person_name || 'Unknown'}</td>
                    <td>${record.timestamp || 'N/A'}</td>
                    <td>${actionBadge}</td>
                `;
                tableBody.appendChild(row);
            });
        }
    } catch (error) {
        console.error('Error loading scan history:', error);
        showAlert('Error loading scan history', 'error');
    }
}

// Export RFID list as CSV
async function exportRFIDList() {
    try {
        const response = await fetch('/api/admin/rfid/list');
        const data = await response.json();
        
        if (data.status === 'success') {
            let csv = 'RFID Code,Person Name,Added Date,Status\n';
            
            data.rfids.forEach(rfid => {
                csv += `"${rfid.rfid_code}","${rfid.person_name}","${rfid.added_date}","${rfid.is_active ? 'Active' : 'Inactive'}"\n`;
            });
            
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `rfid_list_${new Date().toISOString().split('T')[0]}.csv`;
            a.click();
            
            showAlert('RFID list exported successfully!', 'success');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error exporting RFID list', 'error');
    }
}

// ================= FAN CONTROL FUNCTIONS =================

// Control fan manually
async function controlFan(action) {
    try {
        const response = await fetch('/api/admin/fan/control', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                action: action  // 'on', 'off', or 'auto'
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showAlert(data.message, 'success');
            loadFanStatus();
        } else {
            showAlert(data.message || 'Error controlling fan', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error controlling fan', 'error');
    }
}

// Load fan status
async function loadFanStatus() {
    try {
        const response = await fetch('/api/admin/fan/status');
        const data = await response.json();
        
        if (data.status === 'success') {
            // Update fan status display
            const statusDisplay = document.getElementById('fanStatusDisplay');
            const modeDisplay = document.getElementById('fanModeDisplay');
            const lastUpdatedDisplay = document.getElementById('fanLastUpdated');
            
            if (statusDisplay) {
                statusDisplay.textContent = data.fan_on ? '🟢 ON' : '🔴 OFF';
                statusDisplay.style.color = data.fan_on ? '#4CAF50' : '#f44336';
            }
            
            if (modeDisplay) {
                if (data.manual_mode) {
                    modeDisplay.textContent = `👤 Manual (${data.manual_state ? 'ON' : 'OFF'})`;
                    modeDisplay.style.color = '#FF9800';
                } else if (data.auto_enabled) {
                    modeDisplay.textContent = '🤖 Automatic';
                    modeDisplay.style.color = '#2196F3';
                } else {
                    modeDisplay.textContent = '⚪ Disabled';
                    modeDisplay.style.color = '#999';
                }
            }
            
            if (lastUpdatedDisplay) {
                const lastTime = new Date(data.last_updated);
                lastUpdatedDisplay.textContent = lastTime.toLocaleString();
            }
        }
    } catch (error) {
        console.error('Error loading fan status:', error);
    }
}

// Update fan settings
async function updateFanSettings() {
    try {
        const tempThreshold = parseFloat(document.getElementById('autoTempThresholdInput')?.value || 25);
        const fanRuntime = parseInt(document.getElementById('autoFanRuntimeInput')?.value || 30);
        
        if (isNaN(tempThreshold) || isNaN(fanRuntime)) {
            showAlert('Please enter valid numbers', 'warning');
            return;
        }
        
        const response = await fetch('/api/admin/settings/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                temp_threshold: tempThreshold,
                fan_runtime_minutes: fanRuntime,
                vent_status: true
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showAlert('Fan settings updated successfully!', 'success');
        } else {
            showAlert(data.message || 'Error updating settings', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error updating fan settings', 'error');
    }
}

// Initialize admin panel
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('rfidTableBody')) {
        loadRFIDList();
        setInterval(loadRFIDList, 10000); // Refresh every 10 seconds
    }
    
    if (document.getElementById('scanHistoryBody')) {
        loadScanHistory();
        setInterval(loadScanHistory, 5000); // Refresh every 5 seconds
    }
    
    // Load fan status if on fan tab
    if (document.getElementById('fanTab')) {
        loadFanStatus();
        setInterval(loadFanStatus, 2000); // Refresh every 2 seconds
    }
});
