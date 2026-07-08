"""Discovery module — privacy-safe guest sessions + analytics event sink.

First slice of the Discovery / Recommendation / Ads rescue
(``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §3/§8). Provides the first-party
anonymous discovery session (coarse, allowlisted signals only — never PII) and the
``POST /discovery/events`` analytics sink that ad-funded surfaces and recommendation
rails call. Recommendation/ranking (S2) reads ``discovery_sessions.coarse_tags`` and
emits impression events through this module.
"""
