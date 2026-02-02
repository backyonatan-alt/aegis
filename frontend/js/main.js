// =============================================
// MAIN CONTROLLER
// =============================================

// Strike active flag — set to true when a strike is confirmed
const STRIKE_ACTIVE = true;

function activateStrikeMode() {
    const overlay = document.getElementById('strikeOverlay');
    const banner = document.getElementById('strikeBanner');
    const strikeTime = document.getElementById('strikeTime');

    if (overlay) overlay.classList.add('active');
    if (banner) banner.classList.add('active');
    if (strikeTime) {
        strikeTime.textContent = new Date().toLocaleString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric',
            hour: '2-digit', minute: '2-digit', hour12: true
        });
    }

    // Override the gauge to show 100%
    const gaugeValue = document.getElementById('gaugeValue');
    const statusLabel = document.getElementById('statusLabel');
    if (gaugeValue) {
        gaugeValue.textContent = 'ACTIVE';
        gaugeValue.className = 'gauge-value orange';
    }
    if (statusLabel) {
        statusLabel.textContent = 'Strike Detected';
        statusLabel.className = 'status-label high';
    }

    // Fill gauge to max
    const gaugeFill = document.getElementById('gaugeFill');
    if (gaugeFill) {
        gaugeFill.style.strokeDashoffset = '0';
        gaugeFill.setAttribute('stroke', 'url(#gradRed)');
    }

    // Update page title
    document.title = 'STRIKE DETECTED — StrikeRadar';
}

function dismissStrikeOverlay() {
    const overlay = document.getElementById('strikeOverlay');
    if (overlay) overlay.classList.remove('active');
}

// Load and display data from data.json
async function loadData() {
    const data = await getData();

    if (data) {
        initChart(data.total_risk?.history); // Pass restructured history
        displayData(data);
    }

    // Re-apply strike mode after data display (so it overrides gauge values)
    if (STRIKE_ACTIVE) {
        activateStrikeMode();
    }
}

async function forceRefresh() {
    showToast('🔄 Refreshing data...');
    await loadData();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    if (STRIKE_ACTIVE) {
        activateStrikeMode();
    }

    startCountdown();
    await loadData(); // Single source of truth

    // Update every 5 minutes
    setInterval(loadData, 5 * 60 * 1000);

    // Online/offline handlers
    window.addEventListener('online', () => {
        showToast('✅ Connection restored');
        loadData();
    });
    window.addEventListener('offline', updateOnlineStatus);
});
