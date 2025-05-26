"""
COMP5349 Assignment: Image Upload App with AWS Services

IMPORTANT:
Before running this application, ensure that you update the following configurations:
1. Replace the AWS S3 bucket name (`S3_BUCKET`) with your own S3 bucket.
2. Update the RDS MySQL database credentials (`DB_HOST`, `DB_USER`, `DB_PASSWORD`).
3. Ensure all necessary dependencies are installed by running the provided setup script.

NOTE: Image captioning is now handled automatically by the Lambda function when images are uploaded to S3.
"""

# To use on an AWS Linux instance
# #!/bin/bash
# sudo yum install python3-pip -y
# pip install flask
# pip install mysql-connector-python
# pip install boto3 werkzeug
# sudo yum install -y mariadb105

import boto3  # AWS S3 SDK
import mysql.connector  # MySQL database connector
from flask import Flask, request, render_template, jsonify  # Web framework
from werkzeug.utils import secure_filename  # Secure filename handling
import base64  # Encoding image data for display
from io import BytesIO  # Handling in-memory file objects

# Flask app setup
app = Flask(__name__)

# AWS S3 Configuration, REPLACE with your S3 bucket
S3_BUCKET = "caption-vram0324"
S3_REGION = "us-east-1"

def get_s3_client():
    """Returns a new S3 client that automatically refreshes credentials if using an IAM role."""
    return boto3.client("s3", region_name=S3_REGION)

# Database Configuration, REPLACE with your RDS credentials
DB_HOST = "captions-db.cb1s8yxr7oib.us-east-1.rds.amazonaws.com"
DB_NAME = "image_caption_db"
DB_USER = "admin"
DB_PASSWORD = "ramjay2281"

def get_db_connection():
    """
    Establishes a connection to the MySQL RDS database.

    :return: Database connection object or None if connection fails
    """
    try:
        connection = mysql.connector.connect(
            host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
        )
        return connection
    except mysql.connector.Error as err:
        print("Error connecting to database:", err)
        return None

# Allowed file types for upload
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    """
    Checks if the uploaded file has a valid extension.

    :param filename: Name of the uploaded file
    :return: True if valid, False otherwise
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def upload_form():
    """Render the homepage with the file upload form."""
    return render_template("index.html")

@app.route("/upload", methods=["GET", "POST"])
def upload_image():
    """
    Handles image upload and stores the file in AWS S3.
    Caption generation is handled automatically by Lambda function.
    """
    if request.method == "POST":
        if "file" not in request.files:
            return render_template("upload.html", error="No file selected")

        file = request.files["file"]

        if file.filename == "":
            return render_template("upload.html", error="No file selected")

        if not allowed_file(file.filename):
            return render_template("upload.html", error="Invalid file type")

        filename = secure_filename(file.filename)
        file_data = file.read()  # Read file as binary

        # Upload file to S3
        try:
            s3 = get_s3_client()  # Get a fresh S3 client
            s3.upload_fileobj(BytesIO(file_data), S3_BUCKET, filename)
            print(f"Successfully uploaded {filename} to S3")
        except Exception as e:
            return render_template("upload.html", error=f"S3 Upload Error: {str(e)}")

        # Prepare image for frontend display using Base64 encoding
        encoded_image = base64.b64encode(file_data).decode("utf-8")
        file_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{filename}"
        
        return render_template(
            "upload.html", 
            image_data=encoded_image, 
            file_url=file_url, 
            success_message=f"Image '{filename}' uploaded successfully! Caption will be generated automatically.",
            filename=filename
        )

    return render_template("upload.html")

@app.route("/gallery")
def gallery():
    """
    Retrieves images and their captions from the database,
    generates pre-signed URLs for secure access, and renders the gallery page.
    """
    try:
        connection = get_db_connection()
        if connection is None:
            return render_template("gallery.html", error="Database Error: Unable to connect to the database.")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT image_key, caption, uploaded_at FROM captions ORDER BY uploaded_at DESC")
        results = cursor.fetchall()
        connection.close()

        images_with_captions = []
        for row in results:
            try:
                presigned_url = get_s3_client().generate_presigned_url(
                    "get_object",
                    Params={"Bucket": S3_BUCKET, "Key": row["image_key"]},
                    ExpiresIn=3600,  # URL expires in 1 hour
                )
                images_with_captions.append({
                    "url": presigned_url,
                    "caption": row["caption"] if row["caption"] else "Caption being generated...",
                    "filename": row["image_key"],
                    "uploaded_at": row["uploaded_at"]
                })
            except Exception as e:
                print(f"Error generating presigned URL for {row['image_key']}: {e}")
                continue

        return render_template("gallery.html", images=images_with_captions)

    except Exception as e:
        return render_template("gallery.html", error=f"Database Error: {str(e)}")

@app.route("/check_caption/<filename>")
def check_caption(filename):
    """
    API endpoint to check if a caption has been generated for a specific image.
    Useful for polling until Lambda function completes caption generation.
    """
    try:
        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT caption FROM captions WHERE image_key = %s", (filename,))
        result = cursor.fetchone()
        connection.close()
        
        if result and result["caption"]:
            return jsonify({
                "status": "ready",
                "caption": result["caption"]
            })
        else:
            return jsonify({
                "status": "processing",
                "message": "Caption is being generated..."
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
