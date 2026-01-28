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
        content: `<div class="modal-body" id="infoBody"><strong>Disclaimer</strong><br><br>This is an <strong>experimental project</strong> for informational purposes only.<br><br><strong>NOT:</strong><br>• Official intelligence<br>• Verified predictions<br>• Basis for decisions<br><br><strong>Data Sources</strong><br>• BBC World & Al Jazeera<br>• OpenSky Network<br>• Polymarket<br>• OpenWeatherMap<br><br><strong>Limitations</strong><br>Cannot account for classified intel or diplomatic activity. One data point among many.<br><br><em>Stay informed. Think critically.</em></div>`
    },
    calculation: {
        title: 'How We Calculate Risk',
        content: `<strong>Total Risk = Weighted Sum of 6 Signals</strong><br><br>
        <strong>News Intel (25%):</strong> Breaking news with critical keywords increases risk.<br><br>
        <strong>Civil Aviation (20%):</strong> Fewer flights over Iran = airlines avoiding = higher risk.<br><br>
        <strong>Military Tankers (15%):</strong> More US tankers in the region = higher risk.<br><br>
        <strong>Market Odds (20%):</strong> Prediction market betting odds for strike within 7 days.<br><br>
        <strong>Pentagon Activity (10%):</strong> Unusual late-night activity near Pentagon = higher risk.<br><br>
        <strong>Weather (10%):</strong> Clear skies in Tehran = favorable for operations = higher risk.<br><br>
        <strong>Escalation Multiplier:</strong> If 3+ signals are elevated, total gets a 15% boost.<br><br>
        <strong>Risk Levels:</strong><br>
        • 0-30% = Low<br>
        • 31-60% = Elevated<br>
        • 61-85% = High<br>
        • 86-100% = Imminent`
    },
    news: `<strong>News Intelligence</strong><br><br>
        Scans BBC World and Al Jazeera for Iran-related news.<br><br>
        <strong>What we look for:</strong> Headlines containing "strike", "attack", "military", "missile", "war", "imminent"<br><br>
        <strong>How it works:</strong> More critical articles = higher risk. The ratio of alarming headlines to total coverage drives the score.<br><br>
        <strong>Weight:</strong> 25% of total risk`,
    flight: `<strong>Civil Aviation</strong><br><br>
        Tracks commercial flights over Iranian airspace via OpenSky Network.<br><br>
        <strong>Why it matters:</strong> Airlines avoid conflict zones. When flights drop, it often signals that carriers have intelligence suggesting danger.<br><br>
        <strong>How it works:</strong> Fewer aircraft = higher risk. Normal traffic (~100+ planes) = low risk.<br><br>
        <strong>Weight:</strong> 20% of total risk`,
    tanker: `<strong>Military Tankers</strong><br><br>
        Monitors US Air Force refueling aircraft in the Middle East.<br><br>
        <strong>Why it matters:</strong> Tankers (KC-135, KC-46) enable fighters and bombers to operate far from base. A surge in tanker activity often precedes military operations.<br><br>
        <strong>How it works:</strong> More tankers detected = higher risk.<br><br>
        <strong>Weight:</strong> 15% of total risk`,
    pentagon: `<strong>Pentagon Activity</strong><br><br>
        Monitors activity patterns near the Pentagon.<br><br>
        <strong>Why it matters:</strong> Unusual late-night or weekend activity can indicate crisis planning sessions.<br><br>
        <strong>How it works:</strong> Normal business hours = low risk. Elevated activity at odd hours = higher risk.<br><br>
        <strong>Weight:</strong> 10% of total risk`,
    polymarket: `<strong>Prediction Markets</strong><br><br>
        Real-money betting odds on "US or Israel strike Iran" within 7 days.<br><br>
        <strong>Source:</strong> Polymarket<br><br>
        <strong>Why it matters:</strong> When people bet real money, they research carefully. Market odds aggregate the wisdom of thousands of informed traders.<br><br>
        <strong>Weight:</strong> 20% of total risk`,
    weather: `<strong>Weather Conditions</strong><br><br>
        Current weather in Tehran, Iran.<br><br>
        <strong>Why it matters:</strong> Military operations favor clear skies for visibility and precision targeting. Poor weather provides natural cover.<br><br>
        <strong>How it works:</strong> Clear skies = higher risk. Cloudy/poor visibility = lower risk.<br><br>
        <strong>Weight:</strong> 10% of total risk`
};

const ALERT_COOLDOWN = 60 * 60 * 1000; // 1 hour between alerts
