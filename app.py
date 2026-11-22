import os
import re
import uuid
from datetime import datetime
from functools import wraps
from urllib import error as url_error
from urllib import request as url_request
import json

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

app = Flask(__name__, template_folder="template", static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "uniconnect-multipage-secret-2026")

DEFAULT_PASSWORD = "123"
DEPARTMENTS = [
    "Computer Science",
    "Software Engineering",
    "Electrical Engineering",
    "Business Administration",
    "Media & Design",
]

ROLE_LABELS = {
    "student": "Student",
    "society": "Society Member",
    "admin": "Admin",
}

ROLE_EMAIL_PATTERNS = {
    "student": re.compile(r"^st[a-z0-9._-]+@uni\.pk$", re.IGNORECASE),
    "admin": re.compile(r"^ad[a-z0-9._-]+@uni\.pk$", re.IGNORECASE),
    "society": re.compile(r"^s_mem[a-z0-9._-]+@uni\.pk$", re.IGNORECASE),
}

# ---------------- IN-MEMORY MOCK DATA ----------------

USERS_DB = [
    {
        "reg_no": "STU-2024-101",
        "name": "Ali Raza",
        "department": "Computer Science",
        "email": "st.ali@uni.pk",
        "password": DEFAULT_PASSWORD,
        "role": "student",
        "society_name": "",
    },
    {
        "reg_no": "STU-2024-204",
        "name": "Sara Tariq",
        "department": "Business Administration",
        "email": "st.sara@uni.pk",
        "password": DEFAULT_PASSWORD,
        "role": "student",
        "society_name": "",
    },
    {
        "reg_no": "SOC-2024-012",
        "name": "Bilal Ahmed",
        "department": "Computer Science",
        "email": "s_mem.bilal@uni.pk",
        "password": DEFAULT_PASSWORD,
        "role": "society",
        "society_name": "Tech & AI Society",
    },
    {
        "reg_no": "ADM-2024-001",
        "name": "Zainab Malik",
        "department": "Student Affairs",
        "email": "ad.zainab@uni.pk",
        "password": DEFAULT_PASSWORD,
        "role": "admin",
        "society_name": "",
    },
]

EVENTS_DB = [
    {
        "id": 1,
        "title": "Campus Innovation & AI Summit",
        "category": "Seminar",
        "event_date": "2026-11-26",
        "time_slot": "10:00 AM - 01:00 PM",
        "venue": "Main Auditorium",
        "department": "All Departments",
        "allowed_type": "All Departments",
        "organizer": "Tech & AI Society",
        "capacity": 180,
        "description": "University-wide keynote and live demos open to students from every department.",
    },
    {
        "id": 2,
        "title": "Algorithms & Cloud Systems Workshop",
        "category": "Workshop",
        "event_date": "2026-11-28",
        "time_slot": "11:30 AM - 02:00 PM",
        "venue": "CS Lab 2",
        "department": "Computer Science",
        "allowed_type": "Department Only",
        "organizer": "Department of Computer Science",
        "capacity": 65,
        "description": "Focused hands-on lab for Computer Science students on system design and APIs.",
    },
    {
        "id": 3,
        "title": "Market Strategy & Pitch Lab",
        "category": "Workshop",
        "event_date": "2026-12-01",
        "time_slot": "01:00 PM - 03:30 PM",
        "venue": "Business Hall B",
        "department": "Business Administration",
        "allowed_type": "Department Only",
        "organizer": "Business Society",
        "capacity": 75,
        "description": "Case study and venture pitch session tailored for Business Administration students.",
    },
    {
        "id": 4,
        "title": "Inter-Faculty Sports Gala",
        "category": "Sports",
        "event_date": "2026-12-04",
        "time_slot": "02:00 PM - 06:00 PM",
        "venue": "Central Sports Ground",
        "department": "All Departments",
        "allowed_type": "All Departments",
        "organizer": "Sports Council",
        "capacity": 250,
        "description": "Open campus tournament where all departments can register and participate.",
    },
]

REGISTRATIONS_DB = [
    {
        "id": 1,
        "event_id": 1,
        "student_email": "st.ali@uni.pk",
        "student_name": "Ali Raza",
        "reg_no": "STU-2024-101",
        "department": "Computer Science",
    },
]

REQUESTS_DB = [
    {
        "id": 1,
        "society_name": "Tech & AI Society",
        "requester_email": "s_mem.bilal@uni.pk",
        "title": "Python & Automation Sprint",
        "category": "Hackathon",
        "event_date": "2026-12-07",
        "time_slot": "09:30 AM - 03:00 PM",
        "venue": "Seminar Hall 1",
        "department": "Computer Science",
        "allowed_type": "All Departments",
        "capacity": 100,
        "description": "Practical coding sprint for automating campus workflows.",
        "status": "Pending",
        "added_to_calendar": False,
    },
    {
        "id": 2,
        "society_name": "Tech & AI Society",
        "requester_email": "s_mem.bilal@uni.pk",
        "title": "UI Prototyping Clinic",
        "category": "Workshop",
        "event_date": "2026-12-09",
        "time_slot": "02:00 PM - 04:30 PM",
        "venue": "Design Studio A",
        "department": "Media & Design",
        "allowed_type": "Department Only",
        "capacity": 50,
        "description": "Wireframing and interface layout clinic.",
        "status": "Approved",
        "added_to_calendar": False,
    },
]

EMAIL_OUTBOX = []


# ---------------- HELPERS ----------------


def next_id(items):
    return max([item["id"] for item in items], default=0) + 1


def validate_role_email(email, role):
    email_clean = (email or "").strip().lower()
    pattern = ROLE_EMAIL_PATTERNS.get(role)
    if not pattern or not pattern.match(email_clean):
        expected_prefix = {
            "student": "st...@uni.pk",
            "admin": "ad...@uni.pk",
            "society": "s_mem...@uni.pk",
        }.get(role, "...@uni.pk")
        return False, f"Invalid {ROLE_LABELS.get(role, 'role')} email. Must match {expected_prefix}."
    return True, email_clean


def generate_email_body_with_gemini(subject_hint, fallback_text):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return fallback_text

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            f"Write a concise, clear university portal notification email "
                            f"for '{subject_hint}'. Key details: {fallback_text}"
                        )
                    }
                ]
            }
        ]
    }
    req = url_request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with url_request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )
            return text or fallback_text
    except (url_error.URLError, TimeoutError, ValueError, KeyError):
        return fallback_text


def send_notification_email(to_email, subject, details_text):
    body = generate_email_body_with_gemini(subject, details_text)
    EMAIL_OUTBOX.insert(
        0,
        {
            "id": str(uuid.uuid4())[:8],
            "to": to_email,
            "subject": subject,
            "body": body,
            "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
    )


def login_required(roles=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_email" not in session:
                flash("Please sign in first.")
                return redirect(url_for("login"))
            if roles and session.get("user_role") not in roles:
                flash("You do not have permission for that action.")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def find_user_by_email(email):
    target = (email or "").strip().lower()
    for u in USERS_DB:
        if u["email"].lower() == target:
            return u
    return None


def find_event_by_id(event_id):
    for ev in EVENTS_DB:
        if ev["id"] == event_id:
            return ev
    return None


def find_request_by_id(req_id):
    for r in REQUESTS_DB:
        if r["id"] == req_id:
            return r
    return None


def student_eligible_for_event(user, event):
    if event.get("allowed_type") == "All Departments" or event.get("department") == "All Departments":
        return True
    return (event.get("department") or "").strip().lower() == (user.get("department") or "").strip().lower()


def publish_request_to_calendar(req_item):
    if req_item.get("added_to_calendar"):
        return False
    EVENTS_DB.append(
        {
            "id": next_id(EVENTS_DB),
            "title": req_item["title"],
            "category": req_item["category"],
            "event_date": req_item["event_date"],
            "time_slot": req_item["time_slot"],
            "venue": req_item["venue"],
            "department": req_item["department"],
            "allowed_type": req_item["allowed_type"],
            "organizer": req_item["society_name"],
            "capacity": req_item["capacity"],
            "description": req_item["description"],
        }
    )
    req_item["added_to_calendar"] = True
    return True


# ---------------- AUTH & SIGN UP ----------------


@app.route("/")
def home():
    if "user_email" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "student").strip().lower()

        ok, msg_or_email = validate_role_email(email, role)
        if not ok:
            flash(msg_or_email)
            return render_template(
                "login.html",
                departments=DEPARTMENTS,
                active_tab="login",
                selected_role=role,
                entered_email=email,
            )

        user = find_user_by_email(msg_or_email)
        if not user or user["role"] != role or user["password"] != password:
            flash("Invalid credentials or role mismatch. Use a valid @uni.pk account or sign up.")
            return render_template(
                "login.html",
                departments=DEPARTMENTS,
                active_tab="login",
                selected_role=role,
                entered_email=email,
            )

        session.clear()
        session["user_email"] = user["email"]
        session["user_role"] = user["role"]
        flash(f"Signed in as {user['name']} ({ROLE_LABELS[user['role']]}).")
        return redirect(url_for("dashboard"))

    return render_template(
        "login.html",
        departments=DEPARTMENTS,
        active_tab="login",
        selected_role="student",
        entered_email="st.ali@uni.pk",
    )


@app.route("/signup", methods=["POST"])
def signup():
    reg_no = request.form.get("reg_no", "").strip().upper()
    department = request.form.get("department", "Computer Science").strip()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    role = request.form.get("role", "student").strip().lower()
    society_name = request.form.get("society_name", "").strip()

    if role not in ROLE_LABELS:
        role = "student"

    if not reg_no or not name or not email or not password:
        flash("Please fill in registration number, department, name, email, and password.")
        return render_template(
            "login.html",
            departments=DEPARTMENTS,
            active_tab="signup",
            selected_role=role,
            entered_email=email,
        )

    ok, checked_email = validate_role_email(email, role)
    if not ok:
        flash(checked_email)
        return render_template(
            "login.html",
            departments=DEPARTMENTS,
            active_tab="signup",
            selected_role=role,
            entered_email=email,
        )

    if find_user_by_email(checked_email):
        flash("An account with this @uni.pk email already exists in memory.")
        return render_template(
            "login.html",
            departments=DEPARTMENTS,
            active_tab="signup",
            selected_role=role,
            entered_email=email,
        )

    new_user = {
        "reg_no": reg_no,
        "name": name,
        "department": department,
        "email": checked_email,
        "password": password,
        "role": role,
        "society_name": society_name or (f"{department} Society" if role == "society" else ""),
    }
    USERS_DB.append(new_user)

    send_notification_email(
        checked_email,
        "Welcome to UniConnect — Registration Confirmed",
        f"Hello {name} ({reg_no}), your {ROLE_LABELS[role]} account in {department} is active.",
    )

    session.clear()
    session["user_email"] = checked_email
    session["user_role"] = role
    flash(f"Registration successful! Welcome to UniConnect, {name}.")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for("login"))


# ---------------- SEPARATE PAGES ----------------


@app.route("/dashboard")
@login_required()
def dashboard():
    user = find_user_by_email(session["user_email"])
    if not user:
        return redirect(url_for("logout"))

    role = user["role"]
    my_reg_ids = {
        r["event_id"] for r in REGISTRATIONS_DB if r["student_email"].lower() == user["email"].lower()
    }

    if role == "student":
        visible_events = [ev for ev in EVENTS_DB if student_eligible_for_event(user, ev)]
    else:
        visible_events = list(EVENTS_DB)

    my_regs = [ev for ev in EVENTS_DB if ev["id"] in my_reg_ids]
    society_requests = [
        r for r in REQUESTS_DB if r["requester_email"].lower() == user["email"].lower()
    ]
    all_requests = list(REQUESTS_DB)
    user_emails = [
        m for m in EMAIL_OUTBOX if m["to"].lower() == user["email"].lower() or role == "admin"
    ]

    return render_template(
        "dashboard.html",
        user=user,
        role_label=ROLE_LABELS[role],
        departments=DEPARTMENTS,
        events=visible_events,
        all_events_count=len(EVENTS_DB),
        my_regs=my_regs,
        my_reg_ids=my_reg_ids,
        society_requests=society_requests,
        all_requests=all_requests,
        emails=user_emails[:8],
    )


@app.route("/calendar")
@login_required()
def calendar_view():
    user = find_user_by_email(session["user_email"])
    if not user:
        return redirect(url_for("logout"))

    dept_filter = request.args.get("dept", "All").strip()
    sorted_events = sorted(EVENTS_DB, key=lambda x: (x["event_date"], x["id"]))
    if dept_filter and dept_filter != "All":
        filtered = [
            ev for ev in sorted_events
            if ev["department"] == dept_filter or ev["allowed_type"] == "All Departments"
        ]
    else:
        filtered = sorted_events

    my_reg_ids = {
        r["event_id"] for r in REGISTRATIONS_DB if r["student_email"].lower() == user["email"].lower()
    }

    return render_template(
        "calendar.html",
        user=user,
        role_label=ROLE_LABELS[user["role"]],
        departments=DEPARTMENTS,
        selected_dept=dept_filter,
        events=filtered,
        my_reg_ids=my_reg_ids,
        eligible_fn=lambda ev: student_eligible_for_event(user, ev),
    )


@app.route("/profile")
@login_required()
def profile_view():
    user = find_user_by_email(session["user_email"])
    if not user:
        return redirect(url_for("logout"))

    my_regs = [
        r for r in REGISTRATIONS_DB if r["student_email"].lower() == user["email"].lower()
    ]
    my_reqs = [
        r for r in REQUESTS_DB if r["requester_email"].lower() == user["email"].lower()
    ]
    my_emails = [
        m for m in EMAIL_OUTBOX if m["to"].lower() == user["email"].lower()
    ]

    return render_template(
        "profile.html",
        user=user,
        role_label=ROLE_LABELS[user["role"]],
        registered_count=len(my_regs),
        requests_count=len(my_reqs),
        emails=my_emails,
        registered_users_count=len(USERS_DB),
    )


# ---------------- STUDENT ACTIONS ----------------


@app.route("/events/register/<int:event_id>", methods=["POST"])
@login_required(roles=["student"])
def register_for_event(event_id):
    user = find_user_by_email(session["user_email"])
    ev = find_event_by_id(event_id)
    if not ev:
        flash("Event not found.")
        return redirect(url_for("dashboard"))

    if not student_eligible_for_event(user, ev):
        flash(f"'{ev['title']}' is restricted to {ev['department']} students.")
        return redirect(request.referrer or url_for("dashboard"))

    already = any(
        r["event_id"] == event_id and r["student_email"].lower() == user["email"].lower()
        for r in REGISTRATIONS_DB
    )
    if already:
        flash(f"You are already registered for '{ev['title']}'.")
        return redirect(request.referrer or url_for("dashboard"))

    REGISTRATIONS_DB.append(
        {
            "id": next_id(REGISTRATIONS_DB),
            "event_id": event_id,
            "student_email": user["email"],
            "student_name": user["name"],
            "reg_no": user["reg_no"],
            "department": user["department"],
        }
    )

    send_notification_email(
        user["email"],
        f"Event Registration Confirmed: {ev['title']}",
        f"Hi {user['name']}, you registered for '{ev['title']}' on {ev['event_date']} ({ev['time_slot']}) at {ev['venue']}.",
    )
    flash(f"Registered for '{ev['title']}'. Confirmation email sent to {user['email']}.")
    return redirect(request.referrer or url_for("dashboard"))


# ---------------- ADMIN EVENT ACTIONS ----------------


@app.route("/admin/events/add", methods=["POST"])
@login_required(roles=["admin"])
def admin_add_event():
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "Workshop").strip()
    event_date = request.form.get("event_date", "").strip()
    time_slot = request.form.get("time_slot", "").strip()
    venue = request.form.get("venue", "").strip()
    department = request.form.get("department", "All Departments").strip()
    allowed_type = request.form.get("allowed_type", "All Departments").strip()
    capacity = int(request.form.get("capacity") or 100)
    description = request.form.get("description", "").strip() or "University campus event."

    if not title or not event_date or not time_slot or not venue:
        flash("Title, date, time slot, and venue are required.")
        return redirect(url_for("dashboard"))

    EVENTS_DB.append(
        {
            "id": next_id(EVENTS_DB),
            "title": title,
            "category": category,
            "event_date": event_date,
            "time_slot": time_slot,
            "venue": venue,
            "department": department,
            "allowed_type": allowed_type,
            "organizer": "UniConnect Admin",
            "capacity": max(1, capacity),
            "description": description,
        }
    )

    send_notification_email(
        session["user_email"],
        f"Event Added to Calendar: {title}",
        f"Admin added '{title}' on {event_date} at {venue} ({department} / {allowed_type}).",
    )
    flash(f"Added '{title}' to calendar and sent email notification.")
    return redirect(url_for("dashboard"))


@app.route("/admin/events/edit/<int:event_id>", methods=["POST"])
@login_required(roles=["admin"])
def admin_edit_event(event_id):
    ev = find_event_by_id(event_id)
    if not ev:
        flash("Event not found.")
        return redirect(url_for("dashboard"))

    ev["title"] = request.form.get("title", ev["title"]).strip()
    ev["event_date"] = request.form.get("event_date", ev["event_date"]).strip()
    ev["time_slot"] = request.form.get("time_slot", ev["time_slot"]).strip()
    ev["venue"] = request.form.get("venue", ev["venue"]).strip()
    ev["department"] = request.form.get("department", ev["department"]).strip()
    ev["allowed_type"] = request.form.get("allowed_type", ev["allowed_type"]).strip()

    send_notification_email(
        session["user_email"],
        f"Event Updated: {ev['title']}",
        f"Updated details -> Date: {ev['event_date']}, Time: {ev['time_slot']}, Venue: {ev['venue']}, Dept: {ev['department']}.",
    )
    flash(f"Updated '{ev['title']}' and sent update email.")
    return redirect(url_for("dashboard"))


@app.route("/admin/events/delete/<int:event_id>", methods=["POST"])
@login_required(roles=["admin"])
def admin_delete_event(event_id):
    ev = find_event_by_id(event_id)
    if ev:
        EVENTS_DB[:] = [item for item in EVENTS_DB if item["id"] != event_id]
        send_notification_email(
            session["user_email"],
            f"Event Removed: {ev['title']}",
            f"Event '{ev['title']}' scheduled for {ev['event_date']} at {ev['venue']} has been removed.",
        )
        flash(f"Deleted '{ev['title']}' and sent email notification.")
    return redirect(url_for("dashboard"))


# ---------------- SOCIETY REQUEST & APPROVAL ACTIONS ----------------


@app.route("/society/requests/submit", methods=["POST"])
@login_required(roles=["society"])
def society_submit_request():
    user = find_user_by_email(session["user_email"])
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "Workshop").strip()
    event_date = request.form.get("event_date", "").strip()
    time_slot = request.form.get("time_slot", "").strip()
    venue = request.form.get("venue", "").strip()
    department = request.form.get("department", user["department"]).strip()
    allowed_type = request.form.get("allowed_type", "All Departments").strip()
    description = request.form.get("description", "").strip() or "Society event proposal."

    if not title or not event_date or not time_slot or not venue:
        flash("Please complete title, date, time slot, and venue.")
        return redirect(url_for("dashboard"))

    soc_name = user.get("society_name") or f"{user['department']} Society"
    REQUESTS_DB.append(
        {
            "id": next_id(REQUESTS_DB),
            "society_name": soc_name,
            "requester_email": user["email"],
            "title": title,
            "category": category,
            "event_date": event_date,
            "time_slot": time_slot,
            "venue": venue,
            "department": department,
            "allowed_type": allowed_type,
            "capacity": 100,
            "description": description,
            "status": "Pending",
            "added_to_calendar": False,
        }
    )

    send_notification_email(
        user["email"],
        f"Society Request Confirmation: {title}",
        f"Your proposal '{title}' for {event_date} at {venue} has been submitted and is awaiting Admin approval.",
    )
    send_notification_email(
        "ad.zainab@uni.pk",
        f"New Society Event Request: {title}",
        f"Society '{soc_name}' ({user['email']}) submitted '{title}' on {event_date} ({venue}).",
    )
    flash(f"Request '{title}' submitted! Confirmation email sent.")
    return redirect(url_for("dashboard"))


@app.route("/society/requests/edit/<int:req_id>", methods=["POST"])
@login_required(roles=["society"])
def society_edit_request(req_id):
    req_item = find_request_by_id(req_id)
    if not req_item:
        flash("Request not found.")
        return redirect(url_for("dashboard"))

    req_item["title"] = request.form.get("title", req_item["title"]).strip()
    req_item["event_date"] = request.form.get("event_date", req_item["event_date"]).strip()
    req_item["time_slot"] = request.form.get("time_slot", req_item["time_slot"]).strip()
    req_item["venue"] = request.form.get("venue", req_item["venue"]).strip()
    req_item["department"] = request.form.get("department", req_item["department"]).strip()
    req_item["allowed_type"] = request.form.get("allowed_type", req_item["allowed_type"]).strip()

    if req_item["added_to_calendar"]:
        for ev in EVENTS_DB:
            if ev["title"] == req_item["title"] or ev["organizer"] == req_item["society_name"]:
                ev["event_date"] = req_item["event_date"]
                ev["time_slot"] = req_item["time_slot"]
                ev["venue"] = req_item["venue"]
                ev["department"] = req_item["department"]
                ev["allowed_type"] = req_item["allowed_type"]
                break

    send_notification_email(
        req_item["requester_email"],
        f"Society Event Updated: {req_item['title']}",
        f"Updated event '{req_item['title']}' -> {req_item['event_date']}, {req_item['time_slot']}, {req_item['venue']}.",
    )
    flash(f"Updated '{req_item['title']}' and sent confirmation email.")
    return redirect(url_for("dashboard"))


@app.route("/society/requests/add-to-calendar/<int:req_id>", methods=["POST"])
@login_required(roles=["society"])
def society_add_to_calendar(req_id):
    req_item = find_request_by_id(req_id)
    if not req_item:
        flash("Request not found.")
        return redirect(url_for("dashboard"))

    if req_item["status"] != "Approved":
        flash("Event can only be added to the calendar after Admin approval.")
        return redirect(url_for("dashboard"))

    if publish_request_to_calendar(req_item):
        send_notification_email(
            req_item["requester_email"],
            f"Added to Calendar: {req_item['title']}",
            f"'{req_item['title']}' is now live on the UniConnect calendar for {req_item['event_date']} at {req_item['venue']}.",
        )
        flash(f"'{req_item['title']}' added to the calendar!")
    else:
        flash(f"'{req_item['title']}' is already on the calendar.")
    return redirect(url_for("dashboard"))


@app.route("/admin/requests/<int:req_id>/<action>", methods=["POST"])
@login_required(roles=["admin"])
def admin_decide_request(req_id, action):
    req_item = find_request_by_id(req_id)
    if not req_item:
        flash("Request not found.")
        return redirect(url_for("dashboard"))

    if action == "approve":
        req_item["status"] = "Approved"
        publish_request_to_calendar(req_item)
        send_notification_email(
            req_item["requester_email"],
            f"Approved & Published: {req_item['title']}",
            f"Admin approved '{req_item['title']}' and automatically added it to the UniConnect calendar.",
        )
        flash(f"Approved '{req_item['title']}' — automatically added to calendar and email sent.")
    elif action == "reject":
        req_item["status"] = "Rejected"
        send_notification_email(
            req_item["requester_email"],
            f"Request Update: {req_item['title']}",
            f"Your event request '{req_item['title']}' was not approved for {req_item['event_date']}.",
        )
        flash(f"Rejected '{req_item['title']}' and notified society.")

    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)