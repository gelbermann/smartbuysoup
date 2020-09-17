import base64
import itertools
import os
import pickle
from datetime import datetime
from email.mime.text import MIMEText
from typing import Dict, List

import requests
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from secret_keys import FROM_MAIL_ADDR, SMARTBUY_URL, TARGET_MAIL_ADDR, PRODUCTS


def main(products: List[str]):
    html = get_page_data()
    products_found = search_for_products(html, products)
    if products_found is not None:
        alert_me(products_found)


def get_page_data() -> str:
    """ Get HTML data of SMARTBUY_URL page as string. """
    resp = requests.get(SMARTBUY_URL)
    return resp.text


def search_for_products(html: str, products: List[str]) -> Dict[str, List[str]]:
    """Find links ('a' tags) in HTML page data that contain requested keywords,
    that also have a matching time-indicator element with less than 24 hours in it."""
    soup = BeautifulSoup(html, "html.parser")
    a_tags = soup.find_all("a")
    matches = dict()
    products = [p.lower() for p in products]

    # for each 'a' tag in page, check if it contains the product name, and is also from today
    for p in products:
        for a in a_tags:
            if a.string is not None and p in a.string.lower() and a.get("href", ""):
                a_ancestor_element = next(
                    itertools.islice(a.parents, 4, None)
                )  # extract 5th parent (islice required because a.parents is generator)
                date_text = list(
                    list(list(a_ancestor_element.children)[3].children)[3].children
                )[1].text
                date_is_today = "שעות" in date_text or "1 ימים" in date_text
                if date_is_today:
                    matches.setdefault(p, []).append(a.get("href", ""))

    if len(matches.keys()) == 0:
        matches = None

    return matches


def alert_me(products: Dict[str, List[str]]) -> None:
    """Alert user (email address is `FROM_MAIL_ADDR`) about any products that were matched."""
    service = set_up_connection()

    message = compose_message(products)

    try:
        service.users().messages().send(userId="me", body=message).execute()
    except Exception as e:
        with open("errors.log", "a") as f:
            f.writelines(
                [
                    f"****  {datetime.now()}  ****\n",
                    f"An error has occurred trying to login to Gmail or send the response mail.\n",
                    e.__repr__(),
                    "\n\n",
                ]
            )
        print(f"An error has occurred!\n{e}")


def set_up_connection() -> Resource:
    """Set up Gmail API connection according to https://developers.google.com/gmail/api/quickstart/python?authuser=2"""
    SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    service = build("gmail", "v1", credentials=creds)
    return service


def compose_message(products: Dict[str, List[str]]) -> Dict[str, str]:
    """Create message to be sent about products"""
    body = "Great success!\n\n"
    for key, links in products.items():
        body += (
            f'The product responding to keyword "{key}" has been found in SmartBuy.\n'
        )
        body += f"Click here to find out more: {' , '.join(links)}\n\n"

    message = MIMEText(body)
    message["to"] = TARGET_MAIL_ADDR
    message["from"] = FROM_MAIL_ADDR
    message["subject"] = f"SmartBuy products alert! ({', '.join(products.keys()).title()})"

    # workaround required for python 3 (instead of directly encoding):
    enc_message = base64.urlsafe_b64encode(message.as_bytes())
    raw_message = {"raw": enc_message.decode()}

    return raw_message


if __name__ == "__main__":
    # PRODUCTS should be a list of names/keywords for products that you want 
    # (capitalization doesn't matter)
    main(PRODUCTS)  
