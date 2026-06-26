import os
import json
import tempfile
import boto3
from office365.sharepoint.client_context import ClientContext

# ====================== CONFIGURATION SECTION ======================
# Must be the SharePoint *site* URL (not login.microsoftonline.com).
# Example: https://contoso.sharepoint.com/sites/HKGI
SP_SITE_URL = "https://your-tenant.sharepoint.com/sites/YourSite"

# Server-relative folder path (must start with /).
# Example: /sites/YourSite/Shared Documents/General/...
SP_FOLDER_REL_PATH = "/sites/YourSite/Shared Documents/General/HK GI - Red Bull/HKGI Use Cases/Operations & Underwriting/Home Product (Renewal + NB)/Report39_Everyday"

S3_BUCKET_NAME = "hkgi-amazonquick-report39-prod"
S3_UPLOAD_FOLDER = "pending"

AWS_REGION = "us-east-1"
SECRET_STORE_NAME = "dev/sharepoint/hkgi"
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


def connect_sharepoint():
    """
    Connect to SharePoint using Entra ID app-only auth (MSAL client credentials).

    Do NOT use AuthenticationContext + acquire_token_for_app — that is the retired
    ACS (SharePoint app-only) flow and causes AADSTS900023 tenant 'none' errors when
    paired with Azure AD app registration credentials.
    """
    secrets = get_sharepoint_secrets()

    tenant_id = secrets["TENANT_ID"]
    client_id = secrets["CLIENT_ID"]
    client_secret = secrets["CLIENT_SECRET"]

    print("SharePoint app credentials loaded from AWS Secrets Manager.")
    print(f"Targeting tenant ID: {tenant_id}")
    print(f"App registration ID: {client_id}")

    ctx = ClientContext(SP_SITE_URL).with_client_secret(
        tenant=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )

    web = ctx.web.get().execute_query()
    print(f"Successfully connected to SharePoint site: {web.properties.get('Title', SP_SITE_URL)}")
    return ctx


def get_latest_csv_file(ctx):
    """Scans target SharePoint path and returns the newest CSV document."""
    folder_path = SP_FOLDER_REL_PATH if SP_FOLDER_REL_PATH.startswith("/") else f"/{SP_FOLDER_REL_PATH}"
    target_folder = ctx.web.get_folder_by_server_relative_path(folder_path)
    all_files = target_folder.files
    ctx.load(all_files)
    ctx.execute_query()

    csv_file_list = [f for f in all_files if f.properties["Name"].lower().endswith(".csv")]
    if not csv_file_list:
        raise FileNotFoundError("No CSV files found in the target SharePoint directory")

    csv_file_list.sort(key=lambda x: x.properties["TimeLastModified"], reverse=True)
    latest_file = csv_file_list[0]
    print(f"Found latest input CSV file: {latest_file.properties['Name']}")
    return latest_file


def download_sp_file(ctx, sp_file, local_temp_path):
    """Streams file bytes from SharePoint into the Lambda /tmp directory."""
    with open(local_temp_path, "wb") as local_f:
        ctx.download_file(sp_file.serverRelativeUrl, local_f)
    print(f"File cached at temporary path: {local_temp_path}")


def upload_to_s3(local_file_path, s3_object_key):
    """Uploads the cached file to the configured S3 bucket."""
    s3_client = boto3.client("s3", region_name=AWS_REGION)
    s3_client.upload_file(
        Filename=local_file_path,
        Bucket=S3_BUCKET_NAME,
        Key=s3_object_key,
        ExtraArgs={"ContentType": "text/csv"},
    )
    print(f"Upload complete -> s3://{S3_BUCKET_NAME}/{s3_object_key}")


def lambda_handler(event, context):
    """AWS Lambda entry point."""
    tmp_file_path = None
    try:
        sp_ctx = connect_sharepoint()
        latest_csv = get_latest_csv_file(sp_ctx)
        file_name = latest_csv.properties["Name"]
        s3_key = f"{S3_UPLOAD_FOLDER}/{file_name}"

        with tempfile.NamedTemporaryFile(delete=False) as tmp_handle:
            tmp_file_path = tmp_handle.name

        download_sp_file(sp_ctx, latest_csv, tmp_file_path)
        upload_to_s3(tmp_file_path, s3_key)

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
