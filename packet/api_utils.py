"""
Utilities for the REST API code
"""

from enum import Enum
from flask import jsonify


class ErrorTypes(Enum):
    bad_request = 400
    forbidden = 403
    not_found = 404
    server_error = 500


def rest_error(error_name, description, error_type=ErrorTypes.bad_request):
    """
    Helper function for generating REST API error responses
    :param error_name: The machine-friendly name for the error
    :param description: The human-friendly description of the error
    :param error_type: An ErrorTypes enum value for the HTTP status code
    """
    return jsonify({
        "error": error_name,
        "description": description
    }), error_type.value
