// =============================================
// DATA FETCHING
// =============================================

// Read data from Cloudflare Worker (R2-backed, CDN-cached)
// Always fetches from production endpoint — works on preview deploys via CORS
const DATA_URL = 'https://usstrikeradar.com/api/data.json';

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
