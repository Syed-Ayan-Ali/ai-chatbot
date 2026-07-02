import os
import json
import tempfile
from urllib.parse import quote

import boto3
import msal
import requests

# ====================== CONFIGURATION SECTION ======================
SP_SITE_URL = "https://bolttechio.sharepoint.com/sites/GT-AgenticApex"
SP_FOLDER_REL_PATH = "Shared Documents/General/HK GI - Red Bull/HKGI Use Cases/Operations & Underwriting/Home Product (Renewal + NB)/Report39_Everyday"
TARGET_FILE_NAME = "Report_39.xlsx"

S3_BUCKET_NAME = "hkgi-amazonquick-report39-prod"
S3_UPLOAD_FOLDER = "pending"
AWS_REGION = "us-east-1"
SECRET_STORE_NAME = "prod/sharepoint/hkgi"

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
SITE_ID = "bolttechio.sharepoint.com,b68100ba-ae01-47ed-afe1-a26dd71e5eb2,64bf4598-c258-45f8-aabe-395d1e845951"
# ===================================================================


def get_sharepoint_secrets():
    """Dynamically retrieves decrypted variables from AWS Secrets Manager."""
    client = boto3.client("secretsmanager", region_name=AWS_REGION)
    try:
        response = client.get_secret_value(SecretId=SECRET_STORE_NAME)
        return json.loads(response["SecretString"])
    except Exception as e:
        print(f"Failed to retrieve secrets from AWS Secrets Manager: {str(e)}")
        raise


def get_graph_token():
    """Acquires a Microsoft Graph access token using client credentials."""
    secrets = get_sharepoint_secrets()
    tenant_id = secrets["TENANT_ID"]
    client_id = secrets["CLIENT_ID"]
    client_secret = secrets["CLIENT_SECRET"]

    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

    if "access_token" not in result:
        raise PermissionError(f"Azure token exchange failed: {result}")

    print("Graph token acquired successfully.")
    return result["access_token"]


def get_drive_id(token):
    """Gets the default document library drive ID for the site."""
    url = f"{GRAPH_BASE_URL}/sites/{SITE_ID}/drive"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    drive_id = resp.json()["id"]
    print(f"Drive ID: {drive_id}")
    return drive_id


def get_target_file(token, drive_id, file_name=TARGET_FILE_NAME):
    """Gets Report_39.xlsx from the target SharePoint folder by path."""
    folder_path = SP_FOLDER_REL_PATH.replace("Shared Documents/", "")
    item_path = quote(f"{folder_path}/{file_name}", safe="/")
    url = f"{GRAPH_BASE_URL}/drives/{drive_id}/root:/{item_path}"
    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(url, headers=headers)
    if resp.status_code == 404:
        raise FileNotFoundError(
            f"'{file_name}' not found in SharePoint folder: {SP_FOLDER_REL_PATH}"
        )
    resp.raise_for_status()

    file_item = resp.json()
    print(f"Found target file: {file_item['name']}")
    return file_item


def download_file(token, download_url, local_path):
    """Downloads file content to local temp path."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(download_url, headers=headers, stream=True)
    resp.raise_for_status()

    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"File cached at: {local_path}")


def upload_to_s3(local_file_path, s3_object_key, content_type):
    """Uploads the cached file to the configured S3 bucket."""
    s3_client = boto3.client("s3", region_name=AWS_REGION)
    s3_client.upload_file(
        Filename=local_file_path,
        Bucket=S3_BUCKET_NAME,
        Key=s3_object_key,
        ExtraArgs={"ContentType": content_type},
    )
    print(f"Upload complete -> s3://{S3_BUCKET_NAME}/{s3_object_key}")


def lambda_handler(event, context):
    """AWS Lambda entry point."""
    tmp_file_path = None
    try:
        token = get_graph_token()
        drive_id = get_drive_id(token)
        target_file = get_target_file(token, drive_id)

        file_name = target_file["name"]
        download_url = target_file["@microsoft.graph.downloadUrl"]
        s3_key = f"{S3_UPLOAD_FOLDER}/{file_name}"
        content_type = target_file.get("file", {}).get(
            "mimeType",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        with tempfile.NamedTemporaryFile(delete=False) as tmp_handle:
            tmp_file_path = tmp_handle.name

        download_file(token, download_url, tmp_file_path)
        upload_to_s3(tmp_file_path, s3_key, content_type)

        return {
            "statusCode": 200,
            "body": f"Pipeline executed successfully. Processed and sent '{file_name}' to S3.",
        }

    except Exception as err:
        print(f"Pipeline execution failed: {str(err)}")
        return {
            "statusCode": 500,
            "body": f"Pipeline error encountered: {str(err)}",
        }
    finally:
        if tmp_file_path is not None and os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)
            print("Temporary file deleted.")
