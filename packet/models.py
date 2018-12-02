"""
Defines the application's database models
"""

from datetime import datetime
from itertools import chain

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.exc import DataError

from . import db

# The required number of honorary member, advisor, and alumni signatures
REQUIRED_MISC_SIGNATURES = 10


class SigCounts:
    """
    Utility class for returning counts of signatures broken out by type
    """
    def __init__(self, eboard, upper, fresh, misc):
        # Base fields
        self.eboard = eboard
        self.upper = upper      # Upperclassmen excluding eboard
        self.fresh = fresh
        self.misc = misc

        # Capped version of misc so it will never be greater than REQUIRED_MISC_SIGNATURES
        self.misc_capped = misc if misc <= REQUIRED_MISC_SIGNATURES else REQUIRED_MISC_SIGNATURES

        # Totals (calculated using misc_capped)
        self.member_total = eboard + upper + self.misc_capped
        self.total = eboard + upper + fresh + self.misc_capped

    def to_dict(self):
        """
        :return: The SigCounts converted into a dict ready for returning as a json response
        """
        return self.__dict__


class Freshman(db.Model):
    __tablename__ = "freshman"
    rit_username = Column(String(10), primary_key=True)
    name = Column(String(64), nullable=False)
    onfloor = Column(Boolean, nullable=False)
    fresh_signatures = relationship("FreshSignature")

    # One freshman can have multiple packets if they repeat the intro process
    packets = relationship("Packet", order_by="desc(Packet.id)")

    def is_currently_on_packet(self):
        """
        :return: Boolean for if this freshman has a currently open packet
        """
        return Packet.query.filter(Packet.start < datetime.now(), Packet.end > datetime.now(),
                                   Packet.freshman_username == self.rit_username).count() != 0

    def to_dict(self):
        """
        :return: The freshmen converted into a dict ready for returning as a json response
        """
        return {
            "rit_username": self.rit_username,
            "name": self.name,
            "onfloor": self.onfloor,
            "packets": [{"id": packet.id, "open": packet.is_open()} for packet in self.packets]
        }

    def __repr__(self):
        return "<Freshman {}, {}>".format(self.name, self.rit_username)

    @classmethod
    def by_username(cls, rit_username):
        """
        Helper method for fetching 1 freshman by their rit_username
        """
        return cls.query.filter_by(rit_username=rit_username).first()


class Packet(db.Model):
    __tablename__ = "packet"
    id = Column(Integer, primary_key=True, autoincrement=True)
    freshman_username = Column(ForeignKey("freshman.rit_username"))
    start = Column(DateTime, nullable=False)
    end = Column(DateTime, nullable=False)

    freshman = relationship("Freshman", back_populates="packets")

    # The `lazy="subquery"` kwarg enables eager loading for signatures which makes signature calculations much faster
    # See the docs here for details: https://docs.sqlalchemy.org/en/latest/orm/loading_relationships.html
    upper_signatures = relationship("UpperSignature", lazy="subquery",
                                    order_by="UpperSignature.signed.desc(), UpperSignature.updated")
    fresh_signatures = relationship("FreshSignature", lazy="subquery",
                                    order_by="FreshSignature.signed.desc(), FreshSignature.updated")
    misc_signatures = relationship("MiscSignature", lazy="subquery", order_by="MiscSignature.updated")

    def is_open(self):
        return self.start < datetime.now() < self.end

    def signatures_required(self):
        """
        :return: A SigCounts instance with the fields set to the number of signatures received by this packet
        """
        eboard = sum(map(lambda sig: 1 if sig.eboard else 0, self.upper_signatures))
        upper = len(self.upper_signatures) - eboard
        fresh = len(self.fresh_signatures)

        return SigCounts(eboard, upper, fresh, REQUIRED_MISC_SIGNATURES)

    def signatures_received(self):
        """
        :return: A SigCounts instance with the fields set to the number of required signatures for this packet
        """
        eboard = sum(map(lambda sig: 1 if sig.eboard and sig.signed else 0, self.upper_signatures))
        upper = sum(map(lambda sig: 1 if not sig.eboard and sig.signed else 0, self.upper_signatures))
        fresh = sum(map(lambda sig: 1 if sig.signed else 0, self.fresh_signatures))

        return SigCounts(eboard, upper, fresh, len(self.misc_signatures))

    def did_sign(self, username, is_csh):
        """
        :param username: The CSH or RIT username to check for
        :param is_csh: Set to True for CSH accounts and False for freshmen
        :return: Boolean value for if the given account signed this packet
        """
        if is_csh:
            for sig in filter(lambda sig: sig.member == username, chain(self.upper_signatures, self.misc_signatures)):
                if isinstance(sig, MiscSignature):
                    return True
                else:
                    return sig.signed
        else:
            for sig in filter(lambda sig: sig.freshman_username == username, self.fresh_signatures):
                return sig.signed

        # The user must be a misc CSHer that hasn't signed this packet or an off-floor freshmen
        return False

    def is_100(self):
        """
        Checks if this packet has reached 100%
        """
        return self.signatures_required().total == self.signatures_received().total

    def to_dict(self):
        """
        :return: The packet converted into a dict ready for returning as a json response
        """
        return {
            "id": self.id,
            "freshman_name": self.freshman.name,
            "freshman_username": self.freshman_username,
            "start": str(self.start),
            "end": str(self.end),
            "open": self.is_open(),
            "signatures_required": self.signatures_required().to_dict(),
            "signatures_received": self.signatures_received().to_dict(),
            "upper_signatures": [sig.to_dict() for sig in self.upper_signatures],
            "fresh_signatures": [sig.to_dict() for sig in self.fresh_signatures],
            "misc_signatures": [sig.to_dict() for sig in self.misc_signatures]
        }

    def __repr__(self):
        return "<Packet {}, {}>".format(self.freshman_username, self.id)

    @classmethod
    def open_packets(cls):
        """
        Helper method for fetching all currently open packets
        """
        return cls.query.filter(cls.start < datetime.now(), cls.end > datetime.now()).all()

    @classmethod
    def by_id(cls, packet_id):
        """
        Helper method for fetching 1 packet by its id
        """
        try:
            return cls.query.filter_by(id=packet_id).first()
        except DataError:
            return None


class UpperSignature(db.Model):
    __tablename__ = "signature_upper"
    packet_id = Column(Integer, ForeignKey("packet.id"), primary_key=True)
    member = Column(String(36), primary_key=True)
    signed = Column(Boolean, default=False, nullable=False)
    eboard = Column(Boolean, default=False, nullable=False)
    updated = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    packet = relationship("Packet", back_populates="upper_signatures")

    def to_dict(self):
        """
        :return: The UpperSignature converted into a dict ready for returning as a json response
        """
        return {
            "member": self.member,
            "signed": self.signed,
            "eboard": self.eboard
        }


class FreshSignature(db.Model):
    __tablename__ = "signature_fresh"
    packet_id = Column(Integer, ForeignKey("packet.id"), primary_key=True)
    freshman_username = Column(ForeignKey("freshman.rit_username"), primary_key=True)
    signed = Column(Boolean, default=False, nullable=False)
    updated = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    packet = relationship("Packet", back_populates="fresh_signatures")
    freshman = relationship("Freshman", back_populates="fresh_signatures")

    def to_dict(self):
        """
        :return: The FreshSignature converted into a dict ready for returning as a json response
        """
        return {
            "freshman_username": self.freshman_username,
            "signed": self.signed
        }


class MiscSignature(db.Model):
    __tablename__ = "signature_misc"
    packet_id = Column(Integer, ForeignKey("packet.id"), primary_key=True)
    member = Column(String(36), primary_key=True)
    updated = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    packet = relationship("Packet", back_populates="misc_signatures")

    def to_dict(self):
        """
        :return: The MiscSignature converted into a dict ready for returning as a json response
        """
        return {
            "member": self.member
        }
