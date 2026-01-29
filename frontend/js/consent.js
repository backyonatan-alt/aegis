// Cookie Consent Manager
// Manages GDPR & Israeli PPL compliant consent for Google Analytics and Google AdSense.

(function () {
    'use strict';

    var CONSENT_KEY = 'cookie_consent';
    var GA_ID = 'G-JXY7DKJKVK';
    var ADSENSE_ID = 'ca-pub-8033751083492488';

    function getConsent() {
        try {
            return localStorage.getItem(CONSENT_KEY);
        } catch (e) {
            return null;
        }
    }

    function setConsent(value) {
        try {
            localStorage.setItem(CONSENT_KEY, value);
        } catch (e) {
            // Storage unavailable — consent lives only for this page load
        }
    }

    function showBanner() {
        var banner = document.getElementById('cookieConsent');
        if (banner) banner.style.display = 'flex';
    }

    function hideBanner() {
        var banner = document.getElementById('cookieConsent');
        if (banner) banner.style.display = 'none';
    }

    function loadAnalytics() {
        // Avoid loading twice
        if (document.getElementById('ga-script')) return;

        // Google Analytics
        var gaScript = document.createElement('script');
        gaScript.id = 'ga-script';
        gaScript.async = true;
        gaScript.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
        document.head.appendChild(gaScript);

        gaScript.onload = function () {
            window.dataLayer = window.dataLayer || [];
            function gtag() { window.dataLayer.push(arguments); }
            window.gtag = gtag;
            gtag('js', new Date());
            gtag('config', GA_ID);

            // Custom event tracking helper
            window.trackEvent = function (action, category, label, value) {
                gtag('event', action, {
                    'event_category': category,
                    'event_label': label,
                    'value': value
                });
            };

            // Track page engagement
            var sessionStartTime = Date.now();
            window.addEventListener('beforeunload', function () {
                var sessionDuration = Math.round((Date.now() - sessionStartTime) / 1000);
                window.trackEvent('session_end', 'engagement', 'session_duration', sessionDuration);
            });

            // Track scroll depth
            var scrollTracked = { 25: false, 50: false, 75: false, 100: false };
            window.addEventListener('scroll', function () {
                var scrollPercent = Math.round((window.scrollY / (document.body.scrollHeight - window.innerHeight)) * 100);
                [25, 50, 75, 100].forEach(function (threshold) {
                    if (scrollPercent >= threshold && !scrollTracked[threshold]) {
                        scrollTracked[threshold] = true;
                        window.trackEvent('scroll_depth', 'engagement', 'scroll_' + threshold, threshold);
                    }
                });
            });
        };

        // Google AdSense
        if (!document.getElementById('adsense-script')) {
            var adScript = document.createElement('script');
            adScript.id = 'adsense-script';
            adScript.async = true;
            adScript.crossOrigin = 'anonymous';
            adScript.src = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=' + ADSENSE_ID;
            document.head.appendChild(adScript);
        }
    }

    // Public API
    window.acceptConsent = function () {
        setConsent('accepted');
        hideBanner();
        loadAnalytics();
    };

    window.rejectConsent = function () {
        setConsent('rejected');
        hideBanner();
    };

    window.revokeConsent = function () {
        try {
            localStorage.removeItem(CONSENT_KEY);
        } catch (e) {}
        showBanner();
    };

    window.openCookieSettings = function () {
        showBanner();
    };

    // Initialize on DOM ready
    function init() {
        var consent = getConsent();
        if (consent === 'accepted') {
            loadAnalytics();
        } else if (consent === 'rejected') {
            // Do nothing — respect the user's choice
        } else {
            showBanner();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
