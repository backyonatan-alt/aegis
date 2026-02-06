// =============================================
// DATA FETCHING
// =============================================

const DATA_URL = 'https://api.usstrikeradar.com/api/data';
const PULSE_URL = 'https://api.usstrikeradar.com/api/pulse';

async function getData() {
    try {
        const res = await fetch(DATA_URL);
        if (res.ok) {
            return await res.json();
        }
    } catch (e) {
        console.log('Error reading data:', e.message);
    }
    
    // Fallback if data.json can't be read - use new structure
    return {
        news: { risk: 3, detail: 'Data unavailable', history: [], raw_data: {} },
        flight: { risk: 5, detail: 'Data unavailable', history: [], raw_data: {} },
        tanker: { risk: 1, detail: 'Data unavailable', history: [], raw_data: {} },
        weather: { risk: 0, detail: 'Data unavailable', history: [], raw_data: {} },
        polymarket: { risk: 10, detail: 'Data unavailable', history: [], raw_data: {} },
        pentagon: { risk: 10, detail: 'Data unavailable', history: [], raw_data: {} },
        total_risk: { risk: 20, history: [], elevated_count: 0 },
        last_updated: new Date().toISOString()
    };
}

// Log visit and get pulse stats (Global Anxiety Pulse)
async function logPulseVisit() {
    try {
        const res = await fetch(PULSE_URL, { method: 'POST' });
        if (res.ok) {
            return await res.json();
        }
    } catch (e) {
        console.log('Error logging pulse:', e.message);
    }
    return null;
}

// Get pulse stats without logging a visit
async function getPulseStats() {
    try {
        const res = await fetch(PULSE_URL);
        if (res.ok) {
            return await res.json();
        }
    } catch (e) {
        console.log('Error fetching pulse:', e.message);
    }
    return null;
}
