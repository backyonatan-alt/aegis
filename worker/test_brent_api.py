#!/usr/bin/env python3
"""Test script for Alpha Vantage BRENT API.

Run this locally to verify the API works before deploying:
    python3 test_brent_api.py
"""

import json
import urllib.request

API_KEY = "7SOTPD3URT6JO0UX"
URL = f"https://www.alphavantage.co/query?function=BRENT&interval=daily&apikey={API_KEY}"

print(f"Testing Alpha Vantage BRENT API...")
print(f"URL: {URL}\n")

try:
    with urllib.request.urlopen(URL, timeout=10) as response:
        data = json.loads(response.read().decode())

        print("=" * 50)
        print("RAW RESPONSE (first 1000 chars):")
        print("=" * 50)
        print(json.dumps(data, indent=2)[:1000])
        print("\n")

        # Check for errors
        if "Error Message" in data:
            print(f"❌ API ERROR: {data['Error Message']}")
        elif "Note" in data:
            print(f"⚠️ API NOTE (rate limit?): {data['Note']}")
        elif "Information" in data:
            print(f"ℹ️ API INFO: {data['Information']}")
        elif "data" in data:
            print("✅ SUCCESS! Found 'data' array")
            print(f"   Total data points: {len(data['data'])}")

            if data['data']:
                print("\n   First 3 data points:")
                for item in data['data'][:3]:
                    print(f"   - date: {item.get('date')}, value: {item.get('value')}")

                # Test our parsing logic
                prices = []
                for item in data['data'][:7]:
                    value = item.get('value')
                    if value and value != ".":
                        prices.append(float(value))

                if len(prices) >= 2:
                    current = prices[0]
                    avg = sum(prices) / len(prices)
                    change = (current - avg) / avg * 100
                    print(f"\n   Current price: ${current:.2f}")
                    print(f"   7-day average: ${avg:.2f}")
                    print(f"   Change: {change:+.2f}%")
                    print("\n✅ Parsing logic works correctly!")
        else:
            print("❌ UNEXPECTED RESPONSE FORMAT")
            print("   Keys found:", list(data.keys()))

except Exception as e:
    print(f"❌ REQUEST FAILED: {e}")
