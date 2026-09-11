// ─────────────────────────────────────────────────────────────────
//  Shuriken — Fetch OTP from notifications service
//
//  Uses Maestro's built-in http.post() client (okhttp3 wrapper).
//  Stores the 4-digit OTP code into output.OTP_CODE and individual
//  digits into output.OTP_DIGIT_1 .. output.OTP_DIGIT_4 for entry.
//
//  Expects env: AUTH_PHONE, OTP_BRAND_CODE, OTP_API_PREFIX, OTP_ENV
//  Falls back to Brand Three UAT defaults if not set.
// ─────────────────────────────────────────────────────────────────

// ── Configuration (with defaults for Brand Three UAT) ──
var phone      = AUTH_PHONE      || '5555550100';
var brandCode  = OTP_BRAND_CODE  || 'B3';
var apiPrefix  = OTP_API_PREFIX  || 'b3-api';
var env        = OTP_ENV         || 'uat';

var url = 'https://notifications-service-v0.' + apiPrefix + '.' + env + '.staging.example/retrieveOTP/brand/' + brandCode + '/otp';
var body = JSON.stringify({ countryCode: '1', number: phone });

console.log('OTP API URL: ' + url);
console.log('OTP Request body: ' + body);

// ── Retry loop (up to 5 attempts, 3s delay) ──
var otp = null;
var maxRetries = 5;
var attempt = 0;

while (attempt < maxRetries && !otp) {
    attempt++;
    console.log('OTP fetch attempt ' + attempt + ' of ' + maxRetries);

    try {
        var response = http.post(url, {
            headers: {
                'Content-Type': 'application/json',
                'accept': 'application/json'
            },
            body: body
        });

        console.log('HTTP status: ' + response.status);
        console.log('Response body: ' + response.body);

        if (response.status === 200 || response.status === 201) {
            var data = json(response.body);
            otp = data.otp || data.code || data.OTP || data.Code || null;
        }
    } catch (e) {
        console.log('Error on attempt ' + attempt + ': ' + e);
    }

    if (!otp && attempt < maxRetries) {
        console.log('Waiting 3s before retry...');
        // Maestro JS doesn't have setTimeout/sleep, so we use a busy-wait
        var waitUntil = new Date().getTime() + 3000;
        while (new Date().getTime() < waitUntil) {
            // busy wait
        }
    }
}

if (!otp) {
    throw new Error('Failed to retrieve OTP after ' + maxRetries + ' attempts for phone: ' + phone);
}

// ── Store the OTP for the Maestro flow ──
var otpStr = String(otp);
console.log('OTP retrieved successfully: ' + otpStr + ' (' + otpStr.length + ' digits)');

output.OTP_CODE = otpStr;
