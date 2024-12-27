# Community Event Organizer

**Team Members:**  
- Saiteja Poluka  
- Ashmitha Gatla  

## Project Description

The Community Event Organizer is a web application that allows users to create, manage, and explore community events. Users can RSVP for events, filter events based on preferences, post feedback for events, and receive notifications. The project leverages Google Cloud services to provide a scalable, reliable, and efficient solution.

---

## Features

- **User Authentication**: Secure login and user session management.  
- **Event Management**: Create, edit, delete, and filter events.  
- **RSVP Management**: Register for events and receive confirmations.  
- **Real-Time Notifications**: Powered by Google Pub/Sub.  
- **File Uploads**: Event images and static assets stored securely in Google Cloud Storage.  
- **Performance Monitoring**: Integrated with Prometheus for monitoring.  
- **Email Notifications**: Automated email updates using SMTP.  

---

## Tech Stack

- **Backend**: Flask (Python)  
- **Frontend**: HTML, CSS, JavaScript  
- **Database**: Google Cloud SQL (MySQL)  
- **Deployment**: Google Cloud Compute Engine (VM)  
- **Storage**: Google Cloud Storage  
- **Notification Service**: Google Pub/Sub  
- **Monitoring**: Prometheus  
- **External Services**: SMTP for email notifications  

---

## Prerequisites

1. **Google Cloud Account** with the following services enabled:
   - Compute Engine
   - Cloud SQL
   - Cloud Storage
   - Pub/Sub  
2. **Python 3.8+** installed locally or on the VM.  
3. **Git** for version control.  

---

## Installation and Deployment Instructions

### Clone the Repository

```bash
git clone https://github.com/cu-csci-4253-datacenter-fall-2024/finalproject-final-project-team-54.git
cd finalproject-final-project-team-54
```

### Setting Up the Virtual Machine (VM)

1. **Create a Google Cloud VM**:
   - Select a machine type and install the necessary operating system (Ubuntu is recommended).  

2. **Access the VM via SSH**:
   ```bash
   gcloud compute ssh <vm-name> --zone=<zone>
   ```

3. **Install Dependencies**:
   - Update the package list:
     ```bash
     sudo apt update && sudo apt upgrade -y
     ```
   - Install Python and pip:
     ```bash
     sudo apt install python3 python3-pip -y
     ```

### Install Project Dependencies

Inside the project directory, run:
```bash
pip install -r requirements.txt
```

### Configure Sensitive Data

1. Open the `app.py` file in a text editor.
2. Replace placeholders with your actual values for the following variables:

   ```python
   # MySQL Configuration
   MYSQL_HOST = 'your-cloud-sql-host'
   MYSQL_USER = 'your-database-username'
   MYSQL_PASSWORD = 'your-database-password'
   MYSQL_DB = 'community_event_organizer'

   # Pub/Sub Configuration
   PROJECT_ID = "your-google-cloud-project-id"
   TOPIC_ID = "event-updates"
   SUBSCRIPTION_ID = "event-updates-sub"

   # Cloud Storage Configuration
   BUCKET_NAME = 'your-google-cloud-storage-bucket'

   # Email Service Configuration
   EMAIL_HOST = "smtp.gmail.com"
   EMAIL_PORT = 587
   EMAIL_USER = "your-email@gmail.com"
   EMAIL_PASSWORD = "your-email-password-or-app-specific-password"
   ```

### Run the Application

1. Start the Flask server:
   ```bash
   python app.py
   ```

2. Access the application in your browser:
   ```
   http://<vm-external-ip>:5000
   ```

---

## Monitoring and Debugging

- **Prometheus** is set up for monitoring system health. Use the Prometheus web interface to view metrics.  
- For troubleshooting, check logs in the VM:
  ```bash
  tail -f /var/log/app.log
  ```

