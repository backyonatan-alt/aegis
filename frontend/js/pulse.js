// =============================================
// GLOBAL ANXIETY PULSE
// =============================================

// Pulse state
const pulseState = {
    countries: [],
    currentCountryIndex: 0,
    rotationInterval: null,
};

// Format surge percentage
function formatSurge(surge) {
    if (surge === null || surge === undefined || surge === 0) return '--%';
    const percent = Math.round((surge - 1) * 100);
    if (percent >= 0) {
        return `+${percent}%`;
    }
    return `${percent}%`;
}

// Get surge color class based on value
function getSurgeClass(surge) {
    if (surge >= 3.0) return 'surging';
    if (surge >= 2.0) return 'high';
    if (surge >= 1.5) return 'elevated';
    return 'positive';
}

// Animate number counter
function animateCounter(element, targetValue, duration = 500) {
    const startValue = parseInt(element.textContent.replace(/,/g, '')) || 0;
    const startTime = performance.now();

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);

        // Ease out
        const easeProgress = 1 - Math.pow(1 - progress, 3);
        const currentValue = Math.round(startValue + (targetValue - startValue) * easeProgress);

        element.textContent = currentValue.toLocaleString();

        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }

    requestAnimationFrame(update);
}

// Rotate to next country
function rotateCountry() {
    if (pulseState.countries.length === 0) return;

    const flagEl = document.getElementById('pulseRotatingFlag');
    const surgeEl = document.getElementById('pulseRotatingSurge');
    const container = document.querySelector('.pulse-rotating');

    if (!flagEl || !surgeEl || !container) return;

    // Fade out
    container.classList.add('fade-out');

    setTimeout(() => {
        // Move to next country
        pulseState.currentCountryIndex = (pulseState.currentCountryIndex + 1) % pulseState.countries.length;
        const country = pulseState.countries[pulseState.currentCountryIndex];

        // Update content
        flagEl.textContent = country.flag;
        surgeEl.textContent = formatSurge(country.surge);
        surgeEl.className = 'pulse-surge ' + getSurgeClass(country.surge);

        // Fade in
        container.classList.remove('fade-out');
    }, 300);
}

// Start country rotation
function startRotation() {
    if (pulseState.rotationInterval) {
        clearInterval(pulseState.rotationInterval);
    }
    pulseState.rotationInterval = setInterval(rotateCountry, 3000);
}

// Stop country rotation
function stopRotation() {
    if (pulseState.rotationInterval) {
        clearInterval(pulseState.rotationInterval);
        pulseState.rotationInterval = null;
    }
}

// Render pulse data
function renderPulse(pulseData) {
    if (!pulseData) {
        console.log('No pulse data available');
        return;
    }

    // Watching count
    const watchingEl = document.getElementById('pulseWatching');
    if (watchingEl && pulseData.watching_now !== undefined) {
        animateCounter(watchingEl, pulseData.watching_now);
    }

    // Activity multiplier and level
    const multiplierEl = document.getElementById('pulseMultiplier');
    const levelEl = document.getElementById('pulseLevel');
    const activityContainer = document.querySelector('.pulse-activity');

    if (multiplierEl && pulseData.activity_multiplier !== undefined) {
        multiplierEl.textContent = pulseData.activity_multiplier + 'x';
    }

    if (levelEl && pulseData.activity_level) {
        levelEl.textContent = pulseData.activity_level;
    }

    if (activityContainer && pulseData.activity_level) {
        // Remove old level classes
        activityContainer.classList.remove('normal', 'elevated', 'high', 'surging');
        // Add current level class
        activityContainer.classList.add(pulseData.activity_level);
    }

    // Israel surge
    const israelEl = document.getElementById('pulseIsrael');
    if (israelEl && pulseData.israel) {
        israelEl.textContent = formatSurge(pulseData.israel.surge);
        israelEl.className = 'pulse-surge ' + getSurgeClass(pulseData.israel.surge);
    }

    // Rotating countries (exclude Israel, it's shown separately)
    const countries = (pulseData.countries || []).filter(c => c.cc !== 'IL');

    if (countries.length > 0) {
        pulseState.countries = countries;

        // Initialize first country if not rotating yet
        const flagEl = document.getElementById('pulseRotatingFlag');
        const surgeEl = document.getElementById('pulseRotatingSurge');

        if (flagEl && surgeEl) {
            // Reset to first country on data refresh
            pulseState.currentCountryIndex = 0;
            const country = countries[0];
            flagEl.textContent = country.flag;
            surgeEl.textContent = formatSurge(country.surge);
            surgeEl.className = 'pulse-surge ' + getSurgeClass(country.surge);
        }

        // Start rotation if not already running
        if (!pulseState.rotationInterval) {
            startRotation();
        }
    } else {
        // No countries to rotate - show placeholder
        stopRotation();
        const flagEl = document.getElementById('pulseRotatingFlag');
        const surgeEl = document.getElementById('pulseRotatingSurge');
        if (flagEl) flagEl.textContent = '🌍';
        if (surgeEl) {
            surgeEl.textContent = '--%';
            surgeEl.className = 'pulse-surge';
        }
    }
}

// Make functions available globally
window.renderPulse = renderPulse;
window.startRotation = startRotation;
window.stopRotation = stopRotation;
