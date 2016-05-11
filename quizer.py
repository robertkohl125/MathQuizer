#!/usr/bin/python

__author__ = 'robertkohl125@gmail.com (Robert Kohl)'


from datetime import datetime
import datetime as dt

import endpoints
from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

from models import WishlistForm

from utils import getUserId

from settings import WEB_CLIENT_ID

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT ANNOUNCEMENTS"
MEMCACHE_SPEAKER_KEY = "FEATURED_SPEAKER"

CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
    )

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1),
    )

SESS_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1, required=True)
    )

WISHLIST_DEL_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeSessionKey=messages.StringField(1),
    )

WISHLIST_POST_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeSessionKey=messages.StringField(1)
    )

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": [ "Default", "Topic" ],
    }

OPERATORS = {
    'EQ':   '=',
    'GT':   '>',
    'GTEQ': '>=',
    'LT':   '<',
    'LTEQ': '<=',
    'NE':   '!=',
    }

FIELDS = {
    'CITY': 'city',
    'TOPIC': 'topics',
    'MONTH': 'month',
    'MAX_ATTENDEES': 'maxAttendees',
    }

SFIELDS = {
    'DURATION_IN_MUNUTES': 'durationInMinutes',
    }


# - - - Main Class and Endpoint defined - - - - - - - - - - - - - - - - - - - -


@endpoints.api(
    name='conference', 
    version='v1', 
    allowed_client_ids=[WEB_CLIENT_ID, 
    API_EXPLORER_CLIENT_ID], 
    scopes=[EMAIL_SCOPE]
    )
class ConferenceApi(remote.Service):
    """Conference API v0.2
    """


# - - - Profile objects - - - - - - - - - - - - - - - - - - - - - - - - - - - -


    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm.
        """

        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):

                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, 
                        getattr(TeeShirtSize, 
                        getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, 
                        getattr(prof, field.name))
        pf.check_initialized()
        return pf


    def _getProfileFromUser(self):
        """Return user Profile from datastore, 
        creating new one if non-existent.
        """

        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException(
                'Authorization required')

        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()

        # create new Profile if not there
        if not profile:
            profile = Profile(
                key = p_key,
                displayName = user.nickname(), 
                mainEmail= user.email(),
                teeShirtSize = str(TeeShirtSize.NOT_SPECIFIED))
            profile.put()

        # return Profile
        return profile      


    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first.
        """

        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, 
                            str(val))
                        if field == 'teeShirtSize':
                            setattr(prof, field, 
                                str(val).upper())
                        else:
                            setattr(prof, field, val)
                        prof.put()
        return self._copyProfileToForm(prof)


    @endpoints.method(
        message_types.VoidMessage, 
        ProfileForm, 
        path='profile', 
        http_method='GET', 
        name='getProfile'
        )
    def getProfile(self, request):
        """Return user profile.
        """

        return self._doProfile()


    @endpoints.method(
        ProfileMiniForm, 
        ProfileForm, 
        path='profile', 
        http_method='POST', 
        name='saveProfile'
        )
    def saveProfile(self, request):
        """Update & return user profile.
        """

        return self._doProfile(request)


# - - - Conference objects - - - - - - - - - - - - - - - - - - - - - - - - - -


    def _getQuery(self, request):
        """Return formatted query from the submitted filters.
        """

        q = Conference.query()
        inequality_filter, filters = self._formatFilters(
            request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(
                filtr["field"], 
                filtr["operator"], 
                filtr["value"])
            q = q.filter(formatted_query)
        return q


    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters.
        """

        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name) \
                for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException(
                    "Filter contains invalid field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
            # check if inequality operation has been used in previous filters
            # disallow the filter if inequality was performed on a different 
            # field before track the field on which the inequality operation is
            # performed

                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException(
                        "Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)


    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm.
        """

        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):

                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, 
                        str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, 
                        getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf


    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm/request.
        """

        # Fetch current user
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException(
                'Authorization required')
        user_id = getUserId(user)

        # Test for Conference name in request
        if not request.name:
            raise endpoints.BadRequestException(
                "Conference 'name' field required")

        # Copy ConferenceForm/ProtoRPC Message into dict.
        data = {field.name: getattr(request, field.name) \
            for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # Add default values for those missing 
        # (both data model & outbound Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # Convert dates from strings to Date objects.
        # Set month based on start_date.
        if data['startDate']:
            data['startDate'] = datetime.strptime(
                data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(
                data['endDate'][:10], "%Y-%m-%d").date()

        # Set seatsAvailable to be same as maxAttendees on creation, 
        # both for data model & outbound Message
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
            setattr(request, "seatsAvailable", data["maxAttendees"])

        # Make Profile Key from user ID as p_key
        p_key = ndb.Key(Profile, user_id)

        # Allocate new c_id with p_key as parent
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]

        # Make Conference key from ID, uses p_key to define parent 
        # and c_id as unique id
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # Create Conference
        Conference(**data).put()

        # Send email to organizer confirming creation of Conference
        taskqueue.add(
            params={'email': user.email(), 
            'conferenceInfo': repr(request)}, 
            url='/tasks/send_confirmation_email')

        # Return (modified) ConferenceForm
        return request


    @endpoints.method(
        ConferenceForm, 
        ConferenceForm, 
        path='conference', 
        http_method='POST', 
        name='createConference'
        )
    def createConference(self, request):
        """Create new conference.
        """

        return self._createConferenceObject(request)


    @ndb.transactional()
    def _updateConferenceObject(self, request):
        """Updates Conference Object
        """

        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException(
                'Authorization required')
        user_id = getUserId(user)

        # Copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) \
            for field in request.all_fields()}

        # Update existing conference
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()

        # Check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' \
                    % request.websafeConferenceKey)

        # Check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # Copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, 
            getattr(prof, 'displayName'))


    @endpoints.method(
        CONF_POST_REQUEST, 
        ConferenceForm, 
        path='conference/{websafeConferenceKey}', 
        http_method='PUT', 
        name='updateConference'
        )
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info.
        """

        return self._updateConferenceObject(request)


    @endpoints.method(
        QueryForms, 
        ConferenceForms, 
        path='queryConferences', 
        http_method='POST', 
        name='queryConferences'
        )
    def queryConferences(self, request):
        """Query for conferences.
        """

        conferences = self._getQuery(request)

         # Return individual ConferenceForm object per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") \
                for conf in conferences])


    @endpoints.method(
        CONF_GET_REQUEST, 
        ConferenceForm, 
        path='conference/{websafeConferenceKey}', 
        http_method='GET', 
        name='getConference'
        )
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey).
        """

        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: \
                    %s' % request.websafeConferenceKey)
        prof = conf.key.parent().get()

        # return ConferenceForm
        return self._copyConferenceToForm(
            conf, getattr(prof, 'displayName'))


    @endpoints.method(
        message_types.VoidMessage, 
        ConferenceForms, 
        path='getConferencesCreated', 
        http_method='POST', 
        name='getConferencesCreated'
        )
    def getConferencesCreated(self, request):
        """Return only conferences created by user.
        """

        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException(
                'Authorization required')
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)    
        conferences = Conference.query(ancestor=ndb.Key(Profile, user_id))
        prof = p_key.get()
        displayName = getattr(prof, 'displayName')

         # return individual ConferenceForm object per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, displayName) \
                for conf in conferences])


    @endpoints.method(
        message_types.VoidMessage, 
        ConferenceForms, 
        path='conferences/attending', 
        http_method='GET', 
        name='getConferencesToAttend'
        )
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for.
        """

        # get user Profile
        profile = self._getProfileFromUser() 

        # create websafe key
        conf_keys = [ndb.Key(urlsafe=wsck) \
            for wsck in profile.conferenceKeysToAttend]

        # get multiple conference keys
        conferences = ndb.get_multi(conf_keys)

        # get organizers
        organisers = [ndb.Key(Profile, conf.organizerUserId) \
            for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for prof in profiles:
            names[prof.key.id()] = prof.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(
                conf, names[conf.organizerUserId]) \
                for conf in conferences])


# - - - Sessions - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 


    def _getSessionQuery(self, request):
        """Return formatted query from the submitted filters.
        """

        q = Session.query()
        inequality_filter, filters = self._formatSessionFilters(
            request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Session.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Session.name)

        for filtr in filters:
            if filtr["field"] in ["durationInMinutes"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(
                filtr["field"], 
                filtr["operator"], 
                filtr["value"])
            q = q.filter(formatted_query)
        return q


    def _formatSessionFilters(self, filters):
        """Parse, check validity and format user supplied filters.
        """

        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name) \
                for field in f.all_fields()}

            try:
                filtr["field"] = SFIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException(
                    "Filter contains invalid field or operator.")
                
            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used 
                # in previous filters disallow the filter if 
                # inequality was performed on a different field 
                # before track the field on which the inequality 
                # operation is performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException(
                        "Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)


    @endpoints.method(
        QueryForms, 
        SessionForms, 
        path='querySessions', 
        http_method='POST', 
        name='querySessions'
        )
    def querySessions(self, request):
        """Query for sessions.
        """

        sessions = self._getSessionQuery(request)

         # return individual SessionsForm object per session
        return SessionForms(
            items=[self._copySessionToForm(sess) \
                for sess in sessions])


    def _copySessionToForm(self, sess):
        """Copy relevant fields from Session to SessionForm.
        """

        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(sess, field.name):

                # Convert date and startTime to string
                if field.name == ('date', 'startTime'):
                    setattr(sf, field.name, str(getattr(sess, field.name)))

                # Copy other fields
                else:
                    setattr(sf, field.name, getattr(sess, field.name))
            elif field.name == "websafeKey":
                setattr(sf, field.name, sess.key.urlsafe())
        sf.check_initialized()
        return sf


    def _createSessionObject(self, request):
        """Create or update Session object, returning SessionForm/request."""

        # Fetch current user
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException(
                'Authorization required')
        user_id = getUserId(user)

        # test for Session name in request
        if not request.name:
            raise endpoints.BadRequestException(
                "Session 'name' field required")

        # Test for websafeConferenceKey in request
        if not request.websafeConferenceKey:
            raise endpoints.BadRequestException(
                "Session 'websafeConferenceKey' field required")

        # copy SessionForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) \
            for field in request.all_fields()}

        # Fetch conference from request
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()

        # Check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: \
                %s' % request.websafeConferenceKey)

        # Check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can add sessions.')

        # Convert dates from strings to Date objects
        if data['date']:
            data['date'] = datetime.strptime(
                data['date'][:10], "%Y-%m-%d").date()

        # convert time from strings to Time object
        if data['startTime']:
            data['startTime'] = datetime.strptime(
                data['startTime'][:5], "%H:%M").time()

        # Add speaker to memcache
        speaker =data['speaker']
        websafeConferenceKey =data['websafeConferenceKey']
        taskqueue.add(
            params={
            "speaker": speaker,
            "websafeConferenceKey": websafeConferenceKey}, 
            url="/tasks/set_featured_speaker")


        # Make Session Key from Conference ID as p_key
        p_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        
        # Allocate new Session ID with p_key as parent
        s_id = Session.allocate_ids(size=1, parent=p_key)[0]

        # Make Session key from ID uses p_key 
        # to define parent and s_id as unique id
        s_key = ndb.Key(Session, s_id, parent=p_key)
        data['key'] = s_key
        del data['websafeConferenceKey']

        # Create Session
        Session(**data).put()

        # Send email to organizer confirming creation of Session
        taskqueue.add(
            params={
            'email': user.email(), 
            'sessionInfo': repr(request)}, 
            url='/tasks/send_confirmation_email2')

        # Return request
        return request


    @endpoints.method(
        SessionForm, 
        SessionForm, 
        path='session', 
        http_method='POST', 
        name='createSession'
        )
    def createSession(self, request): 
        """Create new session. Only available for conference organizer
        """

        return self._createSessionObject(request)


    @endpoints.method(
        SESS_GET_REQUEST, 
        SessionForms, 
        path='conference/{websafeConferenceKey}/sessions', 
        http_method='GET', 
        name='getConferenceSessions'
        )
    def getConferenceSessions(self, request): 
        """Return requested conference sessions (by websafeConferenceKey).
        """

        # Fetch websafeConferenceKey from request 
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()

        # Check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: \
                    %s' % request.websafeConferenceKey)

        # Perform ancestor query
        s = Session.query(ancestor=ndb.Key(
            urlsafe=request.websafeConferenceKey))

        # Return set of SessionForm objects per ancestor
        return SessionForms(items=[self._copySessionToForm(sess) \
            for sess in s])


    @endpoints.method(
        SessionForm, 
        SessionForms, 
        path='typeOfSession', 
        http_method='GET', 
        name='getConferenceSessionsByType'
        )
    def getConferenceSessionsByType(self, request): 
        """Returns sessions by typeOfSession, across all conferences.
        """

        # Perform the ancestor query.
        s = Session.query(ancestor=ndb.Key(
            urlsafe=request.websafeConferenceKey))

        # Perform the query for all key matches for typeOfSession.
        s = s.filter(
            Session.typeOfSession == request.typeOfSession)

        # Return set of SessionForm objects per typeOfSession
        return SessionForms(items=[self._copySessionToForm(sess) \
            for sess in s])


    @endpoints.method(
        SessionForm, 
        SessionForms, 
        path='speaker', 
        http_method='GET', 
        name='getSessionsBySpeaker'
        )
    def getSessionsBySpeaker(self, request): 
        """Returns sessions by speaker, across all conferences.
        """

        # Perform the query for all key matches for speaker
        s = Session.query()
        s = s.filter(Session.speaker == request.speaker)

        # Return set of SessionForm objects per speaker
        return SessionForms(items=[self._copySessionToForm(sess) \
            for sess in s])


    @endpoints.method(
        SessionForm, 
        SessionForms, 
        path='location', 
        http_method='GET', 
        name='getSessionsByLocation'
        )
    def getSessionsByLocation(self, request): 
        """Returns sessions by location, across all conferences.
        """

        # Perform the query for all key matches for location
        s = Session.query()
        s = s.filter(Session.location == request.location)

        # Return set of SessionForm objects per location
        return SessionForms(items=[self._copySessionToForm(sess) \
            for sess in s])


    @endpoints.method(
        SessionForm, 
        SessionForms, 
        path='datelocationbytime', 
        http_method='GET', 
        name='getSessionsByDateLocationSortByTime'
        )
    def getSessionsByDateLocationSortByTime(self, request): 
        """Returns sessions by date and location, across all conferences,
        orders the results by time.
        """

        # Fetch session data by copying SessionForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) \
            for field in request.all_fields()}
        location = data['location']
        date = data['date']
        startTime = data['startTime']
        if data['date']:
            udate = data['date']
            date = datetime.strptime(udate, '%Y-%m-%d')

        # Perform the query for all key matches for location
        s = Session.query()
        s = s.filter(Session.location == location)

        # Add date and start time filter if included in query        
        if data['date']:
            s = s.filter(Session.date == date)

        # Order by date then start time
        s = s.order(Session.date)
        s = s.order(Session.startTime)

        # Return set of SessionForm objects
        return SessionForms(
            items=[self._copySessionToForm(sess) \
                for sess in s])


    @endpoints.method(
        message_types.VoidMessage, 
        SessionForms, 
        path='specialrequest', 
        http_method='GET', 
        name='getAllNonWorkshopsBefore7PM'
        )
    def getAllNonWorkshopsBefore7PM(self, request): 
        """Returns all non-workshop sessions before 7 pm, 
        across all conferences.
        """

        # Define the time as a time object from the Datetime module (As dt)
        t = dt.time(19,0,0)

        # Perform the query for all key matches for typeOfSession
        s = Session.query()

        # Filter by typeOfSession by calling the TypeOfSession class 
        # and appying an equality filter
        s = s.filter(ndb.OR(
            Session.typeOfSession == TypeOfSession.Keynote,
            Session.typeOfSession == TypeOfSession.Lecture))
        s = s.filter(Session.startTime < t)
        s = s.order(Session.startTime)

        # Return set of SessionForm objects per typeOfSession
        return SessionForms(
            items=[self._copySessionToForm(sess) \
                for sess in s])


# - - - Wishlist - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 


    @ndb.transactional(xg=True)
    def _sessionWishlist(self, request, addTo=True):
        """Add or remove session from users wishlist.
        """

        retval = None

        # Fetch user profile
        prof = self._getProfileFromUser()

        # Fetch session from websafeSessionKey and check if exists
        wsck = request.websafeSessionKey
        sess = ndb.Key(urlsafe=wsck).get()
        if not sess:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % wsck)

        # Check if session is already in wishlist otherwise add
        if addTo:
            if wsck in prof.wishlistSessionKeys:
                raise ConflictException(
                    "You have already added this session to your wishlist")
            prof.wishlistSessionKeys.append(wsck)
            retval = True

        # Check if session is in wishlist then remove
        else:
            if wsck in prof.wishlistSessionKeys:
                prof.wishlistSessionKeys.remove(wsck)
                retval = True
            else:
                retval = False

        # Put back in datastore and return
        prof.put()
        return BooleanMessage(data=retval)


    @endpoints.method(
        WISHLIST_POST_REQUEST, 
        BooleanMessage, 
        path='session/{websafeSessionKey}/wishlist', 
        http_method='POST', 
        name='addSessionToWishlist'
        )
    def addSessionToWishlist(self, request):
        """Add websafeSessionKey to users profile.
        """

        return self._sessionWishlist(request)


    @endpoints.method(
        WISHLIST_DEL_REQUEST, 
        BooleanMessage, 
        path='session/{websafeSessionKey}/wishlist', 
        http_method='DELETE', 
        name='deleteSessionInWishlist'
        )
    def deleteSessionInWishlist(self, request):
        """Remove websafeSessionKey from users profile.
        """

        return self._sessionWishlist(request, addTo=False)


    @endpoints.method(
        message_types.VoidMessage, 
        SessionForms, 
        path='profile/wishlist', 
        http_method='GET', 
        name='getSessionsInWishlist'
        )
    def getSessionsInWishlist(self, request):
        """ Given a user, returns all sessions in wishlist.
        """

        # Fetch user Profile
        prof = self._getProfileFromUser() 

        # Get wishlistSessionKeys from Profile all at once
        sk = [ndb.Key(urlsafe=wssk) \
            for wssk in prof.wishlistSessionKeys]
        wishList = ndb.get_multi(sk)

        # return set of SessionForm objects per Session found in wishList
        return SessionForms(items=[self._copySessionToForm(sess) \
            for sess in wishList]
        )


# - - - Registration - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 


    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference.
        """

        retval = None

        # Fetch user profile
        prof = self._getProfileFromUser() 

        # Fetch conference from websafeConferenceKey and check if exists 
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)


    @endpoints.method(
        CONF_GET_REQUEST, 
        BooleanMessage, 
        path='conference/{websafeConferenceKey}', 
        http_method='POST', 
        name='registerForConference'
        )
    def registerForConference(self, request):
        """Register user for selected conference.
        """

        return self._conferenceRegistration(request)


    @endpoints.method(
        CONF_GET_REQUEST, 
        BooleanMessage, 
        path='conference/{websafeConferenceKey}', 
        http_method='DELETE', 
        name='unregisterFromConference'
        )
    def unregisterFromConference(self, request):
        """Unregister user for selected conference.
        """

        return self._conferenceRegistration(request, reg=False)


# - - - Announcements - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """

        confs = Conference.query(
            ndb.AND(
                Conference.seatsAvailable <= 5, 
                Conference.seatsAvailable > 0)) \
                .fetch(projection=[Conference.name])
        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = '%s %s' % (
                'Last chance to attend! The following conferences \
                are nearly sold out:',', '.join(conf.name \
                    for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)
        return announcement


    @endpoints.method(
        message_types.VoidMessage, 
        StringMessage, 
        path='conference/announcement/get', 
        http_method='GET', 
        name='getAnnouncement'
        )
    def getAnnouncement(self, request):
        """Return Announcement from memcache.
        """

        announcement = memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY)
        if not announcement:
            announcement = ""
        return StringMessage(data=announcement)


# - - - Featured Speaker - - - - - - - - - - - - - - - - - - - - - - - - - - - 


    @endpoints.method(
        message_types.VoidMessage, 
        StringMessage, 
        path='getFeaturedSpeaker', 
        http_method='POST', 
        name='getFeaturedSpeaker'
        )
    def getFeaturedSpeaker(self, request):
        """Fetches featured speaker with sessions from memcache.
        """
        return StringMessage(data=memcache.get(MEMCACHE_SPEAKER_KEY) or '')


# - - - Method for testing filters - - - - - - - - - - - - - - - - - - - - - - 


    @endpoints.method(
        message_types.VoidMessage, 
        ConferenceForms, 
        path='filterTester', 
        http_method='POST', 
        name='filterTester'
        )
    def filterTester(self, request):
        """Playground for testing queries.
        """

        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException(
                'Authorization required')
        p_key = ndb.Key(Profile, getUserId(user))    

        field = "city"
        operator = "<="
        value = "Paris"
        filters = ndb.query.FilterNode(field, operator, value)

        q = Conference.query()
        conferences = q.filter(filters)
        conferences = q.order(Conference.name)
        conferences = q.filter(Conference.month == 6)

        prof = p_key.get()
        displayName = getattr(prof, 'displayName')

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") \
                for conf in conferences])


# registers API
api = endpoints.api_server([QuizerApi]) 

