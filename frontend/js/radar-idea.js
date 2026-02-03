// Radar Idea Feature
// Collects user ideas for what they would track with their own radar

(function() {
    const STORAGE_KEY = 'radarIdeaSubmitted';

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

        // Prepare data for backend
        const payload = {
            idea: idea,
            timestamp: new Date().toISOString(),
            // Backend can add: IP, country, etc.
        };

        // TODO: Your friend will replace this with actual API call
        // Example:
        // fetch('/api/radar-ideas', {
        //     method: 'POST',
        //     headers: { 'Content-Type': 'application/json' },
        //     body: JSON.stringify(payload)
        // });

        console.log('Radar idea submitted:', payload);

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
