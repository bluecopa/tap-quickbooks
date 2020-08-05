import json
import backoff
import requests
import singer

from requests_oauthlib import OAuth2Session

LOGGER = singer.get_logger()
PROD_ENDPOINT_BASE = "https://quickbooks.api.intuit.com"
SANDBOX_ENDPOINT_BASE = "https://sandbox-quickbooks.api.intuit.com"
TOKEN_REFRESH_URL = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'


class QuickbooksAuthenticationError(Exception):
    pass


class QuickbooksClient():
    def __init__(self, config_path, config):
        token = {
            'access_token': "wrong",
            'refresh_token': config['refresh_token'],
            'token_type': 'Bearer',
            # Set expires_in to a negative number to force the client to reauthenticate
            'expires_in': '-30'
        }
        extra = {
            'client_id': config['client_id'],
            'client_secret': config['client_secret']
        }

        # TODO: Cleanup
        if config['sandbox'] == 'true' or config['sandbox'] == 'True':
            self.sandbox = True

        self.user_agent = config['user_agent']
        self.realm_id = config['realm_id']
        self.config_path = config_path
        self.session = OAuth2Session(config['client_id'],
                                     token=token,
                                     auto_refresh_url=TOKEN_REFRESH_URL,
                                     auto_refresh_kwargs=extra,
                                     token_updater=self._write_config)
        try:
            # Make an authenticated request after creating the object to any endpoint
            self.get('/v3/company/{}/query'.format(self.realm_id), params={"query": "SELECT * FROM CompanyInfo"}).get('CompanyInfo', {})
        except Exception as e:
            LOGGER.info("Error initializing QuickbooksClient during token refresh, please reauthenticate.")
            raise QuickbooksAuthenticationError(e)

    def _write_config(self, token):
        LOGGER.info("Credentials Refreshed")

        # Update config at config_path
        with open(self.config_path) as file:
            config = json.load(file)

        config['refresh_token'] = token['refresh_token']

        with open(self.config_path, 'w') as file:
            json.dump(config, file, indent=2)


    @backoff.on_exception(backoff.constant,
                          (requests.exceptions.HTTPError),
                          max_tries=3,
                          interval=10)
    def _make_request(self, method, endpoint, headers=None, params=None, data=None):
        # Make sure the correct endpoint is used
        if self.sandbox:
            full_url = SANDBOX_ENDPOINT_BASE + endpoint
        else:
            full_url = PROD_ENDPOINT_BASE + endpoint

        LOGGER.info(
            "%s - Making request to %s endpoint %s, with params %s",
            full_url,
            method.upper(),
            endpoint,
            params,
        )

        default_headers = {
            'Accept': 'application/json',
            'User-Agent': self.user_agent
        }
        # TODO: We should merge headers with some default headers like user_agent - fix this
        response = self.session.request(method, full_url, headers=default_headers, params=params, data=data)

        response.raise_for_status()

        # TODO: Check error status, rate limit, etc.
        return response.json()


    def get(self, url, headers=None, params=None):
        return self._make_request("GET", url, headers=headers, params=params)