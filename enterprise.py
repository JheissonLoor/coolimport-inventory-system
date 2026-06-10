from google.oauth2 import service_account
import google.auth.transport.requests
import requests

SCOPES = ['https://www.googleapis.com/auth/androidmanagement']
SERVICE_ACCOUNT_FILE = './mdm-coolimport-f1ae8c90b61f.json'

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)

auth_req = google.auth.transport.requests.Request()
credentials.refresh(auth_req)

token = credentials.token
print("Access Token:", token)
