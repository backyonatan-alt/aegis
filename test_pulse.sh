#!/bin/bash
# Simple Pulse Data Flow Test

echo "=== PULSE DATA FLOW TEST ==="
echo ""

API_URL="${1:-http://localhost:8787/data.json}"

echo "Testing: $API_URL"
echo ""

# Test 1: Basic fetch
echo "1. Fetching data..."
RESPONSE=$(curl -s "$API_URL")

if echo "$RESPONSE" | grep -q '"pulse"'; then
    echo "   ✅ Pulse data present"
else
    echo "   ❌ No pulse data found"
    echo "   Response: $RESPONSE"
    exit 1
fi

# Test 2: Check watching_now
WATCHING=$(echo "$RESPONSE" | grep -o '"watching_now":[0-9]*' | cut -d: -f2)
echo "   👁️  watching_now: $WATCHING"

# Test 3: Check activity
MULTIPLIER=$(echo "$RESPONSE" | grep -o '"activity_multiplier":[0-9.]*' | cut -d: -f2)
LEVEL=$(echo "$RESPONSE" | grep -o '"activity_level":"[^"]*"' | cut -d: -f2 | tr -d '"')
echo "   ⚡ activity: ${MULTIPLIER}x $LEVEL"

# Test 4: Check Israel
ISRAEL_SURGE=$(echo "$RESPONSE" | grep -o '"israel":{[^}]*}' | grep -o '"surge":[0-9.]*' | cut -d: -f2)
echo "   🇮🇱 israel surge: $ISRAEL_SURGE"

# Test 5: Simulate multiple visitors
echo ""
echo "2. Simulating 5 visitors from different countries..."
for CC in IL US DE GB IR; do
    curl -s -H "cf-ipcountry: $CC" "$API_URL" > /dev/null
    echo "   → Visitor from $CC"
done

# Test 6: Check updated count
echo ""
echo "3. Checking updated stats..."
RESPONSE=$(curl -s "$API_URL")
WATCHING=$(echo "$RESPONSE" | grep -o '"watching_now":[0-9]*' | cut -d: -f2)
echo "   👁️  watching_now: $WATCHING"

echo ""
echo "=== TEST COMPLETE ==="
