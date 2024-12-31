from OpenreviewScrape.definitions import PROJECT_ROOT_DIR
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
import google.auth
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


def get_folders(drive, folder_id="root", prefix=""):
    lst = drive.ListFile({'q': f"'{folder_id}' in parents and trashed=false"}).GetList()
    result = []
    for f in lst:
        # print(f"Title: {f['title']}, ID: {f['id']}")
        if f['mimeType'] == 'application/vnd.google-apps.folder':
            tmp = get_folders(drive, f['id'], prefix=f"{prefix}/{f['title']}")
            result.extend(tmp)
        else:
            result.append((f"{prefix}/{f['title']}", f['id']))
    return result


def get_gdrive_login_credentials():
    gauth = GoogleAuth()

    gauth.LoadCredentialsFile(f"{PROJECT_ROOT_DIR}/credentials/mycreds.txt")
    if gauth.credentials is None or gauth.access_token_expired:
        gauth.LoadClientConfigFile(f"{PROJECT_ROOT_DIR}/credentials/client_secret2.json")
        gauth.LocalWebserverAuth()
        gauth.SaveCredentialsFile(f"{PROJECT_ROOT_DIR}/credentials/mycreds.txt")
    else:
        gauth.Authorize()

    drive = GoogleDrive(gauth)
    return drive, gauth


def create_new_sheet(drive, sheet_title):
    """
    Creates a new Google Sheet in Drive and returns the file ID.
    """
    file_metadata = {
        "title": sheet_title,
        "mimeType": "application/vnd.google-apps.spreadsheet",
    }
    file = drive.CreateFile(file_metadata)
    file.Upload()  # Upload the empty spreadsheet to Drive
    print(f"Created sheet: {sheet_title} with ID: {file['id']}")
    return file['id']


def get_sheets_service(gauth):
    """
    Build and return a Google Sheets API service using the
    credentials from PyDrive2's GoogleAuth.
    """
    # PyDrive2 uses google-auth style credentials in gauth.credentials
    # Convert them to google.oauth2.credentials.Credentials
    creds = Credentials(
        token=gauth.credentials.access_token,
        refresh_token=gauth.credentials.refresh_token,
        token_uri=gauth.credentials.token_uri,
        client_id=gauth.credentials.client_id,
        client_secret=gauth.credentials.client_secret
    )

    service = build("sheets", "v4", credentials=creds)
    return service


def insert_values_into_sheet(sheets_service, spreadsheet_id):
    """
    Inserts sample data into the given spreadsheet (by ID) using the Sheets API.
    """
    # Define the range and the values
    range_name = "Sheet1!A1:C3"  # e.g., from cell A1 to C3
    values = [
        ["Name", "Age", "City"],
        ["Alice", 30, "New York"],
        ["Bob",   25, "Chicago"],
    ]

    body = {
        "values": values
    }

    # Call the Sheets API to update the cells
    result = sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="RAW",
        body=body
    ).execute()


def do_ls():
    drive, gauth = get_gdrive_login_credentials()
    """
    https://github.com/iterative/PyDrive2
    """
    # Step 3: Example: List files in the root folder
    # file_list = drive.ListFile({'q': "'root' in parents and trashed=false"}).GetList()
    # for file in file_list:
    #     print(f"Title: {file['title']}, ID: {file['id']}")

    lst = get_folders(drive)
    for idx, f in enumerate(lst):
        print(f'{idx} "{f[0]}" -> {f[1]}')
