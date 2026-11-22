import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "skyway.db")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'customer',
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            passport_no TEXT NOT NULL,
            loyalty_points INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS flights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flight_number TEXT NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            departure_time TEXT NOT NULL,
            arrival_time TEXT NOT NULL,
            price REAL NOT NULL,
            airline TEXT NOT NULL,
            cabin_class TEXT NOT NULL,
            seats_available INTEGER NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hotels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            country TEXT NOT NULL,
            rating REAL NOT NULL,
            price_per_night REAL NOT NULL,
            description TEXT NOT NULL,
            amenities TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_ref TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            flight_id INTEGER NOT NULL,
            passenger_name TEXT NOT NULL,
            passenger_email TEXT NOT NULL,
            status TEXT NOT NULL,
            total_price REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    # Seed dummy users if empty
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        users_seed = [
            ("alice", "alice.martin@example.com", "password123", "customer", "Alice Martin", "+1-555-0142", "US-9981204", 4250),
            ("bob", "bob.carter@example.com", "summer2026", "customer", "Bob Carter", "+1-555-0188", "US-7743109", 1890),
            ("sarah.j", "sarah.jenkins@example.com", "123456", "vip_member", "Sarah Jenkins", "+44-20-7946-0192", "UK-5532018", 15400),
            ("admin", "admin@skyway-travel.example.com", "Admin@2026", "admin", "Marcus Vance", "+1-555-0100", "US-0001122", 99000),
        ]
        cur.executemany(
            "INSERT INTO users (username, email, password, role, full_name, phone, passport_no, loyalty_points) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            users_seed,
        )

    # Seed dummy flights if empty
    cur.execute("SELECT COUNT(*) FROM flights")
    if cur.fetchone()[0] == 0:
        flights_seed = [
            ("SW101", "New York (JFK)", "London (LHR)", "2026-12-10 18:30", "2026-12-11 06:45", 649.00, "SkyWay Air", "Economy", 24),
            ("SW204", "New York (JFK)", "Paris (CDG)", "2026-12-12 20:15", "2026-12-13 09:20", 715.00, "SkyWay Air", "Economy", 16),
            ("SW318", "London (LHR)", "Dubai (DXB)", "2026-12-15 11:00", "2026-12-15 21:45", 890.00, "Emirates Partner", "Business", 8),
            ("SW412", "Chicago (ORD)", "Tokyo (HND)", "2026-12-18 13:40", "2026-12-19 17:10", 1120.00, "Pacific Wings", "Economy", 19),
            ("SW509", "San Francisco (SFO)", "Rome (FCO)", "2026-12-20 16:05", "2026-12-21 12:30", 785.00, "SkyWay Air", "Premium Economy", 11),
            ("SW622", "Dubai (DXB)", "Istanbul (IST)", "2026-12-22 08:20", "2026-12-22 12:15", 340.00, "EuroJet", "Economy", 32),
            ("SW730", "Paris (CDG)", "Barcelona (BCN)", "2026-12-24 09:50", "2026-12-24 11:35", 165.00, "EuroJet", "Economy", 40),
            ("SW845", "Los Angeles (LAX)", "Sydney (SYD)", "2026-12-27 22:30", "2026-12-29 07:45", 1340.00, "Pacific Wings", "Business", 5),
        ]
        cur.executemany(
            "INSERT INTO flights (flight_number, origin, destination, departure_time, arrival_time, price, airline, cabin_class, seats_available) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            flights_seed,
        )

    # Seed dummy hotels if empty
    cur.execute("SELECT COUNT(*) FROM hotels")
    if cur.fetchone()[0] == 0:
        hotels_seed = [
            ("The Kensington Grand", "London", "United Kingdom", 4.8, 245.00, "Boutique luxury suites steps from Hyde Park with complimentary breakfast.", "Free Wi-Fi, Spa, Airport Shuttle"),
            ("Hôtel Lumière Champs-Élysées", "Paris", "France", 4.7, 290.00, "Classic Parisian elegance with Eiffel Tower balcony views.", "Free Wi-Fi, Concierge, Fine Dining"),
            ("Palm Oasis Resort", "Dubai", "UAE", 4.9, 380.00, "Beachfront resort featuring private cabanas and infinity pools.", "Private Beach, Pool, Gym, Spa"),
            ("Shibuya Horizon Hotel", "Tokyo", "Japan", 4.6, 195.00, "Modern high-rise hotel connected directly to Shibuya transit hub.", "Free Wi-Fi, Rooftop Bar, Onsen"),
            ("Colosseum Heritage Suites", "Rome", "Italy", 4.5, 175.00, "Charming historic property within walking distance of ancient landmarks.", "Free Wi-Fi, Breakfast Included"),
            ("Marina Bay Vista", "Barcelona", "Spain", 4.7, 210.00, "Contemporary Mediterranean rooms overlooking the waterfront promenade.", "Pool, Terrace, Free Wi-Fi"),
        ]
        cur.executemany(
            "INSERT INTO hotels (name, city, country, rating, price_per_night, description, amenities) VALUES (?, ?, ?, ?, ?, ?, ?)",
            hotels_seed,
        )

    # Seed dummy bookings if empty
    cur.execute("SELECT COUNT(*) FROM bookings")
    if cur.fetchone()[0] == 0:
        bookings_seed = [
            ("SW-849201", 1, 1, "Alice Martin", "alice.martin@example.com", "Confirmed", 649.00, "2026-11-10 14:22:00"),
            ("SW-731944", 2, 2, "Bob Carter", "bob.carter@example.com", "Confirmed", 715.00, "2026-11-12 09:15:00"),
            ("SW-550182", 3, 3, "Sarah Jenkins", "sarah.jenkins@example.com", "Ticketed", 890.00, "2026-11-15 17:40:00"),
            ("SW-992014", 1, 5, "Alice Martin", "alice.martin@example.com", "Pending Payment", 785.00, "2026-11-18 11:05:00"),
        ]
        cur.executemany(
            "INSERT INTO bookings (booking_ref, user_id, flight_id, passenger_name, passenger_email, status, total_price, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            bookings_seed,
        )

    conn.commit()
    conn.close()
