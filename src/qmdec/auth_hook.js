var pattern = "71 71 6d 75 73 69 63 5f 6b 65 79 3d";
var heapRanges = Process.enumerateRanges('r--');
var found = false;

for (var i = 0; i < heapRanges.length && !found; i++) {
    var range = heapRanges[i];
    if (range.size > 50 * 1024 * 1024) continue;
    try {
        var results = Memory.scanSync(range.base, range.size, pattern);
        if (results.length > 0) {
            var r = results[0];
            try {
                var cookie = r.address.readUtf8String(512);
                var end = cookie.indexOf('\n');
                if (end > 0) cookie = cookie.substring(0, end);
                end = cookie.indexOf('\r');
                if (end > 0) cookie = cookie.substring(0, end);
                send({type: "cookie", value: cookie.trim()});
                found = true;
            } catch(e) {}
        }
    } catch(e) {}
}

if (!found) {
    send({type: "error", value: "cookie not found in QQMusic process memory"});
}
