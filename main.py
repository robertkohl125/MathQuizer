import webapp2
from google.appengine.api import app_identity
from google.appengine.api import mail
from conference import ConferenceApi
from models import Session
from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

MEMCACHE_SPEAKER_KEY = "FEATURED_SPEAKER"


class SetAnnouncementHandler(webapp2.RequestHandler):
    def get(self):
        """Set Announcement in Memcache.
        """
        ConferenceApi._cacheAnnouncement()


class SendConfirmationEmailHandler(webapp2.RequestHandler):
    def post(self):
        """Send email confirming Conference creation.
        """
        mail.send_mail(
            'noreply@%s.appspotmail.com' % (
                app_identity.get_application_id()),     # from
            self.request.get('email'),                  # to
            'You created a new Conference!',            # subj
            'Hi, you have created a following '         # body
            'conference:\r\n\r\n%s' % self.request.get(
                'conferenceInfo')
            )


class SendConfirmationEmailHandler2(webapp2.RequestHandler):
    def post(self):
        """Send email confirming Session creation.
        """
        mail.send_mail(
            'noreply@%s.appspotmail.com' % (
                app_identity.get_application_id()),     # from
            self.request.get('email'),                  # to
            'You created a new Session!',               # subj
            'Hi, you have created a following '         # body
            'session:\r\n\r\n%s' % self.request.get(
                'sessionInfo')
            )

class SetFeaturedSpeakerHandler(webapp2.RequestHandler):
    def post(self):
        """Check if the specified speaker has multiple sessions, 
        then cache them in Memcache as the featured speaker.
        """
        websafeConferenceKey = self.request.get('websafeConferenceKey')
        speaker = self.request.get('speaker')

        # Get all sessions with this speaker listed.
        s = Session.query(ancestor=ndb.Key(
            urlsafe=websafeConferenceKey))
        speakerSessions = s.filter(
            Session.speaker == speaker)

        # Use a for loop to gather only the names
        speakerSessionNames = [
            sess.name for sess in speakerSessions]

        # If there is more than one session for this speaker, join them all
        # back together with the speaker name and put it in memcache
        if len(speakerSessionNames) > 1:
            cache_string = speaker + ': ' + ', '.join(speakerSessionNames)
            memcache.set(MEMCACHE_SPEAKER_KEY, cache_string)


app = webapp2.WSGIApplication([
	('/crons/set_announcement', SetAnnouncementHandler),
    ('/tasks/send_confirmation_email', SendConfirmationEmailHandler),
    ('/tasks/send_confirmation_email2', SendConfirmationEmailHandler2),
    ('/tasks/set_featured_speaker', SetFeaturedSpeakerHandler)
    ], debug=True)
