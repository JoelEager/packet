"""
Shared REST API endpoints
"""

from flask import jsonify

from packet import app, db
from packet.utils import packet_auth, before_request, notify_slack
from packet.api_utils import rest_error
from packet.models import Freshman, Packet, MiscSignature


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


def update_sig(packet, uid):
    """
    Helper method for the sign() endpoint
        Handles finding and updating the correct database row with the new signature
    """
    if app.config["REALM"] == "csh":
        # Check if the CSHer is an upperclassman and if so, sign that row
        for sig in filter(lambda sig: sig.member == uid, packet.upper_signatures):
            if not sig.signed:
                sig.signed = True
                app.logger.info("Member {} signed packet {} as an upperclassman".format(uid, packet.id))
                return jsonify({"message": "Added upperclassman signature"})
            else:
                app.logger.warn("Member {} tried to repeat signing packet {} as an upperclassman".format(uid, packet.id))

        # The CSHer is a misc so add a new row
        db.session.add(MiscSignature(packet=packet, member=uid))
        app.logger.info("Member {} signed packet {} as a misc".format(uid, packet.id))
        return jsonify({"message": "Added misc member signature"})
    else:
        # Check if the freshman is onfloor and if so, sign that row
        for sig in filter(lambda sig: sig.freshman_username == uid, packet.fresh_signatures):
            sig.signed = True
            app.logger.info("Freshman {} signed packet {}".format(uid, packet.id))
            return jsonify({"message": "Added freshman signature"})

        return rest_error("onfloor_freshman", "Off-floor freshmen can't sign packets")


@app.route("/api/packet/<packet_id>/sign/", methods=["POST"])
@packet_auth
@before_request
def sign(packet_id, info):
    """
    Adds a signature for the given packet from the currently logged in user
    """
    def commit_sig():
        db.session.commit()
        if not was_100 and packet.is_100():
            notify_slack(packet.freshman.name)

    uid = info["uid"]
    packet = Packet.by_id(packet_id)

    if packet is None:
        return rest_error("bad_id", "Invalid packet id")
    elif not packet.is_open():
        return rest_error("packet_closed", "That packet is closed so it can't be signed")
    else:
        # Store the current is_100() value for use by commit_sig()
        was_100 = packet.is_100()

        if app.config["REALM"] == "csh":
            # Check if the CSHer is an upperclassman
            for sig in filter(lambda sig: sig.member == uid, packet.upper_signatures):
                if not sig.signed:
                    # Update row and commit the changes
                    sig.signed = True
                    commit_sig()
                    app.logger.info("Member {} signed packet {} as an upperclassman".format(uid, packet.id))
                    return jsonify({"message": "Added upperclassman signature"})
                else:
                    # This is a repeat sig
                    app.logger.warn("Member {} tried to repeat signing packet {} as an upperclassman"
                                    .format(uid, packet.id))
                    return rest_error("already_signed", "You've already signed this packet")

            # The CSHer is a misc
            for _ in filter(lambda sig: sig.member == uid, packet.misc_signatures):
                # This is a repeat sig
                app.logger.warn("Member {} tried to repeat signing packet {} as an misc member".format(uid, packet.id))
                return rest_error("already_signed", "You've already signed this packet")

            # Create the misc row and commit the changes
            db.session.add(MiscSignature(packet=packet, member=uid))
            commit_sig()
            app.logger.info("Member {} signed packet {} as a misc".format(uid, packet.id))
            return jsonify({"message": "Added misc member signature"})
        else:
            # Check if the freshman is onfloor
            for sig in filter(lambda sig: sig.freshman_username == uid, packet.fresh_signatures):
                if not sig.signed:
                    # Update row and commit the changes
                    sig.signed = True
                    commit_sig()
                    app.logger.info("Freshman {} signed packet {}".format(uid, packet.id))
                    return jsonify({"message": "Added freshman signature"})
                else:
                    # This is a repeat sig
                    app.logger.warn("Freshman {} tried to repeat signing packet {}".format(uid, packet.id))
                    return rest_error("already_signed", "You've already signed this packet")

            # Off-floor freshman
            app.logger.warn("Off-floor freshman {} tried to sign packet {}".format(uid, packet.id))
            return rest_error("onfloor_freshman", "Off-floor freshmen can't sign packets")
