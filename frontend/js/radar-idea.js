// Radar Idea Feature
// Collects user ideas for what they would track with their own radar

(function() {
    const STORAGE_KEY = 'radarIdeaSubmitted';
    const API_URL = 'https://api.usstrikeradar.com/api/radar-ideas';

    // Check if user already submitted
    function hasSubmitted() {
        return localStorage.getItem(STORAGE_KEY) === 'true';
    }

    // Hide the card if already submitted
    function initRadarIdea() {
        const card = document.getElementById('radarIdeaCard');
        if (!card) return;

        if (hasSubmitted()) {
            card.classList.add('hidden');
        }

        // Add enter key support
        const input = document.getElementById('radarIdeaInput');
        if (input) {
            input.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    submitRadarIdea();
                }
            });
        }
    }

    // Submit handler
    window.submitRadarIdea = function() {
        const input = document.getElementById('radarIdeaInput');
        const form = document.getElementById('radarIdeaForm');
        const thanks = document.getElementById('radarIdeaThanks');
        const card = document.getElementById('radarIdeaCard');
        const submitBtn = document.getElementById('radarIdeaSubmit');

        const idea = input.value.trim();

        if (!idea) {
            input.focus();
            return;
        }

        // Disable button while "submitting"
        submitBtn.disabled = true;
        submitBtn.textContent = '...';

        // Submit to backend
        fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ idea: idea })
        }).catch(function(err) {
            console.log('Error submitting idea:', err.message);
        });

        // Mark as submitted
        localStorage.setItem(STORAGE_KEY, 'true');

        // Show thank you message
        form.style.display = 'none';
        thanks.style.display = 'flex';

        // Fade out the card after 2 seconds
        setTimeout(function() {
            card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
            card.style.opacity = '0';
            card.style.transform = 'translateY(-10px)';

            setTimeout(function() {
                card.classList.add('hidden');
            }, 500);
        }, 2000);
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initRadarIdea);
    } else {
        initRadarIdea();
    }
})();
