from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from google.cloud import pubsub_v1, storage
from google.auth import credentials
import sqlite3
import os
from werkzeug.utils import secure_filename
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from google.protobuf.timestamp_pb2 import Timestamp
from prometheus_client import Counter, Histogram, start_http_server, generate_latest
import time 
import mysql.connector
import threading
import sched
import logging
from mysql.connector import Error

# Replace with your actual Cloud SQL credentials
MYSQL_HOST = 'IP address'  # either the IP address or the Unix socket path
MYSQL_USER = 'Database username'           # Database username (e.g., 'root')
MYSQL_PASSWORD = 'Database password'       # Database password
MYSQL_DB = 'Database name'                 # Database name (e.g., 'mydatabase')

UPLOAD_FOLDER = 'static/event_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Create custom metrics for monitoring specific endpoints
HTTP_REQUESTS = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])

# Histogram for latency monitoring
REQUEST_LATENCY = Histogram('http_request_latency_seconds', 'HTTP request latency', ['method', 'endpoint'])

app = Flask(__name__)
app.secret_key = 'b4fcb5245d6d2579d0731eb510d2ff8d60f8a2ab0be67f50f34a1e5f9492b573'  # Replace with your secret key




# Pub/Sub setup
PROJECT_ID = "dcsc-project-final"  # Replace with your Google Cloud project ID
SUBSCRIPTION_ID = "event-updates-sub"  # Your subscription ID
subscription_path = f"projects/{PROJECT_ID}/subscriptions/{SUBSCRIPTION_ID}"

# Initialize the Pub/Sub Subscriber Client
subscriber = pubsub_v1.SubscriberClient()

TOPIC_ID = "event-updates"  # Pub/Sub topic


BUCKET_NAME = 'my-event-images-bucket'

# Initialize the Cloud Storage client
storage_client = storage.Client()
logging.basicConfig(level=logging.INFO)

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

# Email setup
EMAIL_HOST = "smtp.gmail.com"  # Replace with your email provider SMTP server
EMAIL_PORT = 587  # Typically 587 for TLS
EMAIL_USER = "email address"  # Replace with your email address
EMAIL_PASSWORD = "app-specific password"  # Replace with your email password or use an app-specific password


def send_event_reminder(event_id, event_title, event_date, event_location, event_description, user_email):
    # Format the event date (without time)
    formatted_date = event_date.strftime("%A, %B %d, %Y")
    
    # Email subject
    subject = f"Reminder: {event_title} is happening tomorrow!"
    
    # Email body (plain text)
    body = f"""
    Hello,

    This is a reminder that your event is happening tomorrow!

    Event Details:
    -------------------
    Title:       {event_title}
    Date:        {formatted_date}
    Location:    {event_location}
    Description: {event_description}

    We look forward to seeing you at the event!

    Best regards,
    Your Event Team
    """
    send_email(subject, body, user_email)


def check_event_reminders():
    conn = db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get today's date and the date 24 hours later
    today = datetime.now()
    reminder_time = today + timedelta(days=1)
    reminder_date = reminder_time.date()

    # Fetch events happening in the next 24 hours
    cursor.execute("SELECT * FROM events WHERE DATE(event_date) = %s", (reminder_date,))
    events_to_remind = cursor.fetchall()

    for event in events_to_remind:
        # Fetch all users who have RSVP'd to the event
        cursor.execute("SELECT u.email,u.id FROM rsvps r JOIN users u ON r.user_id = u.id WHERE r.event_id = %s AND r.status = 'Yes'AND r.reminder_sent = 'No'", (event['id'],))
        users = cursor.fetchall()
        for user in users:
            send_event_reminder(event['id'], event['title'], event['event_date'],event['location'],event['description'], user['email'])
            cursor.execute(
            """
            UPDATE rsvps 
            SET reminder_sent = %s 
            WHERE event_id = %s AND user_id = %s
            """,
            ('Yes', event['id'], user['id'])
            )
            conn.commit()

    cursor.close()
    conn.close()
    threading.Timer(60, check_event_reminders).start()


def db_connection():
    try:
        # Connect to MySQL database
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB
        )
        if conn.is_connected():
            print("Connected to MySQL database")
            return conn
    except Error as e:
        print(f"Error: {e}")
        return None


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_image_to_gcs(image_file):
    # Ensure the filename is safe for use
    filename = secure_filename(image_file.filename)

    # Get the Cloud Storage bucket
    bucket = storage_client.bucket(BUCKET_NAME)

    user_id = session["user_id"]

    # Create a new blob (file) in the bucket
    blob = bucket.blob(f'event_images/{user_id}/{filename}')

    # Upload the file to Cloud Storage
    blob.upload_from_file(image_file)

    # Return the public URL of the object
    return f"https://storage.googleapis.com/{BUCKET_NAME}/event_images/{user_id}/{filename}"

# Initialize database with required tables
def init_db():
    conn = db_connection()

    # Create users table
    conn.cursor().execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            profile_image VARCHAR(255)
        );
    """)

    # Create events table
    conn.cursor().execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            event_date DATETIME NOT NULL,
            location VARCHAR(255) NOT NULL,
            user_id INT,
            image VARCHAR(255),
            category VARCHAR(255),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
    """)

    # Create rsvps table
    conn.cursor().execute("""
        CREATE TABLE IF NOT EXISTS rsvps (
            id INT AUTO_INCREMENT PRIMARY KEY,
            event_id INT NOT NULL,
            user_id INT NOT NULL,
            status VARCHAR(50) NOT NULL,
            reminder_sent ENUM('Yes', 'No') DEFAULT 'No',
            FOREIGN KEY (event_id) REFERENCES events (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(event_id, user_id)
        );
    """)

    # Create feedback table
    conn.cursor().execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            event_id INT NOT NULL,
            rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
            comments TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (event_id) REFERENCES events (id),
            UNIQUE(user_id, event_id)
        );
    """)

    conn.commit()
    conn.close()


# Publish message to Pub/Sub
def publish_message(message_data):
    future = publisher.publish(topic_path, message_data.encode("utf-8"))
    logging.info("Publishing message: %s", message_data)
    print(f"Published message ID: {future.result()}")
    pull_and_process_messages()

def pull_and_process_messages():
    try:
        # Pull messages from the subscription
        response = subscriber.pull(
            subscription=subscription_path,
            max_messages=10,  # Adjust the number of messages to pull as needed
            timeout=10  # Timeout in seconds for waiting for messages
        )
        
        if not response.received_messages:
            print("No messages received.")
            return

        for received_message in response.received_messages:
            print(f"Received message: {received_message.message.data.decode('utf-8')}")
            logging.info("Received message: %s", received_message.message.data.decode('utf-8'))
            
            # Acknowledge the message
            subscriber.acknowledge(
                subscription=subscription_path,
                ack_ids=[received_message.ack_id]
            )
            print(f"Acknowledged message ID: {received_message.message.message_id}")
            logging.info("Acknowledged message ID: %s", received_message.message.message_id)
    except Exception as e:
        print(f"Error during message pull: {str(e)}")

@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.before_request
def before_request():
    # Record the start time of the request for latency
    request.start_time = time.time()

@app.after_request
def after_request(response):
    # Calculate latency and record it
    latency = time.time() - request.start_time
    REQUEST_LATENCY.labels(method=request.method, endpoint=request.endpoint).observe(latency)
    HTTP_REQUESTS.labels(method=request.method, endpoint=request.endpoint).inc()
    return response



# Send email notification
def send_email(subject, body, recipient_email):
    try:
        # Set up the email server
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()  # Secure the connection
        server.login(EMAIL_USER, EMAIL_PASSWORD)

        # Prepare the email content
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Send email
        server.sendmail(EMAIL_USER, recipient_email, msg.as_string())
        server.quit()
        print(f"Email sent to {recipient_email}")
    except Exception as e:
        print(f"Failed to send email: {str(e)}")




@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("events"))
    return render_template("login.html")


# RSVP Form route to show the form
@app.route("/rsvp_form/<int:event_id>", methods=["GET"])
def rsvp_form(event_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("rsvp.html", event_id=event_id)

@app.route("/filter_page", methods=["GET"])
def filter_page():
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("filter.html")


# Login route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_email"] = user["email"]
            return redirect(url_for("events"))
        else:
            return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

@app.route("/viewprofile", methods=["GET", "POST"])
def view_profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    conn = db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch user data from the database
    cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
    user = cursor.fetchone()
    
    if request.method == "POST":
        # If the form is submitted, update the user's profile information
        new_name = request.form.get("name")
        new_email = request.form.get("email")
        new_profile_image = request.files.get("profile_image")
        profile_image_url = user["profile_image"]

        if new_profile_image:
            # Upload the new image to GCS and get the URL
            profile_image_url = upload_image_to_gcs(new_profile_image)
        
        # Update the user's profile data in the database
        cursor.execute("""
            UPDATE users
            SET name = %s, email = %s, profile_image = %s
            WHERE id = %s
        """, (new_name, new_email, profile_image_url, session["user_id"]))
        conn.commit()
        
        # Update the session variables
        session["user_email"] = new_email  # Update the session email if changed
        
        # Redirect to the updated profile page
        return render_template("view_profile.html", user=user, success="True")
    
    cursor.close()
    conn.close()

    return render_template("view_profile.html", user=user)



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = generate_password_hash(request.form.get("password"))

        try:
            conn = db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                (name, email, password),
            )
            conn.commit()
            cursor.close()
            conn.close()
            return render_template("register.html", success=True)
        except mysql.connector.IntegrityError:
            return render_template("register.html", email_exists=True)

    return render_template("register.html")



# Logout route
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/filter_events", methods=["GET", "POST"])
def filter_events():
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Establish MySQL connection
    conn = db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
    user = cursor.fetchone()

    # Get filter parameters from the form
    location_filter = request.form.get('location')
    date_filter = request.form.get('date')
    if date_filter:
        date_modified_filter = datetime.strptime(date_filter, '%Y-%m-%d').date()
    else:
        date_modified_filter = None
    category_filter = request.form.get('category')

    # Build SQL query with dynamic filters
    query = "SELECT * FROM events WHERE DATE(event_date) >= %s"  # Filter events greater than today
    params = [datetime.now().date()]  # Pass current date as the base filter

    if location_filter:
        query += " AND location LIKE %s"
        params.append(f"%{location_filter}%")
    if date_filter:
        query += " AND DATE(event_date) LIKE %s"
        params.append(f"%{date_modified_filter}%")
    if category_filter:
        query += " AND category LIKE %s"
        params.append(f"%{category_filter}%")

    # Execute query with filters
    cursor.execute(query, params)
    events = cursor.fetchall()

    # Get feedback for the logged-in user
    cursor.execute("SELECT * FROM feedback WHERE user_id = %s", (session["user_id"],))
    feedback_records = cursor.fetchall()
    feedback_found = {}

    # Loop through feedback records and update the dictionary
    for feedback in feedback_records:
        feedback_found[feedback['event_id']] = True

    # Get the RSVP status for the logged-in user for each event
    rsvp_status = {}
    for event in events:
        event['event_date'] = event['event_date'].date()
        cursor.execute(
            "SELECT status FROM rsvps WHERE event_id = %s AND user_id = %s",
            (event["id"], session["user_id"]),
        )
        rsvp = cursor.fetchone()
        rsvp_status[event["id"]] = rsvp["status"] if rsvp else None

    cursor.close()
    conn.close()

    current_date = datetime.now().date()
    return render_template("events.html", events=events, rsvp_status=rsvp_status, current_user_id=session["user_id"], current_date=current_date, feedback_found=feedback_found,profile_image=user['profile_image'])

# Events route
@app.route("/events")
def events():
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Establish MySQL connection
    conn = db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
    user = cursor.fetchone()

    # Get current date
    current_date = datetime.now().date()

    # Fetch future events
    cursor.execute("SELECT * FROM events WHERE DATE(event_date) >= %s", (current_date,))
    events = cursor.fetchall()

    # Get feedback records for the logged-in user
    cursor.execute("SELECT * FROM feedback WHERE user_id = %s", (session["user_id"],))
    feedback_records = cursor.fetchall()
    feedback_found = {}

    # Loop through feedback records and update the dictionary
    for feedback in feedback_records:
        feedback_found[feedback['event_id']] = True

    # Get the RSVP status for the logged-in user for each event
    rsvp_status = {}
    for event in events:
        event['event_date'] = event['event_date'].date()
        cursor.execute(
            "SELECT status FROM rsvps WHERE event_id = %s AND user_id = %s",
            (event["id"], session["user_id"]),
        )
        rsvp = cursor.fetchone()
        rsvp_status[event["id"]] = rsvp["status"] if rsvp else None

    # Close cursor and connection
    cursor.close()
    conn.close()

    # Get the current date as a datetime object
    current_date = datetime.now().date()

    return render_template(
        "events.html",
        events=events,
        rsvp_status=rsvp_status,
        current_user_id=session["user_id"],
        current_date=current_date,  # Now current_date is a datetime object
        feedback_found=feedback_found,
        profile_image = user['profile_image']
    )


# Past Events route
@app.route("/past_events")
def past_events():
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Establish MySQL connection
    conn = db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get current date
    current_date = datetime.now().date()

    # Fetch future events
    cursor.execute("SELECT * FROM events WHERE DATE(event_date) < %s", (current_date,))
    events = cursor.fetchall()

    # Get feedback records for the logged-in user
    cursor.execute("SELECT * FROM feedback WHERE user_id = %s", (session["user_id"],))
    feedback_records = cursor.fetchall()
    feedback_found = {}

    # Loop through feedback records and update the dictionary
    for feedback in feedback_records:
        feedback_found[feedback['event_id']] = True

    # Get the RSVP status for the logged-in user for each event
    rsvp_status = {}
    for event in events:
        cursor.execute(
            "SELECT status FROM rsvps WHERE event_id = %s AND user_id = %s",
            (event["id"], session["user_id"]),
        )
        rsvp = cursor.fetchone()
        rsvp_status[event["id"]] = rsvp["status"] if rsvp else None

    # Close cursor and connection
    cursor.close()
    conn.close()

    # Get the current date as a datetime object
    current_date = datetime.now()

    return render_template(
        "past_events.html",
        events=events,
        rsvp_status=rsvp_status,
        current_user_id=session["user_id"],
        current_date=current_date,  # Now current_date is a datetime object
        feedback_found=feedback_found,
    )


# Create event route
@app.route("/create_event", methods=["GET", "POST"])
def create_event():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        
        title = request.form.get("title")
        description = request.form.get("description")
        event_date = request.form.get("event_date")
        location = request.form.get("location")
        category = request.form.get("category")  # Get category from the form

        # Handle image upload
        image_filename = None
        if 'image' in request.files:
            image = request.files['image']
            if image and allowed_file(image.filename):
                image_filename = upload_image_to_gcs(image)

        # Establish connection to the MySQL database
        conn = db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)

            # Insert the event data into the 'events' table, including the category
            cursor.execute(
                """
                INSERT INTO events (title, description, event_date, location, category, user_id, image)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (title, description, event_date, location, category, session["user_id"], image_filename)
            )
            conn.commit()

            # Publish event creation notification
            message = f"New Event Created: {title} on {event_date} at {location} in the {category} category"
            publish_message(message)

            # Send email notifications to all users
            cursor.execute("SELECT email FROM users")
            users = cursor.fetchall()

            # Close cursor and connection
            cursor.close()
            conn.close()

            # Send email to each user
            for user in users:
                send_email(
                    subject=f"New Event Created: {title}",
                    body=f"Dear user, a new event has been created: {title}. \nEvent Date: {event_date}\nLocation: {location}\nCategory: {category}\nDescription: {description}",
                    recipient_email=user['email']
                )

        return redirect(url_for("events"))

    return render_template("create_event.html", header="Create", today = datetime.today().strftime('%Y-%m-%d'))


# RSVP route
@app.route("/rsvp", methods=["POST"])
def rsvp():
    if "user_id" not in session:
        return redirect(url_for("login"))

    event_id = request.form.get("event_id")
    status = request.form.get("status")

    if not event_id or not status:
        return "Invalid RSVP submission", 400

    conn = db_connection()

    try:
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
            event = cursor.fetchone()

            cursor.execute("SELECT * FROM users WHERE id = %s", (event["user_id"],))
            user = cursor.fetchone()


            # Insert or update RSVP into the database (using MySQL syntax for "ON DUPLICATE KEY UPDATE")
            cursor.execute(
                """
                INSERT INTO rsvps (event_id, user_id, status)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE status = %s
                """,
                (event_id, session["user_id"], status, status)
            )
            conn.commit()

            # Publish RSVP notification
            message = f"User {session['user_email']} RSVP'd with '{status}' for Event ID {event_id}"
            publish_message(message)

            # Send email notification
            subject = f"Your RSVP for event: {event_id}"

            body = f"""Dear {session['user_email']},

            You have RSVP'd for the event with the following details:

            Event ID: {event_id}
            Status: {status}

            Event Details:
            Title: {event['title']}
            Description: {event['description']}
            Date: {event['event_date']}
            Location: {event['location']}

            We are excited to have you join us and look forward to seeing you there!

            Thank you for your response.
            """

            send_email(subject, body, session['user_email'])


            # Send email notification to the event owner
            subject_owner = f"RSVP Notification for Your Event: {event_id}"

            body_owner = f"""Dear {user['email']},

            The following user has RSVP'd for your event:

            User Email: {session['user_email']}
            Event ID: {event_id}
            RSVP Status: {status}

            Thank you for organizing the event!

            Best regards,
            Your Event Platform Team
            """

            send_email(subject_owner, body_owner, user['email'])


        else:
            return "Database connection error", 500

    except Exception as e:
        conn.rollback()
        return f"Error occurred: {str(e)}", 500

    finally:
        if conn:
            cursor.close()
            conn.close()

    return redirect(url_for("events"))

#feedback submission route
@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():
    if "user_id" not in session:
        return redirect(url_for("login"))

    event_id = request.form.get("event_id")
    rating = request.form.get("rating")
    feedback_text = request.form.get("comments")

    # Validate the form data
    if not event_id or not rating or not feedback_text:
        return "Invalid feedback submission", 400

    # Ensure rating is an integer and is between 1 and 5
    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            return "Rating must be between 1 and 5", 400
    except ValueError:
        return "Invalid rating", 400

    conn = db_connection()

    try:
        if conn:
            cursor = conn.cursor()

            # Insert feedback into the database (using MySQL syntax for "ON DUPLICATE KEY UPDATE")
            cursor.execute(
                """
                INSERT INTO feedback (user_id, event_id, rating, comments)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE rating = %s, comments = %s
                """,
                (session["user_id"], event_id, rating, feedback_text, rating, feedback_text)
            )
            conn.commit()

        else:
            return "Database connection error", 500

    except Exception as e:
        conn.rollback()
        return f"Error occurred: {str(e)}", 500

    finally:
        if conn:
            cursor.close()
            conn.close()

    return redirect(url_for("events"))

# Edit event route
@app.route("/edit_event/<int:event_id>", methods=["GET", "POST"])
def edit_event(event_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = db_connection()

    # Get the event details to edit
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM events WHERE id = %s AND user_id = %s", (event_id, session["user_id"]))
    event = cursor.fetchone()

    if not event:
        cursor.close()
        conn.close()
        return "Event not found or you do not have permission to edit this event.", 404

    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        event_date = request.form.get("event_date")
        location = request.form.get("location")
        category = request.form.get("category")  # Get the selected category
        image_filename = event["image"]

        # Handle image upload if present
        if 'image' in request.files:
            image = request.files['image']
            if image and allowed_file(image.filename):
                image_filename = upload_image_to_gcs(image)

        # Update event in the database
        cursor.execute(
            """
            UPDATE events 
            SET title = %s, description = %s, event_date = %s, location = %s, category = %s, image = %s 
            WHERE id = %s
            """,
            (title, description, event_date, location, category, image_filename, event_id)
        )
        
        # Send email to users notifying them about the event update
        cursor.execute("SELECT email FROM users")
        users = cursor.fetchall()

        conn.commit()

        # Publish message about the event update
        message = f"Event Updated: {title} on {event_date} at {location} in the {category} category"
        publish_message(message)

        # Send email notifications
        for user in users:
            send_email(
                subject=f"Event Updated: {title}",
                body=f"Dear user, the event you were interested in has been updated.\n\n"
                f"Event Title: {title}\n"
                f"Event Date: {event_date}\n"
                f"Location: {location}\n"
                f"Category: {category}\n\n"
                f"Please check the updated details. We hope to see you there!",
                recipient_email=user['email']
            )

        # Clean up database connection
        cursor.close()
        conn.close()

        return redirect(url_for("events"))

    # Close connection and return the template for editing
    cursor.close()
    conn.close()
    return render_template("create_event.html", event=event, header="Edit", today=datetime.today().strftime('%Y-%m-%d'))


@app.route("/feedback/<int:event_id>", methods=["GET", "POST"])
def feedback(event_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("feedback.html", event_id=event_id)

# Cancel event route
@app.route("/cancel_event/<int:event_id>", methods=["POST"])
def cancel_event(event_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = db_connection()

    cursor = conn.cursor(dictionary=True)

    # Check if the event exists and belongs to the logged-in user
    cursor.execute("SELECT * FROM events WHERE id = %s AND user_id = %s", (event_id, session["user_id"]))
    event = cursor.fetchone()

    if not event:
        cursor.close()
        conn.close()
        return "Event not found or you do not have permission to cancel this event.", 404

    #DELETE ASSOCIATED RSVP
    cursor.execute("DELETE FROM rsvps WHERE event_id = %s", (event_id,))

    # Delete the event
    cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
    conn.commit()

    # Publish message about event cancellation
    message = f"Event Cancelled: {event['title']} on {event['event_date']} at {event['location']}"
    publish_message(message)

    # Get all users' emails
    cursor.execute("SELECT email FROM users")
    users = cursor.fetchall()

    # Close the connection and cursor
    cursor.close()
    conn.close()

    # Send email notifications to all users about the cancellation
    for user in users:
        send_email(
            subject=f"Event Cancelled: {event['title']}",
            body=f"Dear user, the event you were interested in has been cancelled.\n\n"
            f"Event Title: {event['title']}\n"
            f"Event Date: {event['event_date']}\n"
            f"Location: {event['location']}\n\n"
            f"Sorry for any inconvenience caused.",
            recipient_email=user['email']
        )

    return redirect(url_for("events"))



if __name__ == "__main__":
    init_db()  # Initialize database on startup
    check_event_reminders()
    app.run(host='0.0.0.0', debug=True)
