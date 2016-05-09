"""models.py

Udacity conference server-side Python App Engine data & ProtoRPC models

$Id: models.py,v 1.1 2014/05/24 22:01:10 wesc Exp $

created/forked from conferences.py by wesc on 2014 may 24

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

import httplib
import endpoints
from protorpc import messages
from google.appengine.ext import ndb
from google.appengine.ext.ndb import msgprop


class TypeOfSession(messages.Enum):
    """SessionType -- session type enumeration value"""
    Workshop = 1
    Lecture = 2
    Keynote = 3


# Define the Profile Kind
class Profile(ndb.Model):
    """Profile -- User profile object"""
    user_id             = ndb.StringProperty()
    displayName         = ndb.StringProperty()
    mainEmail           = ndb.StringProperty()
    teeShirtSize        = ndb.StringProperty(default='NOT_SPECIFIED')
    conferenceKeysToAttend = ndb.StringProperty(repeated=True)
    wishlistSessionKeys = ndb.StringProperty(repeated=True)


# Define the Conference Kind
class Conference(ndb.Model):
    """Conference -- Conference object"""
    name                = ndb.StringProperty(required=True)
    description         = ndb.StringProperty()
    organizerUserId     = ndb.StringProperty()
    topics              = ndb.StringProperty(repeated=True)
    city                = ndb.StringProperty()
    startDate           = ndb.DateProperty()
    month               = ndb.IntegerProperty()
    endDate             = ndb.DateProperty()
    maxAttendees        = ndb.IntegerProperty()
    seatsAvailable      = ndb.IntegerProperty()


# Define the Session Kind
class Session(ndb.Model):
    """Session -- Session object"""
    name                = ndb.StringProperty(required=True)
    highlights          = ndb.StringProperty()
    speaker             = ndb.StringProperty()
    startTime           = ndb.TimeProperty() 
    durationInMinutes   = ndb.IntegerProperty()
    typeOfSession       = msgprop.EnumProperty(TypeOfSession)
    date                = ndb.DateProperty()
    location            = ndb.StringProperty()


# Needed for conference registration
class BooleanMessage(messages.Message):
    """BooleanMessage-- outbound Boolean value message"""
    data = messages.BooleanField(1)


class TeeShirtSize(messages.Enum):
    """TeeShirtSize -- t-shirt size enumeration value"""
    NOT_SPECIFIED = 1
    XS_M = 2
    XS_W = 3
    S_M = 4
    S_W = 5
    M_M = 6
    M_W = 7
    L_M = 8
    L_W = 9
    XL_M = 10
    XL_W = 11
    XXL_M = 12
    XXL_W = 13
    XXXL_M = 14
    XXXL_W = 15


# Needed for conference registration
class ConflictException(endpoints.ServiceException):
    """ConflictException -- exception mapped to HTTP 409 response"""
    http_status = httplib.CONFLICT


# Called by the getAnnouncement endpoint
class StringMessage(messages.Message):
    """StringMessage-- outbound (single) string message"""
    data = messages.StringField(1, required=True)


class QueryForm(messages.Message):
    """QueryForm -- Query inbound form message"""
    field = messages.StringField(1)
    operator = messages.StringField(2)
    value = messages.StringField(3)


class QueryForms(messages.Message):
    """QueryForms -- multiple QueryForm inbound form message"""
    filters = messages.MessageField(QueryForm, 1, repeated=True)


class ProfileMiniForm(messages.Message):
    """ProfileMiniForm -- update Profile form message"""
    displayName = messages.StringField(1)
    teeShirtSize = messages.EnumField('TeeShirtSize', 2)


class ProfileForm(messages.Message):
    """ProfileForm -- Profile outbound form message"""
    displayName = messages.StringField(1)
    teeShirtSize = messages.EnumField('TeeShirtSize', 2)
    mainEmail = messages.StringField(3)
    wishlistSessionKeys = messages.StringField(4, repeated=True)
    conferenceKeysToAttend = messages.StringField(5, repeated=True)


class ConferenceForm(messages.Message):
    """ConferenceForm -- Conference outbound form message"""
    name            = messages.StringField(1)
    description     = messages.StringField(2)
    organizerUserId = messages.StringField(3)
    topics          = messages.StringField(4, repeated=True)
    city            = messages.StringField(5)
    startDate       = messages.StringField(6) #DateTimeField()
    month           = messages.IntegerField(7, variant=messages.Variant.INT32)
    maxAttendees    = messages.IntegerField(8, variant=messages.Variant.INT32)
    seatsAvailable  = messages.IntegerField(9, variant=messages.Variant.INT32)
    endDate         = messages.StringField(10) #DateTimeField()
    websafeKey      = messages.StringField(11)
    organizerDisplayName = messages.StringField(12)


class ConferenceForms(messages.Message):
    """ConferenceForms -- multiple Conference outbound form message"""
    items = messages.MessageField(ConferenceForm, 1, repeated=True)


class SessionForm(messages.Message):
    """SessionForm -- Conference outbound form message"""
    name                = messages.StringField(1)
    highlights          = messages.StringField(2)
    speaker             = messages.StringField(3)
    startTime           = messages.StringField(4) #TimeField() in 24 hour notation so it can be ordered
    durationInMinutes   = messages.IntegerField(5, variant=messages.Variant.INT32)
    typeOfSession       = messages.EnumField('TypeOfSession', 6, default='Workshop')
    date                = messages.StringField(7) #DateTimeField()
    location            = messages.StringField(8)
    websafeConferenceKey= messages.StringField(9)
    websafeKey          = messages.StringField(10)


class SessionForms(messages.Message):
    """SessionsForms -- multiple Session outbound form message"""
    items = messages.MessageField(SessionForm, 1, repeated=True)


class WishlistForm(messages.Message):
    """SessionForm -- Conference outbound form message"""
    wishlistSessionKeys = messages.StringField(1, required=True)