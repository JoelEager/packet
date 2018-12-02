"""
Shared REST API endpoints
"""

from datetime import datetime
from flask import jsonify

from packet import app
from packet.utils import packet_auth
from packet.api_utils import rest_error
from packet.models import Freshman, Packet


@app.route("/api/packet/<packet_id>/")
@packet_auth
def get_packet(packet_id):
    """
    :return: Returns a packet based on username
    """
    packet = Packet.by_id(packet_id)

    if packet is not None:
        return jsonify(packet.to_dict())
    else:
        return rest_error("bad_id", "Invalid packet id")


@app.route("/api/freshman/<freshman_username>/")
@packet_auth
def get_freshman(freshman_username):
    """
    :return: Returns a freshman based on username
    """
    freshman = Freshman.by_username(freshman_username)

    if freshman is not None:
        return jsonify(freshman.to_dict())
    else:
        return rest_error("bad_username", "Invalid freshman username")


@app.route("/api/freshmen/<search_term>/")
@packet_auth
def get_freshmen(search_term):
    """
    Case-insensitive string search for freshmen based on real name
    :return: List of the freshmen that match and if they have a currently open packet
    """
    if search_term.isalpha():
        results = Freshman.query.filter(Freshman.name.ilike("%" + search_term + "%")).all()
        return jsonify([freshman.to_dict() for freshman in results])
    else:
        return rest_error("bad_search_term", "Only letters are allowed in the search text")
