"""Functions related to user authentication."""

import os
import time
from functools import wraps

import requests
from flask import flash, jsonify, redirect, request, session, url_for

from app_helper import logger

# Routes that don't require authentication
PUBLIC_ROUTES = [
    "static",
    "login",
    "login_page",
    "signup",
    "logout",
]

def check_auth():
    """Middleware to check if user is authenticated before processing requests.

    Redirects to login page if not authenticated and not accessing a public route.
    Also handles token refresh to prevent redirect loops.
    """
    # Skip authentication check for public routes
    if request.endpoint in PUBLIC_ROUTES:
        return None

    # Skip authentication for OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        return None

    # Check if user is authenticated
    id_token = session.get("id_token")
    if not id_token:
        # If AJAX request, return 401 Unauthorized
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json":
            return jsonify({"status": "error", "message": "Authentication required", "code": "auth_required"}), 401

        # Get the current URL to redirect back after login
        next_url = request.url
        # Don't include the host in the URL
        if next_url.startswith(request.host_url):
            next_url = next_url[len(request.host_url.rstrip("/")):]

        # Otherwise redirect to login page with a clear message
        flash("Please log in to continue.", "info")
        return redirect(url_for("login_page", redirect_to=next_url))

    # Check if token needs refresh
    if should_refresh_token():
        try:
            # Try to refresh the token
            refreshed = refresh_token()
            if not refreshed:
                # If refresh failed, clear the session and redirect to login
                session.clear()
                # If AJAX request, return 401 Unauthorized
                if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json":
                    return jsonify({"status": "error", "message": "Session expired. Please log in again.", "code": "session_expired"}), 401

                # Get the current URL to redirect back after login
                next_url = request.url
                # Don't include the host in the URL
                if next_url.startswith(request.host_url):
                    next_url = next_url[len(request.host_url.rstrip("/")):]

                # Otherwise redirect to login page with a clear message
                flash("Your session has expired. Please log in again.", "warning")
                return redirect(url_for("login_page", redirect_to=next_url))
        except Exception:
            logger.exception("Token refresh failed")
            session.clear()
            # If AJAX request, return 401 Unauthorized
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json":
                return jsonify({"status": "error", "message": "Authentication error. Please log in again.", "code": "auth_error"}), 401

            # Get the current URL to redirect back after login
            next_url = request.url
            # Don't include the host in the URL
            if next_url.startswith(request.host_url):
                next_url = next_url[len(request.host_url.rstrip("/")):]

            # Otherwise redirect to login page with a clear message
            flash("Authentication error. Please log in again.", "error")
            return redirect(url_for("login_page", redirect_to=next_url))
    else:
        return None

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        id_token = session.get("id_token")

        if not id_token:
            # Get the current URL to redirect back after login
            next_url = request.url
            # Don't include the host in the URL
            if next_url.startswith(request.host_url):
                next_url = next_url[len(request.host_url.rstrip("/")):]

            # User is not logged in, redirect to login page
            flash("Please log in to continue.", "info")
            return redirect(url_for("login_page", redirect_to=next_url))

        # Token refresh is now handled by the check_auth middleware
        # so we can just proceed with the function call
        return f(*args, **kwargs)
    return decorated_function

def should_refresh_token():
    """Check if the token needs to be refreshed based on expiration time.

    Uses a timestamp-based approach to avoid decoding JWT on every request.
    """
    token_timestamp = session.get("token_timestamp")

    # If no timestamp exists, token should be refreshed
    if token_timestamp is None:
        return True

    try:
        # Convert to float if it's a string
        if isinstance(token_timestamp, str):
            token_timestamp = float(token_timestamp)

        # Firebase ID tokens expire after 1 hour, refresh if older than 55 minutes
        return (time.time() - token_timestamp) > (55 * 60)
    except (ValueError, TypeError):
        logger.exception("Invalid token timestamp format")
        # If we can't parse the timestamp, assume token needs refresh
        return True

def refresh_token():
    """Refresh the Firebase authentication token using the refresh token.

    Returns True if successful, False otherwise.
    """
    refresh_token_value = session.get("refresh_token")
    if not refresh_token_value:
        logger.warning("No refresh token available in session")
        return False

    try:
        # Use Firebase Auth REST API to refresh the token
        firebase_api_key = os.environ.get("FIREBASE_API_KEY")
        if not firebase_api_key:
            logger.error("FIREBASE_API_KEY environment variable not set")
            return False

        refresh_url = f"https://securetoken.googleapis.com/v1/token?key={firebase_api_key}"
        refresh_payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token_value,
        }

        logger.info("Attempting to refresh Firebase token")
        response = requests.post(refresh_url, json=refresh_payload, timeout=10)

        if response.status_code == 200:
            response_data = response.json()
            if "id_token" in response_data:
                # Update session with new tokens
                session["id_token"] = response_data["id_token"]
                session["refresh_token"] = response_data.get("refresh_token", refresh_token_value)
                session["token_timestamp"] = time.time()
                logger.info("Successfully refreshed Firebase token")
                return True
            else:
                logger.warning("Firebase token refresh response missing id_token")
                return False

        # Log specific error codes for better debugging
        if response.status_code == 400:
            logger.warning("Firebase token refresh failed: Invalid refresh token (400)")
        elif response.status_code == 401:
            logger.warning("Firebase token refresh failed: Unauthorized (401)")
        elif response.status_code == 403:
            logger.warning("Firebase token refresh failed: Forbidden (403)")
        else:
            logger.warning(f"Failed to refresh token: {response.status_code} - {response.text}")
    except requests.exceptions.Timeout:
        logger.warning("Firebase token refresh request timed out")
    except Exception:
        logger.exception("Token refresh request failed")
    return False
