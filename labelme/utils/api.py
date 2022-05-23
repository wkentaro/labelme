from typing import Any, Dict
import requests
from labelme.logger import logger

class api_utils():
    username: str = ""
    auth_tok: str = ""
    API_ROOT: str = "https://app.deepwalkresearch.com:3015"

    def __init__(self, username="", password=""):
        if username and password:
            self.login(username, password)

    def login(self, username, password):
        r = requests.post(
            self.API_ROOT + "/auth/login",
            json={'email': username, 'password': password}
        )

        if r.status_code == 200:
            r_json = r.json()
            self.username = username
            self.auth_tok = r_json["accessToken"]
        else:
            logger.warning("Login error. Status Code: {}".format(r.status_code))
        
        return r.status_code

    def get_models(self) -> Dict:
        r = requests.get(
            self.API_ROOT + "/model",
            headers={"auth": self.auth_tok}
        )

        if r.status_code == 200:
            return r.json()
        
        logger.warning("Get models error. Status Code: {}".format(r.status_code))
        return None

    def setStage(self, folder, stage):
        r = requests.post(
            self.API_ROOT + "/model/stage",
            headers={"auth": self.auth_tok},
            json={"folderName": folder, "stage": stage}
        )

        if r.status_code != 200:
            logger.warning("Set stage error. Status Code: {}".format(r.status_code))

        return r.status_code

    def setFailures(self, folder, failures):
        r = requests.post(
            self.API_ROOT + "/model/failure",
            headers={"auth": self.auth_tok},
            json={"folderName": folder, "failure": failures}
        )
        
        if r.status_code != 200:
            logger.warning("Set failures error. Status Code: {}".format(r.status_code))

        return r.status_code

    def getUsername(self, userId):
        r = requests.get(
            self.API_ROOT + "/user/username",
            headers={"auth": self.auth_tok},
            json={"userId": userId}
        )

        if r.status_code == 200:
            return r.json()["email"]
        
        logger.warning("Get username error. Status Code: {}".format(r.status_code))
        return None

    def getUserid(self, username):
        r = requests.get(
            self.API_ROOT + "/user/userid",
            headers={"auth": self.auth_tok},
            json={"username": username}
        )

        if r.status_code == 200:
            return r.json()["id"]

        logger.warning("Get username error. Status Code: {}".format(r.status_code))
        return None
