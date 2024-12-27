# Created by Samuel Lesuffleur 29-09-2017
#
# Copyright (c) 2017 Sandtable Ltd. All rights reserved.
"""
    Flask-Auth0 is an extension for Flask that allows you to authenticate
    through Auth0 service.
"""
import json
import logging
from functools import wraps
from six.moves.urllib.parse import urlencode, urlparse

from authlib.flask.client import OAuth
import flask
from flask import current_app

logger = logging.getLogger(__name__)


class AuthError(Exception):
    def __init__(self, error, status_code=401):
        self.error = error
        self.status_code = status_code


class Auth0(object):
    """The core Auth0 client object."""

    def __init__(self, app=None):
        self._server = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Do setup required by a Flask app."""
        app.config.setdefault('AUTH0_ALGORITHMS', 'RS256')
        app.config.setdefault('AUTH0_AUDIENCE', None)
        app.config.setdefault('AUTH0_CALLBACK_URL', None)
        app.config.setdefault('AUTH0_CLIENT_ID', None)
        app.config.setdefault('AUTH0_CLIENT_SECRET', None)
        app.config.setdefault('AUTH0_DOMAIN', None)
        app.config.setdefault('AUTH0_LOGOUT_URL', None)
        app.config.setdefault('AUTH0_REQUIRE_VERIFIED_EMAIL', True)
        app.config.setdefault('AUTH0_SESSION_JWT_PAYLOAD_KEY', 'jwt_payload')
        app.config.setdefault('AUTH0_SESSION_TOKEN_KEY', 'auth0_token')
        app.config.setdefault('AUTH0_SCOPE', 'openid profile email')

        self._client_id = app.config['AUTH0_CLIENT_ID']
        self._client_secret = app.config['AUTH0_CLIENT_SECRET']
        self._domain = app.config['AUTH0_DOMAIN']
        self._base_url = 'https://{}'.format(self._domain)
        self._access_token_url = self._base_url + '/oauth/token'
        self._callback_url = app.config['AUTH0_CALLBACK_URL']
        self._logout_url = app.config['AUTH0_LOGOUT_URL']
        self._authorize_url = self._base_url + '/authorize'
        default_audience = self._base_url + '/userinfo'
        self._audience = app.config.get('AUTH0_AUDIENCE', default_audience)
        self._scope = app.config['AUTH0_SCOPE']
        self._session_token_key = app.config['AUTH0_SESSION_TOKEN_KEY']
        self._session_jwt_payload_key = \
            app.config['AUTH0_SESSION_JWT_PAYLOAD_KEY']

        self._auth0 = OAuth(app).register(
            'auth0',
            client_id=self._client_id,
            client_secret=self._client_secret,
            api_base_url=self._base_url,
            access_token_url=self._access_token_url,
            authorize_url=self._authorize_url,
            client_kwargs={
                'audience': self._audience,
                'scope': self._scope,
            },
        )

        route = urlparse(self._callback_url).path
        app.route(route)(self._callback)

        @app.errorhandler(AuthError)
        def handle_auth_error(ex):
            response = flask.jsonify(ex.error)
            response.status_code = ex.status_code
            return response

    def _callback(self):
        """Redirect to the originally requested page."""
        args = flask.request.args.to_dict(flat=True)
        try:
            state = json.loads(args['state'])
            destination = state['destination']
        except (ValueError, KeyError) as e:
            logger.exception(e)
            raise AuthError('Invalid callback request')

        token = self._auth0.authorize_access_token()
        resp = self._auth0.get('userinfo')
        userinfo = resp.json()
        flask.session[self._session_token_key] = token
        flask.session[self._session_jwt_payload_key] = userinfo

        scheme = current_app.config['PREFERRED_URL_SCHEME']
        next_url = flask.url_for(destination, _external=True, _scheme=scheme)
        logger.debug('redirecting to `{}`'.format(next_url))
        return flask.redirect(next_url)

    def _redirect_to_auth_server(self, destination):
        """Redirect to the auth0 server.

        Args:
           destination: URL to redirect user
        """
        state = json.dumps({"destination": destination})
        return self._auth0.authorize_redirect(
            redirect_uri=self._callback_url,
            audience=self._audience,
            state=state)

    def requires_auth(self, view_func):
        """Decorates view functions that require a user to be logged in."""
        @wraps(view_func)
        def decorated(*args, **kwargs):
            if self._session_token_key not in flask.session:
                return self._redirect_to_auth_server(flask.request.endpoint)
            logger.debug('user is authenticated')
            return view_func(*args, **kwargs)
        return decorated

    def logout(self):
        """Logout user.

        Request the browser to clear the current session and also clear the
        Auth0 session (clearing the SSO cookie).

        The user won't be log out from a third party Identity Provider.

        The user is redirected to the logout callback.
        """
        flask.session.clear()
        params = {'returnTo': self._logout_url, 'client_id': self._client_id}
        url = self._auth0.api_base_url + '/v2/logout?' + urlencode(params)
        logger.debug('redirecting to `{}`'.format(url))
        return flask.redirect(url)

    @property
    def access_token(self):
        """Get access token (user must be authenticated)."""
        tokens = flask.session.get(self._session_token_key)
        if not tokens:
            return None
        return tokens['access_token']

    @property
    def jwt_payload(self):
        """Get JWT payload (user must be authenticated)."""
        return flask.session.get(self._session_jwt_payload_key, None)
