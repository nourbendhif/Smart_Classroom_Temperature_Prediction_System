// script.js - Main JavaScript functionality

// Show alert/notification
function showAlert(message, type = 'success') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.textContent = message;
    alertDiv.style.position = 'fixed';
    alertDiv.style.top = '20px';
    alertDiv.style.right = '20px';
    alertDiv.style.zIndex = '10000';
    alertDiv.style.minWidth = '300px';
    
    document.body.appendChild(alertDiv);
    
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}

// Close modal
function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('show');
}

// Open modal
function openModal(modalId) {
    document.getElementById(modalId).classList.add('show');
}

// Fetch sensor data and update dashboard
async function updateSensorData() {
    try {
        // Use /api/sensor/latest which returns the latest sensor data
        const response = await fetch('/api/sensor/latest');
        const result = await response.json();
        
        if (result.status === 'success' && result.data && Object.keys(result.data).length > 0) {
            const data = result.data;
            
            // Update temperature
            if (document.getElementById('tempValue') && data.temperature !== undefined) {
                document.getElementById('tempValue').textContent = parseFloat(data.temperature).toFixed(2) + ' °C';
            }
            
            // Update humidity
            if (document.getElementById('humValue') && data.humidity !== undefined) {
                document.getElementById('humValue').textContent = parseFloat(data.humidity).toFixed(2) + ' %';
            }
            
            // Update pressure
            if (document.getElementById('pressureValue') && data.pressure !== undefined) {
                document.getElementById('pressureValue').textContent = parseFloat(data.pressure).toFixed(2) + ' hPa';
            }
            
            // Update movement
            if (document.getElementById('movementValue') && data.movement !== undefined) {
                document.getElementById('movementValue').textContent = data.movement;
            }
            
            // Update prediction
            if (document.getElementById('predictionValue') && data.prediction !== undefined) {
                document.getElementById('predictionValue').textContent = parseFloat(data.prediction).toFixed(2);
            }
            
            // Update confidence
            if (document.getElementById('confidence') && data.confidence !== undefined) {
                document.getElementById('confidence').textContent = parseFloat(data.confidence).toFixed(0);
            }
            
            // Update occupancy
            if (document.getElementById('occupancyValue') && data.occupancy !== undefined) {
                document.getElementById('occupancyValue').textContent = data.occupancy;
            }
            
            // Update last update time
            if (document.getElementById('lastUpdate')) {
                document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
            }
        } else {
            console.log('No sensor data available yet');
        }
    } catch (error) {
        console.error('Error updating sensor data:', error);
    }
}

// Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString();
}

// Copy to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showAlert('Copied to clipboard!', 'success');
    }).catch(() => {
        showAlert('Failed to copy', 'error');
    });
}

// Initialize WebSocket for real-time updates
function initializeWebSocket() {
    // Check if Socket.IO is available
    if (typeof io === 'undefined') {
        console.warn('Socket.IO not loaded, falling back to polling');
        startAutoRefresh();
        return;
    }
    
    // Connect to WebSocket
    const socket = io({
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        reconnectionAttempts: 5
    });
    
    // When connected to WebSocket
    socket.on('connect', function() {
        console.log('✓ Connected to real-time server');
        // Request current data immediately
        socket.emit('request_data');
    });
    
    // Receive sensor updates in real-time
    socket.on('sensor_update', function(data) {
        // Update temperature
        if (document.getElementById('tempValue') && data.temperature !== undefined) {
            document.getElementById('tempValue').textContent = parseFloat(data.temperature).toFixed(2) + ' °C';
        }
        
        // Update humidity
        if (document.getElementById('humValue') && data.humidity !== undefined) {
            document.getElementById('humValue').textContent = parseFloat(data.humidity).toFixed(2) + ' %';
        }
        
        // Update pressure
        if (document.getElementById('pressureValue') && data.pressure !== undefined) {
            document.getElementById('pressureValue').textContent = parseFloat(data.pressure).toFixed(2) + ' hPa';
        }
        
        // Update movement
        if (document.getElementById('movementValue') && data.movement !== undefined) {
            document.getElementById('movementValue').textContent = data.movement;
        }
        
        // Update prediction
        if (document.getElementById('predictionValue') && data.prediction !== undefined) {
            document.getElementById('predictionValue').textContent = parseFloat(data.prediction).toFixed(2);
        }
        
        // Update confidence
        if (document.getElementById('confidence') && data.confidence !== undefined) {
            document.getElementById('confidence').textContent = parseFloat(data.confidence).toFixed(0);
        }
        
        // Update occupancy
        if (document.getElementById('occupancyValue') && data.occupancy !== undefined) {
            document.getElementById('occupancyValue').textContent = data.occupancy;
        }
        
        // Update last update time
        if (document.getElementById('lastUpdate')) {
            document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
        }
    });
    
    // Connection errors
    socket.on('connect_error', function(error) {
        console.warn('WebSocket connection error, falling back to polling:', error);
        startAutoRefresh();
    });
    
    socket.on('disconnect', function() {
        console.log('Disconnected from real-time server');
    });
}


// ================= FAN CONTROL FUNCTIONS =================

// Update fan status display
async function updateFanStatus() {
    try {
        const response = await fetch('/api/fan/status');
        const data = await response.json();
        if (data.status === 'success') {
            // Update status display
            const fanStatusEl = document.getElementById('fanStatus');
            if (fanStatusEl) {
                fanStatusEl.textContent = data.fan_on ? '● ON' : '● OFF';
                fanStatusEl.style.color = data.fan_on ? '#4caf50' : '#f44336';
            }
            // Update mode display
            const fanModeEl = document.getElementById('fanMode');
            if (fanModeEl) {
                fanModeEl.textContent = data.mode.toUpperCase();
                fanModeEl.style.color = data.mode === 'manual' ? '#667eea' : '#ff9800';
            }
        }
    } catch (e) {
        console.error('Error updating fan status:', e);
    }
}

// Switch between manual and automatic tabs
function switchTab(mode) {
    const manualConfig = document.getElementById('manualConfig');
    const autoConfig = document.getElementById('autoConfig');
    const btnManualTab = document.getElementById('btnManualTab');
    const btnAutoTab = document.getElementById('btnAutoTab');
    
    if (mode === 'manual') {
        manualConfig.style.display = 'block';
        autoConfig.style.display = 'none';
        btnManualTab.style.background = '#4caf50';
        btnManualTab.style.color = 'white';
        btnAutoTab.style.background = '#ccc';
        btnAutoTab.style.color = '#333';
    } else {
        manualConfig.style.display = 'none';
        autoConfig.style.display = 'block';
        btnManualTab.style.background = '#ccc';
        btnManualTab.style.color = '#333';
        btnAutoTab.style.background = '#ff9800';
        btnAutoTab.style.color = 'white';
    }
}

// Set manual mode
async function setManualMode() {
    const runtime = parseInt(document.getElementById('runtimeMinutes').value);
    if (isNaN(runtime) || runtime < 1 || runtime > 480) {
        showAlert('Invalid runtime (1-480 minutes)', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/fan/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: 'manual', runtime_minutes: runtime})
        });
        const data = await response.json();
        if (data.status === 'success') {
            showAlert(`✓ Manual mode set (${runtime} min)`, 'success');
            updateFanStatus();
        } else {
            showAlert(`Error: ${data.message}`, 'error');
        }
    } catch (e) {
        showAlert('Failed to set manual mode', 'error');
    }
}

// Set automatic mode
async function setAutoMode() {
    const threshold = parseFloat(document.getElementById('thresholdTemp').value);
    if (isNaN(threshold) || threshold < 0 || threshold > 50) {
        showAlert('Invalid threshold (0-50°C)', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/fan/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: 'automatic', temperature_threshold: threshold})
        });
        const data = await response.json();
        if (data.status === 'success') {
            showAlert(`✓ Auto mode set (threshold: ${threshold}°C)`, 'success');
            updateFanStatus();
        } else {
            showAlert(`Error: ${data.message}`, 'error');
        }
    } catch (e) {
        showAlert('Failed to set auto mode', 'error');
    }
}

// Turn fan ON
async function turnFanOn() {
    try {
        const response = await fetch('/api/fan/command', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: 'on'})
        });
        const data = await response.json();
        if (data.status === 'success') {
            showAlert('✓ Fan turned ON', 'success');
            updateFanStatus();
        } else {
            showAlert(`Error: ${data.message}`, 'error');
        }
    } catch (e) {
        showAlert('Failed to turn on fan', 'error');
    }
}

// Turn fan OFF
async function turnFanOff() {
    try {
        const response = await fetch('/api/fan/command', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: 'off'})
        });
        const data = await response.json();
        if (data.status === 'success') {
            showAlert('✓ Fan turned OFF', 'success');
            updateFanStatus();
        } else {
            showAlert(`Error: ${data.message}`, 'error');
        }
    } catch (e) {
        showAlert('Failed to turn off fan', 'error');
    }
}

// Auto-refresh sensor data every 5 seconds (fallback for WebSocket)
function startAutoRefresh() {
    setInterval(updateSensorData, 5000);
}

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initial sensor data load
    if (document.getElementById('tempValue')) {
        updateSensorData();
        updateFanStatus();  // Load initial fan status
        // Try WebSocket first, falls back to polling if not available
        initializeWebSocket();
        // Refresh fan status every 5 seconds
        setInterval(updateFanStatus, 5000);
    }
    
    // Close modal on outside click
    window.addEventListener('click', function(event) {
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            if (event.target === modal) {
                modal.classList.remove('show');
            }
        });
    });
});
