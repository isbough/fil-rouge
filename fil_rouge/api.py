import os
import boto3
import logging
import csv
import codecs
import pandas as pd
import time
import json
import urllib
import base64
from flask import Flask, request, jsonify, make_response
from constants import (
    PATH_TO_UPLOADED_FILES_FOLDER,
    ALLOWED_EXTENSIONS,
    BUCKET_NAME,
    BUCKET_URI,
)
from helpers import allowed_file
from werkzeug.exceptions import BadRequest
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from botocore.exceptions import ClientError
from PIL import Image
from PIL.ExifTags import TAGS
from PyPDF2 import PdfFileReader
from io import BytesIO, StringIO, TextIOWrapper
from docx import Document
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

# swagger_destination_path = './swagger.json'

# # Create the bluepints
# blueprint = Blueprint('objects', __name__)

app = Flask(__name__)
app.config.from_pyfile("config.py")

# # Create swagger version 3.0 generator
# generator = Generator.of(SwaggerVersion.VERSION_THREE)

s3 = boto3.resource("s3")
bucket = s3.Bucket(BUCKET_NAME)


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({"error": "End Point Not found"}), 404)


@app.errorhandler(500)
def not_found(error):
    return make_response(jsonify({"error": "Internal Server Error"}), 500)


@app.route("/upload", methods=["POST"])
def upload_file():
    response = {}
    if request.method == "POST":
        if "file" not in request.files:
            response["file_upload"] = "No file uploaded"
            return jsonify(response)
        file = request.files["file"]
        second_file = request.files["file"]
        if file.filename == "":
            response["file_upload"] = "No file selected"
            return jsonify(response)
        elif not allowed_file(file.filename):
            response["file_upload"] = "File format not supported"
            return jsonify(response)
        if file:
            filename = file.filename
            if upload_file_to_s3(request,file):
                file_metadata = generate_final_metadata(file)
                return jsonify(file_metadata)
            else:
                response["file_upload"] = "Problem occured, cannot return metadata"
                return response


def generate_final_metadata(file):
    metadata = {}
    file_content = {}
    file_metadata = {}
    final_metadata = {}
    file.seek(0)
    content = request.files["file"].read()
    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    metadata["file_name"] = file.filename
    metadata["file_size"] = file_length
    metadata["mime_type"] = file.mimetype
    filename, extension = os.path.splitext(file.filename)
    if extension in {".jpg", ".jpeg", ".png", ".gif", ".pdf", ".mp3", ".mp4", ".docx"}:
        file_content["data"] = base64.b64encode(content)
        file_content["data"] = file_content["data"].decode("utf-8")
    else:
        file_content["data"] = content.decode("utf-8")
    file_metadata = generate_metadata(file)
    metadata.update(file_metadata)
    final_metadata["metadonnees"] = metadata
    final_metadata["donnees"] = file_content
    return final_metadata


def generate_metadata(file):

    filename, extension = os.path.splitext(file.filename)
    filename = file.filename
    if extension in {".jpg", ".jpeg", ".png", ".gif"}:
        image_metadata = generate_image_metadata(file, filename)
        if extension in {".jpg", ".png"}:
            image_rekognition = {}
            image_rekognition["Rekognition - computer vision"] = detect_labels_image(filename)
            image_metadata.update(image_rekognition)
        return image_metadata

    if extension == ".pdf":
        pdf_metadata = generate_pdf_metadata(file, filename)
        return pdf_metadata

    if extension == ".csv":
        csv_metadata = generate_csv_metadata(file, filename)
        return csv_metadata

    if extension == ".txt":
        sentiment_analysis = {}
        txt_metadata, data = generate_txt_metadata(file, filename)
        comprehend_metadata = comprehend_text(data)
        sentiment_analysis["sentiment-analysis"] = comprehend_metadata
        txt_metadata.update(sentiment_analysis)
        return txt_metadata

    if extension == ".mp3":
        mp3_metadata = generate_mp3_metadata(file, filename)
        text = transcribe_audio_file(filename)
        comprehend_metadata = comprehend_text(text)
        mp3_metadata.update(comprehend_metadata)
        return mp3_metadata

    if extension == ".mp4":
        mp4_metadata = generate_mp4_metadata(file, filename)
        return mp4_metadata

    if extension == ".docx":
        docx_metadata = generate_docx_metadata(file, filename)
        return docx_metadata


def generate_image_metadata(file, object_key):
    image_metadata = {}
    response = {}
    object = bucket.Object(object_key)
    image_file = object.get()
    file_stream = image_file["Body"]

    try:
        img = Image.open(file_stream)
    except:
        response["file_upload"] = "Cannot open file"
        return response

    exif_data = img.getexif()
    if exif_data is not None:
        for tag_id in exif_data:
            tag = TAGS.get(tag_id, tag_id)
            data = exif_data.get(tag_id)
            if not isinstance(data, (float, int, str, list, dict, tuple)):
                continue
            image_metadata[tag] = data
    return image_metadata


def generate_pdf_metadata(file, object_key):
    pdf_metadata = {}
    object = bucket.Object(object_key)
    pdf_file = object.get()["Body"].read()
    pdfFile = PdfFileReader(BytesIO(pdf_file))

    xmpm = pdfFile.getXmpMetadata()
    if xmpm is not None:
        if xmpm.dc_title:
            pdf_metadata["Title"] = xmpm.dc_title
        if xmpm.xmp_createDate:
            pdf_metadata["Created"] = xmpm.xmp_createDate
        if xmpm.dc_subject:
            pdf_metadata["Subject"] = xmpm.dc_subject
        if xmpm.dc_description:
            pdf_metadata["Description"] = xmpm.dc_description
        if xmpm.dc_creator:
            pdf_metadata["Creator"] = xmpm.dc_creator
        if xmpm.xmp_modifyDate:
            pdf_metadata["Modified"] = xmpm.xmp_modifyDate

    return pdf_metadata


def generate_csv_metadata(file, object_key):
    csv_metadata = {}
    response = {}
    object = bucket.Object(object_key)
    df = pd.read_csv(BytesIO(object.get()["Body"].read()), encoding="utf8")
    columns = df.shape[1]
    rows = df.shape[0]
    null_values = df.isnull().sum(axis=1)
    csv_metadata["number_of_columns"] = columns
    csv_metadata["number_of_rows"] = rows
    csv_metadata["number_of_null_values"] = int(null_values[1].sum())
    return csv_metadata


def generate_docx_metadata(file, object_key):
    docx_metadata = {}
    object = bucket.Object(object_key)
    docx_file = object.get()["Body"].read()
    doc = Document(BytesIO(docx_file))
    prop = doc.core_properties
    if prop.author:
        docx_metadata["author"] = prop.author
    if prop.version:
        docx_metadata["version"] = prop.version
    if prop.modified:
        docx_metadata["modified"] = prop.modified
    if prop.language:
        docx_metadata["language"] = prop.language
    if prop.created:
        docx_metadata["created"] = prop.created
    if prop.content_status:
        docx_metadata["content_status"] = prop.content_status
    if prop.title:
        docx_metadata["title"] = prop.title
    if prop.last_modified_by:
        docx_metadata["last_modified_by"] = prop.last_modified_by
    if prop.keywords:
        docx_metadata["keywords"] = prop.keywords
    if prop.category:
        docx_metadata["category"] = prop.category
    if prop.identifier:
        docx_metadata["identifier"] = prop.identifier
    return docx_metadata


def generate_mp3_metadata(file, object_key):
    media_metadata = {}
    object = bucket.Object(object_key)
    media_file = object.get()["Body"].read()
    media = BytesIO(media_file)
    mp3 = MP3(media)
    if mp3.info.length:
        media_metadata["mp3_length_in_seconds"] = mp3.info.length
    if mp3.info.bitrate:
        media_metadata["mp3_bitrate"] = mp3.info.bitrate
    if mp3.info.mode:
        media_metadata["mp3_mode"] = mp3.info.mode
    if mp3.info.sample_rate:
        media_metadata["mp3_sample_rate_in_Hz"] = mp3.info.sample_rate
    return media_metadata


def generate_mp4_metadata(file, object_key):
    media_metadata = {}
    object = bucket.Object(object_key)
    media_file = object.get()["Body"].read()
    media = BytesIO(media_file)
    mp4 = MP4(media)
    if mp4.info.length:
        media_metadata["mp4_length_in_seconds"] = mp4.info.length
    if mp4.info.bitrate:
        media_metadata["mp4_bitrate"] = mp4.info.bitrate
    if mp4.info.sample_rate:
        media_metadata["mp4_sample_rate_in_Hz"] = mp4.info.sample_rate
    if mp4.info.channels:
        media_metadata["mp4_number_of_audio_channels"] = mp4.info.channels
    return media_metadata


def generate_txt_metadata(file, object_key):
    txt_metadata = {}
    lines_count = 0
    object = bucket.Object(object_key)
    txt_file = object.get()["Body"].read()
    file = BytesIO(txt_file)
    file_string = TextIOWrapper(file, encoding="utf-8")
    # count the numbers of wordsd in the file
    data = file_string.read()
    lines = data.split("\n")
    words_count = data.split()
    # count the number of lines in the file
    for l in lines:
        if l:
            lines_count = lines_count + 1
    txt_metadata["number_of_lines"] = lines_count
    txt_metadata["number_of_words"] = len(words_count)
    return txt_metadata,data


def upload_file_to_s3(request,file,object_name=None):
    if object_name is None:
        object_name = file.filename

    client = boto3.client("s3")

    try:
        #client.upload_file(file.filename,BUCKET_NAME,object_name)
        client.put_object(Body=file, Bucket= BUCKET_NAME, Key= object_name, ContentType=request.mimetype)
    except ClientError as e:
        logging.error(e)
        return False
    return True


def detect_labels_image(photo):
    labels = {}
    bounding_box = {}
    client = boto3.client("rekognition")
    response = client.detect_labels(
        Image={"S3Object": {"Bucket": BUCKET_NAME, "Name": photo}}, MaxLabels=10
    )
    # for label in response["Labels"]:
    #     labels["Name"] = label["Name"]
    #     labels["Confidence"] = str(label["Confidence"])
    #     for instance in label["Instances"]:
    #         bounding_box["Top"] = str(instance["BoundingBox"]["Top"])
    #         bounding_box["Left"] = str(instance["BoundingBox"]["Left"])
    #         bounding_box["Width"] = str(instance["BoundingBox"]["Width"])
    #         bounding_box["Height"] = str(instance["BoundingBox"]["Height"])
    #         bounding_box["Confidence"] = str(instance["Confidence"])
    #     labels["label"] = bounding_box
    for label in response["Labels"]:
        labels[label["Name"]] = label["Confidence"]
    return labels


def transcribe_audio_file(object_key):
    job_name = "JOB_name"
    job_uri = "https://s3.amazonaws.com/" + BUCKET_NAME + "/" + object_key
    transcribe = boto3.client("transcribe")
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": job_uri},
        MediaFormat="mp3",
        LanguageCode="en-US",
    )
    while True:
        status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        if status["TranscriptionJob"]["TranscriptionJobStatus"] in [
            "COMPLETED",
            "FAILED",
        ]:
            break
        print("Not ready yet...")
        time.sleep(2)
    if status["TranscriptionJob"]["TranscriptionJobStatus"] == "COMPLETED":
        response = urllib.request.urlopen(
            status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
        )
        data = json.loads(response.read())
        text = data["results"]["transcripts"][0]["transcript"]
        transcribe.delete_transcription_job(TranscriptionJobName=job_name)
    return text


def comprehend_text(text):
    new_sentiment_analysis = {}
    comprehend = boto3.client("comprehend")
    sentiment_analysis = comprehend.detect_sentiment(Text=text, LanguageCode="en")
    new_sentiment_analysis["Sentiment"] = sentiment_analysis["Sentiment"]
    new_sentiment_analysis["SentimentScore"] = sentiment_analysis["SentimentScore"]
    return new_sentiment_analysis


if __name__ == "__main__":
 #   app.run(host='0.0.0.0')
    app.run()
