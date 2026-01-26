// =============================================
// CONFIG & CONSTANTS
// =============================================

const state = {
    trendLabels: [],
    trendData: [],
    signalHistory: {
        news: [],
        flight: [],
        tanker: [],
        pentagon: [],
        polymarket: [],
        weather: []
    }
};

const KEYWORDS = ['retaliation', 'strike', 'attack', 'escalation', 'military', 'threat', 'imminent', 'missile', 'nuclear', 'war'];

const INFO_CONTENT = {
    about: {
        title: 'About Strike Radar',
        content: `<div class="modal-body" id="infoBody"><strong>⚠️ Disclaimer</strong><br><br>This is an <strong>experimental project</strong> for informational purposes only.<br><br><strong>NOT:</strong><br>• Official intelligence<br>• Verified predictions<br>• Basis for decisions<br><br><strong>Data Sources</strong><br>• NewsData.io<br>• GDELT Project<br>• Wikipedia<br>• Aviationstack<br>• OpenWeatherMap<br><br><strong>Limitations</strong><br>Cannot account for classified intel or diplomatic activity. One data point among many.<br><br><em>Stay informed. Think critically.</em></div>`
    },
    calculation: {
        title: 'How We Calculate Risk',
        content: `<strong>Total Risk = Sum of 6 Signals</strong><br><br>
        📰 <strong>News Intel (30%):</strong> Real-time news from Reuters, BBC, NYT, Al Jazeera. Critical keywords like "strike", "attack", "imminent".<br><br>
        ✈️ <strong>Civil Aviation (35%):</strong> Aircraft over Iran airspace. Fewer = airlines avoiding = higher risk.<br><br>
        🛩️ <strong>Military Tankers (15%):</strong> KC-135 refueling tankers detected in Middle East via ADS-B.<br><br>
        📊 <strong>Market Odds (10%):</strong> Polymarket prediction odds for "US strikes Iran" events.<br><br>
        🍕 <strong>Pentagon Pizza Meter (10%):</strong> Pizza delivery busyness near Pentagon. Late-night/weekend spikes = potential overtime work.<br><br>
        ☀️ <strong>Op. Conditions (5%):</strong> Clear weather in Tehran = favorable for operations.<br><br>
        <strong>Escalation Multiplier:</strong> If 3+ signals are elevated, total gets a 15% boost.<br><br>
        <strong>Risk Levels:</strong><br>
        • 0-30% = Low Risk<br>
        • 31-60% = Elevated<br>
        • 61-85% = High Risk<br>
        • 86-100% = Imminent`
    },
    news: `<strong>News Intelligence Monitor</strong><br><br>
        Analyzes breaking news from BBC World and Al Jazeera for Iran conflict developments.<br><br>
        <strong>Alert triggers:</strong> Headlines with keywords like "strike", "retaliation", "imminent"<br>
        <strong>Max contribution:</strong> 30% of total risk<br>
        <strong>Update frequency:</strong> Every 30 minutes via server`,
    flight: `<strong>Civil Aviation Monitor</strong><br><br>
        Tracks commercial aircraft over Iranian airspace using OpenSky Network.<br><br>
        <strong>Logic:</strong> Fewer flights = Higher risk (airlines avoiding area)<br>
        <strong>Max contribution:</strong> 35% of total risk<br>
        <strong>Data source:</strong> OpenSky Network API`,
    tanker: `<strong>Military Tanker Activity</strong><br><br>
        Monitors US Air Force refueling tankers (KC-135, KC-10, KC-46) in the Middle East.<br><br>
        <strong>Significance:</strong> Tanker presence enables extended combat operations<br>
        <strong>Max contribution:</strong> 15% of total risk<br>
        <strong>Region:</strong> 20°-45°N, 30°-65°E`,
    pentagon: `<strong>Pentagon Pizza Meter</strong><br><br>
        Monitors pizza delivery activity near the Pentagon as a proxy for late-night military activity.<br><br>
        <strong>Theory:</strong> Unusual late-night orders may indicate crisis planning<br>
        <strong>Max contribution:</strong> 10% of total risk<br>
        <strong>Update frequency:</strong> Every 30 minutes`,
    polymarket: `<strong>Prediction Market Odds</strong><br><br>
        Real-money betting markets on Iran strike probability.<br><br>
        <strong>Source:</strong> Polymarket (decentralized prediction market)<br>
        <strong>Max contribution:</strong> 10% of total risk<br>
        <strong>Why it matters:</strong> Aggregates wisdom of thousands of traders with money at stake`,
    weather: `<strong>Operation Conditions</strong><br><br>
        Weather conditions in Tehran that could affect military operations.<br><br>
        <strong>Favorable:</strong> Clear skies, good visibility (higher risk)<br>
        <strong>Max contribution:</strong> 5% of total risk<br>
        <strong>Source:</strong> OpenWeatherMap API`
};

const ALERT_COOLDOWN = 60 * 60 * 1000; // 1 hour between alerts
