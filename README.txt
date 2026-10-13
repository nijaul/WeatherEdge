WeatherEdge AI v0.2 — Kalshi-first weather contract research

RUN:
1. Extract the ZIP archive.
2. Install Python 3.10+ if it is not already installed.
3. Double-click START_WEATHEREDGE.cmd.
4. A local dashboard opens in your default browser.

WHAT IS IMPLEMENTED:
- Live public Kalshi /events catalog scanning with up to 8 pages.
- Weather-contract discovery based on event/market metadata.
- YES/NO bid and ask prices and contract inspection.
- Conservative recognition of certain high-temperature thresholds,
  explicit target dates and a set of supported US cities.
- Automatic NWS point/hourly forecast requests for matched cities.
- Preliminary Gaussian probability estimates for matching ranges.
- Read-only forecast-vs-market comparisons and uncertainty warnings.
- No Kalshi credentials, order placement or trading features.

IMPORTANT LIMITATIONS:
- Kalshi's event catalog is paginated. This version scans up to eight
  open-event pages, not necessarily every live weather market.
- Weather identification and contract parsing are conservative heuristics.
- The exact Kalshi settlement station, rounding and observation rules
  are NOT automatically verified.
- NWS city-point forecast maxima may not equal official station highs.
- The normal-error sigma is a heuristic, NOT historical calibration.
- No neural network is trained and NO signal is validated for betting.
- The app may show no automatic comparisons if live contract titles
  do not expose a safely recognizable city, date and temperature range.
- Public API formats and availability can change.
- No external AI service or API key is needed.
- Python standard library only; localhost-only HTTP server.

This package was syntax-checked but not executed against the live
Kalshi/NWS endpoints or on a Windows desktop in the authoring environment.
