# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Assuming your service account file is located at /path/to/your/service-account-key.json
COPY  tidy-tine-437718-h3-75853ecdd578.json /app/service-account-key.json

# Set the environment variable
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/service-account-key.json


# Make port 5000 available to the world outside the container
EXPOSE 5000

# Define environment variable
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0


# Run the Flask app when the container launches
CMD ["flask", "run"]
