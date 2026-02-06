// =============================================
// MAIN CONTROLLER
// =============================================

// Load and display data from data.json
async function loadData() {
    const data = await getData();

    if (data) {
        initChart(data.total_risk?.history); // Pass restructured history
        displayData(data);
    }
}

// Load pulse data (Global Anxiety Pulse)
async function loadPulse(logVisit = false) {
    const pulse = logVisit ? await logPulseVisit() : await getPulseStats();
    if (pulse && typeof renderPulse === 'function') {
        renderPulse(pulse);
    }
}

async function forceRefresh() {
    showToast('🔄 Refreshing data...');
    await loadData();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    startCountdown();
    await loadData(); // Single source of truth

    // Log visit and load pulse data
    loadPulse(true);

    // Update data every 5 minutes
    setInterval(loadData, 5 * 60 * 1000);

    // Update pulse every 30 seconds (without logging new visit)
    setInterval(() => loadPulse(false), 30 * 1000);

    // Online/offline handlers
    window.addEventListener('online', () => {
        showToast('✅ Connection restored');
        loadData();
        loadPulse(false);
    });
    window.addEventListener('offline', updateOnlineStatus);
});
