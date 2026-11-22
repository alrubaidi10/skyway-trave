import base64
import json
import os
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import FastAPI, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import get_db_connection, init_db

init_db()

app = FastAPI(
    title="SkyWay Travel API",
    version="2.4.1",
    description="Commercial Flight, Hotel & Booking Management API for SkyWay Travel.",
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


def make_predictable_token(user_id: int, username: str, role: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
    payload_dict = {"sub": user_id, "username": username, "role": role, "iat": 1763800000}
    payload = base64.urlsafe_b64encode(json.dumps(payload_dict).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(f"skyway-sig-{user_id}-{username}".encode()).decode().rstrip("=")
    return f"{header}.{payload}.{sig}"


def current_username(request: Request) -> Optional[str]:
    token = request.cookies.get("session_id")
    if not token:
        return None
    parts = token.split(".")
    if len(parts) == 3:
        try:
            padded = parts[1] + "=" * (-len(parts[1]) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded).decode())
            return data.get("username")
        except Exception:
            return None
    return token


@app.middleware("http")
async def insecure_headers_and_cors_middleware(request: Request, call_next):
    if request.method == "OPTIONS" and request.url.path.startswith("/api/"):
        response = Response(status_code=204)
    else:
        response = await call_next(request)

    # Misconfigured server & technology disclosure headers
    response.headers["Server"] = "Apache/2.4.49 (Ubuntu)"
    response.headers["X-Powered-By"] = "PHP/8.1.2"
    response.headers["Content-Security-Policy"] = "default-src * 'unsafe-inline' 'unsafe-eval'"

    # Intentionally omit security headers if any framework added them
    for hdr in ("X-Frame-Options", "X-Content-Type-Options", "Strict-Transport-Security", "Referrer-Policy"):
        if hdr in response.headers:
            del response.headers[hdr]

    # Insecure CORS on /api/* endpoints
    if request.url.path.startswith("/api/"):
        origin = request.headers.get("origin") or "*"
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"

    return response


# ---------------------------------------------------------------------------
# Web Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = get_db_connection()
    flights = conn.execute("SELECT * FROM flights ORDER BY price ASC").fetchall()
    hotels = conn.execute("SELECT * FROM hotels ORDER BY rating DESC").fetchall()
    conn.close()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"flights": flights, "hotels": hotels, "current_user": current_username(request)},
    )


@app.get("/flights", response_class=HTMLResponse)
async def flights_page(request: Request):
    conn = get_db_connection()
    flights = conn.execute("SELECT * FROM flights ORDER BY id ASC").fetchall()
    conn.close()
    return templates.TemplateResponse(
        request,
        "flights.html",
        {"flights": flights, "destination": "", "sql_error": None, "current_user": current_username(request)},
    )


@app.get("/flights/search", response_class=HTMLResponse)
async def flights_search(request: Request, destination: str = ""):
    conn = get_db_connection()
    flights = []
    sql_error = None
    # Intentionally vulnerable raw SQL string concatenation (sandboxed against dummy SQLite)
    query = f"SELECT * FROM flights WHERE destination LIKE '%{destination}%' OR origin LIKE '%{destination}%'"
    try:
        flights = conn.execute(query).fetchall()
    except Exception as exc:
        sql_error = f"SQLite Error executing [{query}]:\n{exc}\n\n{traceback.format_exc()}"
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "flights.html",
        {
            "flights": flights,
            "destination": destination,
            "sql_error": sql_error,
            "current_user": current_username(request),
        },
    )


@app.get("/hotels", response_class=HTMLResponse)
async def hotels_page(request: Request):
    conn = get_db_connection()
    hotels = conn.execute("SELECT * FROM hotels ORDER BY rating DESC").fetchall()
    conn.close()
    return templates.TemplateResponse(
        request,
        "hotels.html",
        {"hotels": hotels, "current_user": current_username(request)},
    )


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    conn = get_db_connection()
    flights = []
    hotels = []
    if q:
        flights = conn.execute(
            "SELECT * FROM flights WHERE destination LIKE ? OR origin LIKE ? OR airline LIKE ?",
            (f"%{q}%", f"%{q}%", f"%{q}%"),
        ).fetchall()
        hotels = conn.execute(
            "SELECT * FROM hotels WHERE name LIKE ? OR city LIKE ? OR country LIKE ?",
            (f"%{q}%", f"%{q}%", f"%{q}%"),
        ).fetchall()
    else:
        flights = conn.execute("SELECT * FROM flights LIMIT 4").fetchall()
        hotels = conn.execute("SELECT * FROM hotels LIMIT 4").fetchall()
    conn.close()
    return templates.TemplateResponse(
        request,
        "search.html",
        {"q": q, "flights": flights, "hotels": hotels, "current_user": current_username(request)},
    )


@app.get("/bookings", response_class=HTMLResponse)
async def bookings_page(request: Request, book_flight: Optional[int] = None):
    conn = get_db_connection()
    message = None
    if book_flight:
        flight = conn.execute("SELECT * FROM flights WHERE id = ?", (book_flight,)).fetchone()
        if flight:
            uname = current_username(request) or "guest_traveler"
            new_ref = f"SW-{100000 + int(datetime.utcnow().timestamp()) % 899999}"
            conn.execute(
                "INSERT OR IGNORE INTO bookings (booking_ref, user_id, flight_id, passenger_name, passenger_email, status, total_price, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_ref,
                    1,
                    flight["id"],
                    uname,
                    f"{uname}@example.com",
                    "Confirmed",
                    flight["price"],
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()
            message = f"Flight {flight['flight_number']} booked! Reference: {new_ref}"

    bookings = conn.execute(
        """
        SELECT b.*, f.flight_number, f.origin, f.destination
        FROM bookings b
        JOIN flights f ON b.flight_id = f.id
        ORDER BY b.id DESC
        """
    ).fetchall()
    conn.close()
    return templates.TemplateResponse(
        request,
        "bookings.html",
        {"bookings": bookings, "message": message, "current_user": current_username(request)},
    )


@app.get("/booking/details", response_class=HTMLResponse)
async def booking_details(request: Request, ref: str = ""):
    if ref == "invalid" or not ref:
        try:
            raise ValueError(f"Invalid booking reference lookup: ref='{ref}' cannot be parsed by ItineraryEngine")
        except Exception:
            return PlainTextResponse(traceback.format_exc(), status_code=500)

    conn = get_db_connection()
    booking = conn.execute(
        """
        SELECT b.*, f.flight_number, f.airline, f.origin, f.destination, f.departure_time
        FROM bookings b
        JOIN flights f ON b.flight_id = f.id
        WHERE b.booking_ref = ?
        """,
        (ref,),
    ).fetchone()
    conn.close()

    if not booking:
        try:
            raise KeyError(f"Booking reference '{ref}' not found in SkyWay GDS ledger")
        except Exception:
            return PlainTextResponse(traceback.format_exc(), status_code=500)

    return templates.TemplateResponse(
        request,
        "booking_detail.html",
        {"booking": booking, "current_user": current_username(request)},
    )


@app.get("/support", response_class=HTMLResponse)
async def support_page(request: Request, msg: str = ""):
    return templates.TemplateResponse(
        request,
        "support.html",
        {"msg": msg, "submitted": False, "current_user": current_username(request)},
    )


@app.post("/support", response_class=HTMLResponse)
async def support_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO support_tickets (name, email, subject, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, email, subject, message, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()
    return templates.TemplateResponse(
        request,
        "support.html",
        {"msg": "", "submitted": True, "current_user": current_username(request)},
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None, "current_user": current_username(request)},
    )


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? AND password = ?",
        (username, password),
    ).fetchone()
    conn.close()

    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password.", "current_user": None},
            status_code=401,
        )

    token = make_predictable_token(user["id"], user["username"], user["role"])
    resp = RedirectResponse(url="/bookings", status_code=302)
    # Intentionally insecure cookies: no HttpOnly, no Secure, no SameSite
    resp.set_cookie(key="session_id", value=token, httponly=False, secure=False, samesite=None)
    resp.set_cookie(key="user_role", value=user["role"], httponly=False, secure=False, samesite=None)
    return resp


@app.get("/old-login")
async def old_login():
    return RedirectResponse(url="/login", status_code=302)


@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/", status_code=302)
    resp.delete_cookie("session_id")
    resp.delete_cookie("user_role")
    return resp


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(
        request,
        "register.html",
        {"error": None, "current_user": current_username(request)},
    )


@app.post("/register")
async def register_submit(
    request: Request,
    full_name: str = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    # Weak password policy: accepts any non-empty password (even 1 char)
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO users (username, email, password, role, full_name, phone, passport_no, loyalty_points) VALUES (?, ?, ?, 'customer', ?, '+1-555-0199', 'US-NEW-001', 100)",
            (username, email, password, full_name),
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    except Exception as exc:
        conn.close()
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": f"Registration failed: {exc}", "current_user": None},
            status_code=400,
        )
    conn.close()

    token = make_predictable_token(user["id"], user["username"], user["role"])
    resp = RedirectResponse(url="/bookings", status_code=302)
    resp.set_cookie(key="session_id", value=token, httponly=False, secure=False, samesite=None)
    resp.set_cookie(key="user_role", value=user["role"], httponly=False, secure=False, samesite=None)
    return resp


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    # Broken Function Level Authorization: no role check enforced
    conn = get_db_connection()
    users = conn.execute("SELECT * FROM users ORDER BY id ASC").fetchall()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_bookings = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    total_revenue = conn.execute("SELECT COALESCE(SUM(total_price), 0) FROM bookings").fetchone()[0]
    total_flights = conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
    conn.close()
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "users": users,
            "stats": {
                "total_users": total_users,
                "total_bookings": total_bookings,
                "total_revenue": total_revenue,
                "total_flights": total_flights,
            },
            "current_user": current_username(request),
        },
    )


@app.get("/api-docs", response_class=HTMLResponse)
async def api_docs_page(request: Request):
    return templates.TemplateResponse(
        request,
        "api_docs.html",
        {"current_user": current_username(request)},
    )


# ---------------------------------------------------------------------------
# Redirects & Simulated Path Traversal / LFI
# ---------------------------------------------------------------------------

@app.get("/redirect")
async def open_redirect(next: str = "/"):
    return RedirectResponse(url=next, status_code=302)


@app.get("/partner-offer")
async def partner_offer_redirect(url: str = "https://partners.skyway-travel.example.com/deals"):
    return RedirectResponse(url=url, status_code=302)


@app.get("/brochures")
async def brochures_lfi(file: str = "summer-deals.pdf"):
    # Safely simulated path traversal / LFI against hardcoded dummy responses
    normalized = file.lower()
    if "etc/passwd" in normalized or ".." in normalized:
        dummy_passwd = (
            "root:x:0:0:root:/root:/bin/bash\n"
            "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\n"
            "www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin\n"
            "skyway:x:1001:1001:SkyWay Service:/home/skyway:/bin/bash\n"
        )
        return PlainTextResponse(dummy_passwd, media_type="text/plain")

    brochures = {
        "summer-deals.pdf": "SkyWay Travel 2026 Summer Brochure\n- London & Paris from $649\n- Dubai Luxury Escapes from $890\n",
        "winter-ski.pdf": "SkyWay Travel 2026 Winter Alpine Guide\n- Zurich & Geneva Packages from $799\n",
    }
    content = brochures.get(file, f"SkyWay Brochure Document: {file}\nContact concierge@skyway-travel.example.com for full print edition.\n")
    return PlainTextResponse(content, media_type="text/plain")


# ---------------------------------------------------------------------------
# Sensitive Files, Backup & Metadata Exposure
# ---------------------------------------------------------------------------

@app.get("/.git/config", response_class=PlainTextResponse)
async def git_config():
    return (
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        "\tfilemode = true\n"
        "\tbare = false\n"
        "[remote \"origin\"]\n"
        "\turl = https://git.skyway-travel.example.com/platform/skyway-web.git\n"
        "\tfetch = +refs/heads/*:refs/remotes/origin/*\n"
        "[branch \"main\"]\n"
        "\tremote = origin\n"
        "\tmerge = refs/heads/main\n"
    )


@app.get("/.env", response_class=PlainTextResponse)
async def env_file():
    return (
        "APP_NAME=SkyWayTravel\n"
        "APP_ENV=production\n"
        "APP_DEBUG=true\n"
        "DB_CONNECTION=sqlite\n"
        "DB_HOST=db-internal.skyway-travel.example.com\n"
        "DB_USERNAME=skyway_admin\n"
        "DB_PASSWORD=DummyDbPassword!2026\n"
        "JWT_SECRET=skyway_super_secret_jwt_key_2026\n"
        "AMADEUS_API_KEY=DUMMY_AMADEUS_KEY_9948120\n"
        "STRIPE_SECRET_KEY=sk_test_51DummySkyWayTravelKey000000\n"
    )


@app.get("/config.json")
async def config_json():
    return JSONResponse(
        {
            "service": "skyway-travel-web",
            "environment": "production",
            "database": {
                "driver": "sqlite",
                "user": "skyway_admin",
                "password": "DummyDbPassword!2026",
            },
            "jwt_secret": "skyway_super_secret_jwt_key_2026",
            "third_party_keys": {
                "gds_provider": "DUMMY_GDS_KEY_112233",
                "payment_gateway": "pk_test_DummyGatewayKey9988",
            },
        }
    )


@app.get("/phpinfo.php", response_class=HTMLResponse)
async def phpinfo():
    return """<!DOCTYPE html>
<html><head><title>phpinfo()</title></head>
<body style="font-family:sans-serif;background:#fff;color:#222;padding:2rem;">
<h1>PHP Version 8.1.2</h1>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>System</th><td>Linux skyway-prod-01 5.15.0-76-generic #83-Ubuntu SMP x86_64</td></tr>
<tr><th>Server API</th><td>Apache 2.0 Handler</td></tr>
<tr><th>Apache Version</th><td>Apache/2.4.49 (Ubuntu)</td></tr>
<tr><th>DOCUMENT_ROOT</th><td>/var/www/skyway-travel/public</td></tr>
<tr><th>SESSION_SAVE_PATH</th><td>/var/lib/php/sessions</td></tr>
</table>
</body></html>"""


@app.get("/server-status", response_class=HTMLResponse)
async def server_status():
    return """<!DOCTYPE html>
<html><head><title>Apache Status</title></head>
<body style="font-family:monospace;padding:1.5rem;">
<h1>Apache Server Status for skyway-travel.example.com (via 10.0.4.12)</h1>
<p>Server Version: Apache/2.4.49 (Ubuntu) PHP/8.1.2</p>
<p>Server MPM: prefork</p>
<p>Current Time: Sunday, 22-Nov-2026 20:55:00 UTC</p>
<p>Total accesses: 48291 - Total Traffic: 1.4 GB</p>
<p>4 requests currently being processed, 12 idle workers</p>
</body></html>"""


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return (
        "User-agent: *\n"
        "Disallow: /admin\n"
        "Disallow: /api/internal\n"
        "Disallow: /backup\n"
        "Sitemap: /sitemap.xml\n"
    )


@app.get("/sitemap.xml")
async def sitemap_xml(request: Request):
    base = str(request.base_url).rstrip("/")
    urls = ["/", "/flights", "/hotels", "/search", "/bookings", "/support", "/login", "/register", "/admin", "/api-docs", "/swagger-ui.html", "/graphql"]
    items = "".join(f"<url><loc>{base}{u}</loc></url>" for u in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'
    return Response(content=xml, media_type="application/xml")


@app.get("/.well-known/security.txt", response_class=PlainTextResponse)
async def security_txt():
    return (
        "Contact: mailto:security@skyway-travel.example.com\n"
        "Expires: 2027-12-31T23:59:59.000Z\n"
        "Preferred-Languages: en\n"
    )


# ---------------------------------------------------------------------------
# API & Microservice Exposures (Swagger, GraphQL, Actuator, BOLA, SQLi, SSRF)
# ---------------------------------------------------------------------------

@app.get("/swagger.json")
async def swagger_json():
    return app.openapi()


@app.get("/swagger-ui.html", response_class=HTMLResponse)
async def swagger_ui():
    return """<!DOCTYPE html>
<html>
<head>
  <title>SkyWay Travel — Swagger UI</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = function() {
      SwaggerUIBundle({ url: '/openapi.json', dom_id: '#swagger-ui' });
    };
  </script>
</body>
</html>"""


@app.get("/actuator")
async def actuator_root():
    return {
        "_links": {
            "self": {"href": "/actuator"},
            "health": {"href": "/actuator/health"},
            "env": {"href": "/actuator/env"},
        }
    }


@app.get("/actuator/health")
async def actuator_health():
    return {"status": "UP", "components": {"db": {"status": "UP", "database": "SQLite"}, "diskSpace": {"status": "UP"}}}


@app.get("/actuator/env")
async def actuator_env():
    return {
        "activeProfiles": ["production"],
        "propertySources": [
            {
                "name": "applicationConfig",
                "properties": {
                    "skyway.db.url": {"value": "sqlite:///app/skyway.db"},
                    "skyway.jwt.secret": {"value": "skyway_super_secret_jwt_key_2026"},
                    "skyway.gds.apiKey": {"value": "DUMMY_GDS_KEY_112233"},
                },
            }
        ],
    }


@app.get("/api/v1/users")
async def api_list_users():
    conn = get_db_connection()
    users = [dict(row) for row in conn.execute("SELECT * FROM users").fetchall()]
    conn.close()
    return {"users": users}


@app.get("/api/v1/users/{user_id}")
async def api_get_user(user_id: int):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return JSONResponse({"error": "User not found"}, status_code=404)
    return dict(user)


@app.get("/api/v1/bookings/{booking_id}")
async def api_get_booking(booking_id: int):
    # BOLA/IDOR: returns any booking without ownership check
    conn = get_db_connection()
    booking = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    conn.close()
    if not booking:
        return JSONResponse({"error": "Booking not found"}, status_code=404)
    return dict(booking)


@app.get("/api/v1/profile")
async def api_get_profile(user_id: int = 1):
    # BOLA/IDOR: accepts arbitrary user_id query param
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return JSONResponse({"error": "Profile not found"}, status_code=404)
    return dict(user)


@app.get("/api/v1/admin/stats")
async def api_admin_stats():
    # Broken Function Level Authorization: no admin role check
    conn = get_db_connection()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_bookings = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    total_revenue = conn.execute("SELECT COALESCE(SUM(total_price), 0) FROM bookings").fetchone()[0]
    conn.close()
    return {
        "total_users": total_users,
        "total_bookings": total_bookings,
        "total_revenue": total_revenue,
        "server_env": "production",
    }


@app.get("/api/v1/flights")
async def api_get_flight(id: str = "1"):
    # Intentionally vulnerable raw SQL string concatenation
    conn = get_db_connection()
    query = f"SELECT * FROM flights WHERE id = {id}"
    try:
        rows = [dict(r) for r in conn.execute(query).fetchall()]
        return {"query": query, "flights": rows}
    except Exception as exc:
        return JSONResponse(
            {
                "error": "SQL syntax or execution error",
                "query": query,
                "detail": str(exc),
                "traceback": traceback.format_exc(),
            },
            status_code=500,
        )
    finally:
        conn.close()


@app.get("/api/v1/check-hotel-availability")
async def check_hotel_availability(hotel_id: int = 1, webhook_url: str = "https://hotels.skyway-travel.example.com/status"):
    # Simulated SSRF: safely returns simulated internal metadata for localhost/127.0.0.1/169.254.169.254
    lower_url = webhook_url.lower()
    if any(host in lower_url for host in ("127.0.0.1", "localhost", "169.254.169.254", "0.0.0.0")):
        return {
            "hotel_id": hotel_id,
            "requested_url": webhook_url,
            "status": "fetched_internal",
            "response_body": {
                "instance_id": "i-0skywayprod9921",
                "region": "us-east-1",
                "internal_service": "skyway-metadata-v1",
                "iam_role": "skyway-ec2-readonly-dummy",
            },
        }
    return {
        "hotel_id": hotel_id,
        "requested_url": webhook_url,
        "status": "available",
        "rooms_left": 6,
        "rate_guarantee": True,
    }


@app.get("/api/debug")
async def api_debug():
    try:
        raise RuntimeError("Debug diagnostics triggered: SkyWay GDS connection pool dump [host=10.0.4.12]")
    except Exception:
        return PlainTextResponse(traceback.format_exc(), status_code=500)


# ---------------------------------------------------------------------------
# GraphQL Endpoint with Introspection Enabled
# ---------------------------------------------------------------------------

GRAPHQL_SCHEMA = {
    "__schema": {
        "queryType": {"name": "Query"},
        "types": [
            {
                "name": "Query",
                "kind": "OBJECT",
                "fields": [
                    {"name": "flights", "type": {"name": "Flight", "kind": "OBJECT"}},
                    {"name": "bookings", "type": {"name": "Booking", "kind": "OBJECT"}},
                    {"name": "users", "type": {"name": "User", "kind": "OBJECT"}},
                ],
            },
            {
                "name": "Flight",
                "kind": "OBJECT",
                "fields": [
                    {"name": "id", "type": {"name": "Int", "kind": "SCALAR"}},
                    {"name": "flight_number", "type": {"name": "String", "kind": "SCALAR"}},
                    {"name": "origin", "type": {"name": "String", "kind": "SCALAR"}},
                    {"name": "destination", "type": {"name": "String", "kind": "SCALAR"}},
                    {"name": "price", "type": {"name": "Float", "kind": "SCALAR"}},
                ],
            },
            {
                "name": "Booking",
                "kind": "OBJECT",
                "fields": [
                    {"name": "id", "type": {"name": "Int", "kind": "SCALAR"}},
                    {"name": "booking_ref", "type": {"name": "String", "kind": "SCALAR"}},
                    {"name": "passenger_name", "type": {"name": "String", "kind": "SCALAR"}},
                    {"name": "passenger_email", "type": {"name": "String", "kind": "SCALAR"}},
                    {"name": "status", "type": {"name": "String", "kind": "SCALAR"}},
                ],
            },
        ],
    }
}


@app.get("/graphql", response_class=HTMLResponse)
async def graphql_playground(query: Optional[str] = None):
    if query:
        return JSONResponse(_execute_graphql(query))
    return """<!DOCTYPE html>
<html>
<head><title>SkyWay GraphQL Explorer</title></head>
<body style="font-family:sans-serif;padding:2rem;max-width:800px;margin:auto;">
  <h2>SkyWay Travel GraphQL Endpoint</h2>
  <p>POST JSON <code>{"query": "{ flights { flight_number origin destination price } }"}</code> to <code>/graphql</code>.</p>
  <p>Try introspection: <a href="/graphql?query={__schema{types{name}}}">/graphql?query={__schema{types{name}}}</a></p>
</body>
</html>"""


@app.post("/graphql")
async def graphql_post(request: Request):
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"errors": [{"message": "Invalid JSON body"}]}, status_code=400)
    query = body.get("query", "")
    return JSONResponse(_execute_graphql(query))


def _execute_graphql(query: str) -> Dict[str, Any]:
    if "__schema" in query or "__type" in query:
        return {"data": GRAPHQL_SCHEMA}

    conn = get_db_connection()
    data: Dict[str, Any] = {}
    if "flights" in query:
        data["flights"] = [dict(r) for r in conn.execute("SELECT * FROM flights").fetchall()]
    if "bookings" in query:
        data["bookings"] = [dict(r) for r in conn.execute("SELECT * FROM bookings").fetchall()]
    if "users" in query:
        data["users"] = [dict(r) for r in conn.execute("SELECT * FROM users").fetchall()]
    conn.close()

    if not data:
        return {"data": {"flights": [], "bookings": []}}
    return {"data": data}
